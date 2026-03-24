"""
Interaction API - 用户交互端点

提供 ask_user 响应提交、待处理请求查询、请求取消等接口
"""

import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/interaction", tags=["Interaction"])


class InteractionRespondRequest(BaseModel):
    """用户交互响应请求"""

    request_id: str = Field(..., description="交互请求ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    choice: Optional[str] = Field(None, description="用户选择的选项值")
    choices: List[str] = Field(default_factory=list, description="多选结果")
    input_value: Optional[str] = Field(None, description="用户输入内容")
    user_message: Optional[str] = Field(None, description="用户消息 (system_reminder 格式)")
    grant_scope: Optional[str] = Field(None, description="授权范围")
    grant_duration: Optional[int] = Field(None, description="授权时长(秒)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class InteractionCancelRequest(BaseModel):
    """取消交互请求"""

    request_id: str = Field(..., description="交互请求ID")
    reason: str = Field("user_cancel", description="取消原因")


class InteractionRespondResponse(BaseModel):
    """响应结果"""

    success: bool
    message: str
    request_id: str


class PendingRequestItem(BaseModel):
    """待处理请求项"""

    request_id: str
    interaction_type: str
    title: str
    message: str
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _get_interaction_gateway():
    """获取全局交互网关实例"""
    try:
        from derisk.agent.interaction.interaction_gateway import get_interaction_gateway

        gateway = get_interaction_gateway()
        return gateway
    except ImportError:
        logger.warning("[InteractionAPI] Cannot import interaction gateway")
        return None
    except Exception as e:
        logger.warning(f"[InteractionAPI] Failed to get interaction gateway: {e}")
        return None


@router.post("/respond", response_model=InteractionRespondResponse)
async def respond_to_interaction(request: InteractionRespondRequest):
    """
    提交用户交互响应

    前端 VisConfirmCard 提交用户选择后调用此接口，
    解除 Agent 的 send_and_wait() 阻塞，继续执行。
    """
    gateway = _get_interaction_gateway()
    if not gateway:
        raise HTTPException(
            status_code=503,
            detail="Interaction gateway not available",
        )

    try:
        from derisk.agent.interaction.interaction_protocol import (
            InteractionResponse,
            InteractionStatus,
        )

        response = InteractionResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            choice=request.choice,
            choices=request.choices,
            input_value=request.input_value,
            user_message=request.user_message,
            status=InteractionStatus.RESPONSED,
            grant_scope=request.grant_scope,
            grant_duration=request.grant_duration,
            metadata=request.metadata,
        )

        await gateway.deliver_response(response)

        logger.info(
            f"[InteractionAPI] Response delivered for request_id={request.request_id}"
        )

        return InteractionRespondResponse(
            success=True,
            message="Response delivered successfully",
            request_id=request.request_id,
        )

    except Exception as e:
        logger.exception(f"[InteractionAPI] Failed to deliver response: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to deliver response: {str(e)}",
        )


@router.get("/pending")
async def get_pending_requests(session_id: str) -> List[PendingRequestItem]:
    """
    获取指定会话的待处理交互请求
    """
    gateway = _get_interaction_gateway()
    if not gateway:
        return []

    try:
        requests = await gateway.get_pending_requests(session_id)
        return [
            PendingRequestItem(
                request_id=req.request_id,
                interaction_type=req.interaction_type,
                title=req.title,
                message=req.message,
                created_at=req.created_at.isoformat()
                if hasattr(req.created_at, "isoformat")
                else str(req.created_at),
                metadata=req.metadata,
            )
            for req in requests
        ]
    except Exception as e:
        logger.warning(f"[InteractionAPI] Failed to get pending requests: {e}")
        return []


@router.post("/cancel", response_model=InteractionRespondResponse)
async def cancel_interaction(request: InteractionCancelRequest):
    """
    取消交互请求
    """
    gateway = _get_interaction_gateway()
    if not gateway:
        raise HTTPException(
            status_code=503,
            detail="Interaction gateway not available",
        )

    try:
        await gateway.cancel_request(request.request_id, request.reason)

        logger.info(
            f"[InteractionAPI] Request cancelled: request_id={request.request_id}, reason={request.reason}"
        )

        return InteractionRespondResponse(
            success=True,
            message="Request cancelled",
            request_id=request.request_id,
        )

    except Exception as e:
        logger.exception(f"[InteractionAPI] Failed to cancel request: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel request: {str(e)}",
        )
