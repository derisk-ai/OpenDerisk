"""
V2Adapter - Core_v2 与原架构的集成适配层

核心功能:
1. 消息格式转换 - V2Message 转换为 GptsMessage
2. 资源桥梁 - 连接 AgentResource 体系与 V2 Tool 系统
3. 上下文桥梁 - 连接 V2 AgentContext 与原 AgentContext
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class V2StreamChunk:
    type: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_final: bool = False


class V2MessageConverter:
    """
    消息格式转换器

    负责在 Core_v2 的消息格式与原架构的 GptsMessage 之间转换
    支持 VIS 组件渲染
    """

    def __init__(self, vis_converter: Optional[Any] = None):
        self._vis_converter = vis_converter
        self._vis_tags_cache: Dict[str, Any] = {}

    def _get_vis_tag(self, tag_name: str) -> Optional[Any]:
        from derisk.vis.vis_converter import SystemVisTag

        tag_map = {
            "thinking": SystemVisTag.VisThinking.value,
            "tool": SystemVisTag.VisTool.value,
            "text": SystemVisTag.VisText.value,
            "message": SystemVisTag.VisMessage.value,
        }
        return tag_map.get(tag_name)

    def to_gpts_message(
        self,
        v2_message: Dict[str, Any],
        conv_id: str,
        sender: str = "assistant",
        receiver: str = "user",
    ) -> Dict[str, Any]:
        v2_msg = (
            v2_message if isinstance(v2_message, dict) else {"content": str(v2_message)}
        )

        gpts_msg = {
            "message_id": v2_msg.get("message_id", str(uuid.uuid4().hex)),
            "conv_id": conv_id,
            "sender": v2_msg.get("sender", sender),
            "receiver": v2_msg.get("receiver", receiver),
            "content": v2_msg.get("content", ""),
            "rounds": v2_msg.get("rounds", 0),
            "current_goal": v2_msg.get("current_goal", ""),
            "goal_id": v2_msg.get("goal_id", ""),
            "action_report": v2_msg.get("action_report"),
            "model_name": v2_msg.get("model_name", ""),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "success": v2_msg.get("success", True),
        }
        return gpts_msg

    def to_v2_message(self, gpts_message: Any) -> Dict[str, Any]:
        if hasattr(gpts_message, "to_dict"):
            msg_dict = gpts_message.to_dict()
        elif hasattr(gpts_message, "dict"):
            msg_dict = gpts_message.dict()
        else:
            msg_dict = dict(gpts_message) if gpts_message else {}

        return {
            "role": msg_dict.get("sender", "user"),
            "content": msg_dict.get("content", ""),
            "metadata": {
                "message_id": msg_dict.get("message_id"),
                "conv_id": msg_dict.get("conv_id"),
                "rounds": msg_dict.get("rounds", 0),
                "current_goal": msg_dict.get("current_goal"),
            },
        }

    def stream_chunk_to_vis(
        self,
        chunk: V2StreamChunk,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        将 V2StreamChunk 转换为 VIS 组件格式

        返回 VIS 组件标记，前端可以渲染
        """
        if chunk.type == "thinking":
            return self._render_thinking(chunk)
        elif chunk.type == "tool_call":
            return self._render_tool_call(chunk)
        elif chunk.type == "tool_result":
            return self._render_tool_result(chunk)
        elif chunk.type == "response":
            return self._render_response(chunk)
        elif chunk.type == "error":
            return self._render_error(chunk)
        else:
            return chunk.content

    def _render_thinking(self, chunk: V2StreamChunk) -> str:
        """渲染思考内容为 VIS 组件 (markdown 代码块格式)"""
        return f"```vis-thinking\n{chunk.content}\n```"

    def _render_tool_call(self, chunk: V2StreamChunk) -> str:
        """渲染工具调用为 VIS 组件 (markdown 代码块格式)"""
        import json

        tool_name = chunk.metadata.get("tool_name", "unknown")
        tool_data = {
            "name": tool_name,
            "args": chunk.metadata.get("args", {}),
            "status": "running",
        }
        return f"```vis-tool\n{json.dumps(tool_data, ensure_ascii=False)}\n```"

    def _render_tool_result(self, chunk: V2StreamChunk) -> str:
        """渲染工具结果为 VIS 组件 (markdown 代码块格式)"""
        import json

        tool_name = chunk.metadata.get("tool_name", "unknown")
        tool_data = {
            "name": tool_name,
            "status": "completed",
            "output": chunk.content,
        }
        return f"```vis-tool\n{json.dumps(tool_data, ensure_ascii=False)}\n```"

    def _render_response(self, chunk: V2StreamChunk) -> str:
        """渲染响应内容 - 纯文本格式"""
        return chunk.content or ""

    def _render_error(self, chunk: V2StreamChunk) -> str:
        """渲染错误内容"""
        return f"[ERROR]{chunk.content}[/ERROR]"


class V2ResourceBridge:
    """
    资源桥梁

    将原架构的 AgentResource 体系转换为 Core_v2 的 Tool 和 Resource
    """

    def __init__(self):
        self._resource_map: Dict[str, Any] = {}
        self._tool_registry: Dict[str, Any] = {}

    def register_resource(self, name: str, resource: Any):
        self._resource_map[name] = resource
        logger.info(f"[V2ResourceBridge] 注册资源: {name}")

    def register_tool(self, name: str, tool: Any):
        self._tool_registry[name] = tool
        logger.info(f"[V2ResourceBridge] 注册工具: {name}")

    def get_resource(self, name: str) -> Optional[Any]:
        return self._resource_map.get(name)

    def get_tool(self, name: str) -> Optional[Any]:
        return self._tool_registry.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tool_registry.keys())

    def convert_to_v2_tools(self, resources: List[Any]) -> Dict[str, Any]:
        from derisk.agent.resource import BaseTool
        from derisk.agent.tools import ToolBase

        tools = {}
        for resource in resources:
            if isinstance(resource, BaseTool):
                tool_wrapper = self._wrap_v1_tool(resource)
                tools[resource.name] = tool_wrapper
            elif isinstance(resource, ToolBase):
                tools[resource.info.name] = resource

        return tools

    def _wrap_v1_tool(self, v1_tool: Any) -> Any:
        from derisk.agent.tools.base import ToolBase, ToolMetadata

        class V1ToolWrapper(ToolBase):
            def __init__(self, v1_tool):
                info = ToolInfo(
                    name=v1_tool.name,
                    description=getattr(v1_tool, "description", ""),
                    parameters=getattr(v1_tool, "args", {}),
                )
                super().__init__(info)
                self._v1_tool = v1_tool

            async def execute(self, **kwargs) -> Any:
                if hasattr(self._v1_tool, "execute"):
                    result = self._v1_tool.execute(**kwargs)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                raise NotImplementedError(
                    f"Tool {self._v1_tool.name} has no execute method"
                )

        return V1ToolWrapper(v1_tool)


class V2ContextBridge:
    """
    上下文桥梁

    连接 Core_v2 的 AgentContext 与原架构的 AgentContext
    """

    def __init__(self):
        self._context_map: Dict[str, Any] = {}

    def create_v2_context(
        self,
        conv_id: str,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        from ..agent_base import AgentContext

        context = AgentContext(
            session_id=session_id,
            conversation_id=conv_id,
            user_id=user_id,
            metadata=metadata or {},
        )
        self._context_map[conv_id] = context
        return context

    def get_context(self, conv_id: str) -> Optional[Any]:
        return self._context_map.get(conv_id)

    def update_context(self, conv_id: str, updates: Dict[str, Any]):
        if conv_id in self._context_map:
            context = self._context_map[conv_id]
            for key, value in updates.items():
                if hasattr(context, key):
                    setattr(context, key, value)

    def sync_from_v1_context(self, v1_context: Any) -> Any:
        conv_id = getattr(v1_context, "conv_id", str(uuid.uuid4().hex))
        session_id = getattr(v1_context, "conv_session_id", conv_id)
        user_id = getattr(v1_context, "user_id", None)

        return self.create_v2_context(
            conv_id=conv_id,
            session_id=session_id,
            user_id=user_id,
            metadata={
                "app_code": getattr(v1_context, "agent_app_code", None),
                "language": getattr(v1_context, "language", "en"),
            },
        )


class V2Adapter:
    """
    V2 集成适配器主类

    统一管理消息转换、资源桥梁、上下文桥梁
    """

    def __init__(
        self,
        message_converter: Optional[V2MessageConverter] = None,
        resource_bridge: Optional[V2ResourceBridge] = None,
        context_bridge: Optional[V2ContextBridge] = None,
    ):
        self.message_converter = message_converter or V2MessageConverter()
        self.resource_bridge = resource_bridge or V2ResourceBridge()
        self.context_bridge = context_bridge or V2ContextBridge()

        self._stream_handlers: Dict[str, Callable] = {}
        self._tool_executors: Dict[str, Callable] = {}

    def register_stream_handler(self, event_type: str, handler: Callable):
        self._stream_handlers[event_type] = handler

    def register_tool_executor(self, tool_name: str, executor: Callable):
        self._tool_executors[tool_name] = executor

    async def process_stream(
        self,
        conv_id: str,
        stream: AsyncIterator[str],
        gpts_memory: Any,
    ) -> AsyncIterator[V2StreamChunk]:
        async for chunk in stream:
            if chunk.startswith("[THINKING]"):
                content = chunk.replace("[THINKING]", "").replace("[/THINKING]", "")
                yield V2StreamChunk(type="thinking", content=content)
            elif chunk.startswith("[TOOL:"):
                parts = chunk.split("]", 1)
                tool_name = parts[0].replace("[TOOL:", "")
                content = parts[1].replace("[/TOOL]", "") if len(parts) > 1 else ""
                yield V2StreamChunk(
                    type="tool_call",
                    content=content,
                    metadata={"tool_name": tool_name},
                )
            elif chunk.startswith("[ERROR]"):
                content = chunk.replace("[ERROR]", "").replace("[/ERROR]", "")
                yield V2StreamChunk(type="error", content=content)
            else:
                yield V2StreamChunk(type="response", content=chunk)

    async def push_to_gpts_memory(
        self,
        conv_id: str,
        chunk: V2StreamChunk,
        gpts_memory: Any,
    ):
        if not gpts_memory:
            return

        vis_content = self.message_converter.stream_chunk_to_vis(chunk)

        await gpts_memory.push_message(
            conv_id,
            stream_msg={
                "type": chunk.type,
                "content": vis_content,
                "metadata": chunk.metadata,
            },
        )
