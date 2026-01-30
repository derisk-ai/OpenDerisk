import json
import logging
from typing import Optional

from derisk.agent import Action, Resource
from derisk.agent.core.action.base import ToolCall
from derisk.agent.core.reasoning.reasoning_action import KnowledgeRetrieveAction, \
    KnowledgeRetrieveActionInput
from derisk.agent.resource import ToolParameter, FunctionTool

logger = logging.getLogger(__name__)
class KnowledgeSearch(KnowledgeRetrieveAction, FunctionTool):
    """Knowledge Search action.

    内部知识库交互接口。用于在当前提供的知识中进行知识检索。
    """
    name = "knowledge_search"

    @classmethod
    def get_action_description(cls) -> str:
        return ("内部知识库交互接口。用于在当前提供的知识中进行知识检索。"
                "**注意事项**:* 注意使用合适的检索模式 'func' 和正确的检索范围 'knowledge_ids'、'doc_uuids'。"
                "**防御性原则**：必须在提供了知识范围的情况下使用。")

    @property
    def description(self):
        return self.get_action_description()

    @property
    def args(self):
        return {
            "query": ToolParameter(
                type="string",
                name="query",
                description="要匹配和检索的内容",
                required=True
            ),
            "func": ToolParameter(
                type="string",
                name="func",
                description=(
                    "检索模式,取值范围(search、ls、doc_ls、read), 默认为search。"
                    "search:根据用户问题语义搜索知识库;"
                    "ls:查询整个知识库目录;"
                    "doc_ls:查阅文档目录大纲;"
                    "read:按需读取文档内容(阅读ls返回目录中的一个文档)"
                ),
                required=False,
                default="search"
            ),
            "knowledge_ids": ToolParameter(
                type="array",
                name="knowledge_ids",
                description='需要检索相关知识库id列表,["id1","id2"], 如果都不涉及返回[]',
                required=False
            ),
            "doc_uuids": ToolParameter(
                type="array",
                name="doc_uuids",
                description=(
                    "需要检索相关文档uuid列表, ['uuid1','uuid2'], 如果都不涉及返回[];"
                    "如果func是doc_ls和read, 则doc_uuids为最相关的文档uuid列表；"
                    "如果func是search和ls, 则doc_uuids=[]"
                ),
                required=False
            ),
            "header": ToolParameter(
                type="string",
                name="header",
                description=(
                    "具体文档大纲标题, 如果func是read, 则header为最相关的文档大纲标题；"
                    "如果func是search和ls, 则header=''"
                ),
                required=False
            ),
        }

    def execute(self, *args, **kwargs):
        if "output" in kwargs:
            return kwargs["output"]
        if "final_answer" in kwargs:
            return kwargs["final_answer"]
        return args[0] if args else "knowledge search completed"

    async def async_execute(self, *args, **kwargs):
        return self.execute(*args, **kwargs)

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional["Action"] = None,
        resource: Optional[Resource] = None,
        **kwargs,
    ) -> Optional["Action"]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """

        if tool_call.name == cls.name:
            if not tool_call.args:
                if not tool_call.args.get("query"):
                    raise ValueError("没有需要检索的目标信息！")
            temp_knowledge_ids = tool_call.args.get("knowledge_ids")
            temp_doc_uuids = tool_call.args.get("doc_uuids")
            knowledge_ids = []
            doc_uuids = []
            try:
                knowledge_ids = json.loads(temp_knowledge_ids) if isinstance(temp_knowledge_ids,
                                                                             str) else temp_knowledge_ids
                doc_uuids = json.loads(temp_doc_uuids) if isinstance(temp_doc_uuids, str) else temp_doc_uuids

            except Exception as e:
                logger.exception("Knowledge search input parse failed！")

            return cls(action_uid=tool_call.tool_call_id,
                       action_input=KnowledgeRetrieveActionInput(query=tool_call.args.get("query"),
                                                                 func=tool_call.args.get("func"),
                                                                 knowledge_ids=knowledge_ids,
                                                                 doc_uuids=doc_uuids,
                                                                 header=tool_call.args.get("header"),
                                                                 intention=tool_call.args.get("intention"),
                                                                 thought=tool_call.args.get("thought")
                                                                 ))


        else:
            return None
