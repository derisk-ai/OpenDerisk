"""Plugin Action Module."""

import datetime
import json
import logging
import time
import uuid
from typing import Optional

from mcp.types import CallToolResult, ImageContent, TextContent

from derisk._private.pydantic import BaseModel, Field
from derisk.vis import Vis
from derisk.vis.schema import VisStepContent, VisTextContent, VisConfirm
from derisk.vis.vis_converter import (
    SystemVisTag,
)
from ... import AgentContext
from ...core.action.base import Action, ActionOutput
from ...core.schema import Status, ActionInferenceMetrics
from ...resource import BaseTool
from ...resource.base import AgentResource, Resource, ResourceType
from ...resource.tool.pack import ToolPack

logger = logging.getLogger(__name__)


class ToolInput(BaseModel):
    """Plugin input model."""

    tool_name: str = Field(
        ...,
        description="The name of a tool that can be used to answer the current question"
                    " or solve the current task.",
    )
    args: dict = Field(
        default={"arg name1": "", "arg name2": ""},
        description="The tool selected for the current target, the parameter "
                    "information required for execution",
    )
    thought: str = Field(..., description="Summary of thoughts to the user")


class ToolAction(Action[ToolInput]):
    """Tool action class."""

    def __init__(self, **kwargs):
        """Tool action init."""
        super().__init__(**kwargs)

        ## this action out view vis tag name
        self.action_view_tag: str = SystemVisTag.VisTool.value

    @property
    def resource_need(self) -> Optional[ResourceType]:
        """Return the resource type needed for the action."""
        return None

    @property
    def out_model_type(self):
        """Return the output model type."""
        return ToolInput

    @property
    def ai_out_schema(self) -> Optional[str]:
        """Return the AI output schema."""
        out_put_schema = {
            "thought": "Summary of thoughts to the user",
            "tool_name": "The name of a tool that can be used to answer the current "
                         "question or solve the current task.",
            "args": {
                "arg name1": "arg value1",
                "arg name2": "arg value2",
            },
        }

        return f"""Please response in the following json format:
        {json.dumps(out_put_schema, indent=2, ensure_ascii=False)}
        Make sure the response is correct json and can be parsed by Python json.loads.
        """

    @staticmethod
    def process_files(tool_result: CallToolResult):
        """
        从tool_result中提取ImageContent单独处理
        """
        text_content = []
        if not tool_result.content:
            return
        for item in tool_result.content:
            if isinstance(item, ImageContent) and item.mimeType == "oss_file":
                text_content.append(TextContent(type="text", text=f"输出文件，文件信息如下: \n {item.data}"))
            else:
                text_content.append(item)
        tool_result.content = text_content

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the plugin action.

        Args:
            ai_message (str): The AI message.
            resource (Optional[AgentResource], optional): The resource. Defaults to
                None.
            rely_action_out (Optional[ActionOutput], optional): The rely action output.
                Defaults to None.
            need_vis_render (bool, optional): Whether need visualization rendering.
                Defaults to True.
        """
        metrics = ActionInferenceMetrics()
        metrics.start_time_ms = time.time_ns() // 1_000_000

        agent_context: Optional[AgentContext] = kwargs.get("agent_context")


        try:
            param: ToolInput = self.action_input or self._input_convert(
                ai_message, ToolInput
            )
        except Exception as e:
            logger.exception((str(e)))
            return ActionOutput(
                is_exe_success=False,
                content="The requested correctly structured answer could not be found.",
            )

        message_id = kwargs.get("message_id")
        action_out: ActionOutput = await self.run_tool(
            param.tool_name,
            param.args,
            self.resource,
            say_to_user=param.thought,
            render_protocol=self.render_protocol,
            need_vis_render=need_vis_render,
            message_id=message_id,
            require_approval=kwargs.get("require_approval", False),
        )
        metrics.end_time_ms = time.time_ns() // 1_000_000
        metrics.result_tokens = len(action_out.content)
        return action_out

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
        require_approval: bool = False
    ) -> ActionOutput:
        """Run the tool."""
        is_terminal = None
        try:
            tool_packs = ToolPack.from_resource(resource)
            if not tool_packs:
                raise ValueError("The tool resource is not found！")
            tool_pack: ToolPack = tool_packs[0]

            tool_info: BaseTool = await tool_pack.get_resources_info(resource_name=name)
            logger.info(tool_info)

            response_success = True
            err_msg = None

            if raw_tool_input and tool_pack.parse_execute_args(
                resource_name=name, input_str=raw_tool_input
            ):
                # Use real tool to parse the input, it will raise raw error when failed
                # it will make agent to modify the input and retry
                parsed_args = tool_pack.parse_execute_args(
                    resource_name=name, input_str=raw_tool_input
                )
                if parsed_args and isinstance(parsed_args, tuple):
                    args = parsed_args[1]

            start_time = datetime.datetime.now().timestamp()
            ask_user: bool = self.ask_user(tool_pack, name)
            if require_approval and ask_user:
                tool_result = ""
                status = Status.WAITING.value
                is_terminal = True
            else:
                try:
                    tool_result = await tool_pack.async_execute(resource_name=name, **args)
                    status = Status.COMPLETE.value
                    is_terminal = tool_pack.is_terminal(name)
                except Exception as e:
                    response_success = False
                    logger.exception(f"Tool [{name}] execute failed!")
                    status = Status.FAILED.value
                    err_msg = f"Tool [{tool_pack.name}:{name}] execute failed! {str(e)}"
                    tool_result = err_msg

            drsk_content = VisStepContent(
                uid=uuid.uuid4().hex,
                message_id=message_id,
                type="all",
                avatar=None,
                status=status,
                tool_name=tool_info.description,
                tool_args=json.dumps(args, ensure_ascii=False),
                tool_result=str(tool_result),
                err_msg=err_msg,
                progress=None,
            )

            view = self._render.vis_inst(SystemVisTag.VisText.value).sync_display(
                content=VisTextContent(
                    markdown=say_to_user, type="all", uid=message_id + "_content"
                ).to_dict()
            )
            if render_protocol:
                view = (
                    view
                    + "\n"
                    + await render_protocol.display(content=drsk_content.to_dict())
                )
            elif need_vis_render:
                raise NotImplementedError("The render_protocol should be implemented.")

            logger.info(f"Tool [{name}] result view:{view}")

            if isinstance(tool_result, CallToolResult):
                self.process_files(tool_result)

            return ActionOutput(
                is_exe_success=response_success,
                action=name,
                action_name=self.name,
                action_input=json.dumps(args, ensure_ascii=False),
                content=str(tool_result) or "无",
                view=view,
                observations=str(tool_result),
                ask_user=ask_user and require_approval,
                terminate=is_terminal,
                cost_ms=int((datetime.datetime.now().timestamp() - start_time) * 1000)
            )
        except Exception as e:
            logger.exception("Tool Action Run Failed！")
            return ActionOutput(
                is_exe_success=False,
                content=f"Tool action run failed!{str(e)}",
                terminate=is_terminal,
            )

    def ask_user(self, tool_pack: ToolPack, tool_name: str) -> bool:
        return tool_pack.ask_user or tool_pack._get_execution_tool(tool_name).ask_user
