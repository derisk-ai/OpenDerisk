# 历史消息统一存储与渲染方案

> 文档版本: v1.0  
> 创建日期: 2026-03-02  
> 目标: 保留一套表机制，统一Core和Core_v2的历史消息存储与渲染

---

## 一、当前问题诊断

### 1.1 数据冗余分析

```
Core V1架构数据流:
  OnceConversation → chat_history.messages字段 (存储JSON)
                  → chat_history_message表 (单条存储)
                    ↓
                  前端API读取 → 渲染

Core V2架构数据流:
  GptsMessage → gpts_messages表 (结构化存储)
              → gpts_conversations表 (会话元数据)
                    ↓
                  前端API读取 → VIS渲染

冗余点:
  - 同一轮对话可能同时存在chat_history和gpts_messages
  - chat_history.messages字段与chat_history_message表重复
  - 渲染数据格式不一致（MessageVo vs VIS格式）
```

### 1.2 核心问题

| 问题 | 影响 |
|------|------|
| 双表存储 | 数据一致性难保证，存储成本高 |
| 渲染格式不统一 | 前端需要适配两套逻辑 |
| 预渲染存储 | chat_history.messages存的是渲染后数据，灵活性差 |
| Core V1和V2隔离 | 无法共享历史记录 |

---

## 二、统一存储方案设计

### 2.1 方案选择：保留gpts_messages体系

**理由**:
1. gpts_messages表结构化程度高（thinking, tool_calls, action_report独立字段）
2. 支持Core V2的完整功能集
3. Core V1的功能可以作为子集
4. 避免chat_history.messages的预渲染耦合

### 2.2 表结构调整

#### 2.2.1 保留表（优化）

```sql
-- 1. gpts_conversations (主表)
CREATE TABLE gpts_conversations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conv_id VARCHAR(255) UNIQUE NOT NULL,
    conv_session_id VARCHAR(255),           -- 会话分组ID
    user_goal TEXT,
    gpts_name VARCHAR(255),                 -- Agent名称
    team_mode VARCHAR(50),
    state VARCHAR(50),                      -- 对话状态
    max_auto_reply_round INT,
    auto_reply_count INT,
    user_code VARCHAR(255),
    sys_code VARCHAR(255),
    
    -- 新增字段（兼容Core V1）
    chat_mode VARCHAR(50),                  -- 对话模式
    model_name VARCHAR(100),                -- 模型名称
    summary VARCHAR(500),                   -- 对话摘要
    
    -- 可视化配置
    vis_render TEXT,
    extra TEXT,
    gmt_create DATETIME,
    gmt_modified DATETIME,
    
    INDEX idx_session_id (conv_session_id),
    INDEX idx_user_code (user_code),
    INDEX idx_state (state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. gpts_messages (消息表，核心表)
CREATE TABLE gpts_messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conv_id VARCHAR(255),
    conv_session_id VARCHAR(255),
    message_id VARCHAR(255),
    rounds INT,
    
    -- 发送者信息
    sender VARCHAR(255),                    -- user, assistant, agent_name
    sender_name VARCHAR(100),
    receiver VARCHAR(255),
    receiver_name VARCHAR(100),
    
    -- 核心内容
    content LONGTEXT,                       -- 消息正文
    thinking LONGTEXT,                      -- 思考过程（Core V2专用）
    
    -- 工具调用
    tool_calls LONGTEXT,                    -- JSON格式的工具调用
    
    -- 观察和上下文
    observation LONGTEXT,
    context LONGTEXT,                       -- JSON格式的上下文信息
    system_prompt LONGTEXT,
    user_prompt LONGTEXT,
    
    -- Action和资源报告
    action_report LONGTEXT,                 -- JSON格式的动作报告
    resource_info LONGTEXT,                 -- JSON格式的资源信息
    review_info LONGTEXT,                   -- 审查信息
    
    -- 可视化（Core V2专用）
    vis_render LONGTEXT,                    -- 可视化渲染数据
    
    -- 性能指标
    metrics TEXT,                           -- JSON格式的性能指标
    
    -- 扩展字段（兼容Core V1）
    message_type VARCHAR(50),               -- human/ai/view/system
    message_index INT,                      -- 消息序号
    
    -- 时间戳
    gmt_create DATETIME,
    gmt_modified DATETIME,
    
    INDEX idx_conv_id (conv_id),
    INDEX idx_session_id (conv_session_id),
    INDEX idx_message_id (message_id),
    INDEX idx_sender (sender),
    INDEX idx_rounds (conv_id, rounds)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 2.2.2 废弃表（保留作为历史归档）

```sql
-- 归档表（重命名）
RENAME TABLE chat_history TO chat_history_archived;
RENAME TABLE chat_history_message TO chat_history_message_archived;
```

---

## 三、统一数据访问层设计

### 3.1 统一消息模型

```python
# /packages/derisk-core/src/derisk/core/interface/unified_message.py

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class UnifiedMessage:
    """统一消息模型"""
    
    # 基础字段
    message_id: str
    conv_id: str
    conv_session_id: Optional[str] = None
    
    # 发送者信息
    sender: str                                    # user, assistant, agent_name
    sender_name: Optional[str] = None
    receiver: Optional[str] = None
    receiver_name: Optional[str] = None
    
    # 消息类型
    message_type: str = "human"                    # human/ai/view/system/agent
    
    # 内容
    content: str = ""
    thinking: Optional[str] = None                 # Core V2思考过程
    
    # 工具调用
    tool_calls: Optional[List[Dict]] = None
    
    # 观察和上下文
    observation: Optional[str] = None
    context: Optional[Dict] = None
    
    # Action报告
    action_report: Optional[Dict] = None
    resource_info: Optional[Dict] = None
    
    # 可视化
    vis_render: Optional[Dict] = None              # VIS渲染数据
    
    # 元数据
    rounds: int = 0
    message_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 时间戳
    created_at: Optional[datetime] = None
    
    # ============ 转换方法 ============
    
    @classmethod
    def from_base_message(cls, msg: 'BaseMessage', conv_id: str, **kwargs) -> 'UnifiedMessage':
        """从Core V1的BaseMessage转换"""
        from derisk.core.interface.message import BaseMessage
        
        # 确定message_type
        type_mapping = {
            "human": "human",
            "ai": "ai",
            "system": "system",
            "view": "view"
        }
        
        message_type = type_mapping.get(msg.type, msg.type)
        
        # 提取content
        content = ""
        if hasattr(msg, 'content'):
            content = str(msg.content) if msg.content else ""
        
        # 构建UnifiedMessage
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
        """从Core V2的GptsMessage转换"""
        from derisk.agent.core.memory.gpts.base import GptsMessage
        
        return cls(
            message_id=msg.message_id,
            conv_id=msg.conv_id,
            conv_session_id=msg.conv_session_id,
            sender=msg.sender or "assistant",
            sender_name=msg.sender_name,
            receiver=msg.receiver,
            receiver_name=msg.receiver_name,
            message_type="agent" if msg.sender and "::" in msg.sender else "assistant",
            content=msg.content if isinstance(msg.content, str) else str(msg.content),
            thinking=msg.thinking,
            tool_calls=msg.tool_calls,
            observation=msg.observation,
            context=msg.context,
            action_report=msg.action_report,
            resource_info=msg.resource_info,
            vis_render=msg.vis_render if hasattr(msg, 'vis_render') else None,
            rounds=msg.rounds,
            metadata={
                "source": "core_v2",
                "role": msg.role,
                "metrics": msg.metrics.__dict__ if msg.metrics else None
            },
            created_at=datetime.now()
        )
    
    def to_base_message(self) -> 'BaseMessage':
        """转换为Core V1的BaseMessage"""
        from derisk.core.interface.message import (
            HumanMessage, AIMessage, SystemMessage, ViewMessage
        )
        
        # 根据message_type选择对应的类
        message_classes = {
            "human": HumanMessage,
            "ai": AIMessage,
            "system": SystemMessage,
            "view": ViewMessage
        }
        
        msg_class = message_classes.get(self.message_type, AIMessage)
        
        return msg_class(
            content=self.content,
            additional_kwargs=self.metadata.get('additional_kwargs', {})
        )
    
    def to_gpts_message(self) -> 'GptsMessage':
        """转换为Core V2的GptsMessage"""
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
    
    def to_dict(self) -> Dict:
        """转换为字典（用于序列化）"""
        return {
            "message_id": self.message_id,
            "conv_id": self.conv_id,
            "conv_session_id": self.conv_session_id,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "message_type": self.message_type,
            "content": self.content,
            "thinking": self.thinking,
            "tool_calls": self.tool_calls,
            "observation": self.observation,
            "context": self.context,
            "action_report": self.action_report,
            "vis_render": self.vis_render,
            "rounds": self.rounds,
            "message_index": self.message_index,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
```

### 3.2 统一DAO层

```python
# /packages/derisk-core/src/derisk/storage/unified_message_dao.py

from typing import List, Optional, Dict
from datetime import datetime
import json

class UnifiedMessageDAO:
    """统一消息DAO，底层使用gpts_messages表"""
    
    def __init__(self):
        # 复用现有的GptsMessagesDao
        from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao
        
        self.msg_dao = GptsMessagesDao()
        self.conv_dao = GptsConversationsDao()
    
    async def save_message(self, message: UnifiedMessage) -> None:
        """保存消息（统一入口）"""
        from derisk_serve.agent.db.gpts_messages_db import GptsMessagesEntity
        
        # 序列化JSON字段
        tool_calls_json = json.dumps(message.tool_calls, ensure_ascii=False) if message.tool_calls else None
        context_json = json.dumps(message.context, ensure_ascii=False) if message.context else None
        action_report_json = json.dumps(message.action_report, ensure_ascii=False) if message.action_report else None
        resource_info_json = json.dumps(message.resource_info, ensure_ascii=False) if message.resource_info else None
        vis_render_json = json.dumps(message.vis_render, ensure_ascii=False) if message.vis_render else None
        
        entity = GptsMessagesEntity(
            conv_id=message.conv_id,
            conv_session_id=message.conv_session_id,
            message_id=message.message_id,
            sender=message.sender,
            sender_name=message.sender_name,
            receiver=message.receiver,
            receiver_name=message.receiver_name,
            rounds=message.rounds,
            content=message.content,
            thinking=message.thinking,
            tool_calls=tool_calls_json,
            observation=message.observation,
            context=context_json,
            action_report=action_report_json,
            resource_info=resource_info_json,
            vis_render=vis_render_json,
            gmt_create=message.created_at or datetime.now()
        )
        
        await self.msg_dao.update_message(entity)
    
    async def save_messages_batch(self, messages: List[UnifiedMessage]) -> None:
        """批量保存消息"""
        for msg in messages:
            await self.save_message(msg)
    
    async def get_messages_by_conv_id(
        self, 
        conv_id: str,
        limit: Optional[int] = None,
        include_thinking: bool = False
    ) -> List[UnifiedMessage]:
        """获取对话的所有消息"""
        
        gpts_messages = await self.msg_dao.get_by_conv_id(conv_id)
        
        unified_messages = []
        for gpt_msg in gpts_messages:
            unified_msg = self._entity_to_unified(gpt_msg)
            unified_messages.append(unified_msg)
        
        if limit:
            unified_messages = unified_messages[-limit:]
        
        return unified_messages
    
    async def get_messages_by_session(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[UnifiedMessage]:
        """获取会话下的所有消息"""
        
        gpts_messages = await self.msg_dao.get_by_session_id(session_id)
        
        unified_messages = []
        for gpt_msg in gpts_messages:
            unified_msg = self._entity_to_unified(gpt_msg)
            unified_messages.append(unified_msg)
        
        return unified_messages[:limit]
    
    async def get_latest_messages(
        self,
        conv_id: str,
        limit: int = 10
    ) -> List[UnifiedMessage]:
        """获取最新的N条消息"""
        
        all_messages = await self.get_messages_by_conv_id(conv_id)
        return all_messages[-limit:]
    
    async def create_conversation(
        self,
        conv_id: str,
        user_id: str,
        goal: Optional[str] = None,
        chat_mode: str = "chat_normal",
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """创建对话记录"""
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsEntity
        
        entity = GptsConversationsEntity(
            conv_id=conv_id,
            conv_session_id=session_id or conv_id,
            user_goal=goal,
            user_code=user_id,
            gpts_name=agent_name or "assistant",
            state="active",
            gmt_create=datetime.now()
        )
        
        await self.conv_dao.a_add(entity)
    
    def _entity_to_unified(self, entity) -> UnifiedMessage:
        """将数据库实体转换为UnifiedMessage"""
        
        # 反序列化JSON字段
        tool_calls = json.loads(entity.tool_calls) if entity.tool_calls else None
        context = json.loads(entity.context) if entity.context else None
        action_report = json.loads(entity.action_report) if entity.action_report else None
        resource_info = json.loads(entity.resource_info) if entity.resource_info else None
        vis_render = json.loads(entity.vis_render) if entity.vis_render else None
        
        return UnifiedMessage(
            message_id=entity.message_id,
            conv_id=entity.conv_id,
            conv_session_id=entity.conv_session_id,
            sender=entity.sender,
            sender_name=entity.sender_name,
            receiver=entity.receiver,
            receiver_name=entity.receiver_name,
            content=entity.content or "",
            thinking=entity.thinking,
            tool_calls=tool_calls,
            observation=entity.observation,
            context=context,
            action_report=action_report,
            resource_info=resource_info,
            vis_render=vis_render,
            rounds=entity.rounds or 0,
            created_at=entity.gmt_create
        )
```

---

## 四、Core V1适配器实现

### 4.1 StorageConversation改造

**目标**: 保持StorageConversation接口不变，底层改为使用UnifiedMessageDAO

```python
# /packages/derisk-core/src/derisk/core/interface/message.py
# 修改StorageConversation类

class StorageConversation:
    """对话存储适配器（改造版）"""
    
    def __init__(
        self,
        conv_uid: str,
        chat_mode: str = "chat_normal",
        user_name: Optional[str] = None,
        sys_code: Optional[str] = None,
        # 新增参数
        agent_name: Optional[str] = None,
        conv_session_id: Optional[str] = None,
    ):
        self.conv_uid = conv_uid
        self.chat_mode = chat_mode
        self.user_name = user_name
        self.sys_code = sys_code
        self.agent_name = agent_name
        self.conv_session_id = conv_session_id or conv_uid
        
        # 消息列表
        self.messages: List[BaseMessage] = []
        
        # 改造：使用UnifiedMessageDAO
        from derisk.storage.unified_message_dao import UnifiedMessageDAO
        self._unified_dao = UnifiedMessageDAO()
    
    async def save_to_storage(self) -> None:
        """保存到统一存储（改造）"""
        
        # 1. 创建对话记录（如果不存在）
        await self._unified_dao.create_conversation(
            conv_id=self.conv_uid,
            user_id=self.user_name or "unknown",
            goal=getattr(self, 'summary', None),
            chat_mode=self.chat_mode,
            agent_name=self.agent_name,
            session_id=self.conv_session_id
        )
        
        # 2. 转换并保存消息
        unified_messages = []
        for idx, msg in enumerate(self.messages):
            unified_msg = UnifiedMessage.from_base_message(
                msg=msg,
                conv_id=self.conv_uid,
                conv_session_id=self.conv_session_id,
                message_id=f"{self.conv_uid}_msg_{idx}",
                sender=self._get_sender_from_message(msg),
                sender_name=self.user_name,
                round_index=getattr(msg, 'round_index', 0),
                index=idx
            )
            unified_messages.append(unified_msg)
        
        await self._unified_dao.save_messages_batch(unified_messages)
    
    async def load_from_storage(self) -> 'StorageConversation':
        """从统一存储加载（改造）"""
        
        # 1. 从统一存储加载消息
        unified_messages = await self._unified_dao.get_messages_by_conv_id(
            self.conv_uid
        )
        
        # 2. 转换为BaseMessage
        self.messages = []
        for unified_msg in unified_messages:
            base_msg = unified_msg.to_base_message()
            # 保留round_index等元数据
            base_msg.round_index = unified_msg.rounds
            self.messages.append(base_msg)
        
        return self
    
    def _get_sender_from_message(self, msg: BaseMessage) -> str:
        """从消息类型推断sender"""
        type_to_sender = {
            "human": "user",
            "ai": self.agent_name or "assistant",
            "system": "system",
            "view": "view"
        }
        return type_to_sender.get(msg.type, "assistant")
```

### 4.2 OnceConversation改造

```python
# /packages/derisk-core/src/derisk/core/interface/message.py
# 修改OnceConversation类

class OnceConversation:
    """单次对话（改造版）"""
    
    def __init__(
        self,
        conv_uid: str,
        chat_mode: str = "chat_normal",
        user_name: Optional[str] = None,
        # 新增
        agent_name: Optional[str] = None,
    ):
        self.conv_uid = conv_uid
        self.chat_mode = chat_mode
        self.user_name = user_name
        self.agent_name = agent_name
        
        self.messages: List[BaseMessage] = []
        
        # 改造：使用UnifiedMessageDAO
        from derisk.storage.unified_message_dao import UnifiedMessageDAO
        self._unified_dao = UnifiedMessageDAO()
    
    def add_user_message(self, message: str, **kwargs) -> None:
        """添加用户消息"""
        from derisk.core.interface.message import HumanMessage
        
        msg = HumanMessage(content=message, **kwargs)
        msg.round_index = len([m for m in self.messages if m.round_index])
        self.messages.append(msg)
    
    def add_ai_message(self, message: str, **kwargs) -> None:
        """添加AI消息"""
        from derisk.core.interface.message import AIMessage
        
        msg = AIMessage(content=message, **kwargs)
        msg.round_index = self.messages[-1].round_index if self.messages else 0
        self.messages.append(msg)
    
    async def save_to_storage(self) -> None:
        """保存到统一存储"""
        # 复用StorageConversation的逻辑
        storage_conv = StorageConversation(
            conv_uid=self.conv_uid,
            chat_mode=self.chat_mode,
            user_name=self.user_name,
            agent_name=self.agent_name
        )
        storage_conv.messages = self.messages
        await storage_conv.save_to_storage()
```

---

## 五、Core V2适配实现

### 5.1 GptsMessageMemory改造

**目标**: GptsMessageMemory继续使用gpts_messages表，但通过UnifiedMessage接口

```python
# /packages/derisk-serve/src/derisk_serve/agent/agents/derisks_memory.py
# 修改GptsMessageMemory类

class GptsMessageMemory:
    """Gpts消息记忆（改造版）"""
    
    def __init__(self):
        # 改造：使用UnifiedMessageDAO
        from derisk.storage.unified_message_dao import UnifiedMessageDAO
        self._unified_dao = UnifiedMessageDAO()
        
        # 兼容：保留原GptsMessagesDao用于特定查询
        from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
        self.gpts_messages = GptsMessagesDao()
    
    async def append(self, message: GptsMessage) -> None:
        """追加消息"""
        # 转换为UnifiedMessage
        unified_msg = UnifiedMessage.from_gpts_message(message)
        
        # 保存到统一存储
        await self._unified_dao.save_message(unified_msg)
    
    async def get_by_conv_id(self, conv_id: str) -> List[GptsMessage]:
        """获取对话消息"""
        # 从统一存储获取
        unified_messages = await self._unified_dao.get_messages_by_conv_id(conv_id)
        
        # 转换为GptsMessage（兼容现有代码）
        gpts_messages = [msg.to_gpts_message() for msg in unified_messages]
        
        return gpts_messages
    
    async def get_by_session_id(self, session_id: str) -> List[GptsMessage]:
        """获取会话消息"""
        unified_messages = await self._unified_dao.get_messages_by_session(session_id)
        return [msg.to_gpts_message() for msg in unified_messages]
```

---

## 六、统一API层设计

### 6.1 统一历史消息API

```python
# /packages/derisk-serve/src/derisk_serve/unified_api/endpoints.py

from fastapi import APIRouter, Query, Depends
from typing import List, Optional

router = APIRouter(prefix="/api/v1/unified", tags=["Unified API"])

@router.get("/conversations/{conv_id}/messages", response_model=UnifiedMessageListResponse)
async def get_conversation_messages(
    conv_id: str,
    limit: Optional[int] = Query(50, ge=1, le=500),
    include_thinking: bool = Query(False),
    include_vis: bool = Query(False),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取对话历史消息（统一API）
    
    参数:
    - conv_id: 对话ID
    - limit: 消息数量限制
    - include_thinking: 是否包含思考过程（Core V2专用）
    - include_vis: 是否包含可视化数据（Core V2专用）
    """
    
    # 从统一存储加载
    messages = await unified_dao.get_messages_by_conv_id(
        conv_id=conv_id,
        limit=limit,
        include_thinking=include_thinking
    )
    
    # 转换为响应格式
    return UnifiedMessageListResponse(
        conv_id=conv_id,
        total=len(messages),
        messages=[
            UnifiedMessageResponse(
                message_id=msg.message_id,
                sender=msg.sender,
                sender_name=msg.sender_name,
                message_type=msg.message_type,
                content=msg.content,
                thinking=msg.thinking if include_thinking else None,
                tool_calls=msg.tool_calls,
                action_report=msg.action_report,
                vis_render=msg.vis_render if include_vis else None,
                rounds=msg.rounds,
                created_at=msg.created_at
            )
            for msg in messages
        ]
    )

@router.get("/sessions/{session_id}/messages", response_model=UnifiedMessageListResponse)
async def get_session_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=500),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取会话历史消息（统一API）
    
    支持按会话分组查询多轮对话
    """
    
    messages = await unified_dao.get_messages_by_session(
        session_id=session_id,
        limit=limit
    )
    
    return UnifiedMessageListResponse(
        session_id=session_id,
        total=len(messages),
        messages=[
            UnifiedMessageResponse.from_unified_message(msg)
            for msg in messages
        ]
    )

@router.get("/conversations/{conv_id}/render")
async def get_conversation_render(
    conv_id: str,
    render_type: str = Query("vis", regex="^(vis|markdown|simple)$"),
    unified_dao: UnifiedMessageDAO = Depends(get_unified_dao)
):
    """
    获取对话渲染数据（统一API）
    
    render_type:
    - vis: VIS可视化格式（Core V2）
    - markdown: Markdown格式（Core V1/V2）
    - simple: 简单格式（Core V1）
    """
    
    messages = await unified_dao.get_messages_by_conv_id(conv_id)
    
    if render_type == "vis":
        # Core V2: 使用VIS渲染器
        from derisk_ext.vis.derisk.derisk_vis_window3_converter import DeriskIncrVisWindow3Converter
        
        converter = DeriskIncrVisWindow3Converter()
        gpts_messages = [msg.to_gpts_message() for msg in messages]
        
        # 构建VIS渲染数据
        vis_data = await converter.visualization(
            messages=gpts_messages,
            stream_msg=None
        )
        
        return {
            "render_type": "vis",
            "data": json.loads(vis_data)
        }
    
    elif render_type == "markdown":
        # Core V1/V2: 返回Markdown格式
        markdown_lines = []
        for msg in messages:
            if msg.message_type == "human":
                markdown_lines.append(f"**用户**: {msg.content}\n")
            else:
                markdown_lines.append(f"**助手**: {msg.content}\n")
                
                if msg.thinking:
                    markdown_lines.append(f"**思考**: {msg.thinking}\n")
        
        return {
            "render_type": "markdown",
            "data": "\n".join(markdown_lines)
        }
    
    else:  # simple
        # Core V1: 简单格式
        return {
            "render_type": "simple",
            "data": [
                {
                    "role": msg.message_type,
                    "content": msg.content
                }
                for msg in messages
            ]
        }
```

### 6.2 响应模型

```python
# /packages/derisk-serve/src/derisk_serve/unified_api/schemas.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class UnifiedMessageResponse(BaseModel):
    """统一消息响应"""
    
    message_id: str
    sender: str
    sender_name: Optional[str]
    message_type: str
    
    content: str
    thinking: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    action_report: Optional[Dict] = None
    vis_render: Optional[Dict] = None
    
    rounds: int = 0
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_unified_message(cls, msg: UnifiedMessage) -> 'UnifiedMessageResponse':
        return cls(
            message_id=msg.message_id,
            sender=msg.sender,
            sender_name=msg.sender_name,
            message_type=msg.message_type,
            content=msg.content,
            thinking=msg.thinking,
            tool_calls=msg.tool_calls,
            action_report=msg.action_report,
            vis_render=msg.vis_render,
            rounds=msg.rounds,
            created_at=msg.created_at
        )

class UnifiedMessageListResponse(BaseModel):
    """统一消息列表响应"""
    
    conv_id: Optional[str] = None
    session_id: Optional[str] = None
    total: int
    messages: List[UnifiedMessageResponse]
```

---

## 七、前端统一渲染方案

### 7.1 前端适配层

```typescript
// /web/src/api/unified-messages.ts

export interface UnifiedMessage {
  message_id: string;
  sender: string;
  sender_name?: string;
  message_type: 'human' | 'ai' | 'agent' | 'view' | 'system';
  content: string;
  thinking?: string;
  tool_calls?: ToolCall[];
  action_report?: ActionReport;
  vis_render?: VisRender;
  rounds: number;
  created_at?: string;
}

export interface UnifiedMessageListResponse {
  conv_id?: string;
  session_id?: string;
  total: number;
  messages: UnifiedMessage[];
}

export class UnifiedMessageAPI {
  /**
   * 获取对话历史消息
   */
  static async getConversationMessages(
    convId: string,
    options?: {
      limit?: number;
      includeThinking?: boolean;
      includeVis?: boolean;
    }
  ): Promise<UnifiedMessageListResponse> {
    const params = new URLSearchParams({
      limit: (options?.limit || 50).toString(),
      include_thinking: (options?.includeThinking || false).toString(),
      include_vis: (options?.includeVis || false).toString()
    });
    
    const response = await fetch(
      `/api/v1/unified/conversations/${convId}/messages?${params}`
    );
    
    return response.json();
  }
  
  /**
   * 获取渲染数据
   */
  static async getRenderData(
    convId: string,
    renderType: 'vis' | 'markdown' | 'simple' = 'vis'
  ): Promise<any> {
    const response = await fetch(
      `/api/v1/unified/conversations/${convId}/render?render_type=${renderType}`
    );
    
    return response.json();
  }
}
```

### 7.2 统一渲染组件

```typescript
// /web/src/components/chat/UnifiedMessageRenderer.tsx

import React from 'react';
import { UnifiedMessage } from '@/api/unified-messages';
import { VisRenderer } from './VisRenderer';
import { MarkdownRenderer } from './MarkdownRenderer';

interface UnifiedMessageRendererProps {
  message: UnifiedMessage;
  renderMode?: 'full' | 'simple';
}

export function UnifiedMessageRenderer({ 
  message, 
  renderMode = 'full' 
}: UnifiedMessageRendererProps) {
  
  // 判断是否有可视化数据
  const hasVisData = message.vis_render && Object.keys(message.vis_render).length > 0;
  
  // 判断是否有thinking
  const hasThinking = message.thinking && message.thinking.length > 0;
  
  // 判断是否有tool_calls
  const hasToolCalls = message.tool_calls && message.tool_calls.length > 0;
  
  // 渲染用户消息
  if (message.message_type === 'human') {
    return (
      <div className="user-message">
        <div className="message-header">
          <span className="sender-name">{message.sender_name || '用户'}</span>
          <span className="timestamp">{message.created_at}</span>
        </div>
        <div className="message-content">
          <MarkdownRenderer content={message.content} />
        </div>
      </div>
    );
  }
  
  // 渲染助手/Agent消息
  return (
    <div className="assistant-message">
      <div className="message-header">
        <span className="sender-name">{message.sender_name || '助手'}</span>
        <span className="sender-type-badge">{message.message_type}</span>
        <span className="timestamp">{message.created_at}</span>
      </div>
      
      {/* 思考过程 */}
      {hasThinking && (
        <div className="thinking-section">
          <details>
            <summary>思考过程</summary>
            <MarkdownRenderer content={message.thinking!} />
          </details>
        </div>
      )}
      
      {/* 工具调用 */}
      {hasToolCalls && (
        <div className="tool-calls-section">
          <details>
            <summary>工具调用 ({message.tool_calls!.length})</summary>
            {message.tool_calls!.map((call, idx) => (
              <ToolCallCard key={idx} toolCall={call} />
            ))}
          </details>
        </div>
      )}
      
      {/* 可视化渲染（优先） */}
      {hasVisData && renderMode === 'full' && (
        <div className="visualization-section">
          <VisRenderer data={message.vis_render!} />
        </div>
      )}
      
      {/* 消息内容 */}
      <div className="message-content">
        <MarkdownRenderer content={message.content} />
      </div>
    </div>
  );
}

// 消息列表组件
export function UnifiedMessageList({ 
  messages 
}: { 
  messages: UnifiedMessage[] 
}) {
  return (
    <div className="unified-message-list">
      {messages.map((msg) => (
        <UnifiedMessageRenderer 
          key={msg.message_id} 
          message={msg} 
        />
      ))}
    </div>
  );
}
```

### 7.3 Hook封装

```typescript
// /web/src/hooks/use-unified-messages.ts

import { useState, useEffect } from 'react';
import { UnifiedMessageAPI, UnifiedMessage } from '@/api/unified-messages';

export function useUnifiedMessages(convId: string | null) {
  const [messages, setMessages] = useState<UnifiedMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  useEffect(() => {
    if (!convId) return;
    
    loadMessages();
  }, [convId]);
  
  const loadMessages = async () => {
    if (!convId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await UnifiedMessageAPI.getConversationMessages(convId, {
        limit: 100,
        includeThinking: true,
        includeVis: true
      });
      
      setMessages(response.messages);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };
  
  const addMessage = (message: UnifiedMessage) => {
    setMessages(prev => [...prev, message]);
  };
  
  return {
    messages,
    loading,
    error,
    reload: loadMessages,
    addMessage
  };
}
```

---

## 八、兼容性处理

### 8.1 向后兼容API

```python
# /packages/derisk-serve/src/derisk_serve/conversation/api/endpoints.py
# 在原有API基础上增加适配

@router.get("/messages/history", response_model=Result[List[MessageVo]])
async def get_history_messages(
    con_uid: str, 
    service: Service = Depends(get_service)
):
    """
    获取历史消息（兼容API）
    
    底层已改用UnifiedMessageDAO，但返回格式保持不变
    """
    
    # 改造：使用UnifiedMessageDAO
    from derisk.storage.unified_message_dao import UnifiedMessageDAO
    from derisk.core.interface.unified_message import UnifiedMessage
    
    unified_dao = UnifiedMessageDAO()
    
    # 从统一存储加载
    unified_messages = await unified_dao.get_messages_by_conv_id(con_uid)
    
    # 转换为MessageVo格式（兼容现有前端）
    message_vos = []
    for msg in unified_messages:
        # 根据message_type映射role
        role_mapping = {
            "human": "human",
            "ai": "ai",
            "agent": "ai",
            "view": "view",
            "system": "system"
        }
        
        message_vos.append(
            MessageVo(
                role=role_mapping.get(msg.message_type, msg.message_type),
                context=msg.content,  # 直接使用content
                order=msg.rounds,
                time_stamp=msg.created_at,
                model_name=None,  # 从metadata中获取
                feedback=None
            )
        )
    
    return Result.succ(message_vos)
```

### 8.2 数据迁移脚本

```python
# /scripts/migrate_chat_history_to_gpts.py

"""
将chat_history数据迁移到gpts_messages
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict

from derisk.storage.chat_history.chat_history_db import ChatHistoryDao
from derisk.storage.unified_message_dao import UnifiedMessageDAO
from derisk.core.interface.unified_message import UnifiedMessage

async def migrate_chat_history():
    """迁移chat_history到gpts_messages"""
    
    chat_history_dao = ChatHistoryDao()
    unified_dao = UnifiedMessageDAO()
    
    # 1. 查询所有chat_history记录
    chat_histories = await chat_history_dao.list_all()
    
    print(f"开始迁移 {len(chat_histories)} 个对话...")
    
    for idx, history in enumerate(chat_histories):
        try:
            # 2. 解析messages字段
            messages_json = json.loads(history.messages) if history.messages else []
            
            # 3. 为每个conversation创建gpts_conversations记录
            for conv_data in messages_json:
                conv_uid = history.conv_uid
                session_id = history.conv_uid
                
                # 创建会话记录
                await unified_dao.create_conversation(
                    conv_id=conv_uid,
                    user_id=history.user_name or "unknown",
                    goal=conv_data.get('summary'),
                    chat_mode=conv_data.get('chat_mode', 'chat_normal'),
                    session_id=session_id
                )
                
                # 4. 转换消息
                unified_messages = []
                for msg_idx, msg_data in enumerate(conv_data.get('messages', [])):
                    msg_type = msg_data.get('type', 'human')
                    msg_content = msg_data.get('data', {}).get('content', '')
                    
                    unified_msg = UnifiedMessage(
                        message_id=f"{conv_uid}_msg_{msg_idx}",
                        conv_id=conv_uid,
                        conv_session_id=session_id,
                        sender="user" if msg_type == "human" else "assistant",
                        sender_name=history.user_name,
                        message_type=msg_type,
                        content=msg_content,
                        rounds=msg_data.get('round_index', 0),
                        message_index=msg_idx,
                        created_at=datetime.now()
                    )
                    
                    unified_messages.append(unified_msg)
                
                # 5. 批量保存
                await unified_dao.save_messages_batch(unified_messages)
            
            print(f"[{idx+1}/{len(chat_histories)}] 迁移完成: {history.conv_uid}")
            
        except Exception as e:
            print(f"[{idx+1}/{len(chat_histories)}] 迁移失败: {history.conv_uid}, 错误: {e}")
    
    print("迁移完成！")

if __name__ == "__main__":
    asyncio.run(migrate_chat_history())
```

---

## 九、实施计划

### 9.1 实施步骤

#### Phase 1: 数据层改造（2周）

**Week 1: DAO层实现**
1. 创建`UnifiedMessage`模型
2. 实现`UnifiedMessageDAO`
3. 编写单元测试

**Week 2: 存储适配器改造**
1. 改造`StorageConversation`
2. 改造`OnceConversation`
3. 适配测试

#### Phase 2: API层统一（1周）

**Week 3: API开发**
1. 实现统一API端点
2. 实现向后兼容API
3. API文档更新

#### Phase 3: 前端适配（1周）

**Week 4: 前端改造**
1. 实现统一渲染组件
2. 改造历史页面
3. 前端测试

#### Phase 4: 数据迁移（1周）

**Week 5: 迁移与验证**
1. 执行数据迁移脚本
2. 数据校验
3. 性能测试

#### Phase 5: 灰度发布（1周）

**Week 6: 灰度上线**
1. 灰度10%流量
2. 监控告警
3. 逐步扩大到100%
4. 下线旧表

### 9.2 关键里程碑

| 里程碑 | 完成时间 | 验收标准 |
|--------|---------|---------|
| M1: DAO层完成 | Week 2 | 单元测试通过 |
| M2: API层完成 | Week 3 | API文档更新，测试通过 |
| M3: 前端适配完成 | Week 4 | 历史页面正常渲染 |
| M4: 数据迁移完成 | Week 5 | 数据校验100%通过 |
| M5: 灰度100% | Week 6 | 无功能回退 |

---

## 十、风险与应对

### 10.1 技术风险

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 数据迁移失败 | 中 | 高 | 迁移前备份，提供回滚脚本 |
| 性能下降 | 低 | 中 | 优化索引，引入缓存 |
| 前端兼容问题 | 中 | 中 | 保留兼容API，渐进式迁移 |

### 10.2 业务风险

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 历史数据丢失 | 低 | 高 | 数据备份，迁移后校验 |
| 用户感知差 | 中 | 中 | 灰度发布，快速回滚 |

---

## 十一、总结

### 11.1 方案优势

✅ **最小改动**: 不修改Core和Core_v2 Agent架构，仅改造存储层和API层  
✅ **统一存储**: 保留gpts_messages一套表，消除数据冗余  
✅ **向后兼容**: 提供兼容API，不影响现有前端  
✅ **平滑迁移**: 提供数据迁移脚本，支持灰度发布  
✅ **易于维护**: 统一的数据模型和API，降低维护成本  

### 11.2 核心改动点

| 层次 | 改动内容 | 影响范围 |
|------|---------|---------|
| **数据层** | 新增UnifiedMessage模型和DAO | 小 |
| **存储层** | StorageConversation/OnceConversation改造 | 中 |
| **API层** | 新增统一API + 兼容API | 中 |
| **前端** | 新增统一渲染组件 | 小 |
| **数据库** | 迁移chat_history到gpts_messages | 大 |

### 11.3 后续优化方向

1. **性能优化**: 引入Redis缓存，优化查询性能
2. **功能增强**: 支持消息搜索、向量化检索
3. **监控告警**: 完善监控指标和告警规则
4. **文档完善**: 更新技术文档和用户手册

---

**方案核心思想**: 在保留一套表机制的前提下，通过**统一数据访问层**和**统一API层**，实现Core和Core_v2的历史消息统一存储和渲染，**不修改Agent架构**，**最小化改动**，**平滑迁移**。