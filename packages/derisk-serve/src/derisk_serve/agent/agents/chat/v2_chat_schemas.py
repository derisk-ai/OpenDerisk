"""V2 Chat API 请求/响应 schema 定义。

独立于 BAIZE 的 V2 Agent 接口。
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class V2ChatRequest(BaseModel):
    """V2 Chat 请求参数

    Attributes:
        agent_id: Agent ID（对应 BAIZE 的 app_code）
        prompt: 用户输入
        conv_id: 会话 ID（可选，不传则自动生成）
        user_id: 用户 ID
        session_id: 浏览器 session ID
        context: 额外上下文（预留）
        resources: 资源列表（预留）
        max_steps: 最大步数，默认 20
    """

    agent_id: str
    prompt: str
    conv_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = Field(default=None)
    resources: Optional[List[Dict[str, Any]]] = Field(default=None)
    max_steps: int = 20
