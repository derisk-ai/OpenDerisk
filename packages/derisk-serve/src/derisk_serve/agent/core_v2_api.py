"""
Core_v2 API 路由

支持 VIS 可视化组件渲染 (vis_window3 协议)
支持文件输入 (image_url, file_url)
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from fastapi import APIRouter
from fastapi import Request as FastAPIRequest
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .core_v2_adapter import get_core_v2
from derisk.agent.core_v2.vis_converter import CoreV2VisWindow3Converter
from derisk.storage.chat_history.chat_history_db import (
    ChatHistoryDao,
    ChatHistoryEntity,
)
from derisk_serve.agent.db.gpts_conversations_db import (
    GptsConversationsDao,
    GptsConversationsEntity,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["Core_v2 Agent"])

_vis_converter = CoreV2VisWindow3Converter()


class ImageURLContent(BaseModel):
    """图片URL内容"""

    url: str
    file_name: Optional[str] = None
    file_id: Optional[str] = None


class FileURLContent(BaseModel):
    """文件URL内容"""

    url: str
    file_name: Optional[str] = None
    file_id: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None


class UserInputItem(BaseModel):
    """用户输入项，支持文本、图片、文件"""

    type: str = Field(..., description="类型: text, image_url, file_url")
    text: Optional[str] = None
    image_url: Optional[ImageURLContent] = None
    file_url: Optional[FileURLContent] = None


class ChatRequest(BaseModel):
    message: Optional[str] = None
    user_input: Optional[Union[str, List[UserInputItem]]] = None  # 支持字符串或文件列表
    session_id: Optional[str] = None
    conv_uid: Optional[str] = None  # 兼容前端传递的字段名
    agent_name: Optional[str] = None
    app_code: Optional[str] = None
    user_id: Optional[str] = None
    extend_context: Optional[Dict[str, Any]] = None  # 扩展上下文，可包含 userInputs

    def get_message(self) -> str:
        """获取用户消息，优先使用 user_input"""
        if isinstance(self.user_input, str):
            return self.user_input or self.message or ""
        elif isinstance(self.user_input, list):
            text_items = [
                item.text
                for item in self.user_input
                if item.type == "text" and item.text
            ]
            return " ".join(text_items) or self.message or ""
        return self.message or ""

    def get_session_id(self) -> Optional[str]:
        """获取 session_id，兼容 conv_uid"""
        return self.session_id or self.conv_uid

    def get_user_inputs(self) -> List[Dict[str, Any]]:
        """获取用户输入列表，统一转换为字典格式"""
        result = []

        if isinstance(self.user_input, str) and self.user_input.strip():
            result.append({"type": "text", "text": self.user_input})
        elif isinstance(self.user_input, list):
            for item in self.user_input:
                item_dict = item.model_dump(exclude_none=True)
                result.append(item_dict)

        if self.extend_context and "userInputs" in self.extend_context:
            for ui in self.extend_context["userInputs"]:
                if isinstance(ui, dict) and ui not in result:
                    result.append(ui)

        return result


class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = None
    agent_name: Optional[str] = None
    app_code: Optional[str] = None


@router.post("/chat")
async def chat(request: ChatRequest, http_request: FastAPIRequest):
    """
    发送消息 (流式响应)

    返回与 V1 兼容的 vis 格式 (markdown 代码块)
    支持文件输入 (image_url, file_url)
    """
    core_v2 = get_core_v2()
    if not core_v2.dispatcher:
        await core_v2.start()

    app_code = request.app_code or request.agent_name or "default"
    message = request.get_message()
    session_id = request.get_session_id()
    user_inputs = request.get_user_inputs()

    user_id = request.user_id or http_request.headers.get("user-id")

    multimodal_contents = []
    sandbox_file_refs = []

    if user_inputs:
        try:
            from derisk_serve.agent.file_io import (
                process_chat_input_files,
                build_enhanced_query_with_files,
            )

            result = await process_chat_input_files(
                user_inputs=user_inputs,
                sandbox=None,
                conv_id=session_id,
            )

            multimodal_contents = result.multimodal_contents
            sandbox_file_refs = result.sandbox_file_refs

            if sandbox_file_refs:
                file_names = [ref.file_name for ref in sandbox_file_refs]
                logger.info(
                    f"[v2/chat] Processed {len(sandbox_file_refs)} files: {file_names}"
                )

                if not multimodal_contents:
                    message = build_enhanced_query_with_files(
                        message, sandbox_file_refs
                    )
                    logger.info(f"[v2/chat] Enhanced message with file references")

        except ImportError:
            logger.warning(
                "[v2/chat] file_io module not available, skipping file processing"
            )
        except Exception as e:
            logger.error(f"[v2/chat] Failed to process user files: {e}")

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
                logger.info(
                    f"Created gpts_conversations record for session: {session_id}"
                )

            if message:
                try:
                    chat_history_dao = ChatHistoryDao()
                    entity = chat_history_dao.get_by_uid(session_id)
                    if entity and (
                        not entity.summary or entity.summary == "New Conversation"
                    ):
                        entity.summary = message[:100]
                        chat_history_dao.raw_update(entity)
                except Exception as e:
                    logger.warning(f"Failed to update chat_history summary: {e}")
        except Exception as e:
            logger.warning(f"Failed to persist v2 conversation: {e}")

    async def generate():
        message_id = str(uuid.uuid4().hex)
        accumulated_content = ""
        is_first_chunk = True

        try:
            async for chunk in core_v2.dispatcher.dispatch_and_wait(
                message=message,
                session_id=session_id,
                agent_name=app_code,
                user_id=user_id,
                multimodal_contents=multimodal_contents,
                sandbox_file_refs=sandbox_file_refs,
            ):
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
