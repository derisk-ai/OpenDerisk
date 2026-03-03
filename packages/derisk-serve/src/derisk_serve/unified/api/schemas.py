"""
统一API请求/响应模型定义
"""

from typing import Optional, List
from pydantic import BaseModel


# ========== 会话相关模型 ==========

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    app_code: str
    user_id: Optional[str] = None
    agent_version: str = "v2"


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    session_id: str
    conv_id: str
    app_code: str
    agent_version: str


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    session_id: str
    role: str
    content: str
    metadata: Optional[dict] = None


# ========== 聊天相关模型 ==========

class ChatStreamRequest(BaseModel):
    """流式聊天请求"""
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


# ========== 交互相关模型 ==========

class SubmitInteractionRequest(BaseModel):
    """提交交互响应请求"""
    request_id: str
    response: str
    metadata: Optional[dict] = None


# ========== 可视化相关模型 ==========

class RenderMessageRequest(BaseModel):
    """渲染消息请求"""
    message: dict
    agent_version: str = "v2"