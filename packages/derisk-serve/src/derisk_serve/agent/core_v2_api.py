"""
Core_v2 API 路由

支持 VIS 可视化组件渲染 (vis_window3 协议)
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter
from fastapi import Request as FastAPIRequest
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .core_v2_adapter import get_core_v2
from derisk.agent.core_v2.vis_converter import CoreV2VisWindow3Converter
from derisk.storage.chat_history.chat_history_db import ChatHistoryDao, ChatHistoryEntity
from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao, GptsConversationsEntity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["Core_v2 Agent"])

_vis_converter = CoreV2VisWindow3Converter()


class ChatRequest(BaseModel):
    message: Optional[str] = None
    user_input: Optional[str] = None  # 兼容前端传递的字段名
    session_id: Optional[str] = None
    conv_uid: Optional[str] = None  # 兼容前端传递的字段名
    agent_name: Optional[str] = None
    app_code: Optional[str] = None
    user_id: Optional[str] = None

    def get_message(self) -> str:
        """获取用户消息，优先使用 user_input"""
        return self.user_input or self.message or ""

    def get_session_id(self) -> Optional[str]:
        """获取 session_id，兼容 conv_uid"""
        return self.session_id or self.conv_uid  


class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = None
    agent_name: Optional[str] = None
    app_code: Optional[str] = None


@router.post("/chat")
async def chat(request: ChatRequest, http_request: FastAPIRequest):
    """
    发送消息 (流式响应)

    返回与 V1 兼容的 vis 格式 (markdown 代码块)
    """
    core_v2 = get_core_v2()
    if not core_v2.dispatcher:
        await core_v2.start()

    app_code = request.app_code or request.agent_name or "default"
    message = request.get_message()
    session_id = request.get_session_id()

    user_id = request.user_id or http_request.headers.get("user-id")

    if session_id:
        try:
            gpts_conv_dao = GptsConversationsDao()
            existing = gpts_conv_dao.get_by_conv_id(session_id)
            if not existing:
                user_goal = message[:6500] if message else ""
                gpts_conv_dao.add(
                    GptsConversationsEntity(
                        conv_id=session_id,
                        conv_session_id=session_id,
                        user_goal=user_goal,
                        gpts_name=app_code,
                        team_mode="core_v2",
                        state="running",
                        max_auto_reply_round=0,
                        auto_reply_count=0,
                        user_code=user_id,
                        sys_code="",
                    )
                )
                logger.info(f"Created gpts_conversations record for session: {session_id}")

            # Update chat_history summary from "New Conversation" to actual user message
            if message:
                try:
                    chat_history_dao = ChatHistoryDao()
                    entity = chat_history_dao.get_by_uid(session_id)
                    if entity and (not entity.summary or entity.summary == "New Conversation"):
                        entity.summary = message[:100]
                        chat_history_dao.raw_update(entity)
                except Exception as e:
                    logger.warning(f"Failed to update chat_history summary: {e}")
        except Exception as e:
            logger.warning(f"Failed to persist v2 conversation: {e}")

    async def generate():
        # State tracking for incremental vis_window3 conversion
        message_id = str(uuid.uuid4().hex)
        accumulated_content = ""
        is_first_chunk = True

        try:
            async for chunk in core_v2.dispatcher.dispatch_and_wait(
                message=message,
                session_id=session_id,
                agent_name=app_code,
                user_id=user_id,
            ):
                # Build stream_msg dict matching the vis_window3 protocol
                # (same structure as V2AgentRuntime._push_stream_chunk)
                is_thinking = chunk.type == "thinking"
                if chunk.type == "response":
                    accumulated_content += chunk.content or ""

                stream_msg = {
                    "uid": message_id,
                    "type": "incr",
                    "message_id": message_id,
                    "conv_id": session_id or "",
                    "conv_session_uid": session_id or "",
                    "goal_id": message_id,
                    "task_goal_id": message_id,
                    "sender": app_code,
                    "sender_name": app_code,
                    "sender_role": "assistant",
                    "thinking": chunk.content if is_thinking else None,
                    "content": "" if is_thinking else (chunk.content or ""),
                    "prev_content": accumulated_content,
                    "start_time": datetime.now(),
                }

                # Use CoreV2VisWindow3Converter for proper vis_window3 output
                vis_content = await _vis_converter.visualization(
                    messages=[],
                    stream_msg=stream_msg,
                    is_first_chunk=is_first_chunk,
                    is_first_push=is_first_chunk,
                )
                is_first_chunk = False

                if vis_content:
                    data = {"vis": vis_content}
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                # V1 uses [DONE] to mark end of stream
                if chunk.is_final:
                    yield f"data: {json.dumps({'vis': '[DONE]'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'vis': f'[ERROR]{str(e)}[/ERROR]'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/session")
async def create_session(request: CreateSessionRequest):
    """
    创建新会话

    agent_name/app_code: 数据库中的应用代码 (gpts_name)
    """
    core_v2 = get_core_v2()
    if not core_v2.runtime:
        await core_v2.start()

    app_code = request.app_code or request.agent_name or "default"

    session = await core_v2.runtime.create_session(
        user_id=request.user_id,
        agent_name=app_code,
    )

    # 写入 chat_history 表，以便历史会话列表能够显示
    try:
        chat_history_dao = ChatHistoryDao()
        entity = ChatHistoryEntity(
            conv_uid=session.conv_id,
            chat_mode="chat_agent",
            summary="New Conversation",
            user_name=request.user_id,
            app_code=app_code,
        )
        chat_history_dao.raw_update(entity)
        logger.info(f"Created chat_history record for conv_id: {session.conv_id}")
    except Exception as e:
        logger.warning(f"Failed to create chat_history record: {e}")

    return {
        "session_id": session.session_id,
        "conv_id": session.conv_id,
        "agent_name": session.agent_name,
    }


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    core_v2 = get_core_v2()
    if not core_v2.runtime:
        await core_v2.start()
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
    if not core_v2.runtime:
        await core_v2.start()
    await core_v2.runtime.close_session(session_id)
    return {"status": "closed"}


@router.get("/status")
async def get_status():
    """获取 Core_v2 状态"""
    core_v2 = get_core_v2()
    if not core_v2.dispatcher:
        await core_v2.start()
    return core_v2.dispatcher.get_status()
