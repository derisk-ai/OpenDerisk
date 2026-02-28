"""
Core_v2 API 路由
"""
import json
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .core_v2_adapter import get_core_v2

router = APIRouter(prefix="/api/v2", tags=["Core_v2 Agent"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    agent_name: str = "simple_chat"


class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = None
    agent_name: str = "simple_chat"


@router.post("/chat")
async def chat(request: ChatRequest):
    """发送消息 (流式响应)"""
    core_v2 = get_core_v2()
    
    async def generate():
        async for chunk in core_v2.dispatcher.dispatch_and_wait(
            message=request.message,
            session_id=request.session_id,
            agent_name=request.agent_name,
        ):
            data = {
                "type": chunk.type,
                "content": chunk.content,
                "metadata": chunk.metadata,
                "is_final": chunk.is_final,
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/session")
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    core_v2 = get_core_v2()
    session = await core_v2.runtime.create_session(
        user_id=request.user_id,
        agent_name=request.agent_name,
    )
    return {
        "session_id": session.session_id,
        "conv_id": session.conv_id,
        "agent_name": session.agent_name,
    }


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    core_v2 = get_core_v2()
    session = await core_v2.runtime.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    return {
        "session_id": session.session_id,
        "conv_id": session.conv_id,
        "state": session.state.value,
        "message_count": session.message_count,
    }


@router.delete("/session/{session_id}")
async def close_session(session_id: str):
    """关闭会话"""
    core_v2 = get_core_v2()
    await core_v2.runtime.close_session(session_id)
    return {"status": "closed"}


@router.get("/status")
async def get_status():
    """获取 Core_v2 状态"""
    core_v2 = get_core_v2()
    return core_v2.dispatcher.get_status()
