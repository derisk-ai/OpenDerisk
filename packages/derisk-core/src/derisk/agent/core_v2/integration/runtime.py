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


class V2AgentRuntime:
    """
    V2 Agent 运行时

    核心职责:
    1. Session 生命周期管理
    2. Agent 执行调度
    3. 消息流处理和推送
    4. 与 GptsMemory 集成
    5. 前端交互支持
    """

    def __init__(
        self,
        config: RuntimeConfig = None,
        gpts_memory: Any = None,
        adapter: V2Adapter = None,
    ):
        self.config = config or RuntimeConfig()
        self.gpts_memory = gpts_memory
        self.adapter = adapter or V2Adapter()

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
        if self.gpts_memory and hasattr(self.gpts_memory, "start"):
            await self.gpts_memory.start()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[V2Runtime] 运行时已启动")

    async def stop(self):
        self._state = RuntimeState.TERMINATED
        if self._cleanup_task:
            self._cleanup_task.cancel()
        for task in self._execution_tasks.values():
            task.cancel()
        if self.gpts_memory and hasattr(self.gpts_memory, "shutdown"):
            await self.gpts_memory.shutdown()
        logger.info("[V2Runtime] 运行时已停止")

    async def create_session(
        self,
        conv_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: str = "primary",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        if len(self._sessions) >= self.config.max_concurrent_sessions:
            raise RuntimeError("达到最大并发会话数限制")

        session_id = str(uuid.uuid4().hex)
        conv_id = conv_id or session_id

        context = SessionContext(
            session_id=session_id,
            conv_id=conv_id,
            user_id=user_id,
            agent_name=agent_name,
            metadata=metadata or {},
        )

        self._sessions[session_id] = context
        self._message_queues[session_id] = asyncio.Queue(maxsize=100)

        if self.gpts_memory:
            await self.gpts_memory.init(conv_id)

        logger.info(f"[V2Runtime] 创建会话: {session_id[:8]}, conv_id: {conv_id[:8]}")
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
        **kwargs,
    ) -> AsyncIterator[V2StreamChunk]:
        context = await self.get_session(session_id)
        if not context:
            yield V2StreamChunk(type="error", content="会话不存在")
            return

        context.state = RuntimeState.RUNNING
        context.last_active = datetime.now()
        context.message_count += 1

        agent = await self._get_or_create_agent(context, kwargs)
        if not agent:
            yield V2StreamChunk(type="error", content="Agent 不存在")
            return

        try:
            conv_id = context.conv_id

            if self.gpts_memory:
                await self._push_user_message(conv_id, message)

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

        if agent_name in self._agents:
            return self._agents[agent_name]

        if agent_name in self._agent_factories:
            agent = await self._create_agent_from_factory(agent_name, context, kwargs)
            self._agents[agent_name] = agent
            return agent

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
            return agent
        except Exception as e:
            logger.error(f"[V2Runtime] 创建 Agent 失败: {e}")
            return None

    async def _execute_stream(
        self,
        agent: Any,
        message: str,
        context: SessionContext,
        **kwargs,
    ) -> AsyncIterator[V2StreamChunk]:
        from ..agent_base import AgentBase, AgentState

        if isinstance(agent, AgentBase):
            agent_context = self.adapter.context_bridge.create_v2_context(
                conv_id=context.conv_id,
                session_id=context.session_id,
                user_id=context.user_id,
            )
            await agent.initialize(agent_context)

            async for chunk in agent.run(message, stream=True, **kwargs):
                parsed = self._parse_agent_output(chunk)
                yield parsed

        elif hasattr(agent, "generate_reply"):
            response = await agent.generate_reply(
                received_message={"content": message},
                sender=None,
                **kwargs,
            )
            content = getattr(response, "content", str(response))
            yield V2StreamChunk(type="response", content=content, is_final=True)

        else:
            yield V2StreamChunk(type="error", content="不支持的 Agent 类型")

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
            parts = output.split("]", 1)
            tool_name = parts[0].replace("[TOOL:", "")
            content = parts[1].replace("[/TOOL]", "") if len(parts) > 1 else ""
            return V2StreamChunk(
                type="tool_call",
                content=content,
                metadata={"tool_name": tool_name},
            )
        elif output.startswith("[ERROR]"):
            content = output.replace("[ERROR]", "").replace("[/ERROR]", "")
            return V2StreamChunk(type="error", content=content)
        elif output.startswith("[TERMINATE]"):
            content = output.replace("[TERMINATE]", "").strip()
            return V2StreamChunk(type="response", content=content, is_final=True)
        elif output.startswith("[WARNING]"):
            content = output.replace("[WARNING]", "").replace("[WARNING]", "")
            return V2StreamChunk(type="response", content=content)
        elif output.startswith("[INFO]"):
            content = output.replace("[INFO]", "").replace("[INFO]", "")
            return V2StreamChunk(type="response", content=content)
        else:
            return V2StreamChunk(type="response", content=output)

    async def _push_user_message(self, conv_id: str, message: str):
        from derisk.agent.core.memory.gpts.base import GptsMessage

        if not self.gpts_memory:
            return

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

        await self.gpts_memory.append_message(conv_id, user_msg, save_db=False)

    async def _push_stream_chunk(self, conv_id: str, chunk: V2StreamChunk):
        if not self.gpts_memory:
            return

        vis_content = self.adapter.message_converter.stream_chunk_to_vis(chunk)

        await self.gpts_memory.push_message(
            conv_id,
            stream_msg={
                "type": chunk.type,
                "content": vis_content,
                "metadata": chunk.metadata,
            },
        )

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
