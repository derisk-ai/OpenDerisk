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
from derisk.agent.core_v2.integration.action_report_builder import (
    build_action_report_from_chunk,
)
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

_vis_converter_default = CoreV2VisWindow3Converter()


async def _resolve_vis_converter(app_code: str):
    """根据应用的 layout 配置动态选择 VIS 转换器"""
    try:
        core_v2 = get_core_v2()
        from derisk_serve.building.app.config import SERVE_SERVICE_COMPONENT_NAME
        from derisk_serve.building.app.service.service import Service

        app_service = core_v2.system_app.get_component(
            SERVE_SERVICE_COMPONENT_NAME, Service
        )
        gpt_app = await app_service.app_detail(
            app_code, specify_config_code=None, building_mode=False
        )
        if gpt_app and gpt_app.layout and gpt_app.layout.chat_layout:
            layout_name = gpt_app.layout.chat_layout.name
            if layout_name == "vis_manus":
                from derisk_ext.vis.derisk.derisk_vis_manus_converter import (
                    DeriskIncrVisManusConverter,
                )
                logger.info(f"[v2/chat] Using vis_manus converter for app: {app_code}")
                return DeriskIncrVisManusConverter()
            elif layout_name in ("vis_window3", "derisk_vis_window"):
                try:
                    from derisk_ext.vis.derisk.derisk_vis_window3_converter import (
                        DeriskIncrVisWindow3Converter,
                    )
                    return DeriskIncrVisWindow3Converter()
                except ImportError:
                    pass
    except Exception as e:
        logger.debug(f"[v2/chat] Failed to resolve vis converter for {app_code}: {e}")
    return _vis_converter_default


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

    # 解析应用显示名称（用于 VIS 渲染，避免显示 UUID）
    display_name = await core_v2.resolve_app_display_name(app_code)

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
                # 注意: 文件路径信息将在 runtime 中更新并注入到 message

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
        _vis_converter = await _resolve_vis_converter(app_code)

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

                # Emit ask_user event for interaction requests
                if chunk.type == "ask_user":
                    ask_user_event = {
                        "type": "interaction_request",
                        "request_id": chunk.metadata.get("request_id", ""),
                        "conv_id": session_id or "",
                    }
                    yield f"data: {json.dumps(ask_user_event, ensure_ascii=False)}\n\n"
                    continue

                is_tool = chunk.type in ("tool_start", "tool_result")
                stream_msg = {
                    "uid": message_id,
                    "type": "incr",
                    "message_id": message_id,
                    "conv_id": session_id or "",
                    "conv_session_uid": session_id or "",
                    "goal_id": message_id,
                    "task_goal_id": message_id,
                    "sender": app_code,
                    "sender_name": display_name,
                    "sender_role": "assistant",
                    "model": chunk.metadata.get("model") if chunk.metadata else None,
                    "thinking": chunk.content if is_thinking else None,
                    "content": ""
                    if (is_thinking or is_tool)
                    else (chunk.content or ""),
                    "prev_content": accumulated_content,
                    "start_time": datetime.now(),
                }

                # 为工具类型的 chunk 构建 action_report
                if is_tool:
                    action_report = build_action_report_from_chunk(chunk)
                    if action_report:
                        stream_msg["action_report"] = action_report

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

    # 解析应用布局配置
    layout_name = None
    try:
        from derisk_serve.building.app.config import SERVE_SERVICE_COMPONENT_NAME
        from derisk_serve.building.app.service.service import Service
        app_service = core_v2.system_app.get_component(
            SERVE_SERVICE_COMPONENT_NAME, Service
        )
        gpt_app = await app_service.app_detail(
            app_code, specify_config_code=None, building_mode=False
        )
        if gpt_app and gpt_app.layout and gpt_app.layout.chat_layout:
            layout_name = gpt_app.layout.chat_layout.name
    except Exception as e:
        logger.debug(f"[v2/session] Failed to resolve layout for {app_code}: {e}")

    session = await core_v2.runtime.create_session(
        user_id=request.user_id,
        agent_name=app_code,
        layout_name=layout_name,
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


class StepOutputRequest(BaseModel):
    """请求某个执行步骤的右面板数据"""
    session_id: str
    step_id: str
    app_code: Optional[str] = None


@router.post("/step-output")
async def get_step_output(request: StepOutputRequest):
    """
    获取指定步骤的右面板渲染数据

    用于 Manus 布局中用户切换执行步骤时，按需加载步骤详情。
    前端不缓存所有步骤数据，仅保留当前步骤，切换时从后端获取。
    """
    core_v2 = get_core_v2()
    if not core_v2.runtime:
        await core_v2.start()

    session_id = request.session_id
    step_id = request.step_id

    # 从 gpts_memory 中查找对应步骤的消息
    if not core_v2.runtime.gpts_memory:
        return {"error": "Memory not available"}

    try:
        cache = await core_v2.runtime.gpts_memory._get_cache(session_id)
        if not cache:
            return {"error": "Session cache not found"}

        vis_converter = cache.vis_converter
        if not hasattr(vis_converter, '_steps') or not hasattr(vis_converter, '_outputs'):
            return {"error": "Converter does not support step output retrieval"}

        # 检查步骤是否存在
        step = vis_converter._steps.get(step_id)
        if not step:
            return {"error": f"Step {step_id} not found"}

        # 构建该步骤的右面板数据
        from derisk.agent.core_v2.vis_manus_protocol import (
            ManusActiveStepInfo,
            ManusRightPanelData,
            ManusPanelView,
            ManusStepType,
        )

        active_step_info = ManusActiveStepInfo(
            id=step.id,
            type=step.type,
            title=step.title,
            subtitle=step.subtitle,
            status=step.status,
            detail=step.description,
        )
        outputs = vis_converter._outputs.get(step_id, [])

        panel_view = ManusPanelView.EXECUTION.value
        if active_step_info.type == ManusStepType.HTML.value:
            panel_view = ManusPanelView.HTML_PREVIEW.value
        elif active_step_info.type == ManusStepType.SKILL.value:
            panel_view = ManusPanelView.SKILL_PREVIEW.value

        right_panel = ManusRightPanelData(
            active_step=active_step_info,
            outputs=outputs,
            is_running=False,
            panel_view=panel_view,
        )

        return right_panel.to_dict()
    except Exception as e:
        logger.error(f"[v2/step-output] Error: {e}")
        return {"error": str(e)}


@router.get("/status")
async def get_status():
    """获取 Core_v2 状态"""
    core_v2 = get_core_v2()
    if not core_v2.dispatcher:
        await core_v2.start()
    return core_v2.dispatcher.get_status()
