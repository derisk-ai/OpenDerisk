"""Plugin Action Module."""

import datetime
import json
import logging
import asyncio
import time
from typing import Optional, Any, Tuple, cast

from mcp.types import CallToolResult, ImageContent, TextContent

from derisk._private.pydantic import BaseModel, Field
from derisk.eval.tool.llm_snapshot_tool import LLMSnapshotTool, ToolSnapshot
from derisk.eval.tool_run_model import RunModel, ToolRunModel
from derisk.vis.schema import VisStepContent
from derisk.vis.vis_converter import SystemVisTag
from ... import ConversableAgent, AgentMemory, AgentContext, AgentMessage
from ...core import sandbox_tool_dict
from ...core.system_tool_registry import system_tool_dict
from ...core.action.base import Action, ActionOutput, AskUserType, ToolCall
from ...core.schema import Status, ActionInferenceMetrics

from ...resource import BaseTool
from ...resource.base import Resource
from ...resource.tool.pack import ToolPack, _to_tool_list

logger = logging.getLogger(__name__)


class UnifiedToolAdapter(BaseTool):
    """
    统一工具框架适配器

    将新框架的 ToolBase (derisk.agent.tools.base.ToolBase) 适配为
    旧框架的 BaseTool 兼容接口，使 tool_action.py 能正确处理统一工具。
    """

    def __init__(self, tool_base):
        """
        初始化适配器

        Args:
            tool_base: 新框架的 ToolBase 实例
        """
        self._tool_base = tool_base
        # 不调用 super().__init__()，因为 BaseTool 是 Resource 子类
        # 直接设置需要的属性

    @property
    def name(self) -> str:
        """工具名称"""
        return self._tool_base.name

    @property
    def description(self) -> str:
        """工具描述"""
        return self._tool_base.metadata.description

    @property
    def args(self):
        """工具参数 - 转换为旧格式"""
        from derisk.agent.resource.tool.base import ToolParameter

        params = self._tool_base.parameters or {}
        properties = params.get("properties", {})
        required = params.get("required", [])

        result = {}
        for key, value in properties.items():
            result[key] = ToolParameter(
                name=key,
                title=value.get("title", key.replace("_", " ").title()),
                type=value.get("type", "string"),
                description=value.get("description", ""),
                required=key in required,
            )
        return result

    @property
    def ask_user(self) -> bool:
        """是否需要用户确认"""
        return self._tool_base.metadata.requires_permission

    @property
    def is_stream(self) -> bool:
        """是否流式输出"""
        return self._tool_base.is_stream

    @property
    def is_async(self) -> bool:
        """是否异步执行"""
        return self._tool_base.is_async

    @property
    def stream_queue(self):
        """流式输出队列"""
        return self._tool_base.stream_queue

    def execute(self, *args, **kwargs):
        """同步执行 - 新框架通常是异步的"""
        if self.is_async:
            raise ValueError("This tool is asynchronous, use async_execute instead")
        return self._tool_base.execute(*args, **kwargs)

    async def async_execute(self, *args, **kwargs):
        """异步执行"""
        return await self._tool_base.async_execute(*args, **kwargs)


# Constants for repeated strings
TOOL_EXECUTION_ERROR = "Tool execution failed"
EVAL_MODE_KEY = "eval_mode"
TOOL_RUN_MODE_KEY = "tool_run_mode"
TOOL_SNAPSHOTS_KEY = "tool_snapshots"
SNAPSHOT_MODE_DISPLAY = "快照模式"
KWARGS_FILTERED = ["message_id"]


class MCPResultError(Exception):
    def __init__(self, message=""):
        self.message = message
        super().__init__(self.message)


class ToolInput(BaseModel):
    """Plugin input model."""

    tool_name: str = Field(
        ...,
        description="The name of a tool that can be used to answer the current question or solve the current task.",
    )
    tool_call_id: Optional[str] = Field(
        None,
        description="The id of a too call.",
    )
    args: Optional[dict] = Field(
        None,
        description="The tool selected for the current target, the parameter information required for execution",
    )
    thought: Optional[str] = Field(None, description="Summary of thoughts to the user")


class ToolAction(Action[ToolInput]):
    """Tool action class."""

    name = "Tool"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_view_tag: str = SystemVisTag.VisTool.value

    @property
    def out_model_type(self):
        return ToolInput

    @property
    def ai_out_schema(self) -> Optional[str]:
        out_put_schema = {
            "thought": "Summary of thoughts to the user",
            "tool_name": "The name of a tool that can be used to answer the current question or solve the current task.",
            "args": {
                "arg name1": "arg value1",
                "arg name2": "arg value2",
            },
        }
        return (
            f"Please response in the following json format:\n"
            f"{json.dumps(out_put_schema, indent=2, ensure_ascii=False)}\n"
            "Make sure the response is correct json and can be parsed by Python json.loads."
        )

    @staticmethod
    def process_files(tool_result: CallToolResult):
        """Process file outputs in tool results."""
        if not tool_result.content:
            return False, None

        processed_content = []
        for item in tool_result.content:
            if isinstance(item, ImageContent) and item.mimeType == "oss_file":
                processed_content.append(
                    TextContent(
                        type="text", text=f"输出文件，文件信息如下: \n {item.data}"
                    )
                )
            else:
                processed_content.append(item)
        tool_result.content = processed_content

    @staticmethod
    def get_files(tool_result: Any):
        files = []
        file_match_key = ["file", "oss_file"]
        if isinstance(tool_result, CallToolResult):
            for item in tool_result.content:
                if isinstance(item, ImageContent) and item.mimeType == "oss_file":
                    files.append(item.data)

        elif isinstance(tool_result, dict):
            for key in file_match_key:
                if key in tool_result:
                    files.append(tool_result[key])
        return files

    async def prepare_init_msg(
        self,
        ai_message: str = None,
        resource: Optional[Resource] = None,
        render_protocol=None,
        message_id: str = None,
        current_message: AgentMessage = None,
        sender=None,
        agent=None,
        agent_context=None,
        memory=None,
        **kwargs,
    ) -> Optional[ActionOutput]:
        """Prepare initial action report for batch push (before parallel execution).

        This method is called before parallel tool execution to prepare
        initialization messages in batch, avoiding duplicate pushes.

        Args:
            Same as run() method

        Returns:
            ActionOutput: Initial action report, or None if preparation fails
        """
        try:
            param = self.action_input or self._input_convert(ai_message, ToolInput)
            self.action_input = self.action_input or param
        except Exception as e:
            logger.exception(f"Input conversion failed: {str(e)}")
            return None

        tool_info = None
        tool_pack = None

        if agent.sandbox_manager and param.tool_name in sandbox_tool_dict:
            tool_info = sandbox_tool_dict[param.tool_name]
        elif param.tool_name in system_tool_dict:
            tool_info = system_tool_dict[param.tool_name]
        elif self._try_get_unified_tool(param.tool_name):
            tool_info = self._try_get_unified_tool(param.tool_name)
        else:
            tool_pack, tool_info = await self._get_tool_info(resource, param.tool_name)

        if not tool_info:
            return None

        self._render = render_protocol or self._render

        start_time = datetime.datetime.now()

        view = await self.gen_view(
            message_id=message_id,
            tool_call_id=self.action_uid,
            tool_pack=tool_pack,
            tool_info=tool_info,
            status=Status.RUNNING.value,
            args=param.args,
            start_time=start_time,
        )

        return ActionOutput(
            name=self.name,
            content="执行中..",
            view=view,
            action_id=self.action_uid,
            action=param.tool_name,
            action_name=self._get_tool_attr(tool_info, "description"),
            action_input=param.args,
            state=Status.RUNNING.value,
        )

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[Resource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        skip_init_push: bool = False,
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
            skip_init_push (bool, optional): Skip initial push when batch pushed.
                Defaults to False.
        """
        metrics = ActionInferenceMetrics()
        start_time = datetime.datetime.now()
        metrics.start_time_ms = time.time_ns() // 1_000_000

        ## 请求参数解析
        try:
            param = self.action_input or self._input_convert(ai_message, ToolInput)
            self.action_input = self.action_input or param
        except Exception as e:
            logger.exception(f"Input conversion failed: {str(e)}")
            return ActionOutput(
                action_id=self.action_uid,
                name=self.name,
                is_exe_success=False,
                content="The requested correctly structured answer could not be found.",
            )
        memory: AgentMemory = kwargs.get("memory")
        agent: ConversableAgent = kwargs.get("agent")
        agent_context: AgentContext = kwargs.get("agent_context")
        message_id: str = kwargs.get("message_id")
        current_message: AgentMessage = kwargs.get("current_message")
        require_approval = kwargs.get("require_approval", False)
        action_id = kwargs.get("action_id", None)

        # 诊断日志：检查 render_protocol 传入情况
        render_protocol_from_kwargs = kwargs.get("render_protocol")
        if render_protocol_from_kwargs:
            logger.info(
                f"[ToolAction] render_protocol received: type={type(render_protocol_from_kwargs).__name__}, "
                f"render_name={getattr(render_protocol_from_kwargs, 'render_name', 'unknown')}"
            )
        else:
            logger.warning(
                f"[ToolAction] render_protocol NOT received from kwargs, using existing _render: "
                f"type={type(self._render).__name__}"
            )

        self._render = render_protocol_from_kwargs or self._render

        ## 工具资源准备
        ### Get tool information
        tool_pack = None
        env = "local"

        # 优先检查沙箱工具
        if agent.sandbox_manager and param.tool_name in sandbox_tool_dict:
            tool_info = sandbox_tool_dict[param.tool_name]
            if not self.init_params:
                sandbox_client = agent.sandbox_manager.client
                self.init_params["client"] = sandbox_client
                self.init_params["conversation_id"] = agent_context.conv_session_id
        # 检查系统工具（如 read_file）
        elif param.tool_name in system_tool_dict:
            tool_info = system_tool_dict[param.tool_name]
            # 系统工具需要 agent_file_system 参数
            if kwargs.get("agent_file_system"):
                self.init_params["agent_file_system"] = kwargs.get("agent_file_system")
        # 检查统一工具框架（如 bash, read, write 等）
        elif self._try_get_unified_tool(param.tool_name):
            tool_info = self._try_get_unified_tool(param.tool_name)
            logger.info(f"[ToolAction] 从统一工具框架获取工具: {param.tool_name}")
        else:
            tool_pack, tool_info = await self._get_tool_info(resource, param.tool_name)
        if not tool_info:
            return ActionOutput(
                action_id=self.action_uid,
                name=self.name,
                action=param.tool_name,
                action_name=param.thought,
                action_input=param.args,
                state=Status.FAILED.value,
                is_exe_success=False,
                content=f"Tool '{param.tool_name}' not found in resources",
            )

        ### Parse arguments if raw input provided
        args = self._parse_tool_arguments(
            tool_info, kwargs.get("raw_tool_input"), param.args
        )
        tool_args = {}
        tool_args.update(args)
        # 使用确定的环境变量覆盖生成变量
        tool_args.update(self.init_params)

        # 传入 agent_file_system 供系统工具（如 read_file）使用
        # 注意：只有系统工具才需要此参数，MCP 工具不需要
        if kwargs.get("agent_file_system") and param.tool_name in system_tool_dict:
            tool_args["agent_file_system"] = kwargs.get("agent_file_system")

        ## 推送工具执行初始化消息（如果不跳过）
        if not skip_init_push:
            await self.push_action_init_msg(
                gpts_memory=memory.gpts_memory,
                agent=agent,
                agent_context=agent_context,
                message=current_message,
                tool_pack=tool_pack,
                tool_info=tool_info,
                tool_args=param.args,
                start_time=start_time,
            )
        ## 检查工具审批
        env_context = agent_context.env_context or {}
        eval_mode = env_context.get(EVAL_MODE_KEY, False)

        # Handle user approval requirement
        if require_approval and self.requires_user_approval(tool_info, tool_pack):
            logger.info(
                f"工具[{tool_info.name}]需要进行工具执行确认审核！{require_approval},{self._get_tool_attr(tool_info, 'ask_user')},{tool_pack.ask_user if tool_pack else ''}"
            )
            return await self._create_user_approval_output(
                tool_info,
                message_id,
                args=param.args,
                tool_pack=tool_pack,
                metrics=metrics,
                start_time=start_time,
            )

        ## 工具执行
        tool_result = None
        if tool_info.is_stream:
            task = asyncio.create_task(
                self._execute_tool(tool_info=tool_info, args=tool_args, **kwargs)
            )
            queue = tool_info.stream_queue
            last_queue_data_time = time.time()
            try:
                while not task.done():
                    try:
                        chunk = await asyncio.wait_for(queue.get(), timeout=0.5)
                        last_queue_data_time = time.time()  # 重置计时器
                        await self.push_tool_action_stream_msg(
                            content=chunk,
                            gpts_memory=memory.gpts_memory,
                            agent=agent,
                            agent_context=agent_context,
                            message_id=message_id,
                            tool_pack=tool_pack,
                            tool_info=tool_info,
                            tool_args=param.args,
                            start_time=start_time,
                        )
                    except asyncio.TimeoutError:
                        if time.time() - last_queue_data_time > 90:
                            logger.error(
                                "Queue chunk data timeout: no data received for 90 seconds"
                            )
                            task.cancel()
                            tool_result = {
                                "error": "Tool execution timeout: no chunk data for 90 seconds"
                            }
                            break
                if tool_result is None:
                    tool_result = await task
            except Exception as e:
                logger.exception(f"MCP流式调用异常: {e}")
                if not task.done():
                    task.cancel()
                tool_result = {"error": f"Tool Stream processing failed: {str(e)}"}
        else:
            tool_result = await self._execute_tool(
                tool_info=tool_info, args=tool_args, **kwargs
            )

        ## Process tool result if needed
        result_content = tool_result["content"]
        status = (
            Status.COMPLETE.value if tool_result["success"] else Status.FAILED.value
        )

        metrics.end_time_ms = time.time_ns() // 1_000_000
        metrics.result_tokens = len(str(result_content))
        cost_ms = metrics.end_time_ms - metrics.start_time_ms
        metrics.cost_seconds = round(cost_ms / 1000, 2)

        ## 大结果归档处理 - 使用 Truncator
        # 注意：read_file 工具用于读取已归档文件，不应再次截断归档，否则会形成死循环
        attach_view = None
        archive_file_key = None
        agent_file_system = kwargs.get("agent_file_system")
        max_output_bytes = kwargs.get("max_output_bytes", 5 * 1024)  # 默认 50KB
        max_output_lines = kwargs.get("max_output_lines", 50)
        truncation_result = None

        # 跳过特定工具的截断：
        # - read/read_file/view/skill_read/skill_list: 避免循环归档，这些工具已自行管理输出大小（分段读取）
        # - execute_sql: 已自行管理输出大小（分页+CSV导出），Truncator 按字节截断会破坏 d-sql-query JSON 结构
        # - get_table_spec: 输出是结构化的表 spec，截断会破坏格式；工具已限制最多 3 张表
        should_truncate = (
            result_content
            and agent_file_system
            and isinstance(result_content, str)
            and tool_info.name not in ("read", "read_file", "view", "skill_read", "skill_list", "execute_sql", "get_table_spec")
        )

        if should_truncate:
            from derisk.agent.expand.react_master_agent.truncation import Truncator

            truncator = Truncator(
                max_lines=max_output_lines,
                max_bytes=max_output_bytes,
                agent_file_system=agent_file_system,
            )
            # 使用异步方法避免事件循环问题
            truncation_result = await truncator.truncate_async(
                result_content, tool_info.name
            )

            if truncation_result.is_truncated:
                logger.info(
                    f"[ToolAction] Output truncated for {tool_info.name}: "
                    f"{truncation_result.original_lines}->{truncation_result.truncated_lines} lines, "
                    f"{truncation_result.original_bytes}->{truncation_result.truncated_bytes} bytes, "
                    f"file_key={truncation_result.file_key}"
                )
                archive_file_key = truncation_result.file_key
                result_content = truncation_result.content

                # 生成 d-attach 组件展示归档文件
                if truncation_result.file_key:
                    try:
                        file_metadata = await agent_file_system.get_file_info(
                            truncation_result.file_key
                        )
                        if file_metadata:
                            from derisk.vis import Vis

                            attach_view = Vis.of("d-attach").sync_display(
                                content={
                                    "file_id": file_metadata.file_id,
                                    "file_name": file_metadata.file_name
                                    or truncation_result.file_key,
                                    "file_type": file_metadata.file_type or "txt",
                                    "file_size": file_metadata.file_size or 0,
                                    "oss_url": file_metadata.oss_url,
                                    "preview_url": file_metadata.preview_url,
                                    "download_url": file_metadata.download_url,
                                    "mime_type": file_metadata.mime_type,
                                }
                            )
                            logger.info(
                                f"[ToolAction] Generated d-attach for truncated file: {file_metadata.file_name}"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to generate d-attach: {e}")

        ## 可视化数据生成
        view = None
        if need_vis_render:
            if not self.render_protocol:
                # 降级处理：不抛异常，记录警告并继续执行
                logger.warning("render_protocol not available, skipping visualization")
            else:
                ## 构造工具展示效果
                kwargs_filtered = {
                    k: v for k, v in kwargs.items() if k not in KWARGS_FILTERED
                }
                view = await self.gen_view(
                    message_id=message_id,
                    tool_call_id=self.action_uid,
                    tool_pack=tool_pack,
                    tool_info=tool_info,
                    tool_result=result_content,
                    tool_cost=metrics.cost_seconds,
                    status=status,
                    args=param.args,
                    start_time=start_time,
                    eval_view=tool_result.get("eval_view"),
                    err_msg=tool_result.get("error"),
                    **kwargs_filtered,
                )

                # 如果有归档文件，追加 d-attach 组件到 view
                if attach_view:
                    view = view + "\n" + attach_view

        # 构建最终的 content：如果是截断结果，使用 content 字段而非整个对象
        final_content = result_content
        if truncation_result is not None:
            final_content = truncation_result.content

        return ActionOutput(
            action_id=self.action_uid,
            is_exe_success=tool_result["success"],
            action_name=self._get_tool_attr(tool_info, "description"),
            action=tool_info.name,
            name=self.name,
            action_input=json.dumps(param.args, ensure_ascii=False),
            content=final_content,
            view=view,
            observations=None,
            ask_user=False,
            state=status,  # 使用根据执行结果计算的 status
            thoughts=param.thought,
            terminate=False,  # Terminate 工具已移除
            cost_ms=cost_ms,
            eval_mode=eval_mode,
            metrics=metrics,
            start_time=start_time,
            eval_view=tool_result.get("eval_view", {}),
            extra={"archive_file_key": archive_file_key} if archive_file_key else None,
        )

    async def push_action_init_msg(
        self,
        gpts_memory,
        agent,
        agent_context,
        message: AgentMessage,
        tool_info: BaseTool,
        tool_pack: Optional[ToolPack] = None,
        tool_args: Optional[Any] = None,
        start_time: Optional[Any] = None,
        metrics: Optional[ActionInferenceMetrics] = None,
    ):
        view = await self.gen_view(
            message_id=message.message_id,
            tool_call_id=self.action_uid,
            tool_pack=tool_pack,
            tool_info=tool_info,
            status=Status.RUNNING.value,
            args=tool_args,
            start_time=start_time,
        )
        init_action_report = await self.init_out(view=view, args=tool_args)

        ## 展示工具任务基础信息
        await gpts_memory.push_message(
            conv_id=agent.agent_context.conv_id,
            stream_msg={
                "uid": message.message_id,
                "type": "all",
                "sender": agent.name or agent.role,
                "sender_role": agent.role,
                "message_id": message.message_id,
                "avatar": agent.avatar,
                "goal_id": message.goal_id,
                "conv_id": agent_context.conv_id,
                "conv_session_uid": agent_context.conv_session_id,
                "app_code": agent_context.gpts_app_code,
                "start_time": start_time,
                "action_report": [init_action_report],
            },
        )

    async def push_tool_action_stream_msg(
        self,
        content,
        gpts_memory,
        agent,
        agent_context,
        message_id,
        tool_info: BaseTool,
        tool_pack: Optional[ToolPack] = None,
        tool_args: Optional[Any] = None,
        start_time: Optional[Any] = None,
        metrics: Optional[ActionInferenceMetrics] = None,
    ):
        running_action_report = ActionOutput(
            name=self.name,
            content="执行中",
            view=await self.gen_view(
                message_id=message_id,
                tool_call_id=self.action_uid,
                tool_pack=tool_pack,
                tool_info=tool_info,
                status=Status.RUNNING.value,
                args=tool_args,
                markdown=content,
                start_time=start_time,
                view_type="incr",
            ),
            action_id=self.action_uid,
            action=tool_info.name,
            metrics=metrics,
            action_name=self._get_tool_attr(tool_info, "description"),
            action_input=tool_args,
            state=Status.RUNNING.value,
            stream=True,
        )

        await gpts_memory.push_message(
            conv_id=agent.agent_context.conv_id,
            stream_msg={
                "uid": message_id,
                "type": "incr",
                "sender": agent.name or agent.role,
                "sender_role": agent.role,
                "message_id": message_id,
                "avatar": agent.avatar,
                "conv_id": agent_context.conv_id,
                "conv_session_uid": agent_context.conv_session_id,
                "app_code": agent_context.gpts_app_code,
                "start_time": start_time,
                "action_report": [running_action_report],
            },
        )

    async def init_out(self, view: str = None, args: Optional[Any] = None):
        return ActionOutput(
            name=self.name,
            content="执行中..",
            view=view,
            action_id=self.action_uid,
            action=self.action_input.tool_name if self.action_input else None,
            # metrics=metrics,
            action_name=self.action_input.tool_name if self.action_input else None,
            action_input=self.action_input.args or args,
            state=Status.RUNNING.value,
        )

    def _try_get_unified_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        尝试从统一工具框架获取工具

        Args:
            tool_name: 工具名称

        Returns:
            BaseTool: 适配后的工具实例，如果不存在返回 None
        """
        try:
            from derisk.agent.tools import tool_registry

            tool_base = tool_registry.get(tool_name)
            if tool_base:
                # 使用 UnifiedToolAdapter 适配为 BaseTool 兼容接口
                return UnifiedToolAdapter(tool_base)
            return None
        except ImportError:
            logger.debug("统一工具框架未安装，跳过查找")
            return None
        except Exception as e:
            logger.warning(f"从统一工具框架获取工具失败: {tool_name}, error: {e}")
            return None

    def _get_tool_attr(self, tool_info, attr: str):
        """兼容新旧工具框架获取属性

        新框架 ToolBase: description 在 metadata 中, ask_user 对应 requires_permission
        旧框架 BaseTool: 直接有 description 和 ask_user 属性
        """
        if attr == "description":
            if hasattr(tool_info, "metadata"):
                return tool_info.metadata.description
            return tool_info.description
        elif attr == "ask_user":
            if hasattr(tool_info, "metadata"):
                return tool_info.metadata.requires_permission
            return tool_info.ask_user
        else:
            return getattr(tool_info, attr, None)

    def requires_user_approval(
        self, tool_info, tool_pack: Optional[ToolPack] = None
    ) -> bool:
        """Check if tool requires user approval."""
        if tool_info:
            if self._get_tool_attr(tool_info, "ask_user"):
                return True
            else:
                return tool_pack.ask_user if tool_pack else False
        else:
            return False

    def _normalize_content(self, content: Any) -> Tuple[str, bool, Optional[str]]:
        """Normalize tool execution content to string.

        Handles various content types returned by different tool implementations:
        - ToolResult (统一工具框架)
        - CallToolResult (MCP tools)
        - str (common string output)
        - dict (structured output)
        - list (list output)
        - other types (fallback to str)

        Args:
            content: Raw content from tool execution

        Returns:
            Tuple of (normalized_content, is_success, error_message)
        """
        if content is None:
            return "", True, None

        if isinstance(content, str):
            return content, True, None

        # 处理统一工具框架的 ToolResult
        try:
            from derisk.agent.tools import ToolResult

            if isinstance(content, ToolResult):
                if content.success:
                    output = content.output
                    if output is None:
                        return "", True, None
                    if isinstance(output, str):
                        return output, True, None
                    return json.dumps(output, ensure_ascii=False), True, None
                else:
                    return (
                        content.error or "Tool execution failed",
                        False,
                        content.error,
                    )
        except ImportError:
            pass

        if isinstance(content, CallToolResult):
            self.process_files(content)

            if content.isError:
                error_texts = []
                for item in content.content or []:
                    if isinstance(item, TextContent):
                        error_texts.append(item.text)
                    elif isinstance(item, ImageContent):
                        error_texts.append(f"[Image: {item.mimeType}]")
                error_msg = (
                    "\n".join(error_texts)
                    if error_texts
                    else "MCP tool returned an error"
                )
                return error_msg, False, error_msg
            else:
                text_contents = []
                for item in content.content or []:
                    if isinstance(item, TextContent):
                        text_contents.append(item.text)
                    elif isinstance(item, ImageContent):
                        if item.mimeType and item.mimeType.startswith("image/"):
                            text_contents.append(f"[Image: {item.mimeType}]")
                        else:
                            text_contents.append(f"[File: {item.mimeType}]")
                return "\n".join(text_contents) if text_contents else "", True, None

        if isinstance(content, dict):
            try:
                if "error" in content and content["error"]:
                    error_msg = str(content.get("error", "Unknown error"))
                    return json.dumps(content, ensure_ascii=False), False, error_msg
                return json.dumps(content, ensure_ascii=False), True, None
            except (TypeError, ValueError):
                return str(content), True, None

        if isinstance(content, (list, tuple)):
            try:
                return json.dumps(content, ensure_ascii=False), True, None
            except (TypeError, ValueError):
                return str(content), True, None

        return str(content), True, None

    async def _execute_tool(self, tool_info: BaseTool, args: Any, **kwargs) -> Any:
        """Execute tool with proper mode handling."""
        agent = kwargs.get("agent")
        system_args = {
            "agent_id": agent.agent_context.agent_app_code,
            "conv_id": agent.agent_context.conv_id,
            "conv_session_id": agent.agent_context.conv_session_id,
        }

        # Get environment context
        env_context = (
            agent.agent_context.env_context if agent and agent.agent_context else {}
        )
        eval_mode = env_context.get(EVAL_MODE_KEY, False)

        # Execute tool based on mode
        result = {"success": False, "content": "", "error": None, "eval_view": {}}

        try:
            if (
                eval_mode
                and await self._get_curr_tool_run_mode(env_context, tool_info)
                == RunModel.SNAPSHOT
            ):
                snapshot_data = self._get_tool_snapshots(env_context, tool_info.name)
                if agent and agent.llm_config.llm_client:
                    eval_tool = LLMSnapshotTool(
                        tool_info=tool_info,
                        tool_snapshots=snapshot_data,
                        llm_client=agent.llm_config.llm_client,
                        model_name="aistudio/DeepSeek-V3",
                    )
                    eval_output = await eval_tool.run_tool(args=args)
                    result.update(
                        {
                            "success": eval_output.is_exe_success,
                            "content": eval_output.content,
                            "error": eval_output.error_msg,
                            "eval_view": {
                                "tool_run_mode": SNAPSHOT_MODE_DISPLAY,
                                **eval_output.debug_view(),
                                "all_tool_snapshots": snapshot_data,
                            },
                        }
                    )
                else:
                    raise ValueError("LLM client not configured for snapshot mode")
            else:
                # Build arguments for tool execution
                # Use all passed args (including system-injected params like 'client')
                # and supplement with system_args if not present
                arguments = dict(args)  # Start with all passed args
                for k, v in system_args.items():
                    if k not in arguments:
                        arguments[k] = v

                # Inject agent for system tools that need it (e.g. todowrite, todoread)
                if agent and "agent" not in arguments:
                    arguments["agent"] = agent

                # Build context with sandbox_manager for sandbox tools
                tool_context = None
                if (
                    agent
                    and hasattr(agent, "sandbox_manager")
                    and agent.sandbox_manager
                ):
                    tool_context = {"sandbox_manager": agent.sandbox_manager}

                # Merge system context into arguments before filtering
                if tool_context:
                    arguments["context"] = tool_context

                # Filter arguments based on tool definition to avoid passing
                # unexpected parameters that cause validation errors
                # (especially for MCP tools with strict Pydantic validation)
                valid_keys = None
                if hasattr(tool_info, "args") and tool_info.args:
                    valid_keys = set(tool_info.args.keys())
                elif hasattr(tool_info, "_func") and callable(tool_info._func):
                    import inspect as _inspect

                    sig = _inspect.signature(tool_info._func)
                    # 如果函数签名包含 **kwargs，则不过滤参数，允许额外参数传入
                    has_var_keyword = any(
                        p.kind == _inspect.Parameter.VAR_KEYWORD
                        for p in sig.parameters.values()
                    )
                    if not has_var_keyword:
                        valid_keys = {p for p in sig.parameters if p not in ("self", "cls")}

                # Save context before filtering (for sandbox tools)
                # SandboxToolBase tools need context to get sandbox_client
                saved_context = arguments.get("context")

                if valid_keys is not None:
                    original_keys = set(arguments.keys())
                    removed_keys = original_keys - valid_keys
                    if removed_keys:
                        logger.debug(
                            f"Filtering tool arguments for {tool_info.name}: "
                            f"removed={removed_keys}, kept={original_keys & valid_keys}"
                        )
                    arguments = {k: v for k, v in arguments.items() if k in valid_keys}

                # Restore context for sandbox tools if it was filtered out
                # Check if tool needs sandbox context by checking _get_sandbox_client method
                # (inherited from SandboxToolBase) or by checking tool_info._tool_base
                needs_sandbox_context = False
                if saved_context:
                    # Check if this is a UnifiedToolAdapter wrapping a SandboxToolBase
                    if hasattr(tool_info, "_tool_base"):
                        tool_base = tool_info._tool_base
                        if hasattr(tool_base, "_get_sandbox_client"):
                            needs_sandbox_context = True
                    # Check if tool_info itself has _get_sandbox_client (direct SandboxToolBase)
                    elif hasattr(tool_info, "_get_sandbox_client"):
                        needs_sandbox_context = True
                    # Check if tool has "context" in its args definition
                    elif hasattr(tool_info, "args") and "context" in (
                        tool_info.args or {}
                    ):
                        needs_sandbox_context = True

                if needs_sandbox_context and saved_context:
                    arguments["context"] = saved_context
                    logger.debug(f"Restored context for sandbox tool: {tool_info.name}")

                if tool_info.is_async:
                    raw_content = await tool_info.async_execute(**arguments)
                else:
                    raw_content = tool_info.execute(**arguments)

                normalized_content, is_success, error_msg = self._normalize_content(
                    raw_content
                )
                result.update(
                    {
                        "success": is_success,
                        "content": normalized_content,
                        "error": error_msg,
                    }
                )
        except MCPResultError as e:
            result.update(
                {
                    "success": False,
                    "content": e.message,
                    "error": e.message,
                    "mcp_error": True,
                }
            )
            logger.exception(f"Tool {tool_info.name} execution error: {str(e)}")
        except Exception as e:
            result.update(
                {
                    "success": False,
                    "content": str(e),
                    "error": str(e),
                }
            )
            logger.exception(f"Tool {tool_info.name} execution error: {str(e)}")

        return result

    async def _get_curr_tool_run_mode(
        self, env_context: dict, tool_info: BaseTool
    ) -> str:
        """获取当前工具的执行模式。

        Args:
            env_context: 环境上下文
            tool_info: 工具信息

        Returns:
            当前工具的执行模式
        """
        tool_run_mode_raw = env_context.get(TOOL_RUN_MODE_KEY)
        if not tool_run_mode_raw:
            return RunModel.NORMAL

        try:
            tool_run_model = ToolRunModel(**tool_run_mode_raw)

            # 查找特定工具的配置（注意：tool_run_configs 现在可能是 None）
            if tool_run_model.tool_run_configs:
                for config in tool_run_model.tool_run_configs:
                    if config.tool_name == tool_info.name:
                        return config.run_model

            # 使用默认模式
            return tool_run_model.default_mode
        except Exception as e:
            logger.exception(
                f"Failed to parse tool run mode, Tool: {tool_info.name}, tool_run_mode_raw: {tool_run_mode_raw}, error: {str(e)}"
            )
            return RunModel.NORMAL

    async def _get_tool_info(
        self, resource: Resource, tool_name: str
    ) -> Tuple[Optional[Resource], Optional[BaseTool]]:
        """查找指定名称的工具及其父资源，找到后立即返回"""
        if resource is None:
            return None, None
        # 使用栈代替递归来避免递归深度限制和函数调用开销
        stack = [(resource, None)]  # (当前资源, 父资源)

        while stack:
            current_resource, parent_resource = stack.pop()

            if current_resource.is_pack:
                # 将子资源逆序压入栈，保持原来的顺序
                for child in reversed(current_resource.sub_resources):
                    stack.append((child, current_resource))
            else:
                # 只在叶子节点（非pack资源）中查找工具
                tools = _to_tool_list(current_resource, unpack=False, ignore_error=True)
                # 直接遍历查找匹配的工具，避免不必要的类型转换
                for tool in tools:
                    # 检查名称匹配，避免提前类型转换
                    if hasattr(tool, "name") and tool.name == tool_name:
                        # 找到匹配工具时才进行类型转换
                        typed_tool = cast(BaseTool, tool)
                        return parent_resource, typed_tool
        return None, None

    def _parse_tool_arguments(
        self, tool_info: BaseTool, raw_input: Optional[str], default_args: dict
    ) -> dict:
        """Parse tool arguments from raw input if available."""
        if not raw_input:
            return default_args or {}

        parsed = tool_info.parse_execute_args(input_str=raw_input)
        if parsed and isinstance(parsed, tuple):
            return parsed[1]  # Return the arguments part
        return default_args or {}

    async def _create_user_approval_output(
        self,
        tool_info: BaseTool,
        message_id: str,
        tool_pack: Optional[ToolPack] = None,
        args: Optional[dict] = None,
        metrics: Optional[ActionInferenceMetrics] = None,
        start_time: Optional[Any] = None,
    ) -> ActionOutput:
        """Create output when user approval is required."""

        view = await self.gen_view(
            message_id=message_id,
            tool_call_id=self.action_uid,
            tool_pack=tool_pack,
            tool_info=tool_info,
            status=Status.WAITING.value,
            args=args,
        )
        return ActionOutput(
            action_id=self.action_uid,
            name=self.name,
            is_exe_success=True,
            action=f"{self._get_tool_attr(tool_info, 'description')}「待用户确认」",
            action_name=tool_info.name,
            action_input=json.dumps(args, ensure_ascii=False),
            content="Waiting for user approval",
            view=view,
            observations="",
            ask_user=True,
            metrics=metrics,
            start_time=start_time,
            state=Status.WAITING.value,
            ask_type=AskUserType.BEFORE_ACTION.value,
            terminate=True,
        )

    def _get_tool_snapshots(
        self, env_context: dict, tool_name: str
    ) -> list[ToolSnapshot]:
        """Retrieve relevant tool snapshots from environment context."""
        snapshots = env_context.get(TOOL_SNAPSHOTS_KEY, [])
        return [ToolSnapshot(**s) for s in snapshots if s.get("toolName") == tool_name]

    async def gen_view(
        self,
        message_id,
        tool_call_id,
        tool_info,
        status,
        tool_pack: Optional[ToolPack] = None,
        args: Optional[Any] = None,
        out_type: Optional[str] = "json",
        tool_result: Optional[Any] = None,
        err_msg: Optional[str] = None,
        tool_cost: float = 0,
        start_time: Optional[Any] = None,
        view_type: Optional[str] = "all",
        markdown: Optional[Any] = None,
        eval_view: Optional[dict] = None,
        **kwargs,
    ):
        logger.info(f"Tool Action gen view!{self.action_view_tag}")

        if not self.render_protocol:
            logger.warning("render_protocol not available, returning simple view")
            tool_name = getattr(tool_info, "name", "unknown")
            return f"[Tool: {tool_name}] Status: {status}"

        # 兼容新旧工具框架
        # 新框架 ToolBase: description 在 metadata 中, ask_user 对应 requires_permission
        # 旧框架 BaseTool: 直接有 description 和 ask_user 属性
        if hasattr(tool_info, "metadata"):
            # 新框架 ToolBase
            tool_name = tool_info.name
            tool_desc = tool_info.metadata.description
            need_ask_user = tool_info.metadata.requires_permission
        else:
            # 旧框架 BaseTool
            tool_name = tool_info.name
            tool_desc = tool_info.description
            need_ask_user = tool_info.ask_user

        # 设置进度
        progress = 100 if status == "completed" else (50 if status == "running" else 0)
        # Build visualization content
        drsk_content = VisStepContent(
            uid=tool_call_id,
            message_id=message_id,
            type=view_type,
            avatar=None,
            tool_name=tool_name,
            tool_desc=tool_desc,
            tool_version=None,
            tool_author=None,
            need_ask_user=need_ask_user,
            tool_args=args,
            status=status,
            out_type=out_type,
            tool_result=tool_result,
            err_msg=err_msg,
            tool_cost=tool_cost,
            start_time=start_time,
            progress=progress,
            markdown=markdown,
            eval_view=eval_view,
        )
        self.action_view_tag: str = SystemVisTag.VisTool.value
        return self.render_protocol.sync_display(content=drsk_content.to_dict())

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
        return cls(
            action_uid=tool_call.tool_call_id,
            action_input=ToolInput(
                tool_name=tool_call.name,
                tool_call_id=tool_call.tool_call_id,
                thought=tool_call.thought,
                args=tool_call.args,
            ),
        )

    async def gen_content(self, tool_result: Any) -> Any:
        return tool_result["content"]
