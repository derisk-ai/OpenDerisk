import json
import logging
from enum import Enum
from typing import Optional, List, Any

from derisk.agent import ActionOutput, AgentResource, Resource, ResourceType, Action
from derisk.vis import Vis
from derisk.vis.schema import StepInfo, VisStepContent
from derisk_serve.rag.api.schemas import KnowledgeSearchResponse
from .tool_action import ToolAction
from ...core.schema import Status
from ...resource import ResourcePack

from derisk._private.pydantic import BaseModel, Field, model_to_dict

logger = logging.getLogger(__name__)


class AgenticRAGState(Enum):
    """Enum for Deep Search Action states."""
    REFLECTION = "reflection"
    FINAL_SUMMARIZE = "final_summarize"


class AgenticRAGModel(BaseModel):
    """Model for AgenticRAG."""
    knowledge: Optional[List[str]] = Field(
        None,
        description="List of knowledge IDs to be used in the action.",
    )
    tools: Optional[List[dict]] = Field(
        None,
        description="List of tools to be used in the action, each tool is a dict with 'tool' and 'args'.",
    )
    intention: Optional[str] = Field(
        None,
        description="Intention of the action, a concise description of the action's goal.",
    )

    def to_dict(self):
        """Convert to dict."""
        return model_to_dict(self)


class AgenticRAGAction(ToolAction):
    """React action class."""

    def __init__(self, **kwargs):
        """Tool action init."""
        # self.state = "split_query"
        super().__init__(**kwargs)

    @property
    def resource_need(self) -> Optional[ResourceType]:
        """Return the resource type needed for the action."""
        return None

    @property
    def ai_out_schema(self) -> Optional[str]:
        """Return the AI output schema."""
        out_put_schema = {
            "tools": [{
                "tool": "工具的名称,可以是知识检索工具或搜索工具。",
                "args": {
                    "arg_name1": "arg_value1",
                    "arg_name2": "arg_value2"
                }
            }],
            "knowledge": ["knowledge_id1", "knowledge_id2"],
            "intention": "意图简洁描述",
        }

        return f"""Please response in the following json format:
        {json.dumps(out_put_schema, indent=2, ensure_ascii=False)}
        Make sure the response is correct json and can be parsed by Python json.loads.
        """

    @classmethod
    def parse_action(
            cls,
            ai_message: str,
            default_action: "AgenticRAG",
            resource: Optional[Resource] = None,
            **kwargs,
    ) -> Optional["AgenticRAG"]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """
        return default_action

    async def run(
            self,
            ai_message: str,
            resource: Optional[AgentResource] = None,
            rely_action_out: Optional[ActionOutput] = None,
            need_vis_render: bool = True,
            current_goal: Optional[str] = None,
            state: Optional[str] = None,
            message_id: Optional[str] = None,
            render_vis_fn: Optional[Any] = None,
            **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        try:
            if state == AgenticRAGState.FINAL_SUMMARIZE.value:
                logger.info(f"Final summarize state reached, "
                            f"returning AI message.{ai_message}")
                return ActionOutput(
                    is_exe_success=True,
                    content=ai_message,
                    view=ai_message,
                    terminate=True,
                    thoughts="生成总结",
                    action=f"总结{current_goal}",
                    observations=ai_message,
                    state=AgenticRAGState.FINAL_SUMMARIZE.value,
                )
            action_param: AgenticRAGModel = self._input_convert(
                ai_message, AgenticRAGModel
            )
        except Exception as e:
            logger.error(
                f"RAG AGENT Failed to parse action parameters "
                f"from AI message: {ai_message}. Error: {e}"
            )
            return ActionOutput(
                is_exe_success=False,
                content="The requested correctly structured answer could not be found.",
            )

        if not action_param.tools and not action_param.knowledge:
            return ActionOutput(
                is_exe_success=True,
                content="No knowledge or tools available for search.",
                view="No knowledge or tools available for search.",
                terminate=False,
                observations=ai_message,
                thoughts=action_param.intention,
                state=AgenticRAGState.FINAL_SUMMARIZE.value,
            )
        content = ""
        action_name = ""
        action_input = ""
        knowledge_res = None
        actions = []
        views = []
        action_str = ""
        if action_param.knowledge:
            knowledge_ids = action_param.knowledge
            knowledge_res = await self.knowledge_retrieve(
                query=current_goal,
                knowledge_args=knowledge_ids,
                resource=self.resource,
                actions=actions,
            )
            if actions:
                action_str = "知识搜索" + "\n".join(actions)
            content += knowledge_res.summary_content
            action_name = "KnowledgeRetrieve"
            knowledge_view = await self.format_knowledge_vis(
                query=current_goal,
                knowledge_res=knowledge_res,
                is_exe_success=True,
                message_id=message_id,
                render_vis_fn=render_vis_fn
            )
            views.append(knowledge_view)
        try:
            if action_param.tools:
                for idx, tool in enumerate(action_param.tools):
                    tool_result = await self.run_tool(
                        name=tool["tool"],
                        args=tool["args"],
                        resource=self.resource,
                        say_to_user="",
                        render_protocol=self.render_protocol,
                        need_vis_render=need_vis_render,
                        message_id=message_id + f"_action_{idx}"
                    )
                    logger.info(f"RAG AGENT Tool [{tool['tool']}] result:{tool_result}")
                    action_input = tool_result.action_input
                    content += tool_result.content
                    views.append(content)

        except Exception as e:
            logger.error(
                f"RAG AGENT Failed to run tool. Error: {e}"
            )
            if not knowledge_res:
                content += f"RAG AGENT Failed to run tool. Error: {e}"
                views.append(content)
        return ActionOutput(
            is_exe_success=True,
            content=content,
            view="\n".join(views or []) if len(views or []) > 1 else "".join(
                views or []),
            resource_value=knowledge_res.dict() if knowledge_res else None,
            terminate=False,
            action=action_str,
            action_input=action_input,
            action_name=action_name,
            state=AgenticRAGState.FINAL_SUMMARIZE.value,
            thoughts=action_param.intention,
            observations=content,
        )

    async def knowledge_retrieve(
            self, query: str, knowledge_args: List[str], resource: Resource, actions: List[str]
    ) -> KnowledgeSearchResponse:
        """Perform knowledge retrieval."""
        from derisk_serve.agent.resource.knowledge_pack import KnowledgePackSearchResource
        knowledge_resource: KnowledgePackSearchResource = None
        if isinstance(self.resource, ResourcePack):
            for resource in self.resource.sub_resources:
                if isinstance(resource, KnowledgePackSearchResource):
                    knowledge_resource = resource
                    break
        else:
            if isinstance(resource, KnowledgePackSearchResource):
                knowledge_resource = resource
        if knowledge_resource:
            search_res = await knowledge_resource.get_summary(
                query=query,
                selected_knowledge_ids=knowledge_args
            )
            for knowledge in knowledge_resource.knowledge_spaces:
                if knowledge.knowledge_id in knowledge_args:
                    actions.append(f"{knowledge.name}")
                    break
            return search_res
        return KnowledgeSearchResponse(
            summary_content="",
        )

    async def run_tool(
        self,
        name: str,
        args: dict,
        resource: Resource,
        say_to_user: Optional[str] = None,
        render_protocol: Optional[Vis] = None,
        need_vis_render: bool = False,
        raw_tool_input: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> ActionOutput:
        """Run the tool."""
        try:
            return await super().run_tool(
                name=name,
                args=args,
                resource=resource,
                say_to_user=say_to_user,
                render_protocol=render_protocol,
                need_vis_render=need_vis_render,
                raw_tool_input=raw_tool_input,
                message_id=message_id,
            )
        except Exception as e:
            logger.exception(f"Tool [{name}] run failed!")
            # status = Status.FAILED.value
            err_msg = f"Tool [{name}] run failed! {str(e)}"
            tool_result = err_msg
            return ActionOutput(
                is_exe_success=False,
                content=err_msg,
                view=err_msg,
            )

    async def format_knowledge_vis(self,
                                   message_id,
                                   query,
                                   knowledge_res: KnowledgeSearchResponse,
                                   is_exe_success: bool = None,
                                   render_vis_fn: Optional[Vis] = None,
                                   ) -> Any:

        content = StepInfo()
        content.tool_name = f"知识搜索{query}"
        content.tool_args = json.dumps(
            {"query": query},
            ensure_ascii=False
        )
        content.tool_result = knowledge_res.summary_content if knowledge_res else None
        content.status = (
            Status.TODO.value
            if not is_exe_success
            else Status.COMPLETE
            if is_exe_success
            else Status.FAILED
        )

        return await render_vis_fn.display(
            content=VisStepContent(
                uid=message_id + "_action",
                message_id=message_id + "_action_0",
                type="all",
                status=content.status,
                tool_name=content.tool_name,
                tool_args=content.tool_args,
                tool_result=content.tool_result,
            ).to_dict()
        )





