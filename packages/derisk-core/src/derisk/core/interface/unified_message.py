"""
统一消息模型

用于统一Core V1和Core V2的消息格式，支持双向转换
"""
import uuid
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UnifiedMessage:
    """统一消息模型
    
    支持Core V1（BaseMessage）和Core V2（GptsMessage）的双向转换
    """
    
    # 基础字段
    message_id: str
    conv_id: str
    conv_session_id: Optional[str] = None
    
    # 发送者信息
    sender: str
    sender_name: Optional[str] = None
    receiver: Optional[str] = None
    receiver_name: Optional[str] = None
    
    # 消息类型
    message_type: str = "human"
    
    # 内容
    content: str = ""
    thinking: Optional[str] = None
    
    # 工具调用
    tool_calls: Optional[List[Dict]] = None
    
    # 观察和上下文
    observation: Optional[str] = None
    context: Optional[Dict] = None
    
    # Action报告
    action_report: Optional[Dict] = None
    resource_info: Optional[Dict] = None
    
    # 可视化（Core V2专用）- 不存储，读取时动态渲染
    vis_render: Optional[Dict] = None
    
    # 元数据
    rounds: int = 0
    message_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 时间戳
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @classmethod
    def from_base_message(cls, msg: 'BaseMessage', conv_id: str, **kwargs) -> 'UnifiedMessage':
        """从Core V1的BaseMessage转换
        
        Args:
            msg: BaseMessage实例
            conv_id: 对话ID
            **kwargs: 额外参数
                - conv_session_id: 会话ID
                - sender: 发送者
                - sender_name: 发送者名称
                - round_index: 轮次索引
                - index: 消息索引
                - context: 上下文信息
                
        Returns:
            UnifiedMessage实例
        """
        from derisk.core.interface.message import BaseMessage
        
        type_mapping = {
            "human": "human",
            "ai": "ai",
            "system": "system",
            "view": "view"
        }
        
        message_type = type_mapping.get(msg.type, msg.type)
        
        content = ""
        if hasattr(msg, 'content') and msg.content:
            content = str(msg.content)
        
        return cls(
            message_id=kwargs.get('message_id', str(uuid.uuid4())),
            conv_id=conv_id,
            conv_session_id=kwargs.get('conv_session_id'),
            sender=kwargs.get('sender', 'user'),
            sender_name=kwargs.get('sender_name'),
            message_type=message_type,
            content=content,
            rounds=kwargs.get('round_index', 0),
            message_index=kwargs.get('index', 0),
            context=kwargs.get('context'),
            metadata={
                "source": "core_v1",
                "original_type": msg.type,
                "additional_kwargs": getattr(msg, 'additional_kwargs', {})
            },
            created_at=datetime.now()
        )
    
    @classmethod
    def from_gpts_message(cls, msg: 'GptsMessage') -> 'UnifiedMessage':
        """从Core V2的GptsMessage转换
        
        Args:
            msg: GptsMessage实例
            
        Returns:
            UnifiedMessage实例
        """
        from derisk.agent.core.memory.gpts.base import GptsMessage
        
        content = ""
        if msg.content:
            if isinstance(msg.content, str):
                content = msg.content
            else:
                content = str(msg.content)
        
        return cls(
            message_id=msg.message_id or str(uuid.uuid4()),
            conv_id=msg.conv_id,
            conv_session_id=msg.conv_session_id,
            sender=msg.sender or "assistant",
            sender_name=msg.sender_name,
            receiver=msg.receiver,
            receiver_name=msg.receiver_name,
            message_type="agent" if (msg.sender and "::" in msg.sender) else "assistant",
            content=content,
            thinking=msg.thinking,
            tool_calls=msg.tool_calls,
            observation=msg.observation,
            context=msg.context,
            action_report=msg.action_report,
            resource_info=msg.resource_info,
            rounds=msg.rounds or 0,
            metadata={
                "source": "core_v2",
                "role": msg.role if hasattr(msg, 'role') else "assistant",
                "metrics": msg.metrics.__dict__ if hasattr(msg, 'metrics') and msg.metrics else None
            },
            created_at=datetime.now()
        )
    
    def to_base_message(self) -> 'BaseMessage':
        """转换为Core V1的BaseMessage
        
        Returns:
            BaseMessage实例（HumanMessage/AIMessage/SystemMessage/ViewMessage）
        """
        from derisk.core.interface.message import (
            HumanMessage, AIMessage, SystemMessage, ViewMessage
        )
        
        message_classes = {
            "human": HumanMessage,
            "ai": AIMessage,
            "system": SystemMessage,
            "view": ViewMessage
        }
        
        msg_class = message_classes.get(self.message_type, AIMessage)
        
        additional_kwargs = self.metadata.get('additional_kwargs', {})
        
        msg = msg_class(
            content=self.content,
            additional_kwargs=additional_kwargs
        )
        
        msg.round_index = self.rounds
        
        return msg
    
    def to_gpts_message(self) -> 'GptsMessage':
        """转换为Core V2的GptsMessage
        
        Returns:
            GptsMessage实例
        """
        from derisk.agent.core.memory.gpts.base import GptsMessage
        
        return GptsMessage(
            conv_id=self.conv_id,
            conv_session_id=self.conv_session_id,
            message_id=self.message_id,
            sender=self.sender,
            sender_name=self.sender_name,
            receiver=self.receiver,
            receiver_name=self.receiver_name,
            role=self.metadata.get('role', 'assistant'),
            content=self.content,
            thinking=self.thinking,
            tool_calls=self.tool_calls,
            observation=self.observation,
            context=self.context,
            action_report=self.action_report,
            resource_info=self.resource_info,
            rounds=self.rounds
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）
        
        Returns:
            字典格式的消息数据
        """
        return {
            "message_id": self.message_id,
            "conv_id": self.conv_id,
            "conv_session_id": self.conv_session_id,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "receiver": self.receiver,
            "receiver_name": self.receiver_name,
            "message_type": self.message_type,
            "content": self.content,
            "thinking": self.thinking,
            "tool_calls": self.tool_calls,
            "observation": self.observation,
            "context": self.context,
            "action_report": self.action_report,
            "resource_info": self.resource_info,
            "vis_render": self.vis_render,
            "rounds": self.rounds,
            "message_index": self.message_index,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedMessage':
        """从字典创建实例
        
        Args:
            data: 字典数据
            
        Returns:
            UnifiedMessage实例
        """
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        return cls(
            message_id=data['message_id'],
            conv_id=data['conv_id'],
            conv_session_id=data.get('conv_session_id'),
            sender=data['sender'],
            sender_name=data.get('sender_name'),
            receiver=data.get('receiver'),
            receiver_name=data.get('receiver_name'),
            message_type=data.get('message_type', 'human'),
            content=data.get('content', ''),
            thinking=data.get('thinking'),
            tool_calls=data.get('tool_calls'),
            observation=data.get('observation'),
            context=data.get('context'),
            action_report=data.get('action_report'),
            resource_info=data.get('resource_info'),
            vis_render=data.get('vis_render'),
            rounds=data.get('rounds', 0),
            message_index=data.get('message_index', 0),
            metadata=data.get('metadata', {}),
            created_at=created_at
        )
    
    def __repr__(self) -> str:
        return (
            f"UnifiedMessage(id={self.message_id}, type={self.message_type}, "
            f"sender={self.sender}, rounds={self.rounds})"
        )