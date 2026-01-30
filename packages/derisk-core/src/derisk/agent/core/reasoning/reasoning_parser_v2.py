import json
import logging
import re
from abc import ABC
from typing import Tuple, Optional, Union, List, Type, Any

from derisk.agent import Resource, AgentResource
from derisk.agent.core.reasoning.reasoning_action import (
    Action,
    AgentAction,
    AgentActionInput,
    ActionOutput,
    KnowledgeRetrieveAction,
    KnowledgeRetrieveActionInput,
    ConversableAgent,
)
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningModelOutput,
    ReasoningPlan,
)
from derisk.agent.expand.actions.tool_action import ToolInput
from derisk.agent.resource import FunctionTool, BaseTool, ToolPack, ResourcePack
from derisk.agent.resource.app import AppResource
from derisk.agent.resource.workflow import WorkflowResource
from derisk.agent.util.llm.llm_client import AgentLLMOut
from derisk.core.workflow.workflow_action import WorkflowAction, WorkflowActionInput
from derisk.util.string_utils import is_number
from derisk_ext.agent.actions.ant_tool_action import AntToolAction
from derisk_serve.agent.resource.knowledge_pack import KnowledgePackSearchResource

logger = logging.getLogger("reasoning")

AGENT_ACTION_FUNC_NAME = "agent_action"
KNOWLEDGE_ACTION_FUNC_NAME = "knowledge_action"
WORKFLOW_ACTION_FUNC_NAME = "workflow_action"


def is_str_list(origin) -> bool:
    return isinstance(origin, list) and not any(item for item in origin if not isinstance(item, str))


class FunctionCallParser(ABC):

    def __init__(self):
        self._functions: List[str] = []

    @property
    def action_typ(self) -> Type[Action]:
        raise NotImplementedError

    @property
    def resource_type(self) -> Type[Resource]:
        raise NotImplementedError

    @property
    def func_prefix(self) -> Optional[str]:
        return None

    @property
    def functions(self) -> List[str]:
        return self._functions

    def unpack_ability_resource(self, resource: Resource) -> list[Resource]:
        from derisk_ext.agent.agents.reasoning.utils import ABILITY_RESOURCE_TYPES
        if not resource:
            return []
        elif isinstance(resource, ResourcePack) and resource.sub_resources:
            result = []
            for r in resource.sub_resources:
                if r.type() in ABILITY_RESOURCE_TYPES:
                    result.append(r)
                elif isinstance(r, ResourcePack):
                    result.extend(self.unpack_ability_resource(r))
            return result
        elif resource.type() in ABILITY_RESOURCE_TYPES:
            return [resource]
        return []

    async def item_to_function(self, sub_resource: Resource):
        pass

    async def resources_to_functions(self, all_resources: Resource) -> Optional[List[dict]]:
        resource_cls = self.resource_type
        resources = resource_cls.from_resource(all_resources)
        if not resources:
            return None

        functions: List = []
        for item in resources:
            if item.is_pack:
                sub_resources = self.unpack_ability_resource(resources[0])
                for sub_item in sub_resources:
                    functions.append({
                        "type": "function",
                        "function": await self.item_to_function(sub_item)
                    })
            else:
                functions.append({
                    "type": "function",
                    "function": await self.item_to_function(item)
                })
        return functions

    def build_action_input(self, func_name: str, args: Optional[dict], thought: Optional[str] = None) -> Any:
        pass

    def functions_to_action(self, function_call_param: dict, thought: Optional[str] = None) -> Action:
        function_name: str = function_call_param['function'].get("name")
        if self.func_prefix:
            function_name = function_name.replace(self.func_prefix, "")

        tool_call_id = function_call_param['id']
        # 参数解析
        func_args = function_call_param['function'].get("arguments")
        args = {}
        if func_args:
            args = json.loads(func_args) if isinstance(func_args, str) else func_args
        action_cls = self.action_typ

        action_input = self.build_action_input(
            func_name=function_name,
            thought=thought,
            args=args,
        )

        action = action_cls(action_uid=tool_call_id)
        action.action_input = action_input

        return action


class ToolFunctionCallParser(FunctionCallParser):

    @property
    def action_typ(self) -> Type[Action]:
        return AntToolAction

    @property
    def resource_type(self) -> Type[Resource]:
        return ToolPack

    async def item_to_function(self, resource: Resource):
        tool_item: BaseTool = resource
        properties = {}
        required_list = []
        for key, value in tool_item.args.items():
            properties[key] = {
                "type": value.type,
                "description": value.description,
            }
            if value.required:
                required_list.append(key)
        parameters_dict = {
            "type": "object",
            "properties": properties,
            "required": required_list,
        }

        function = {}
        function['name'] = tool_item.name
        function['description'] = tool_item.description
        function['parameters'] = parameters_dict
        self.functions.append(tool_item.name)
        return function

    def build_action_input(self, func_name: str, args: Optional[dict], thought: Optional[str] = None) -> Any:
        return ToolInput(
            tool_name=func_name,
            args=args,
            thought=thought,
        )


class AgentFunctionCallParser(FunctionCallParser):

    @property
    def action_typ(self) -> Type[Action]:
        return AgentAction

    @property
    def resource_type(self) -> Type[Resource]:
        return AppResource

    @property
    def func_prefix(self) -> Optional[str]:
        return "agent_"

    async def item_to_function(self, resource: Resource):
        agent_resource: AppResource = resource
        properties = {}
        required_list = ['query']

        properties['query'] = {
            "type": 'string',
            "description": "给当前智能助手代理工具的输入问题(必需生成且是明确的完整指令内容)",
        }

        parameters_dict = {
            "type": "object",
            "properties": properties,
            "required": required_list,
        }

        function = {}
        agent_func_name = f'{self.func_prefix}{agent_resource.app_name}'
        function['name'] = agent_func_name
        function['description'] = agent_resource.app_desc or agent_resource.app_name
        function['parameters'] = parameters_dict
        self.functions.append(agent_func_name)
        return function

    def build_action_input(self, func_name: str, args: Optional[dict], thought: Optional[str] = None) -> Any:
        return AgentActionInput(
            agent_name=func_name,
            thought=thought,
            content=args.get("query") or thought,
        )


class KnowledgeFunctionCallParser(FunctionCallParser):
    @property
    def action_typ(self) -> Type[Action]:
        return KnowledgeRetrieveAction

    @property
    def resource_type(self) -> Type[Resource]:
        return KnowledgePackSearchResource

    async def resources_to_functions(self, all_resources: Resource):
        resource_cls = self.resource_type
        resources: List[Resource] = resource_cls.from_resource(all_resources)
        if not resources:
            return None
        kn_resources: KnowledgePackSearchResource = resources[0]

        functions = []
        properties = {}
        required_list = ['query', 'knowledge_ids']

        properties['query'] = {
            "type": 'string',
            "description": "检索内容",
        }
        properties['knowledge_ids'] = {
            "type": 'Array',
            "description": "需要检索相关知识库id列表,['id1','id2'], 如果都不涉及返回[]",
        }
        properties['func'] = {
            "type": 'string',
            "description": "检索函数名, 默认为search, 如果是语义搜索知识,search；"
                           "如果是读取文档大纲，func为doc_ls；"
                           "如果是查询整个知识库目录, func为ls",
        }
        properties['doc_uuids'] = {
            "type": 'string',
            "description": "需要检索相关文档uuid列表, ['uuid1','uuid2'], 如果都不涉及返回[]; "
                           "如果func是doc_ls和read, 则doc_uuids为最相关的文档uuid列表；"
                           "如果func是search和ls, 则doc_uuids=[]",
        }
        properties['header'] = {
            "type": 'string',
            "description": "具体文档大纲标题, 如果func是read, 则header为最相关的文档大纲标题；"
                           "如果func是search和ls, 则header=''",
        }
        parameters_dict = {
            "type": "object",
            "properties": properties,
            "required": required_list,
        }

        knowledge_func_name = "knowledge_retrive"
        function = {}
        function['name'] = knowledge_func_name
        function['description'] = kn_resources.description
        function['parameters'] = parameters_dict
        self.functions.append(knowledge_func_name)
        functions.append({
            "type": "function",
            "function": function
        })
        return functions

    def build_action_input(self, func_name: str, args: Optional[dict], thought: Optional[str] = None) -> Any:
        return KnowledgeRetrieveActionInput(
            **args
        )


class WorkflowFunctionCallParser(FunctionCallParser):
    @property
    def action_typ(self) -> Type[Action]:
        return WorkflowAction

    @property
    def func_prefix(self) -> Optional[str]:
        return "workflow_"

    @property
    def resource_type(self) -> Type[Resource]:
        return WorkflowResource

    async def item_to_function(self, resource: Resource):
        workflow_re: WorkflowResource = resource

        properties = {}
        required_list = ['query']

        properties['query'] = {
            "type": 'string',
            "description": "给当前Workflow的提问或者指令输入",
        }

        parameters_dict = {
            "type": "object",
            "properties": properties,
            "required": required_list,
        }

        function = {}
        workflow_func_name = f'{self.func_prefix}{workflow_re.id}'
        function['name'] = workflow_func_name
        function['description'] = workflow_re.description
        function['parameters'] = parameters_dict
        self.functions.append(workflow_func_name)
        return function

    def build_action_input(self, func_name: str, args: Optional[dict], thought: Optional[str] = None) -> Any:
        return WorkflowActionInput(
            name=func_name,
            thought=thought,
            **args,
        )


def format_actions(
    agent_llm_out, function_call_parsers: List[FunctionCallParser]
) -> Optional[list[Action]]:
    if not agent_llm_out.tool_calls or not function_call_parsers:
        return None
    result_actions = []

    for item in agent_llm_out.tool_calls:
        func_name = item['function']['name']

        function_call_parser: Optional[FunctionCallParser] = None
        for call_parser in function_call_parsers:
            if func_name in call_parser.functions:
                function_call_parser = call_parser

        if not function_call_parser:
            logger.warning("当前函数不在函数定义列表中！")
            continue
        action = function_call_parser.functions_to_action(item, agent_llm_out.content)

        action.intention = agent_llm_out.content
        action.reason = agent_llm_out.content
        result_actions.append(action)

    return result_actions


def parse_actions(
    agent_llm_out: AgentLLMOut, function_call_parsers: List[FunctionCallParser]
) -> Tuple[ReasoningModelOutput, bool, str, Optional[list[Action]]]:
    status: str = 'planing'
    if not agent_llm_out.tool_calls:
        status: str = 'done'

    result = ReasoningModelOutput(status=status, reason=agent_llm_out.content)

    done = True if result.status in ["done", "abort"] else False
    answer = result.answer or result.summary or (result.reason if done else None)
    actions = format_actions(agent_llm_out, function_call_parsers)

    return result, done, answer, actions


def parse_action_reports(text: str) -> list[ActionOutput]:
    def _parse_sub_action_reports(
        content: str, action_report_list: list[ActionOutput]
    ) -> bool:
        """
        递归解析sub_action_report
        :param content:
        :param action_report_list:
        :return: 是否有sub_action_report
        """
        try:
            sub_action_report_dicts_list = json.loads(content) if content else []
            sub_action_report_list = (
                [
                    ActionOutput.from_dict(sub_dict)
                    for sub_dict in sub_action_report_dicts_list
                ]
                if isinstance(sub_action_report_dicts_list, list)
                else []
            )
        except Exception as e:
            return False
        if not sub_action_report_list:
            return False

        sub = False
        for sub_action_report in sub_action_report_list:
            try:
                sub = sub or _parse_sub_action_reports(
                    sub_action_report.content, action_report_list
                )
            except Exception as e:
                pass
        if not sub:
            action_report_list.extend(sub_action_report_list)
        return True

    try:
        if not text:
            return []
        # 先解析最外层的action_report
        action_report_dict = json.loads(text)
        action_report = ActionOutput.from_dict(action_report_dict)
    except Exception as e:
        return []

    result: list[ActionOutput] = []
    if _parse_sub_action_reports(action_report.content, result):
        return result
    return [action_report]


def parse_action_id(id: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    从原始id中解析出task_id、step_id、action_id
    * 若输入的是task_id，则输出的step_id、action_id都为None
    * 若输入的是step_d，则输出只有task_id、step_id，而action_id为None
    * 若输入的是action_id，则输出的task_id、step_id、action_id都不为None
    * 若输入的是非法数据，则输出三个None
    :param id: 原始id 可能是task_id/step_id/action_id
    :return: 解析出的task_id、step_id、action_id
    """
    if is_number(id):
        # 输入的是task_id
        return id, None, None

    # 找到最后一个- 用于切割出task_id
    idx1 = id.rfind("-")
    if idx1 <= 0 or idx1 >= len(id):
        return None, None, None

    task_id = id[:idx1]  # todo: 待校验task_id合法性
    step_part = id[idx1 + 1:]
    if re.match("^\w+$", step_part):  # 不含.-等step_id、action_id分隔符
        # `task_id-`后面跟的是数字 说明id是step_id
        return task_id, id, None

    sps = step_part.split(".")
    if not len(sps) == 2 or not is_number(sps[0]):
        return None, None, None

    return task_id, id[: idx1 + 1 + len(sps[0])], id


def compare_action_id(left: str, right: str) -> int:
    l: list[str] = re.split("[.-]", left)
    r: list[str] = re.split("[.-]", right)
    for i in range(len(l)):
        if len(r) <= i:
            # 短的 说明是上游 排在前面
            break

        if l[i] == r[i]:
            continue

        # 走到这里两者必然不相等

        nl: bool = is_number(l[i])
        nr: bool = is_number(r[i])

        if nl and nr:
            # 都是数字 小的排前面
            return 1 if int(l[i]) > int(r[i]) else -1
        elif (not nl) and (not nr):
            # 都不是数字 按照字符串排序
            return 1 if l[i] > r[i] else -1
        else:
            # 数字排前面 字符串排最后
            return 1 if is_number(r[i]) else -1
    # 前面一截字符串都相同 短的排前面
    return 1 if len(l) > len(r) else -1
