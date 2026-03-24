"""
Streaming Integration for Core and Core_V2 Architecture

如何在两种架构下集成流式参数处理器。
"""

# ============================================================
# Core 架构集成
# ============================================================

"""
在 Core 架构中，工具调用发生在 Agent 的执行循环中。
集成点：LLM 输出流处理 → StreamingFunctionCallProcessor
"""

# 文件：derisk/agent/core/agent.py 或相关执行文件

from derisk.model.streaming import (
    StreamingFunctionCallProcessor,
    get_config_manager,
)


class AgentWithStreaming:
    """支持流式参数的 Agent"""

    def __init__(self, app_code: str = None, **kwargs):
        super().__init__(**kwargs)
        self.app_code = app_code
        self._streaming_processor = None

    def _init_streaming_processor(self, sse_manager):
        """初始化流式处理器"""
        if not self._streaming_processor and self.app_code:
            # 获取配置管理器
            config_manager = get_config_manager()

            # 创建处理器
            self._streaming_processor = StreamingFunctionCallProcessor(
                sse_manager=sse_manager,
                on_event=self._on_streaming_event,
            )

    async def _process_llm_stream(self, llm_stream, session_id: str):
        """处理 LLM 输出流"""
        if self._streaming_processor:
            # 使用流式处理器包装 LLM 流
            async for token in self._streaming_processor.process_llm_stream(
                session_id, llm_stream
            ):
                yield token
        else:
            # 不使用流式处理，直接传递
            async for token in llm_stream:
                yield token

    def _on_streaming_event(self, event):
        """流式事件回调"""
        # 可以在这里添加自定义处理逻辑
        pass


# ============================================================
# Core_V2 架构集成
# ============================================================

"""
Core_V2 架构使用 ProgressBroadcaster 进行进度广播。
集成点：ProgressBroadcaster + StreamingFunctionCallProcessor
"""

# 文件：derisk/agent/core_v2/execution/llm_executor.py

from derisk.agent.core_v2.visualization.progress import (
    ProgressBroadcaster,
    ProgressEventType,
    ProgressEvent,
)
from derisk.model.streaming import (
    StreamingFunctionCallProcessor,
    IncrementalFunctionCallParser,
    ParseEvent,
    get_config_manager,
)


class StreamingLLMExecutor:
    """支持流式参数的 LLM 执行器"""

    def __init__(
        self,
        app_code: str,
        progress_broadcaster: ProgressBroadcaster = None,
        sse_manager=None,
    ):
        self.app_code = app_code
        self.progress_broadcaster = progress_broadcaster
        self.sse_manager = sse_manager

        # 获取配置管理器
        self.config_manager = get_config_manager()

        # 初始化解析器
        self._parser = IncrementalFunctionCallParser()

    async def execute_with_streaming(self, llm_stream, session_id: str):
        """
        执行 LLM 调用，支持流式参数

        这是核心集成方法：
        1. 接收 LLM 原始 token 流
        2. 增量解析 function call
        3. 发送流式事件到前端
        """

        # 重置解析器
        self._parser.reset()

        # 处理流
        async for token in llm_stream:
            # 1. 先 yield 原始 token（下游可能需要）
            yield token

            # 2. 增量解析
            async for event in self._parser.parse_token(token):
                await self._handle_parse_event(event, session_id)

    async def _handle_parse_event(self, event: ParseEvent, session_id: str):
        """处理解析事件"""

        # 获取工具配置
        tool_config = self.config_manager.get_tool_config(
            self.app_code, event.tool_name or "unknown"
        )

        if event.event_type == "tool_start":
            # 通知进度广播器
            if self.progress_broadcaster:
                await self.progress_broadcaster.broadcast(
                    ProgressEvent(
                        type=ProgressEventType.TOOL_STARTED,
                        content=f"Tool started: {event.tool_name}",
                        metadata={
                            "call_id": event.call_id,
                            "tool_name": event.tool_name,
                        },
                    )
                )

            # 发送 SSE 事件
            if self.sse_manager:
                await self.sse_manager.send_sse_event(
                    session_id,
                    "tool_call_start",
                    {
                        "call_id": event.call_id,
                        "tool_name": event.tool_name,
                    },
                )

        elif event.event_type == "param_start":
            # 参数开始
            param_name = event.param_name
            should_stream = tool_config.should_stream(param_name, "")

            if self.sse_manager:
                await self.sse_manager.send_sse_event(
                    session_id,
                    "tool_param_start",
                    {
                        "call_id": event.call_id,
                        "tool_name": event.tool_name,
                        "param_name": param_name,
                        "streaming": should_stream,
                    },
                )

        elif event.event_type == "param_chunk":
            # 参数增量数据
            if self.sse_manager:
                await self.sse_manager.send_sse_event(
                    session_id,
                    "tool_param_chunk",
                    {
                        "call_id": event.call_id,
                        "tool_name": event.tool_name,
                        "param_name": event.param_name,
                        "chunk_data": event.data,
                        "is_delta": True,
                    },
                )

        elif event.event_type == "param_end":
            # 参数结束
            if self.sse_manager:
                await self.sse_manager.send_sse_event(
                    session_id,
                    "tool_param_end",
                    {
                        "call_id": event.call_id,
                        "tool_name": event.tool_name,
                        "param_name": event.param_name,
                    },
                )

        elif event.event_type == "tool_end":
            # 工具调用结束
            if self.progress_broadcaster:
                await self.progress_broadcaster.broadcast(
                    ProgressEvent(
                        type=ProgressEventType.TOOL_COMPLETED,
                        content=f"Tool completed: {event.tool_name}",
                        metadata={
                            "call_id": event.call_id,
                            "tool_name": event.tool_name,
                            "params": event.data,
                        },
                    )
                )

            if self.sse_manager:
                await self.sse_manager.send_sse_event(
                    session_id,
                    "tool_call_end",
                    {
                        "call_id": event.call_id,
                        "tool_name": event.tool_name,
                        "params": event.data,
                    },
                )


# ============================================================
# 使用示例
# ============================================================

# 在应用入口处初始化配置管理器


async def init_app(app_code: str, db_session):
    """初始化应用"""
    from derisk.model.streaming import set_config_manager, StreamingConfigManager

    # 创建配置管理器
    config_manager = StreamingConfigManager(db_session)
    set_config_manager(config_manager)

    # 预加载配置
    config_manager.get_app_configs(app_code)


# 在 Agent 执行入口使用


async def chat_handler(
    app_code: str,
    session_id: str,
    message: str,
    db_session,
    sse_manager,
):
    """处理聊天请求"""
    from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster

    # 获取配置管理器
    config_manager = get_config_manager()

    # 创建进度广播器
    progress_broadcaster = ProgressBroadcaster(session_id)

    # 创建流式执行器
    executor = StreamingLLMExecutor(
        app_code=app_code,
        progress_broadcaster=progress_broadcaster,
        sse_manager=sse_manager,
    )

    # 调用 LLM
    llm_response = await llm_client.chat_stream(message)

    # 执行并处理流式参数
    async for token in executor.execute_with_streaming(llm_response, session_id):
        # 处理原始响应...
        pass


# ============================================================
# 配置动态更新
# ============================================================


async def update_streaming_config(
    app_code: str,
    tool_name: str,
    new_config: dict,
    db_session,
):
    """更新流式配置"""
    from derisk.model.streaming import (
        StreamingConfigManager,
        ToolStreamingConfig,
        ParamStreamingConfig,
        ChunkStrategy,
    )

    manager = StreamingConfigManager(db_session)

    # 构建配置对象
    param_configs = {}
    for param_name, param_data in new_config.get("param_configs", {}).items():
        param_configs[param_name] = ParamStreamingConfig(
            param_name=param_name,
            threshold=param_data.get("threshold", 256),
            strategy=ChunkStrategy(param_data.get("strategy", "adaptive")),
            renderer=param_data.get("renderer", "default"),
            enabled=param_data.get("enabled", True),
        )

    config = ToolStreamingConfig(
        tool_name=tool_name,
        app_code=app_code,
        param_configs=param_configs,
        global_threshold=new_config.get("global_threshold", 256),
        global_strategy=ChunkStrategy(new_config.get("global_strategy", "adaptive")),
        global_renderer=new_config.get("global_renderer", "default"),
        enabled=new_config.get("enabled", True),
    )

    # 保存配置
    success = manager.save_tool_config(app_code, tool_name, config)

    return success
