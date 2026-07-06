"""V2事件发射器 - 负责生成V2 SSE事件。

设计文档 §6.2。
"""
import time
from typing import Any, Dict, Optional

from derisk.agent.core.v2.v2_event_types import V2Event, VIS_UPDATE
from derisk.agent.core.v2.v2_vis_component import (
    SimplifiedVisComponent,
    VisOperationType,
    VisComponentTag,
)


class V2EventEmitter:
    """V2事件发射器

    负责生成符合V2 SSE协议的事件，包含：
    - seq序列号（单调递增）
    - ts时间戳（毫秒）
    - payload事件数据

    使用方式：
        emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")
        event = await emitter.emit("step_start", {"state": "INIT"})
        vis_event = await emitter.emit_vis_update(...)
    """

    def __init__(self, step_id: str, agent_id: str, conv_id: str):
        self.step_id = step_id
        self.agent_id = agent_id
        self.conv_id = conv_id
        self._seq: int = 0

    async def emit(self, event_type: str, payload: Dict[str, Any]) -> V2Event:
        """发射一个V2事件

        Args:
            event_type: 事件类型（如"step_start", "llm_token"等）
            payload: 事件数据

        Returns:
            V2Event dict，可直接JSON序列化为SSE data行
        """
        self._seq += 1
        return V2Event(
            event=event_type,
            seq=self._seq,
            ts=int(time.time() * 1000),
            payload=payload,
        )

    async def emit_vis_update(
        self,
        type: VisOperationType,
        uid: str,
        tag: VisComponentTag,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> V2Event:
        """发射VIS更新事件

        Args:
            type: 操作类型（incr/replace/delete）
            uid: 组件UID
            tag: 组件标签
            content: 内容
            meta: 元数据（可选）

        Returns:
            V2Event，event类型为"vis_update"
        """
        component = SimplifiedVisComponent(
            type=type,
            uid=uid,
            tag=tag,
            content=content,
            meta=meta,
        )
        return await self.emit(VIS_UPDATE, component.to_dict())

    async def emit_step_start(self) -> V2Event:
        """发射step_start事件"""
        return await self.emit("step_start", {
            "step_id": self.step_id,
            "state": "INIT",
            "agent_id": self.agent_id,
        })

    async def emit_step_status(self, state: str) -> V2Event:
        """发射step_status事件"""
        return await self.emit("step_status", {
            "step_id": self.step_id,
            "state": state,
        })

    async def emit_llm_token(
        self, token: str, usage: Optional[Dict] = None
    ) -> V2Event:
        """发射llm_token事件"""
        payload = {"token": token}
        if usage:
            payload["usage"] = usage
        return await self.emit("llm_token", payload)

    async def emit_tool_call(
        self, tool: str, args: Dict, tool_call_id: str
    ) -> V2Event:
        """发射tool_call事件"""
        return await self.emit("tool_call", {
            "tool": tool,
            "args": args,
            "tool_call_id": tool_call_id,
        })

    async def emit_tool_result(
        self, tool_call_id: str, result: Any, success: bool
    ) -> V2Event:
        """发射tool_result事件"""
        return await self.emit("tool_result", {
            "tool_call_id": tool_call_id,
            "result": result,
            "success": success,
        })

    async def emit_step_end(self, had_tool_calls: bool) -> V2Event:
        """发射step_end事件"""
        return await self.emit("step_end", {
            "step_id": self.step_id,
            "state": "DONE",
            "had_tool_calls": had_tool_calls,
        })

    async def emit_done(self) -> V2Event:
        """发射done事件"""
        return await self.emit("done", {})

    async def emit_error(
        self, message: str, code: Optional[str] = None
    ) -> V2Event:
        """发射error事件"""
        payload = {"message": message}
        if code:
            payload["code"] = code
        return await self.emit("error", payload)
