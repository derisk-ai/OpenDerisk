"""
统一消息API响应模型
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class UnifiedMessageResponse(BaseModel):
    """统一消息响应"""
    
    message_id: str = Field(..., description="消息ID")
    conv_id: str = Field(..., description="对话ID")
    conv_session_id: Optional[str] = Field(None, description="会话ID")
    
    sender: str = Field(..., description="发送者")
    sender_name: Optional[str] = Field(None, description="发送者名称")
    message_type: str = Field(..., description="消息类型")
    
    content: str = Field(..., description="消息内容")
    thinking: Optional[str] = Field(None, description="思考过程")
    tool_calls: Optional[List[Dict]] = Field(None, description="工具调用")
    action_report: Optional[Dict] = Field(None, description="动作报告")
    
    rounds: int = Field(0, description="轮次索引")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    @classmethod
    def from_unified_message(cls, msg: 'UnifiedMessage') -> 'UnifiedMessageResponse':
        """从UnifiedMessage创建响应
        
        Args:
            msg: UnifiedMessage实例
            
        Returns:
            UnifiedMessageResponse实例
        """
        return cls(
            message_id=msg.message_id,
            conv_id=msg.conv_id,
            conv_session_id=msg.conv_session_id,
            sender=msg.sender,
            sender_name=msg.sender_name,
            message_type=msg.message_type,
            content=msg.content,
            thinking=msg.thinking,
            tool_calls=msg.tool_calls,
            action_report=msg.action_report,
            rounds=msg.rounds,
            created_at=msg.created_at
        )


class UnifiedMessageListResponse(BaseModel):
    """统一消息列表响应"""
    
    conv_id: Optional[str] = Field(None, description="对话ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    total: int = Field(..., description="消息总数")
    messages: List[UnifiedMessageResponse] = Field(..., description="消息列表")
    
    limit: Optional[int] = Field(None, description="查询限制")
    offset: int = Field(0, description="查询偏移量")


class UnifiedRenderResponse(BaseModel):
    """统一渲染响应"""
    
    render_type: str = Field(..., description="渲染类型")
    data: Any = Field(..., description="渲染数据")
    cached: bool = Field(False, description="是否来自缓存")
    render_time_ms: Optional[int] = Field(None, description="渲染耗时(毫秒)")


class UnifiedConversationSummaryResponse(BaseModel):
    """对话摘要响应"""
    
    conv_id: str = Field(..., description="对话ID")
    user_id: str = Field(..., description="用户ID")
    goal: Optional[str] = Field(None, description="对话目标")
    chat_mode: str = Field(..., description="对话模式")
    state: str = Field(..., description="对话状态")
    
    message_count: int = Field(0, description="消息数量")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class UnifiedConversationListResponse(BaseModel):
    """对话列表响应"""
    
    total: int = Field(..., description="对话总数")
    conversations: List[UnifiedConversationSummaryResponse] = Field(..., description="对话列表")
    
    page: int = Field(1, description="当前页")
    page_size: int = Field(20, description="每页数量")
    has_next: bool = Field(False, description="是否有下一页")


class APIResponse(BaseModel):
    """统一API响应格式"""
    
    success: bool = Field(True, description="是否成功")
    data: Optional[Any] = Field(None, description="响应数据")
    error: Optional[Dict] = Field(None, description="错误信息")
    metadata: Optional[Dict] = Field(None, description="元数据")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    @classmethod
    def success_response(cls, data: Any, metadata: Optional[Dict] = None) -> 'APIResponse':
        """成功响应
        
        Args:
            data: 响应数据
            metadata: 元数据
            
        Returns:
            APIResponse实例
        """
        from datetime import datetime
        return cls(
            success=True,
            data=data,
            metadata=metadata or {
                "timestamp": datetime.now().isoformat()
            }
        )
    
    @classmethod
    def error_response(cls, code: str, message: str, details: Optional[List] = None) -> 'APIResponse':
        """错误响应
        
        Args:
            code: 错误代码
            message: 错误消息
            details: 错误详情
            
        Returns:
            APIResponse实例
        """
        from datetime import datetime
        return cls(
            success=False,
            error={
                "code": code,
                "message": message,
                "details": details or []
            },
            metadata={
                "timestamp": datetime.now().isoformat()
            }
        )