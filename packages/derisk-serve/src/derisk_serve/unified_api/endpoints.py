"""
统一消息API端点

提供统一的历史消息查询和渲染API
支持Core V1和Core V2架构
"""
import json
import logging
import time
from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException

from derisk.storage.unified_message_dao import UnifiedMessageDAO
from derisk_serve.unified_api.schemas import (
    UnifiedMessageListResponse,
    UnifiedMessageResponse,
    UnifiedRenderResponse,
    UnifiedConversationListResponse,
    UnifiedConversationSummaryResponse,
    APIResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/unified", tags=["Unified API"])


def get_unified_dao() -> UnifiedMessageDAO:
    """获取UnifiedMessageDAO实例
    
    Returns:
        UnifiedMessageDAO实例
    """
    return UnifiedMessageDAO()


@router.get(
    "/conversations",
    response_model=APIResponse
)
async def list_conversations(
    user_id: Optional[str] = Query(None, description="用户ID"),
    sys_code: Optional[str] = Query(None, description="系统代码"),
    filter_text: Optional[str] = Query(None, description="过滤关键字（搜索摘要/目标）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取对话列表（统一API）
    
    同时查询Core V1（chat_history）和Core V2（gpts_conversations）的对话记录
    
    参数:
    - user_id: 用户ID
    - sys_code: 系统代码
    - filter_text: 过滤关键字
    - page: 页码（从1开始）
    - page_size: 每页数量
    """
    try:
        result = await unified_dao.list_conversations(
            user_id=user_id,
            sys_code=sys_code,
            filter_text=filter_text,
            page=page,
            page_size=page_size
        )
        
        conversation_responses = [
            UnifiedConversationSummaryResponse(
                conv_id=conv.conv_id,
                user_id=conv.user_id,
                goal=conv.goal,
                chat_mode=conv.chat_mode,
                state=conv.state,
                message_count=conv.message_count,
                created_at=conv.created_at,
                updated_at=conv.updated_at
            )
            for conv in result["items"]
        ]
        
        response_data = UnifiedConversationListResponse(
            total=result["total_count"],
            conversations=conversation_responses,
            page=result["page"],
            page_size=result["page_size"],
            has_next=result["page"] < result["total_pages"]
        )
        
        return APIResponse.success_response(response_data)
        
    except Exception as e:
        logger.error(f"Failed to list conversations: {e}")
        return APIResponse.error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to list conversations: {str(e)}"
        )


@router.get(
    "/conversations/{conv_id}/messages",
    response_model=APIResponse
)
async def get_conversation_messages(
    conv_id: str,
    limit: Optional[int] = Query(50, ge=1, le=500, description="消息数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    include_thinking: bool = Query(False, description="是否包含思考过程"),
    include_tool_calls: bool = Query(False, description="是否包含工具调用"),
    include_action_report: bool = Query(False, description="是否包含动作报告"),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取对话历史消息（统一API）
    
    支持Core V1和Core V2的消息格式
    
    参数:
    - conv_id: 对话ID
    - limit: 消息数量限制
    - offset: 偏移量
    - include_thinking: 是否包含思考过程（Core V2专用）
    - include_tool_calls: 是否包含工具调用（Core V2专用）
    - include_action_report: 是否包含动作报告（Core V2专用）
    """
    try:
        messages = await unified_dao.get_messages_by_conv_id(
            conv_id=conv_id,
            limit=limit,
            include_thinking=include_thinking
        )
        
        message_responses = []
        for msg in messages:
            response = UnifiedMessageResponse.from_unified_message(msg)
            
            if not include_tool_calls:
                response.tool_calls = None
            
            if not include_action_report:
                response.action_report = None
            
            message_responses.append(response)
        
        response_data = UnifiedMessageListResponse(
            conv_id=conv_id,
            total=len(message_responses),
            messages=message_responses,
            limit=limit,
            offset=offset
        )
        
        return APIResponse.success_response(response_data)
        
    except Exception as e:
        logger.error(f"Failed to get messages for conversation {conv_id}: {e}")
        return APIResponse.error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to get messages: {str(e)}"
        )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=APIResponse
)
async def get_session_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=500, description="消息数量限制"),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取会话历史消息（统一API）
    
    支持按会话分组查询多轮对话
    """
    try:
        messages = await unified_dao.get_messages_by_session(
            session_id=session_id,
            limit=limit
        )
        
        message_responses = [
            UnifiedMessageResponse.from_unified_message(msg)
            for msg in messages
        ]
        
        response_data = UnifiedMessageListResponse(
            session_id=session_id,
            total=len(message_responses),
            messages=message_responses
        )
        
        return APIResponse.success_response(response_data)
        
    except Exception as e:
        logger.error(f"Failed to get messages for session {session_id}: {e}")
        return APIResponse.error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to get messages: {str(e)}"
        )


@router.get(
    "/conversations/{conv_id}/render",
    response_model=APIResponse
)
async def get_conversation_render(
    conv_id: str,
    render_type: str = Query(
        "vis",
        regex="^(vis|markdown|simple)$",
        description="渲染类型: vis(VIS可视化), markdown(Markdown格式), simple(简单格式)"
    ),
    use_cache: bool = Query(True, description="是否使用缓存"),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取对话渲染数据（统一API）
    
    打开历史对话时重新渲染，支持Redis缓存
    
    render_type:
    - vis: VIS可视化格式（Core V2）
    - markdown: Markdown格式（Core V1/V2）
    - simple: 简单格式（Core V1）
    """
    try:
        start_time = time.time()
        cached = False
        
        if use_cache:
            cached_data = await _get_cached_render(conv_id, render_type)
            if cached_data:
                cached = True
                render_time_ms = int((time.time() - start_time) * 1000)
                
                response_data = UnifiedRenderResponse(
                    render_type=render_type,
                    data=cached_data,
                    cached=True,
                    render_time_ms=render_time_ms
                )
                
                return APIResponse.success_response(response_data)
        
        messages = await unified_dao.get_messages_by_conv_id(
            conv_id=conv_id,
            include_thinking=True
        )
        
        if render_type == "vis":
            render_data = await _render_vis(messages)
        elif render_type == "markdown":
            render_data = await _render_markdown(messages)
        else:
            render_data = await _render_simple(messages)
        
        if use_cache and render_data:
            await _set_cached_render(conv_id, render_type, render_data)
        
        render_time_ms = int((time.time() - start_time) * 1000)
        
        response_data = UnifiedRenderResponse(
            render_type=render_type,
            data=render_data,
            cached=False,
            render_time_ms=render_time_ms
        )
        
        return APIResponse.success_response(response_data)
        
    except Exception as e:
        logger.error(f"Failed to render conversation {conv_id}: {e}")
        return APIResponse.error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to render conversation: {str(e)}"
        )


@router.get(
    "/conversations/{conv_id}/messages/latest",
    response_model=APIResponse
)
async def get_latest_messages(
    conv_id: str,
    limit: int = Query(10, ge=1, le=50, description="消息数量"),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取最新的N条消息
    
    用于快速加载最新对话内容
    """
    try:
        messages = await unified_dao.get_latest_messages(
            conv_id=conv_id,
            limit=limit
        )
        
        message_responses = [
            UnifiedMessageResponse.from_unified_message(msg)
            for msg in messages
        ]
        
        response_data = UnifiedMessageListResponse(
            conv_id=conv_id,
            total=len(message_responses),
            messages=message_responses
        )
        
        return APIResponse.success_response(response_data)
        
    except Exception as e:
        logger.error(f"Failed to get latest messages for conversation {conv_id}: {e}")
        return APIResponse.error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to get latest messages: {str(e)}"
        )


async def _get_cached_render(conv_id: str, render_type: str):
    """从Redis获取缓存的渲染数据
    
    Args:
        conv_id: 对话ID
        render_type: 渲染类型
        
    Returns:
        缓存的渲染数据，未命中返回None
    """
    try:
        from derisk.component import SystemApp
        
        system_app = SystemApp.get_instance()
        if not system_app:
            return None
        
        cache_client = system_app.get_component("cache")
        if not cache_client:
            return None
        
        cache_key = f"render:{conv_id}:{render_type}"
        cached_data = await cache_client.get(cache_key)
        
        if cached_data:
            logger.debug(f"Cache hit for {cache_key}")
            return json.loads(cached_data)
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get cache: {e}")
        return None


async def _set_cached_render(conv_id: str, render_type: str, data):
    """将渲染数据缓存到Redis
    
    Args:
        conv_id: 对话ID
        render_type: 渲染类型
        data: 渲染数据
    """
    try:
        from derisk.component import SystemApp
        
        system_app = SystemApp.get_instance()
        if not system_app:
            return
        
        cache_client = system_app.get_component("cache")
        if not cache_client:
            return
        
        cache_key = f"render:{conv_id}:{render_type}"
        await cache_client.set(
            cache_key,
            json.dumps(data, ensure_ascii=False),
            ttl=3600
        )
        
        logger.debug(f"Cache set for {cache_key}")
        
    except Exception as e:
        logger.warning(f"Failed to set cache: {e}")


async def _render_vis(messages: list) -> dict:
    """VIS可视化渲染
    
    Args:
        messages: UnifiedMessage列表
        
    Returns:
        VIS渲染数据
    """
    try:
        from derisk_ext.vis.derisk.derisk_vis_window3_converter import (
            DeriskIncrVisWindow3Converter
        )
        
        gpts_messages = []
        for msg in messages:
            gpts_msg = msg.to_gpts_message()
            gpts_messages.append(gpts_msg)
        
        converter = DeriskIncrVisWindow3Converter()
        
        vis_json = await converter.visualization(
            messages=gpts_messages,
            is_first_chunk=True,
            is_first_push=True
        )
        
        if vis_json:
            return json.loads(vis_json)
        
        return {}
        
    except ImportError:
        logger.warning("VIS converter not available, falling back to simple format")
        return await _render_simple(messages)
    except Exception as e:
        logger.error(f"Failed to render VIS: {e}")
        return await _render_simple(messages)


async def _render_markdown(messages: list) -> str:
    """Markdown格式渲染
    
    Args:
        messages: UnifiedMessage列表
        
    Returns:
        Markdown格式字符串
    """
    markdown_lines = []
    
    for msg in messages:
        if msg.message_type == "human":
            markdown_lines.append(f"**用户**: {msg.content}\n")
        elif msg.message_type in ("ai", "agent"):
            markdown_lines.append(f"**助手**: {msg.content}\n")
            
            if msg.thinking:
                markdown_lines.append(f"**思考过程**:\n```\n{msg.thinking}\n```\n")
            
            if msg.tool_calls:
                markdown_lines.append(f"**工具调用**:\n")
                for call in msg.tool_calls:
                    tool_name = call.get("name", "unknown")
                    markdown_lines.append(f"- {tool_name}\n")
        
        elif msg.message_type == "system":
            markdown_lines.append(f"**系统**: {msg.content}\n")
    
    return "\n".join(markdown_lines)


async def _render_simple(messages: list) -> list:
    """简单格式渲染
    
    Args:
        messages: UnifiedMessage列表
        
    Returns:
        简单格式的消息列表
    """
    simple_messages = []
    
    for msg in messages:
        simple_messages.append({
            "role": msg.message_type,
            "content": msg.content,
            "sender": msg.sender
        })
    
    return simple_messages