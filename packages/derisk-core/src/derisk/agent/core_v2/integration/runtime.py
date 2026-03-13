"""
V2AgentRuntime - Core_v2 Agent 运行时

集成 GptsMemory、前端交互、消息转换等核心功能
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Type, Union

from pydantic import BaseModel, Field

from .adapter import V2Adapter, V2MessageConverter, V2StreamChunk
from ..vis_converter import CoreV2VisWindow3Converter
from ..visualization.progress import ProgressBroadcaster, ProgressEventType

logger = logging.getLogger(__name__)


class RuntimeState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class RuntimeConfig:
    max_concurrent_sessions: int = 100
    session_timeout: int = 3600
    enable_streaming: bool = True
    enable_progress: bool = True
    default_max_steps: int = 20
    cleanup_interval: int = 300

    # 项目记忆配置
    enable_project_memory: bool = True
    project_root: Optional[str] = None
    memory_dir: str = ".derisk"
    auto_memory_threshold: int = 10


@dataclass
class SessionContext:
    session_id: str
    conv_id: str
    user_id: Optional[str] = None
    agent_name: str = "primary"
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    state: RuntimeState = RuntimeState.IDLE
    message_count: int = 0

    current_message_id: Optional[str] = None
    accumulated_content: str = ""
    is_first_chunk: bool = True

    # StorageConversation 用于消息持久化到 ChatHistoryMessageEntity
    storage_conv: Optional[Any] = None


class V2AgentRuntime:
    """
    V2 Agent 运行时

    核心职责:
    1. Session 生命周期管理
    2. Agent 执行调度
    3. 消息流处理和推送
    4. 与 GptsMemory 集成
    5. 前端交互支持
    6. 分层上下文管理 (通过 UnifiedContextMiddleware)
    """

    def __init__(
        self,
        config: RuntimeConfig = None,
        gpts_memory: Any = None,
        adapter: V2Adapter = None,
        progress_broadcaster: ProgressBroadcaster = None,
        enable_hierarchical_context: bool = True,
        llm_client: Any = None,
        conv_storage: Any = None,
        message_storage: Any = None,
    ):
        """
        初始化运行时

        Args:
            config: 运行时配置
            gpts_memory: GptsMemory 实例 (用于消息持久化到 gpts_messages)
            adapter: V2Adapter 实例
            progress_broadcaster: 进度广播器
            enable_hierarchical_context: 是否启用分层上下文
            llm_client: LLM 客户端 (用于上下文压缩)
            conv_storage: 会话存储 (用于 StorageConversation)
            message_storage: 消息存储 (用于 ChatHistoryMessageEntity)
        """
        self.config = config or RuntimeConfig()
        self.gpts_memory = gpts_memory
        self.adapter = adapter or V2Adapter()
        self.progress_broadcaster = progress_broadcaster

        # Conversation 存储 (用于 ChatHistoryMessageEntity)
        self._conv_storage = conv_storage
        self._message_storage = message_storage

        # 分层上下文管理
        self._enable_hierarchical_context = enable_hierarchical_context
        self._llm_client = llm_client
        self._context_middleware: Optional[Any] = None

        # 项目记忆管理器 (CLAUDE.md 风格)
        self._project_memory: Optional[Any] = None

        self._sessions: Dict[str, SessionContext] = {}
        self._agents: Dict[str, Any] = {}
        self._agent_factories: Dict[str, Callable] = {}
        self._execution_tasks: Dict[str, asyncio.Task] = {}
        self._message_queues: Dict[str, asyncio.Queue] = {}

        self._state = RuntimeState.IDLE
        self._cleanup_task: Optional[asyncio.Task] = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    def register_agent_factory(self, agent_name: str, factory: Callable):
        self._agent_factories[agent_name] = factory
        logger.info(f"[V2Runtime] 注册 Agent 工厂: {agent_name}")

    def register_agent(self, agent_name: str, agent: Any):
        self._agents[agent_name] = agent
        logger.info(f"[V2Runtime] 注册 Agent: {agent_name}")

    async def start(self):
        self._state = RuntimeState.RUNNING

        # 启动 GptsMemory
        if self.gpts_memory and hasattr(self.gpts_memory, "start"):
            await self.gpts_memory.start()

        # 初始化分层上下文中间件
        if self._enable_hierarchical_context and self.gpts_memory:
            try:
                from derisk.context.unified_context_middleware import (
                    UnifiedContextMiddleware,
                )

                self._context_middleware = UnifiedContextMiddleware(
                    gpts_memory=self.gpts_memory,
                    llm_client=self._llm_client,
                )
                await self._context_middleware.initialize()
                logger.info("[V2Runtime] 分层上下文中间件已初始化")
            except Exception as e:
                logger.warning(f"[V2Runtime] 初始化分层上下文中间件失败: {e}")
                self._context_middleware = None

        # 初始化项目记忆系统 (CLAUDE.md 风格)
        if self.config.enable_project_memory:
            try:
                await self._initialize_project_memory()
            except Exception as e:
                logger.warning(f"[V2Runtime] 初始化项目记忆系统失败: {e}")

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[V2Runtime] 运行时已启动")

    async def stop(self):
        self._state = RuntimeState.TERMINATED

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()

        # 取消所有执行任务
        for task in self._execution_tasks.values():
            task.cancel()

        # 清理分层上下文中间件
        if self._context_middleware:
            try:
                self._context_middleware.clear_all_cache()
            except Exception as e:
                logger.warning(f"[V2Runtime] 清理上下文中间件失败: {e}")

        # 关闭 GptsMemory
        if self.gpts_memory and hasattr(self.gpts_memory, "shutdown"):
            await self.gpts_memory.shutdown()

        # 关闭项目记忆系统
        if self._project_memory:
            try:
                # 项目记忆系统的清理（如果需要）
                pass
            except Exception as e:
                logger.warning(f"[V2Runtime] 关闭项目记忆系统失败: {e}")

        logger.info("[V2Runtime] 运行时已停止")

    # ========== 项目记忆相关方法 ==========

    async def _initialize_project_memory(self) -> None:
        """
        初始化项目记忆系统 (CLAUDE.md 风格)

        这会扫描 .derisk/ 目录，加载多层级记忆文件，
        并注册自动记忆钩子。
        """
        from pathlib import Path

        from ..project_memory import ProjectMemoryManager, ProjectMemoryConfig

        # 确定项目根目录
        project_root = self.config.project_root
        if not project_root:
            # 尝试从当前工作目录推断
            project_root = str(Path.cwd())

        # 创建项目记忆配置
        memory_config = ProjectMemoryConfig(
            project_root=project_root,
            memory_dir=self.config.memory_dir,
            auto_memory_threshold=self.config.auto_memory_threshold,
        )

        # 创建并初始化项目记忆管理器
        self._project_memory = ProjectMemoryManager()
        await self._project_memory.initialize(memory_config)

        # 注册自动记忆钩子
        try:
            from ..filesystem import register_project_memory_hooks

            register_project_memory_hooks(self._project_memory)
            logger.info("[V2Runtime] 项目记忆钩子已注册")
        except Exception as e:
            logger.warning(f"[V2Runtime] 注册项目记忆钩子失败: {e}")

        logger.info(
            f"[V2Runtime] 项目记忆系统已初始化: "
            f"project_root={project_root}, memory_dir={self.config.memory_dir}"
        )

    @property
    def project_memory(self) -> Optional[Any]:
        """获取项目记忆管理器"""
        return self._project_memory

    async def get_project_context(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        获取项目上下文

        这会合并所有记忆层并返回完整的上下文字符串，
        可用于构建 agent 的 system prompt。

        Args:
            agent_name: Agent 名称（用于 agent 特定的记忆）
            session_id: 会话 ID（用于 session 特定的记忆）

        Returns:
            合并后的项目上下文字符串
        """
        if not self._project_memory:
            return ""

        return await self._project_memory.build_context(
            agent_name=agent_name,
            session_id=session_id,
        )

    async def write_auto_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        写入自动记忆

        Args:
            content: 记忆内容
            metadata: 元数据

        Returns:
            记忆 ID 或路径
        """
        if not self._project_memory:
            logger.warning("[V2Runtime] 项目记忆系统未初始化，无法写入自动记忆")
            return None

        return await self._project_memory.write_auto_memory(content, metadata)

    async def create_session(
        self,
        conv_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: str = "primary",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> SessionContext:
        if len(self._sessions) >= self.config.max_concurrent_sessions:
            raise RuntimeError("达到最大并发会话数限制")

        session_id = session_id or str(uuid.uuid4().hex)
        conv_id = conv_id or session_id

        context = SessionContext(
            session_id=session_id,
            conv_id=conv_id,
            user_id=user_id,
            agent_name=agent_name,
            metadata=metadata or {},
        )

        # 初始化 StorageConversation (用于 ChatHistoryMessageEntity 存储)
        if self._conv_storage and self._message_storage:
            try:
                from derisk.core import StorageConversation

                storage_conv = StorageConversation(
                    conv_uid=conv_id,
                    chat_mode="chat_agent",
                    user_name=user_id,
                    conv_storage=self._conv_storage,
                    message_storage=self._message_storage,
                    load_message=False,  # 新会话不需要加载
                )
                storage_conv.start_new_round()
                context.storage_conv = storage_conv
                logger.info(f"[V2Runtime] 初始化 StorageConversation: {conv_id[:8]}")
            except Exception as e:
                logger.warning(f"[V2Runtime] 初始化 StorageConversation 失败: {e}")

        self._sessions[session_id] = context
        self._message_queues[session_id] = asyncio.Queue(maxsize=100)

        if self.gpts_memory:
            vis_converter = CoreV2VisWindow3Converter()
            await self.gpts_memory.init(conv_id, vis_converter=vis_converter)

        logger.info(
            f"[V2Runtime] 创建会话: {session_id[:8]}, conv_id: {conv_id[:8]}, vis_converter: vis_window3"
        )
        return context

    async def get_session(self, session_id: str) -> Optional[SessionContext]:
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str):
        if session_id in self._sessions:
            context = self._sessions.pop(session_id)
            context.state = RuntimeState.TERMINATED

            if session_id in self._execution_tasks:
                self._execution_tasks[session_id].cancel()
                del self._execution_tasks[session_id]

            if session_id in self._message_queues:
                del self._message_queues[session_id]

            if self.gpts_memory and context.conv_id:
                await self.gpts_memory.clear(context.conv_id)

            logger.info(f"[V2Runtime] 关闭会话: {session_id[:8]}")

    async def execute(
        self,
        session_id: str,
        message: str,
        stream: bool = True,
        enable_context_loading: bool = True,
        multimodal_contents: Optional[List[Dict[str, Any]]] = None,
        sandbox_file_refs: Optional[List[Any]] = None,
        **kwargs,
    ) -> AsyncIterator[V2StreamChunk]:
        """
        执行 Agent

        Args:
            session_id: 会话 ID
            message: 用户消息
            stream: 是否流式输出
            enable_context_loading: 是否加载分层上下文
            multimodal_contents: 多模态内容列表 (图片等)
            sandbox_file_refs: 沙箱文件引用列表
            **kwargs: 其他参数

        Yields:
            V2StreamChunk: 响应块
        """
        context = await self.get_session(session_id)
        if not context:
            yield V2StreamChunk(type="error", content="会话不存在")
            return

        context.state = RuntimeState.RUNNING
        context.last_active = datetime.now()
        context.message_count += 1

        context.current_message_id = None
        context.accumulated_content = ""
        context.is_first_chunk = True

        agent = await self._get_or_create_agent(context, kwargs)
        if not agent:
            yield V2StreamChunk(type="error", content="Agent 不存在")
            return

        try:
            conv_id = context.conv_id

            # 加载分层上下文
            context_result = None
            if enable_context_loading and self._context_middleware:
                try:
                    context_result = await self._context_middleware.load_context(
                        conv_id=conv_id,
                        task_description=message[:200] if message else None,
                    )
                    logger.info(
                        f"[V2Runtime] 已加载分层上下文: conv_id={conv_id[:8]}, "
                        f"chapters={context_result.stats.get('chapter_count', 0)}"
                    )
                except Exception as e:
                    logger.warning(f"[V2Runtime] 加载分层上下文失败: {e}")

            # 设置 GptsMemory 到 Agent
            if self.gpts_memory:
                await self._push_user_message(conv_id, message)
                await self.gpts_memory.set_agent(
                    conv_id, self._create_sender_proxy(context.agent_name)
                )

                if context_result and hasattr(agent, "set_context"):
                    agent.set_context(context_result)

            # 处理多模态内容和文件引用
            if multimodal_contents:
                kwargs["multimodal_contents"] = multimodal_contents
                logger.info(
                    f"[V2Runtime] 传递 multimodal_contents: {len(multimodal_contents)} 项"
                )

            if sandbox_file_refs:
                kwargs["sandbox_file_refs"] = sandbox_file_refs
                logger.info(
                    f"[V2Runtime] 传递 sandbox_file_refs: {len(sandbox_file_refs)} 项"
                )

            if stream:
                async for chunk in self._execute_stream(
                    agent, message, context, **kwargs
                ):
                    yield chunk
                    await self._push_stream_chunk(conv_id, chunk)
            else:
                result = await self._execute_sync(agent, message, context, **kwargs)
                yield result
                await self._push_stream_chunk(conv_id, result)

        except Exception as e:
            logger.exception(f"[V2Runtime] 执行错误: {e}")
            yield V2StreamChunk(type="error", content=str(e))

        finally:
            context.state = RuntimeState.IDLE

    async def _get_or_create_agent(
        self, context: SessionContext, kwargs: Dict
    ) -> Optional[Any]:
        agent_name = context.agent_name
        logger.debug(
            f"[V2Runtime] 尝试获取/创建 Agent: {agent_name}, 已注册工厂: {list(self._agent_factories.keys())}"
        )

        if agent_name in self._agents:
            logger.debug(f"[V2Runtime] 从缓存获取 Agent: {agent_name}")
            return self._agents[agent_name]

        if agent_name in self._agent_factories:
            agent = await self._create_agent_from_factory(agent_name, context, kwargs)
            if agent:
                self._agents[agent_name] = agent
            return agent

        if "default" in self._agent_factories:
            logger.info(
                f"[V2Runtime] Agent '{agent_name}' 未预注册，尝试使用 default 工厂创建"
            )
            agent = await self._create_agent_from_factory(
                "default", context, {**kwargs, "app_code": agent_name}
            )
            if agent:
                self._agents[agent_name] = agent
            return agent

        logger.warning(
            f"[V2Runtime] Agent '{agent_name}' 不在已注册工厂列表中: {list(self._agent_factories.keys())}"
        )
        return None

    async def _create_agent_from_factory(
        self,
        agent_name: str,
        context: SessionContext,
        kwargs: Dict,
    ) -> Optional[Any]:
        factory = self._agent_factories.get(agent_name)
        if not factory:
            return None

        try:
            if asyncio.iscoroutinefunction(factory):
                agent = await factory(context=context, **kwargs)
            else:
                agent = factory(context=context, **kwargs)
            if agent is None:
                logger.error(f"[V2Runtime] Agent 工厂返回 None: {agent_name}")
            else:
                logger.info(
                    f"[V2Runtime] Agent 创建成功: {agent_name}, type={type(agent).__name__}"
                )
            return agent
        except Exception as e:
            logger.exception(f"[V2Runtime] 创建 Agent 失败: {agent_name}, error: {e}")
            return None

    async def _execute_stream(
        self,
        agent: Any,
        message: str,
        context: SessionContext,
        **kwargs,
    ) -> AsyncIterator[V2StreamChunk]:
        from ..agent_base import AgentBase, AgentState
        from ..enhanced_agent import AgentBase as EnhancedAgentBase
        import sys

        # Check both AgentBase types (from agent_base.py and enhanced_agent.py)
        is_agent_base = isinstance(agent, (AgentBase, EnhancedAgentBase))
        print(
            f"[_execute_stream] agent type: {type(agent)}, isinstance(AgentBase): {is_agent_base}",
            file=sys.stderr,
            flush=True,
        )
        print(
            f"[_execute_stream] hasattr generate_reply: {hasattr(agent, 'generate_reply')}",
            file=sys.stderr,
            flush=True,
        )

        if is_agent_base:
            print("[_execute_stream] Using AgentBase path", file=sys.stderr, flush=True)
            agent_context = self.adapter.context_bridge.create_v2_context(
                conv_id=context.conv_id,
                session_id=context.session_id,
                user_id=context.user_id,
            )
            await agent.initialize(agent_context)

            if self.progress_broadcaster and hasattr(agent, "_progress_broadcaster"):
                agent._progress_broadcaster = self.progress_broadcaster

            print(
                f"[_execute_stream] Calling agent.run with message: {message[:50]}...",
                file=sys.stderr,
                flush=True,
            )
            chunk_count = 0
            last_chunk = None
            try:
                async for chunk in agent.run(message, stream=True, **kwargs):
                    chunk_count += 1
                    print(
                        f"[_execute_stream] Got chunk #{chunk_count}: {str(chunk)[:100]}",
                        file=sys.stderr,
                        flush=True,
                    )
                    parsed = self._parse_agent_output(chunk)

                    if self.progress_broadcaster:
                        await self._emit_progress_event(parsed)

                    if last_chunk:
                        yield last_chunk
                    last_chunk = parsed
                print(
                    f"[_execute_stream] Total chunks: {chunk_count}",
                    file=sys.stderr,
                    flush=True,
                )

                if last_chunk:
                    last_chunk.is_final = True
                    yield last_chunk
            except Exception as e:
                logger.exception(f"[_execute_stream] agent.run 执行异常: {e}")
                error_chunk = V2StreamChunk(
                    type="error", content=f"执行异常: {e}", is_final=True
                )
                if self.progress_broadcaster:
                    await self._emit_progress_event(error_chunk)
                yield error_chunk

        elif hasattr(agent, "generate_reply"):
            print(
                "[_execute_stream] Using generate_reply path",
                file=sys.stderr,
                flush=True,
            )
            try:
                response = await agent.generate_reply(
                    received_message={"content": message},
                    sender=None,
                    **kwargs,
                )
                content = getattr(response, "content", str(response))
                yield V2StreamChunk(type="response", content=content, is_final=True)
            except Exception as e:
                logger.exception(f"[_execute_stream] generate_reply 执行异常: {e}")
                yield V2StreamChunk(
                    type="error", content=f"执行异常: {e}", is_final=True
                )

        else:
            print(
                "[_execute_stream] Unsupported agent type!", file=sys.stderr, flush=True
            )
            yield V2StreamChunk(
                type="error", content="不支持的 Agent 类型", is_final=True
            )

    async def _emit_progress_event(self, chunk: V2StreamChunk):
        if not self.progress_broadcaster:
            return

        if chunk.type == "thinking":
            await self.progress_broadcaster.thinking(chunk.content, **chunk.metadata)
        elif chunk.type == "tool_call":
            tool_name = chunk.metadata.get("tool_name", "unknown")
            await self.progress_broadcaster.tool_started(
                tool_name, chunk.metadata.get("args", {})
            )
        elif chunk.type == "tool_result":
            tool_name = chunk.metadata.get("tool_name", "unknown")
            await self.progress_broadcaster.tool_completed(tool_name, chunk.content)
        elif chunk.type == "error":
            await self.progress_broadcaster.error(chunk.content, **chunk.metadata)
        elif chunk.type == "response":
            if chunk.is_final:
                await self.progress_broadcaster.complete(chunk.content)

    async def _execute_sync(
        self,
        agent: Any,
        message: str,
        context: SessionContext,
        **kwargs,
    ) -> V2StreamChunk:
        result_chunks = []
        async for chunk in self._execute_stream(agent, message, context, **kwargs):
            result_chunks.append(chunk.content)

        return V2StreamChunk(
            type="response",
            content="\n".join(result_chunks),
            is_final=True,
        )

    def _parse_agent_output(self, output: str) -> V2StreamChunk:
        is_final = False

        if output.startswith("[THINKING]"):
            content = output.replace("[THINKING]", "").replace("[/THINKING]", "")
            return V2StreamChunk(type="thinking", content=content)
        elif output.startswith("[TOOL:"):
            match = output.split("]")
            if len(match) >= 2:
                tool_name = match[0].replace("[TOOL:", "")
                content = (
                    match[1].replace("[/TOOL]", "") if "[/TOOL]" in output else match[1]
                )
            else:
                tool_name = "unknown"
                content = output
            return V2StreamChunk(
                type="tool_call",
                content=content,
                metadata={"tool_name": tool_name},
            )
        elif output.startswith("[ERROR]"):
            content = output.replace("[ERROR]", "").replace("[/ERROR]", "")
            return V2StreamChunk(type="error", content=content)
        elif output.startswith("[TERMINATE]"):
            content = (
                output.replace("[TERMINATE]", "").replace("[/TERMINATE]", "").strip()
            )
            return V2StreamChunk(type="response", content=content, is_final=True)
        elif output.startswith("[WARNING]"):
            content = output.replace("[WARNING]", "").replace("[/WARNING]", "")
            return V2StreamChunk(type="response", content=f"⚠️ {content}")
        elif output.startswith("[INFO]"):
            content = output.replace("[INFO]", "").replace("[/INFO]", "")
            return V2StreamChunk(type="response", content=content)
        elif output.startswith("[执行工具]"):
            tool_name = output.replace("[执行工具]", "").strip()
            return V2StreamChunk(
                type="tool_call",
                content=tool_name,
                metadata={"tool_name": tool_name},
            )
        elif output.startswith("[错误]"):
            content = output.replace("[错误]", "").strip()
            return V2StreamChunk(type="error", content=content)
        elif output.startswith("[异常]"):
            content = output.replace("[异常]", "").strip()
            return V2StreamChunk(type="error", content=content)
        elif output.startswith("[警告]"):
            content = output.replace("[警告]", "").strip()
            return V2StreamChunk(type="response", content=f"⚠️ {content}")
        elif output.startswith("[结果]"):
            content = output.replace("[结果]", "").strip()
            return V2StreamChunk(type="tool_result", content=content)
        elif "[思考]" in output:
            content = output.replace("[思考]", "").replace("[/思考]", "").strip()
            return V2StreamChunk(type="thinking", content=content)
        else:
            return V2StreamChunk(type="response", content=output)

    async def _push_user_message(self, conv_id: str, message: str):
        from derisk.agent.core.memory.gpts.base import GptsMessage

        # 保存到 GptsMemory (gpts_messages 表)
        if self.gpts_memory:
            user_msg = type(
                "GptsMessage",
                (),
                {
                    "message_id": str(uuid.uuid4().hex),
                    "conv_id": conv_id,
                    "sender": "user",
                    "receiver": "assistant",
                    "content": message,
                    "rounds": 0,
                },
            )()
            await self.gpts_memory.append_message(conv_id, user_msg, save_db=True)

        # 同时保存到 StorageConversation (ChatHistoryMessageEntity 表)
        session = None
        for s in self._sessions.values():
            if s.conv_id == conv_id:
                session = s
                break

        if session and session.storage_conv:
            try:
                session.storage_conv.add_user_message(message)
                logger.info(
                    f"[V2Runtime] 用户消息已保存到 StorageConversation: {conv_id[:8]}"
                )
            except Exception as e:
                logger.warning(
                    f"[V2Runtime] 保存用户消息到 StorageConversation 失败: {e}"
                )

    async def _push_stream_chunk(self, conv_id: str, chunk: V2StreamChunk):
        if not self.gpts_memory:
            return

        session = None
        for s in self._sessions.values():
            if s.conv_id == conv_id:
                session = s
                break

        if not session:
            logger.warning(f"Session not found for conv_id: {conv_id}")
            return

        if session.current_message_id is None:
            session.current_message_id = str(uuid.uuid4().hex)
            session.accumulated_content = ""
            session.is_first_chunk = True

        if chunk.type == "response":
            session.accumulated_content += chunk.content or ""

        is_thinking = chunk.type == "thinking"
        stream_msg = {
            "uid": session.current_message_id,
            "type": "incr",
            "message_id": session.current_message_id,
            "conv_id": conv_id,
            "conv_session_uid": session.session_id,
            "goal_id": session.current_message_id,
            "task_goal_id": session.current_message_id,
            "sender": session.agent_name,
            "sender_name": session.agent_name,
            "sender_role": "assistant",
            "thinking": chunk.content if is_thinking else None,
            "content": "" if is_thinking else (chunk.content or ""),
            "prev_content": session.accumulated_content,
            "start_time": datetime.now(),
        }

        await self.gpts_memory.push_message(
            conv_id,
            stream_msg=stream_msg,
            is_first_chunk=session.is_first_chunk,
        )

        if session.is_first_chunk:
            session.is_first_chunk = False

        if chunk.is_final:
            # 生成 vis_window3 最终视图用于持久化
            # 历史会话加载时，前端需要 vis_window3 格式才能正确渲染
            vis_final_content = session.accumulated_content
            if session.accumulated_content:
                try:
                    from derisk.agent.core.memory.gpts.base import (
                        GptsMessage as GptsMsg,
                    )

                    vis_converter = CoreV2VisWindow3Converter()
                    # 构建 GptsMessage 供 final_view 使用
                    final_gpt_msg = GptsMsg(
                        conv_id=conv_id,
                        conv_session_id=session.session_id,
                        sender=session.agent_name,
                        sender_name=session.agent_name,
                        message_id=session.current_message_id or str(uuid.uuid4().hex),
                        role="assistant",
                        content=session.accumulated_content,
                        receiver="user",
                        rounds=0,
                    )
                    vis_view = await vis_converter.final_view(
                        messages=[final_gpt_msg],
                        gpt_msg=final_gpt_msg,
                    )
                    if vis_view:
                        vis_final_content = vis_view
                        logger.info(
                            f"[V2Runtime] 生成 vis_window3 最终视图: {conv_id[:8]}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[V2Runtime] 生成 vis_window3 最终视图失败，回退到纯文本: {e}"
                    )

            # 保存到 GptsMemory (gpts_messages 表)
            if self.gpts_memory and session.accumulated_content:
                assistant_msg = type(
                    "GptsMessage",
                    (),
                    {
                        "message_id": session.current_message_id
                        or str(uuid.uuid4().hex),
                        "conv_id": conv_id,
                        "sender": session.agent_name,
                        "receiver": "user",
                        "content": vis_final_content,
                        "rounds": 0,
                    },
                )()
                await self.gpts_memory.append_message(
                    conv_id, assistant_msg, save_db=True
                )

            # 同时保存到 StorageConversation (ChatHistoryMessageEntity 表)
            if session.storage_conv and session.accumulated_content:
                try:
                    session.storage_conv.add_view_message(vis_final_content)
                    session.storage_conv.end_current_round()
                    logger.info(
                        f"[V2Runtime] AI消息已保存到 StorageConversation: {conv_id[:8]}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[V2Runtime] 保存AI消息到 StorageConversation 失败: {e}"
                    )

            session.current_message_id = None
            session.accumulated_content = ""
            session.is_first_chunk = True

    def _create_sender_proxy(self, agent_name: str):
        """创建一个最小的 sender 代理对象，用于 VIS 转换器"""

        class SenderProxy:
            def __init__(self, name):
                self.name = name
                self.role = "assistant"
                self.agent_context = type(
                    "obj",
                    (object,),
                    {
                        "conv_session_id": name,
                        "agent_app_code": name,
                    },
                )()

        return SenderProxy(agent_name)

    async def _cleanup_loop(self):
        while self._state == RuntimeState.RUNNING:
            await asyncio.sleep(self.config.cleanup_interval)

            now = datetime.now()
            to_close = []

            for session_id, context in self._sessions.items():
                idle_seconds = (now - context.last_active).total_seconds()
                if idle_seconds > self.config.session_timeout:
                    to_close.append(session_id)

            for session_id in to_close:
                await self.close_session(session_id)

            if to_close:
                logger.info(f"[V2Runtime] 清理了 {len(to_close)} 个超时会话")

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self._state.value,
            "total_sessions": len(self._sessions),
            "running_sessions": sum(
                1 for s in self._sessions.values() if s.state == RuntimeState.RUNNING
            ),
            "registered_agents": list(self._agents.keys()),
            "config": {
                "max_concurrent_sessions": self.config.max_concurrent_sessions,
                "session_timeout": self.config.session_timeout,
                "enable_streaming": self.config.enable_streaming,
            },
        }

    async def get_queue_iterator(self, session_id: str) -> Optional[AsyncIterator]:
        context = self._sessions.get(session_id)
        if not context or not self.gpts_memory:
            return None

        return await self.gpts_memory.queue_iterator(context.conv_id)

    # ============== 分层上下文管理 ==============

    @property
    def context_middleware(self) -> Optional[Any]:
        """获取分层上下文中间件"""
        return self._context_middleware

    async def load_context_for_session(
        self,
        session_id: str,
        task_description: Optional[str] = None,
        force_reload: bool = False,
    ) -> Optional[Any]:
        """
        为会话加载分层上下文

        Args:
            session_id: 会话 ID
            task_description: 任务描述
            force_reload: 是否强制重新加载

        Returns:
            ContextLoadResult 或 None
        """
        context = self._sessions.get(session_id)
        if not context:
            return None

        if not self._context_middleware:
            return None

        try:
            return await self._context_middleware.load_context(
                conv_id=context.conv_id,
                task_description=task_description,
                force_reload=force_reload,
            )
        except Exception as e:
            logger.error(f"[V2Runtime] 加载上下文失败: {e}")
            return None

    async def record_execution_step(
        self,
        session_id: str,
        action_out: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        记录执行步骤到分层上下文

        Args:
            session_id: 会话 ID
            action_out: 动作输出
            metadata: 元数据

        Returns:
            Section ID 或 None
        """
        context = self._sessions.get(session_id)
        if not context or not self._context_middleware:
            return None

        try:
            return await self._context_middleware.record_step(
                conv_id=context.conv_id,
                action_out=action_out,
                metadata=metadata,
            )
        except Exception as e:
            logger.error(f"[V2Runtime] 记录执行步骤失败: {e}")
            return None

    def get_context_stats(self, session_id: str) -> Dict[str, Any]:
        """
        获取上下文统计信息

        Args:
            session_id: 会话 ID

        Returns:
            统计信息字典
        """
        context = self._sessions.get(session_id)
        if not context or not self._context_middleware:
            return {"error": "Context not available"}

        return self._context_middleware.get_statistics(context.conv_id)
