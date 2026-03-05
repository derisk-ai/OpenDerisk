"""
统一API端点

提供统一的HTTP API接口，支持V1/V2 Agent的透明接入
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .application import get_unified_app_builder, UnifiedAppInstance
from .session import get_unified_session_manager, UnifiedSession, UnifiedMessage
from .interaction import get_unified_interaction_gateway, InteractionType
from .visualization import get_unified_vis_adapter, VisOutput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/unified", tags=["unified"])


# ========== 请求/响应模型 ==========

class CreateSessionRequest(BaseModel):
    app_code: str
    user_id: Optional[str] = None
    agent_version: str = "v2"


class CreateSessionResponse(BaseModel):
    session_id: str
    conv_id: str
    app_code: str
    agent_version: str


class SendMessageRequest(BaseModel):
    session_id: str
    role: str
    content: str
    metadata: Optional[dict] = None


class ChatStreamRequest(BaseModel):
    session_id: str
    conv_id: str
    app_code: str
    user_input: str
    agent_version: str = "v2"
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_new_tokens: Optional[int] = None
    incremental: bool = False
    vis_render: Optional[str] = None


# ========== 应用相关接口 ==========

@router.get("/app/{app_code}")
async def get_app_config(app_code: str):
    """获取应用配置"""
    try:
        builder = get_unified_app_builder()
        instance = await builder.build_app(app_code)
        return instance.to_dict()
    except Exception as e:
        logger.error(f"获取应用配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 会话相关接口 ==========

@router.post("/session/create", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """创建会话"""
    try:
        manager = get_unified_session_manager()
        session = await manager.create_session(
            app_code=request.app_code,
            user_id=request.user_id,
            agent_version=request.agent_version
        )
        
        return CreateSessionResponse(
            session_id=session.session_id,
            conv_id=session.conv_id,
            app_code=session.app_code,
            agent_version=session.agent_version
        )
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    try:
        manager = get_unified_session_manager()
        session = await manager.get_session(session_id=session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return session.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/close")
async def close_session(request: dict):
    """关闭会话"""
    try:
        session_id = request.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="缺少session_id")
        
        manager = get_unified_session_manager()
        await manager.close_session(session_id)
        
        return {"success": True}
    except Exception as e:
        logger.error(f"关闭会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/history")
async def get_session_history(session_id: str, limit: int = 50, offset: int = 0):
    """获取会话历史消息"""
    try:
        manager = get_unified_session_manager()
        messages = await manager.get_history(session_id, limit, offset)
        
        return {
            "session_id": session_id,
            "messages": [msg.to_dict() for msg in messages],
            "count": len(messages)
        }
    except Exception as e:
        logger.error(f"获取历史消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/message")
async def add_session_message(request: SendMessageRequest):
    """添加消息到会话"""
    try:
        manager = get_unified_session_manager()
        message = await manager.add_message(
            session_id=request.session_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata
        )
        
        return message.to_dict()
    except Exception as e:
        logger.error(f"添加消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 聊天相关接口 ==========

@router.post("/chat/stream")
async def chat_stream(request: ChatStreamRequest, req: Request):
    """
    统一的流式聊天接口
    
    自动适配V1/V2 Agent
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def generate_stream():
        try:
            builder = get_unified_app_builder()
            manager = get_unified_session_manager()
            
            session = await manager.get_session(session_id=request.session_id)
            if not session:
                yield f"data: { {'error': '会话不存在'} }\n\n"
                return
            
            app_instance = await builder.build_app(request.app_code)
            
            if request.agent_version == "v2":
                async for chunk in _execute_v2_chat(app_instance, request):
                    yield f"data: {chunk}\n\n"
            else:
                async for chunk in _execute_v1_chat(app_instance, request):
                    yield f"data: {chunk}\n\n"
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"聊天流式响应失败: {e}")
            yield f"data: { {'error': str(e)} }\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )


async def _execute_v2_chat(app_instance: UnifiedAppInstance, request: ChatStreamRequest):
    """执行V2聊天"""
    try:
        agent = app_instance.agent
        
        from derisk.agent.core_v2.agent_base import AgentBase
        if isinstance(agent, AgentBase):
            async for chunk in agent.run(request.user_input, stream=True):
                import json
                yield json.dumps({
                    "type": "response",
                    "content": chunk,
                    "is_final": False
                })
        else:
            import json
            yield json.dumps({
                "type": "response",
                "content": "V2 Agent not available",
                "is_final": True
            })
    except Exception as e:
        logger.error(f"V2聊天执行失败: {e}")
        import json
        yield json.dumps({
            "type": "error",
            "content": str(e)
        })


async def _execute_v1_chat(app_instance: UnifiedAppInstance, request: ChatStreamRequest):
    """执行V1聊天"""
    try:
        agent = app_instance.agent
        
        if hasattr(agent, "generate_reply"):
            response = await agent.generate_reply(
                received_message={"content": request.user_input},
                sender=None
            )
            
            content = getattr(response, "content", str(response))
            import json
            yield json.dumps({
                "type": "response",
                "content": content,
                "is_final": True
            })
        else:
            import json
            yield json.dumps({
                "type": "response",
                "content": "V1 Agent not available",
                "is_final": True
            })
    except Exception as e:
        logger.error(f"V1聊天执行失败: {e}")
        import json
        yield json.dumps({
            "type": "error",
            "content": str(e)
        })


# ========== 交互相关接口 ==========

@router.get("/interaction/pending")
async def get_pending_interactions():
    """获取待处理的交互请求"""
    try:
        gateway = get_unified_interaction_gateway()
        requests = await gateway.get_pending_requests()
        
        return {
            "requests": [
                {
                    "request_id": req.request_id,
                    "type": req.interaction_type.value,
                    "question": req.question,
                    "options": req.options
                }
                for req in requests
            ]
        }
    except Exception as e:
        logger.error(f"获取待处理交互失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/interaction/submit")
async def submit_interaction_response(request: dict):
    """提交交互响应"""
    try:
        request_id = request.get("request_id")
        response = request.get("response")
        
        if not request_id or not response:
            raise HTTPException(status_code=400, detail="缺少必要参数")
        
        gateway = get_unified_interaction_gateway()
        success = await gateway.submit_response(request_id, response)
        
        return {"success": success}
    except Exception as e:
        logger.error(f"提交交互响应失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 可视化相关接口 ==========

@router.post("/vis/render")
async def render_message(request: dict):
    """渲染消息可视化"""
    try:
        message = request.get("message")
        agent_version = request.get("agent_version", "v2")
        
        if not message:
            raise HTTPException(status_code=400, detail="缺少message参数")
        
        adapter = get_unified_vis_adapter()
        output = await adapter.render_message(message, agent_version)
        
        return output.to_dict()
    except Exception as e:
        logger.error(f"渲染消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 系统接口 ==========

@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "unified-api",
        "version": "1.0.0"
    }


@router.get("/status")
async def get_system_status():
    """获取系统状态"""
    try:
        builder = get_unified_app_builder()
        manager = get_unified_session_manager()
        
        return {
            "app_builder": {
                "cached_apps": len(builder._app_cache)
            },
            "session_manager": {
                "active_sessions": len(manager._sessions)
            }
        }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))