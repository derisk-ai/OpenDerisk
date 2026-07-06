"""V2 Chat API 端点 - 独立于 BAIZE 的 SSE 接口。

设计文档 §6.1。
"""
import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from derisk.agent.core.v2.v2_event_emitter import V2EventEmitter
from derisk.agent.core.v2.v2_vis_component import VisComponentTag, VisOperationType
from derisk_serve.agent.agents.chat.v2_chat_schemas import V2ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["V2 Chat"])


@router.post("/chat")
async def v2_chat(request: V2ChatRequest):
    """V2 Chat SSE 端点

    独立于 BAIZE 的 /api/v2/chat/completions，使用简化 VIS 协议。

    Args:
        request: V2ChatRequest

    Returns:
        StreamingResponse (SSE 格式: data:{json}\n\n)
    """
    step_id = f"step-{uuid.uuid4().hex[:8]}"
    conv_id = request.conv_id or f"conv-{uuid.uuid4().hex[:8]}"

    logger.info(
        f"[V2] chat start: agent_id={request.agent_id}, "
        f"conv_id={conv_id}, step_id={step_id}"
    )

    async def event_stream():
        """生成 V2 SSE 事件流"""
        emitter = V2EventEmitter(
            step_id=step_id,
            agent_id=request.agent_id,
            conv_id=conv_id,
        )

        # 1. step_start
        event = await emitter.emit_step_start()
        yield f"data:{json.dumps(event)}\n\n"

        # 2. step_status THINKING
        event = await emitter.emit_step_status("THINKING")
        yield f"data:{json.dumps(event)}\n\n"

        # 3. VIS: step_status 指示器
        event = await emitter.emit_vis_update(
            type=VisOperationType.REPLACE,
            uid=f"{step_id}-step_status-0",
            tag=VisComponentTag.STEP_STATUS,
            content="",
            meta={"state": "THINKING", "step_id": step_id},
        )
        yield f"data:{json.dumps(event)}\n\n"

        # 4. Mock LLM token 流（后续接入真实 LLM）
        mock_tokens = ["我", "来", "帮", "你", "分析"]
        for token in mock_tokens:
            event = await emitter.emit_llm_token(token)
            yield f"data:{json.dumps(event)}\n\n"

            # VIS: thinking 块追加
            event = await emitter.emit_vis_update(
                type=VisOperationType.INCR,
                uid=f"{step_id}-thinking-0",
                tag=VisComponentTag.THINKING,
                content=token,
            )
            yield f"data:{json.dumps(event)}\n\n"

        # 5. step_end
        event = await emitter.emit_step_end(had_tool_calls=False)
        yield f"data:{json.dumps(event)}\n\n"

        # 6. VIS: step_status 更新为 DONE
        event = await emitter.emit_vis_update(
            type=VisOperationType.REPLACE,
            uid=f"{step_id}-step_status-0",
            tag=VisComponentTag.STEP_STATUS,
            content="",
            meta={"state": "DONE", "step_id": step_id},
        )
        yield f"data:{json.dumps(event)}\n\n"

        # 7. done
        event = await emitter.emit_done()
        yield f"data:{json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def v2_status():
    """V2 服务状态检查"""
    return {
        "status": "ok",
        "version": "v2",
        "protocol": "simplified-vis",
    }
