import json
import logging
import uuid
from typing import Dict, List, Optional

from derisk._private.pydantic import Field
from .actions.tool_action import ToolAction
from .parsers.rag_parser import RagAgentParaser, AgenticRAGState
from .. import Action, BlankAction
from ..core.base_agent import (
    ActionOutput,
    Agent,
    AgentMessage,
    ConversableAgent,
    ProfileConfig,
)
from derisk.agent.core.role import AgentRunMode
from derisk.agent.resource import ResourcePack, ToolPack, FunctionTool
from derisk.util.configure import DynConfig

from ..core.base_parser import AgentParser

from ..core.memory.gpts import GptsPlan
from ..core.reasoning.reasoning_action import KnowledgeRetrieveAction
from ..core.schema import Status
from ...util.tracer import root_tracer

logger = logging.getLogger(__name__)

_RAG_GOAL = """Answer the following questions or solve the tasks by \
selecting the right search tools. 
"""
_AGENTIC_RAG_SYSTEM_TEMPLATE = """
你是一个答疑智能助手。
## 目标
你的任务是根据用户的问题或任务，选择合适的知识库或者工具来回答问题或解决问题。
## 历史记忆
{{most_recent_memories}}

## 可用工具
可用知识和工具: {{resource_prompt}}

## 流程
1. 根据用户问题选择可用的知识或者工具。

## 回复格式
严格按以下JSON格式输出，确保可直接解析：
{
  "tools": [{
    "tool": "工具的名称,可以是知识检索工具或搜索工具。",
    "args": {
      "arg_name1": "arg_value1",
      "arg_name2": "arg_value2"
    }
  }],
  "knowledge": ["knowledge_id1", "knowledge_id2"],
  "intention": "本次的意图,一个简短的描述",
}

注意:如果<可用工具>中没有可用的知识或工具，请返回空的"tools"和"knowledge"字段。
## 用户问题
{{ question }}

当前时间是: {{ now_time }}。
"""

_AGENTIC_RAG_USER_TEMPLATE = """"""
_FINIAL_SUMMARY_TEMPLATE = """
您是一个总结专家,您的目标是根据找到的知识或历史对话记忆回答用户问题
## 已有知识和历史对话记忆
{{most_recent_memories}}
进行归纳总结，专业且有逻辑的回答用户问题。 
1.请用中文回答
2. 总结回答时请务必保留原文中的图片、引用、视频等链接内容
3. 原文中的图片、引用、视频等链接格式, 出现在原文内容中，内容后，段落中都可以认为属于原文内容，请确保在总结答案中依然输出这些内容，不要丢弃，不要修改.(参考图片链接格式：![image.png](xxx) 、普通链接格式:[xxx](xxx))
4.优先从给出的资源中总结用户问题答案，如果没有找到相关信息，则尝试从当前会话的历史对话记忆中找相关信息，忽略无关的信息.
5. 回答时总结内容需要结构良好的，中文字数不超过300字，尽可能涵盖上下文里面所有你认为有用的知识点，如果提供的资源信息带有和用户问题相关的图片![image.png](xxx) ，链接[xxx](xxx))或者表格,总结的时候也将图片，链接，表格按照markdown格式进行输出。
6. 注意需要并在每段总结的**中文**末尾结束标点符号前面注明内容来源的链接编号,语雀链接,语雀标题[i](https://yuque_url.com),i 为引用的序号，必须是数字，eg:1,2,3。
7. 输出图片时需要确认是否和用户当前问题相关，如果不相关则不输出图片链接。
8.如果没有找到工具和知识，请你直接回答用户问题。
9. 回答的时候内容按照论文的格式格式输出，组织结构尽量结构良好。
10.输出的时候每一个要点前面可以加图标，eg:✅🔍🧠📊🔗📎.

用户问题:
{{ question }}
"""


class RAGAgent(ConversableAgent):
    max_retry_count: int = 15
    run_mode: AgentRunMode = AgentRunMode.LOOP

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "AgenticRAGAssistant",
            category="agent",
            key="dbgpt_agent_expand_rag_assistant_agent_name",
        ),
        role=DynConfig(
            "AgenticRAGAssistant",
            category="agent",
            key="dbgpt_agent_expand_rag_assistant_agent_role",
        ),
        goal=DynConfig(
            _RAG_GOAL,
            category="agent",
            key="dbgpt_agent_expand_plugin_assistant_agent_goal",
        ),
        system_prompt_template=_AGENTIC_RAG_SYSTEM_TEMPLATE,
        user_prompt_template=_FINIAL_SUMMARY_TEMPLATE,
    )
    state: str = AgenticRAGState.REFLECTION.value
    next_step_prompt: str = profile.system_prompt_template
    refs: List[dict] = None

    # Agent解析器(如果不配置默认走Action解析)
    agent_paraser: Optional[AgentParser] = RagAgentParaser()

    def __init__(self, **kwargs):
        """Init indicator AssistantAgent."""
        super().__init__(**kwargs)
        self.state = AgenticRAGState.REFLECTION.value

    def register_variables(self):
        """子类通过重写此方法注册变量"""
        logger.info(f"rag agent register_variables {self.role}")
        super().register_variables()

        @self._vm.register('out_schema', 'Agent模型输出结构定义')
        def var_out_schema(instance):
            if instance.agent_paraser:
                return instance.agent_paraser.schema()
            else:
                return None

        @self._vm.register('memory', '特定记忆')
        def var_out_schema(instance):
            if instance.agent_paraser:
                return instance.agent_paraser.schema()
            else:
                return None

    async def load_resource(self, question: str, is_retry_chat: bool = False):
        """Load agent bind resource."""
        prompt = ""
        tool_resources = ""
        if self.resource:
            tool_packs = ToolPack.from_resource(self.resource)
            action_space = {}
            if tool_packs:
                prompt = "<tools>\n"
                tool_pack = tool_packs[0]
                for tool in tool_pack.sub_resources:
                    if isinstance(tool, FunctionTool):
                        tool_simple_desc = tool.description
                        action_space[tool.name] = tool
                        parameters_string = await self._parse_tool_args(tool)
                        prompt += (f"<tool>\n"
                                   f"<tool_name>{tool.name}</tool_name>\n"
                                   f"<tool_desc>{tool_simple_desc}</tool_desc>\n"
                                   f"<parameters>{parameters_string}</parameters>\n"
                                   f"</tool>\n")
                    else:
                        tool_simple_desc = tool.get_prompt()
                        prompt += (f"<tool>\n"
                                   f"<tool_name>{tool.name}</tool_name>\n"
                                   f"<tool_desc>{tool_simple_desc}</tool_desc>\n"
                                   f"</tool>\n")

                prompt += "</tools>"
            tool_resources += prompt
            if isinstance(self.resource, ResourcePack):
                for resource in self.resource.sub_resources:
                    from derisk_serve.agent.resource.knowledge_pack import \
                        KnowledgePackSearchResource
                    if isinstance(resource, KnowledgePackSearchResource):
                        tool_resources += "\n<knowledge>\n"
                        tool_resources += resource.description
                        tool_resources += "</knowledge>\n"

        return tool_resources, []

    async def build_prompt(
        self,
        is_system: bool = True,
        most_recent_memories: Optional[str] = None,
        resource_vars: Optional[Dict] = None,
        is_retry_chat: bool = False,
        **kwargs,
    ) -> str:
        """Return the prompt template for the role.

        Returns:
            str: The prompt template.
        """
        if is_system:
            if self.state == AgenticRAGState.FINAL_SUMMARIZE.value:
                return ""
            if self.current_profile.get_system_prompt_template() == "":
                logger.info(f"RAG system prompt template is empty {self.profile.system_prompt_template}")
                self.current_profile.system_prompt_template = _AGENTIC_RAG_SYSTEM_TEMPLATE
            return self.current_profile.format_system_prompt(
                template_env=self.template_env,
                language=self.language,
                resource_vars=resource_vars,
                is_retry_chat=is_retry_chat,
                **kwargs,
            )
        else:
            if self.state == AgenticRAGState.REFLECTION.value:
                return ""
            if self.current_profile.get_user_prompt_template() == "":
                logger.info(f"RAG user prompt template is empty {self.profile.system_prompt_template}")
                self.current_profile.user_prompt_template = _FINIAL_SUMMARY_TEMPLATE
            return self.current_profile.format_user_prompt(
                template_env=self.template_env,
                language=self.language,
                resource_vars=resource_vars,
                **kwargs,
            )

    async def _init_actions_before(self, actions: list[Action]):
        for action in actions:
            action.init_resource(self.resource)
            await action.init_action(
                render_protocol=self.memory.gpts_memory.vis_converter(self.not_null_agent_context.conv_id))

    async def act(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> List[ActionOutput]:
        """Perform actions."""
        logger.info("RAG Agent current state: %s", self.state)
        agent_llm_out = kwargs.get('agent_llm_out')
        actions = self.agent_paraser.parse_actions(agent_llm_out, received_message=received_message,action_cls_list=self.actions, state=self.state)

        await self._init_actions_before(actions)
        have_run_kt = False
        action_outputs: List[ActionOutput] = []
        tool_action_run = False
        knowledge_action_run = False
        for action in actions:
            if not message:
                raise ValueError("The message content is empty!")
            if isinstance(action, ToolAction):
                tool_action_run = True
            if isinstance(action, KnowledgeRetrieveAction):
                knowledge_action_run = True
            with root_tracer.start_span(
                "agent.act.run",
                metadata={
                    "message": message,
                    "sender": sender.name if sender else None,
                    "recipient": self.name,
                    "reviewer": reviewer.name if reviewer else None,
                    "conv_id": self.not_null_agent_context.conv_id,
                    "total_action": len(actions),
                    "app_code": self.agent_context.agent_app_code,
                    "action": action.name,
                },
            ) as span:
                if self.state == AgenticRAGState.FINAL_SUMMARIZE.value:
                    logger.info(f"RAG AGENT run {self.profile.system_prompt_template}")
                action_out = await action.run(
                    ai_message=message.content if message.content else "",
                    resource=self.resource,
                    message_id=message.message_id,
                    render_protocol=await self.memory.gpts_memory.async_vis_converter(
                        self.not_null_agent_context.conv_id),
                    sender=sender,
                    agent=self,
                    received_message=received_message,
                    agent_context=self.agent_context,
                    memory=self.memory,
                )
                action_outputs.append(action_out)
                step_plans = []
                action_plan_map = {}
                plans: List[GptsPlan] = await self.memory.gpts_memory.get_plans(
                    self.not_null_agent_context.conv_id)
                plan_num = 1
                if plans and len(plans) > 0:
                    plan_num = plans[-1].conv_round
                conv_round_id = uuid.uuid4().hex
                task_uid = uuid.uuid4().hex
                if self.state == AgenticRAGState.REFLECTION.value:
                    step_plan: GptsPlan = GptsPlan(
                        conv_id=self.agent_context.conv_id,
                        conv_session_id=self.agent_context.conv_session_id,
                        conv_round=plan_num + 1,
                        conv_round_id=conv_round_id,
                        sub_task_id=task_uid,
                        sub_task_num=0,
                        task_uid=task_uid,
                        sub_task_content=f"{action_out.action}",
                        sub_task_title=f"{action_out.action}",
                        sub_task_agent="",
                        state=Status.COMPLETE.value,
                        action="",
                        task_round_title=f"{action_out.thoughts}",
                        task_round_description=f"{action_out.thoughts}",
                        planning_agent=self.name,
                        planning_model=message.model_name,
                    )
                    step_plans.append(step_plan)
                    action_plan_map[action.action_uid] = step_plan
                    await self.memory.gpts_memory.append_plans(
                        conv_id=self.agent_context.conv_id,
                        plans=[step_plan])

                span.metadata["action_out"] = action_out.to_dict() if action_out else None
                span.metadata["action_name"] = action_out.action_name if action_out else None

        ## 控制一轮执行(只要有工具或者知识action)就进行总结，
        if self.state == AgenticRAGState.REFLECTION.value:
            if not tool_action_run and not knowledge_action_run:
                ## 非总结回合，异常返回不退出循环
                error_act_out = await BlankAction().run(ai_message="No knowledge or tools available for search.",
                                                        message_id=message.message_id, terminate=False)
                action_outputs.append(error_act_out)
            self.state = AgenticRAGState.FINAL_SUMMARIZE.value

        if not action_outputs:
            raise ValueError("Action should return value！")
        return action_outputs

    async def _parse_tool_args(self, tool: FunctionTool) -> str:
        """解析工具参数"""
        properties = {}
        required_list = []

        for key, value in tool.args.items():
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

        return json.dumps(parameters_dict, ensure_ascii=False)
