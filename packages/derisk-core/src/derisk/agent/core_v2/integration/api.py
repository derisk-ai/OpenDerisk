"""
V2AgentAPI - 前端 API 接口层

提供 HTTP/WebSocket API 供前端调用
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .dispatcher import V2AgentDispatcher, DispatchPriority
from .runtime import V2AgentRuntime, RuntimeConfig
from .adapter import V2StreamChunk

logger = logging.getLogger(__name__)


@dataclass
class APIConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    websocket_path: str = "/ws"
    api_prefix: str = "/api/v2"


class V2AgentAPI:
    """
    V2 Agent API 服务

    提供以下 API:
    1. POST /api/v2/chat - 发送消息
    2. GET /api/v2/session - 获取会话信息
    3. DELETE /api/v2/session - 关闭会话
    4. WebSocket /ws/{session_id} - 流式消息推送

    示例:
        api = V2AgentAPI(dispatcher)
        await api.start()
    """

    def __init__(
        self,
        dispatcher: V2AgentDispatcher,
        config: APIConfig = None,
    ):
        self.dispatcher = dispatcher
        self.config = config or APIConfig()
        self._websockets: Dict[str, List[Any]] = {}
        self._server = None

    async def start(self):
        await self.dispatcher.start()
        logger.info(f"[V2API] API 服务启动于 {self.config.host}:{self.config.port}")

    async def stop(self):
        for ws_list in self._websockets.values():
            for ws in ws_list:
                try:
                    await ws.close()
                except:
                    pass
        self._websockets.clear()
        await self.dispatcher.stop()
        logger.info("[V2API] API 服务已停止")

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        conv_id: Optional[str] = None,
        user_id: Optional[str] = None,
        stream: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        处理聊天请求

        Args:
            message: 用户消息
            session_id: 会话 ID (可选，不提供则创建新会话)
            conv_id: 对话 ID (可选)
            user_id: 用户 ID (可选)
            stream: 是否流式返回

        Yields:
            Dict: 消息响应
        """
        try:
            if stream:
                async for chunk in self.dispatcher.dispatch_and_wait(
                    message=message,
                    session_id=session_id,
                    conv_id=conv_id,
                    user_id=user_id,
                ):
                    yield self._chunk_to_response(chunk)
            else:
                task_id = await self.dispatcher.dispatch(
                    message=message,
                    session_id=session_id,
                    conv_id=conv_id,
                    user_id=user_id,
                )
                yield {"task_id": task_id, "status": "pending"}

        except Exception as e:
            logger.exception(f"[V2API] 聊天处理错误: {e}")
            yield {"error": str(e)}

    def _chunk_to_response(self, chunk: V2StreamChunk) -> Dict[str, Any]:
        return {
            "type": chunk.type,
            "content": chunk.content,
            "metadata": chunk.metadata,
            "is_final": chunk.is_final,
        }

    async def create_session(
        self,
        user_id: Optional[str] = None,
        agent_name: str = "primary",
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """创建新会话"""
        session = await self.dispatcher.runtime.create_session(
            user_id=user_id,
            agent_name=agent_name,
            metadata=metadata,
        )
        return {
            "session_id": session.session_id,
            "conv_id": session.conv_id,
            "agent_name": session.agent_name,
            "created_at": session.created_at.isoformat(),
        }

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        session = await self.dispatcher.runtime.get_session(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "conv_id": session.conv_id,
            "agent_name": session.agent_name,
            "state": session.state.value,
            "message_count": session.message_count,
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat(),
        }

    async def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        try:
            await self.dispatcher.runtime.close_session(session_id)
            return True
        except Exception as e:
            logger.error(f"[V2API] 关闭会话失败: {e}")
            return False

    async def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return self.dispatcher.get_status()

    def register_websocket(self, session_id: str, websocket: Any):
        """注册 WebSocket 连接"""
        if session_id not in self._websockets:
            self._websockets[session_id] = []
        self._websockets[session_id].append(websocket)

    def unregister_websocket(self, session_id: str, websocket: Any):
        """注销 WebSocket 连接"""
        if session_id in self._websockets:
            try:
                self._websockets[session_id].remove(websocket)
            except ValueError:
                pass

    async def broadcast_to_session(self, session_id: str, message: Dict):
        """向指定会话的所有 WebSocket 广播消息"""
        if session_id not in self._websockets:
            return

        message_json = json.dumps(message, ensure_ascii=False)
        for ws in list(self._websockets[session_id]):
            try:
                await ws.send(message_json)
            except Exception as e:
                logger.error(f"[V2API] WebSocket 发送失败: {e}")
                self.unregister_websocket(session_id, ws)

    async def handle_websocket(self, session_id: str, websocket: Any):
        """处理 WebSocket 连接"""
        self.register_websocket(session_id, websocket)

        try:
            async for data in websocket:
                try:
                    message = json.loads(data)
                    msg_type = message.get("type")

                    if msg_type == "chat":
                        async for response in self.chat(
                            message=message.get("content", ""),
                            session_id=session_id,
                            stream=True,
                        ):
                            await websocket.send(
                                json.dumps(response, ensure_ascii=False)
                            )

                    elif msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))

                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"error": "Invalid JSON"}))

        except Exception as e:
            logger.error(f"[V2API] WebSocket 处理错误: {e}")

        finally:
            self.unregister_websocket(session_id, websocket)


async def create_api_server(
    gpts_memory: Any = None,
    model_provider: Any = None,
    config: APIConfig = None,
) -> V2AgentAPI:
    """
    创建 API 服务器

    Args:
        gpts_memory: GptsMemory 实例
        model_provider: 模型提供者
        config: API 配置

    Returns:
        V2AgentAPI: API 服务器实例
    """
    from .runtime import V2AgentRuntime, RuntimeConfig
    from .dispatcher import V2AgentDispatcher

    runtime_config = RuntimeConfig()
    runtime = V2AgentRuntime(
        config=runtime_config,
        gpts_memory=gpts_memory,
    )

    dispatcher = V2AgentDispatcher(runtime=runtime)

    api = V2AgentAPI(dispatcher=dispatcher, config=config)

    return api
