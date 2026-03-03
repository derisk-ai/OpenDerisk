# 历史对话记录架构改造方案（理想架构版）

> 文档版本: v2.0  
> 创建日期: 2026-03-02  
> 设计原则: **架构最优、不考虑数据迁移成本**

---

## 一、当前架构的根本性问题

### 1.1 架构层面问题

#### 问题1. 数据模型分裂

```
当前状态:
┌─────────────────────────────────────────────────────┐
│  Application Layer                                   │
├─────────────────────────────────────────────────────┤
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │  Core Agents     │    │  Core_v2 Agents  │       │
│  │  (Conversable)   │    │  (Production)    │       │
│  └────────┬─────────┘    └────────┬─────────┘       │
│           │                       │                  │
│           ├───────────────────────┤                  │
│           │  两套独立的记忆系统    │                  │
│           ▼                       ▼                  │
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │ StorageConv      │    │  GptsMemory      │       │
│  └────────┬─────────┘    └────────┬─────────┘       │
│           │                       │                  │
│           ▼                       ▼                  │
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │ chat_history     │    │ gpts_convs       │       │
│  │ +                │    │ +                │       │
│  │ chat_history_msg │    │ gpts_messages    │       │
│  └──────────────────┘    └──────────────────┘       │
│                                                       │
│  数据模型不一致、重复存储、无法共享                    │
└─────────────────────────────────────────────────────┘
```

**根本问题**:
- 缺乏统一的对话领域模型
- Agent层直接依赖具体存储实现
- 违背了依赖倒置原则(DIP)

#### 问题2. 职责混乱

```
当前职责分布（混乱）:

Agent层:
  - 负责对话逻辑 ✅
  - 直接操作数据库 ❌ 
  - 处理消息格式转换 ❌
  - 维护对话状态 ❌

DAO层:
  - 简单的CRUD ✅
  - 包含业务逻辑(如状态转换) ❌
  - 跨表关联不一致 ❌

Service层:
  - 异步流程编排 ✅
  - 重复的权限校验 ❌
  - 硬编码的数据转换 ❌
```

**违反的原则**:
- 单一职责原则(SRP)
- 接口隔离原则(ISP)

#### 问题3. 扩展性差

```python
# 当前模式: 硬编码扩展
class AgentChat:
    def __init__(self):
        # 如果要支持新的对话类型,需要修改这里
        if chat_mode == "chat_normal":
            self.memory = NormalChatMemory()
        elif chat_mode == "chat_agent":
            self.memory = AgentChatMemory()
        elif chat_mode == "chat_flow":
            # 需要添加新分支
            self.memory = FlowChatMemory()
        # 违反开闭原则(OCP)
```

### 1.2 数据模型问题

#### 问题1. 存储粒度错误

```sql
-- chat_history表: 冗余的双层存储
CREATE TABLE chat_history (
    messages LONGTEXT,              -- 存储完整对话JSON ★ 冗余
    ...
);

CREATE TABLE chat_history_message (
    message_detail LONGTEXT,        -- 再次存储单条消息JSON ★ 冗余
    ...
);
```

**问题**:
- `messages`字段与`chat_history_message`表重复存储
- 同一数据两次序列化，浪费存储
- 更新时需要同步多处，一致性难保证

#### 问题2. 字段设计不合理

```sql
-- gpts_messages: 过度扁平化
CREATE TABLE gpts_messages (
    content LONGTEXT,
    thinking LONGTEXT,
    tool_calls LONGTEXT,           -- JSON存储,无法建索引
    observation LONGTEXT,
    action_report LONGTEXT,        -- JSON存储,查询困难
    ...
);
```

**问题**:
- 复杂结构存储为JSON,丧失关系型数据库优势
- 无法对这些字段建索引和高效查询
- 统计分析需要全表扫描反序列化

#### 问题3. 缺少核心实体

```
缺失的实体:

① Agent实体:
  - 当前agent信息散落在各表的varchar字段
  - 无法统一管理Agent生命周期
  - Agent间的协作关系无法建模

② Session实体:
  - conv_session_id是varchar,不是外键
  - 无法准确表达会话-对话的父子关系
  - 会话级别的配置和状态无法集中管理

③ Context实体:
  - 对话上下文散落在system_prompt和context字段
  - 无法复用和版本管理
  - 上下文的依赖关系不明确
```

### 1.3 性能问题

#### 问题1. N+1查询

```python
# 当前实现
async def load_conversation_history(conv_id):
    # 1. 查询会话
    conv = await dao.get_conversation(conv_id)
    
    # 2. 查询消息 (N+1问题)
    messages = await dao.get_messages(conv_id)
    
    # 3. 每条消息可能还需要查询工具调用
    for msg in messages:
        if msg.tool_calls:
            # N次额外的工具详情查询
            tools = await dao.get_tool_details(msg.id)
            ...
```

#### 问题2. 全表扫描

```python
# 统计查询: 无法利用索引
SELECT 
    COUNT(*) as total,
    JSON_EXTRACT(action_report, '$.tool_name') as tool_name
FROM gpts_messages
WHERE tool_calls IS NOT NULL
GROUP BY tool_name;
-- 需要全表扫描并反序列化JSON
```

### 1.4 API设计问题

#### 问题1. 接口不一致

```
当前API设计:

/api/v1/serve/conversation/messages
  └─ 返回: {role, content, context}

/api/v1/app/conversations/{conv_id}/messages  
  └─ 返回: {sender, content, thinking, tool_calls, ...}

同一个"获取消息"功能,两套API,两套数据格式
```

#### 问题2. 违反RESTful原则

```
/api/v1/chat/completions          # 面向动作,不是资源
/api/v1/app/conversations         # /app前缀混乱
/api/v1/serve/conversation        # /serve前缀冗余
```

---

## 二、理想架构设计方案

### 2.1 架构设计原则

#### 2.1.1 核心原则

1. **领域驱动设计(DDD)**
   - 建立清晰的对话领域模型
   - 聚合根、实体、值对象分离
   - 领域服务封装业务逻辑

2. **依赖倒置(DIP)**
   - 高层模块不依赖低层模块
   - 都依赖于抽象接口
   - 存储实现可插拔

3. **单一职责(SRP)**
   - 每个类只有一个变更原因
   - 清晰的层次边界

4. **开闭原则(OCP)**
   - 对扩展开放,对修改关闭
   - 策略模式和工厂模式结合

5. **接口隔离(ISP)**
   - 不应强迫客户依赖不用的方法
   - 细粒度接口

#### 2.1.2 技术原则

1. **CQRS模式**
   - 读写分离
   - 优化查询性能
   - 支持不同的数据模型

2. **Event Sourcing**
   - 消息作为事件流
   - 状态由事件推导
   - 支持时间旅行

3. **微服务友好**
   - 服务边界清晰
   - 支持独立部署
   - API版本化管理

### 2.2 领域模型设计

#### 2.2.1 核心聚合

```
Conversation聚合:

┌─────────────────────────────────────────────────┐
│  Conversation (聚合根)                           │
├─────────────────────────────────────────────────┤
│  - id: ConversationId                           │
│  - session: Session                             │  ←─┐
│  - goal: ConversationGoal                       │    │
│  - participants: Set[Participant]               │    │ 会话聚合
│  - messages: List[Message]                      │    │
│  - state: ConversationState                     │    │
│  - context: ConversationContext                 │    │
│  - metadata: Metadata                           │    │
│                                                  │    │
│  行为:                                           │    │
│  + start()                                      │    │
│  + add_message(msg)                             │    │
│  + complete()                                   │    │
│  + get_history(filter)                          │    │
│  + restore_from_events(events)                  │    │
└─────────────────────────────────────────────────┘    │
                                                       │
┌─────────────────────────────────────────────────┐  │
│  Message (实体)                                  │  │
├─────────────────────────────────────────────────┤  │
│  - id: MessageId                                │  │
│  - conversation_id: ConversationId              │──┘
│  - sender: Participant                          │
│  - content: MessageContent                      │
│  - type: MessageType                            │
│  - metadata: MessageMetadata                    │
│  - created_at: Timestamp                        │
│                                                  │
│  行为:                                           │
│  + render()                                     │
│  + to_event()                                   │
│  + contains_tools()                             │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Participant (值对象)                            │
├─────────────────────────────────────────────────┤
│  - id: ParticipantId                            │
│  - name: str                                    │
│  - type: ParticipantType                        │
│  - avatar: Optional[URL]                        │
│  - capabilities: Set[Capability]                │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  ToolExecution (实体)                            │
├─────────────────────────────────────────────────┤
│  - id: ToolExecutionId                          │
│  - message_id: MessageId                        │
│  - tool: Tool                                   │
│  - input: ToolInput                             │
│  - output: Optional[ToolOutput]                 │
│  - status: ExecutionStatus                      │
│  - metrics: ExecutionMetrics                    │
│  - started_at: Timestamp                        │
│  - finished_at: Optional[Timestamp]             │
└─────────────────────────────────────────────────┘
```

#### 2.2.2 领域服务

```python
# conversation_service.py

from typing import Protocol, List, Optional
from datetime import datetime
from dataclasses import dataclass
from abc import ABC, abstractmethod

# ==================== 领域模型 ====================

@dataclass(frozen=True)
class ConversationId:
    """对话ID值对象"""
    value: str
    
    def __post_init__(self):
        if not self.value or len(self.value) != 36:
            raise ValueError("Invalid conversation ID format")

@dataclass(frozen=True)
class MessageId:
    """消息ID值对象"""
    value: str

@dataclass(frozen=True)
class ParticipantType:
    """参与者类型枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"
    SYSTEM = "system"

@dataclass(frozen=True)
class Participant:
    """参与者值对象"""
    id: str
    name: str
    type: ParticipantType
    avatar: Optional[str] = None
    
    def is_agent(self) -> bool:
        return self.type == ParticipantType.AGENT

@dataclass
class MessageContent:
    """消息内容"""
    text: str
    thinking: Optional[str] = None
    type: str = "text"  # text, markdown, code, vis
    
    def to_plain_text(self) -> str:
        """提取纯文本"""
        # 简化版,实际可用BeautifulSoup等
        return self.text

@dataclass
class MessageMetadata:
    """消息元数据"""
    round_index: Optional[int] = None
    tokens: Optional[int] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    tags: Optional[List[str]] = None

@dataclass
class Message:
    """消息实体"""
    id: MessageId
    conversation_id: ConversationId
    sender: Participant
    content: MessageContent
    metadata: MessageMetadata
    created_at: datetime
    
    def contains_thinking(self) -> bool:
        """是否包含思考过程"""
        return self.content.thinking is not None
    
    def to_dict(self) -> dict:
        """转换为字典(用于序列化)"""
        return {
            "id": self.id.value,
            "conversation_id": self.conversation_id.value,
            "sender": {
                "id": self.sender.id,
                "name": self.sender.name,
                "type": self.sender.type
            },
            "content": {
                "text": self.content.text,
                "thinking": self.content.thinking,
                "type": self.content.type
            },
            "metadata": {
                "round_index": self.metadata.round_index,
                "tokens": self.metadata.tokens,
                "model": self.metadata.model
            },
            "created_at": self.created_at.isoformat()
        }

@dataclass
class ConversationState:
    """对话状态"""
    status: str  # active, paused, completed, failed
    last_message_id: Optional[MessageId] = None
    last_active_at: Optional[datetime] = None
    message_count: int = 0
    
    def is_active(self) -> bool:
        return self.status == "active"
    
    def is_completed(self) -> bool:
        return self.status == "completed"

@dataclass
class Conversation:
    """对话聚合根"""
    id: ConversationId
    session_id: Optional[str]  # 所属会话
    goal: Optional[str]  # 对话目标
    chat_mode: str
    participants: List[Participant]
    state: ConversationState
    created_at: datetime
    updated_at: datetime
    
    # 延迟加载的消息列表
    _messages: Optional[List[Message]] = None
    _message_repository: Optional['MessageRepository'] = None
    
    def add_message(self, message: Message) -> None:
        """添加消息"""
        if self._messages is not None:
            self._messages.append(message)
        
        # 更新状态
        self.state.last_message_id = message.id
        self.state.last_active_at = message.created_at
        self.state.message_count += 1
        self.updated_at = message.created_at
    
    async def get_messages(self) -> List[Message]:
        """获取消息列表(延迟加载)"""
        if self._messages is None and self._message_repository:
            self._messages = await self._message_repository.find_by_conversation(
                self.id
            )
        return self._messages or []
    
    async def get_latest_messages(self, limit: int = 10) -> List[Message]:
        """获取最新的N条消息"""
        messages = await self.get_messages()
        return messages[-limit:] if len(messages) > limit else messages

# ==================== 领域事件 ====================

@dataclass
class DomainEvent(ABC):
    """领域事件基类"""
    event_id: str
    occurred_at: datetime
    aggregate_id: str

@dataclass
class ConversationStarted(DomainEvent):
    """对话开始事件"""
    aggregate_id: str  # conversation_id
    goal: str
    chat_mode: str
    participants: List[Participant]

@dataclass
class MessageAdded(DomainEvent):
    """消息添加事件"""
    aggregate_id: str  # conversation_id
    message: Message

@dataclass
class ConversationCompleted(DomainEvent):
    """对话完成事件"""
    aggregate_id: str  # conversation_id
    final_message_count: int

# ==================== 仓储接口 ====================

class ConversationRepository(Protocol):
    """对话仓储接口"""
    
    async def save(self, conversation: Conversation) -> None:
        """保存对话"""
        ...
    
    async def find_by_id(self, id: ConversationId) -> Optional[Conversation]:
        """根据ID查找对话"""
        ...
    
    async def find_by_session(
        self, 
        session_id: str,
        limit: int = 100
    ) -> List[Conversation]:
        """查找会话下的所有对话"""
        ...
    
    async def find_by_participant(
        self,
        participant_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Conversation]:
        """查找参与者的对话"""
        ...
    
    async def update_state(
        self,
        id: ConversationId,
        state: ConversationState
    ) -> None:
        """更新对话状态"""
        ...

class MessageRepository(Protocol):
    """消息仓储接口"""
    
    async def save(self, message: Message) -> None:
        """保存消息"""
        ...
    
    async def save_batch(self, messages: List[Message]) -> None:
        """批量保存消息"""
        ...
    
    async def find_by_id(self, id: MessageId) -> Optional[Message]:
        """根据ID查找消息"""
        ...
    
    async def find_by_conversation(
        self,
        conversation_id: ConversationId,
        limit: Optional[int] = None,
        offset: int = 0,
        order: str = 'asc'
    ) -> List[Message]:
        """查找对话的所有消息"""
        ...
    
    async def find_latest(
        self,
        conversation_id: ConversationId,
        limit: int = 10
    ) -> List[Message]:
        """查找最新的N条消息"""
        ...
    
    async def delete_by_conversation(self, conversation_id: ConversationId) -> None:
        """删除对话的所有消息"""
        ...

# ==================== 领域服务 ====================

class ConversationService:
    """对话领域服务"""
    
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        event_publisher: 'EventPublisher'
    ):
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.event_publisher = event_publisher
    
    async def start_conversation(
        self,
        chat_mode: str,
        goal: Optional[str],
        participants: List[Participant],
        session_id: Optional[str] = None
    ) -> Conversation:
        """开始新对话"""
        
        # 创建对话
        conversation_id = ConversationId(self._generate_id())
        now = datetime.now()
        
        conversation = Conversation(
            id=conversation_id,
            session_id=session_id,
            goal=goal,
            chat_mode=chat_mode,
            participants=participants,
            state=ConversationState(
                status="active",
                message_count=0
            ),
            created_at=now,
            updated_at=now
        )
        
        # 注入仓储(用于延迟加载)
        conversation._message_repository = self.message_repo
        
        # 持久化
        await self.conversation_repo.save(conversation)
        
        # 发布领域事件
        await self.event_publisher.publish(
            ConversationStarted(
                event_id=self._generate_id(),
                occurred_at=now,
                aggregate_id=conversation_id.value,
                goal=goal or "",
                chat_mode=chat_mode,
                participants=participants
            )
        )
        
        return conversation
    
    async def add_message(
        self,
        conversation_id: ConversationId,
        sender: Participant,
        content: MessageContent,
        metadata: Optional[MessageMetadata] = None
    ) -> Message:
        """添加消息到对话"""
        
        # 加载对话
        conversation = await self.conversation_repo.find_by_id(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        if not conversation.state.is_active():
            raise ValueError(f"Conversation {conversation_id} is not active")
        
        # 创建消息
        message = Message(
            id=MessageId(self._generate_id()),
            conversation_id=conversation_id,
            sender=sender,
            content=content,
            metadata=metadata or MessageMetadata(
                round_index=conversation.state.message_count
            ),
            created_at=datetime.now()
        )
        
        # 添加到对话
        conversation.add_message(message)
        
        # 持久化
        await self.message_repo.save(message)
        await self.conversation_repo.update_state(
            conversation_id,
            conversation.state
        )
        
        # 发布事件
        await self.event_publisher.publish(
            MessageAdded(
                event_id=self._generate_id(),
                occurred_at=message.created_at,
                aggregate_id=conversation_id.value,
                message=message
            )
        )
        
        return message
    
    async def complete_conversation(
        self,
        conversation_id: ConversationId
    ) -> None:
        """完成对话"""
        
        conversation = await self.conversation_repo.find_by_id(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        # 更新状态
        conversation.state.status = "completed"
        conversation.updated_at = datetime.now()
        
        await self.conversation_repo.update_state(
            conversation_id,
            conversation.state
        )
        
        # 发布事件
        await self.event_publisher.publish(
            ConversationCompleted(
                event_id=self._generate_id(),
                occurred_at=conversation.updated_at,
                aggregate_id=conversation_id.value,
                final_message_count=conversation.state.message_count
            )
        )
    
    async def get_conversation_history(
        self,
        conversation_id: ConversationId,
        limit: Optional[int] = None,
        include_metadata: bool = True
    ) -> Optional[Conversation]:
        """获取对话历史"""
        
        conversation = await self.conversation_repo.find_by_id(conversation_id)
        if not conversation:
            return None
        
        # 加载消息
        if limit:
            conversation._messages = await self.message_repo.find_latest(
                conversation_id,
                limit=limit
            )
        else:
            conversation._messages = await self.message_repo.find_by_conversation(
                conversation_id
            )
        
        return conversation
    
    def _generate_id(self) -> str:
        import uuid
        return str(uuid.uuid4())

# ==================== 事件发布者 ====================

class EventPublisher(Protocol):
    """事件发布者接口"""
    
    async def publish(self, event: DomainEvent) -> None:
        """发布领域事件"""
        ...
    
    async def publish_batch(self, events: List[DomainEvent]) -> None:
        """批量发布事件"""
        ...
```

### 2.3 数据库设计方案

#### 2.3.1 表结构设计

```sql
-- ============================================
-- 核心表: 优化设计
-- ============================================

-- 1. 对话表 (聚合根)
CREATE TABLE conversations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 核心标识
    conv_id VARCHAR(36) UNIQUE NOT NULL,
    session_id VARCHAR(36),                        -- 所属会话
    parent_conv_id VARCHAR(36),                    -- 父对话(支持对话树)
    
    -- 对话目标
    goal TEXT,
    goal_embedding VECTOR(1536),                   -- 目标向量化(用于相似对话检索)
    
    -- 分类与模式
    chat_mode VARCHAR(50) NOT NULL,                -- chat_normal/chat_agent/chat_flow
    agent_type VARCHAR(50),                        -- core/core_v2
    
    -- 参与者 (JSON数组,支持多方对话)
    participants JSON NOT NULL,
    participant_ids JSON,                          -- 参与者ID数组(用于索引)
    
    -- 状态
    status VARCHAR(50) NOT NULL,
    last_message_id VARCHAR(36),
    message_count INT DEFAULT 0,
    last_active_at DATETIME,
    
    -- 配置
    config JSON,                                   -- 对话配置(temperature等)
    
    -- 时间戳
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_session (session_id),
    INDEX idx_status (status),
    INDEX idx_chat_mode (chat_mode),
    INDEX idx_last_active (last_active_at),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL,
    
    -- 全文索引(用于搜索)
    FULLTEXT INDEX ft_goal (goal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 消息表 (实体)
CREATE TABLE messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 关联
    conv_id VARCHAR(36) NOT NULL,
    parent_msg_id VARCHAR(36),                     -- 父消息(支持消息树)
    
    -- 核心标识
    msg_id VARCHAR(36) UNIQUE NOT NULL,
    msg_index INT NOT NULL,                        -- 消息序号
    round_index INT,                               -- 轮次索引
    
    -- 发送者
    sender_id VARCHAR(255) NOT NULL,
    sender_type VARCHAR(50) NOT NULL,              -- user/assistant/agent/system
    sender_name VARCHAR(255),
    
    -- 内容
    content TEXT NOT NULL,
    content_embedding VECTOR(1536),                -- 内容向量化
    content_type VARCHAR(50) DEFAULT 'text',       -- text/markdown/code/vis
    
    -- 扩展内容 (分离存储,避免单个字段过大)
    thinking TEXT,                                 -- 思考过程
    observation TEXT,                              -- 观察结果
    
    -- 元数据
    tokens_used INT,
    model_name VARCHAR(100),
    latency_ms INT,
    tags JSON,
    
    -- 可视化
    vis_type VARCHAR(50),
    vis_data JSON,
    
    -- 时间戳
    created_at DATETIME NOT NULL,
    
    -- 索引
    INDEX idx_conv (conv_id),
    INDEX idx_msg_id (msg_id),
    INDEX idx_sender (sender_id, sender_type),
    INDEX idx_round (conv_id, round_index),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (conv_id) REFERENCES conversations(conv_id) ON DELETE CASCADE,
    
    -- 全文索引
    FULLTEXT INDEX ft_content (content)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 工具执行表 (实体)
CREATE TABLE tool_executions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 关联
    msg_id VARCHAR(36) NOT NULL,
    conv_id VARCHAR(36) NOT NULL,
    
    -- 核心标识
    execution_id VARCHAR(36) UNIQUE NOT NULL,
    
    -- 工具信息
    tool_name VARCHAR(255) NOT NULL,
    tool_type VARCHAR(50),                         -- function/code/api
    tool_provider VARCHAR(100),                    -- 工具提供者
    
    -- 输入输出
    input_params JSON NOT NULL,
    output_result JSON,
    output_type VARCHAR(50),                       -- text/json/file
    
    -- 执行状态
    status VARCHAR(50) NOT NULL,                   -- pending/running/success/failed
    error_message TEXT,
    
    -- 执行指标
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    duration_ms INT,
    memory_used_mb DECIMAL(10,2),
    cpu_percent DECIMAL(5,2),
    
    -- 索引
    INDEX idx_msg (msg_id),
    INDEX idx_conv (conv_id),
    INDEX idx_tool_name (tool_name),
    INDEX idx_status (status),
    INDEX idx_started_at (started_at),
    FOREIGN KEY (msg_id) REFERENCES messages(msg_id) ON DELETE CASCADE,
    FOREIGN KEY (conv_id) REFERENCES conversations(conv_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 会话表 (新增: 支持会话管理)
CREATE TABLE sessions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 核心标识
    session_id VARCHAR(36) UNIQUE NOT NULL,
    parent_session_id VARCHAR(36),                 -- 父会话
    
    -- 用户信息
    user_id VARCHAR(255) NOT NULL,
    
    -- 会话信息
    title VARCHAR(255),                            -- 会话标题
    description TEXT,                              -- 会话描述
    
    -- 关联应用
    app_id VARCHAR(255),
    app_name VARCHAR(255),
    
    -- 状态
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    conversation_count INT DEFAULT 0,
    
    -- 配置
    config JSON,                                   -- 会话配置
    
    -- 时间戳
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_user (user_id),
    INDEX idx_app (app_id),
    INDEX idx_status (status),
    INDEX idx_parent (parent_session_id),
    
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Agent注册表 (新增: 支持Agent管理)
CREATE TABLE agents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 核心标识
    agent_id VARCHAR(255) UNIQUE NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    
    -- Agent信息
    agent_type VARCHAR(50) NOT NULL,               -- core/core_v2
    description TEXT,
    avatar VARCHAR(500),
    
    -- 能力
    capabilities JSON NOT NULL,                    -- 能力列表
    supported_modes JSON,                          -- 支持的对话模式
    
    -- 配置
    default_config JSON,                           -- 默认配置
    system_prompt TEXT,                            -- 系统提示词
    
    -- 状态
    status VARCHAR(50) DEFAULT 'active',
    version VARCHAR(50),
    
    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_name (agent_name),
    INDEX idx_type (agent_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 消息模板表 (新增: 支持模板复用)
CREATE TABLE message_templates (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 核心标识
    template_id VARCHAR(36) UNIQUE NOT NULL,
    template_name VARCHAR(255) NOT NULL,
    
    -- 分类
    category VARCHAR(100),                         -- system/user/assistant
    tags JSON,
    
    -- 内容
    content TEXT NOT NULL,
    variables JSON,                                -- 模板变量定义
    
    -- 元数据
    description TEXT,
    version VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_category (category),
    INDEX idx_name (template_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 对话统计表 (新增: 支持CQRS读模型)
CREATE TABLE conversation_stats (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 关联
    conv_id VARCHAR(36) UNIQUE NOT NULL,
    
    -- 统计指标
    total_messages INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    total_tool_calls INT DEFAULT 0,
    avg_message_length DECIMAL(10,2),
    avg_latency_ms DECIMAL(10,2),
    
    -- 参与者统计
    unique_participants INT DEFAULT 0,
    agent_participants INT DEFAULT 0,
    
    -- 时间统计
    duration_seconds INT,
    first_message_at DATETIME,
    last_message_at DATETIME,
    
    -- 工具统计(JSON)
    tool_usage_stats JSON,
    
    -- 更新时间
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_conv (conv_id),
    FOREIGN KEY (conv_id) REFERENCES conversations(conv_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 对话事件流表 (新增: 支持Event Sourcing)
CREATE TABLE conversation_events (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 事件标识
    event_id VARCHAR(36) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_version INT NOT NULL,
    
    -- 聚合信息
    aggregate_id VARCHAR(36) NOT NULL,             -- conversation_id
    aggregate_type VARCHAR(50) DEFAULT 'conversation',
    
    -- 事件数据
    event_data JSON NOT NULL,
    
    -- 元数据
    caused_by VARCHAR(255),                        -- 触发者
    correlation_id VARCHAR(36),                    -- 关联ID
    
    -- 时间戳
    occurred_at DATETIME NOT NULL,
    stored_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_aggregate (aggregate_id, occurred_at),
    INDEX idx_event_type (event_type),
    INDEX idx_correlation (correlation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 2.3.2 设计亮点

**1. 分离存储与查询**

```
写模型(OLTP):
  ├─ conversations        (主表)
  ├─ messages             (明细表)
  └─ tool_executions      (执行记录)

读模型(OLAP):
  └─ conversation_stats   (统计视图)
```

**2. 向量化支持**

```sql
-- 内容向量化字段
content_embedding VECTOR(1536)

-- 支持向量检索(相似对话)
SELECT conv_id, 
       COSINE_SIMILARITY(content_embedding, :query_vector) as similarity
FROM messages
WHERE COSINE_SIMILARITY(content_embedding, :query_vector) > 0.8
ORDER BY similarity DESC
LIMIT 10;
```

**3. 全文检索**

```sql
-- 支持全文搜索
SELECT * FROM conversations 
WHERE MATCH(goal) AGAINST('数据查询' IN NATURAL LANGUAGE MODE);

SELECT * FROM messages 
WHERE MATCH(content) AGAINST('错误修复' IN BOOLEAN MODE);
```

**4. 事件溯源**

```sql
-- 所有状态变更记录为事件
conversation_events表记录:
  - ConversationStarted
  - MessageAdded
  - ToolExecuted
  - ConversationCompleted
  
可以通过重放事件恢复任意时间点的状态
```

### 2.4 分层架构设计

#### 2.4.1 架构层次

```
┌─────────────────────────────────────────────────────────┐
│  Presentation Layer (表现层)                             │
├─────────────────────────────────────────────────────────┤
│  API Controllers (HTTP/gRPC/WebSocket)                  │
│  ├─ ConversationController                             │
│  ├─ MessageController                                  │
│  ├─ SessionController                                  │
│  └─ AgentController                                    │
│                                                          │
│  Request/Response DTOs                                 │
│  ├─ CreateConversationRequest                          │
│  ├─ AddMessageRequest                                  │
│  ├─ ConversationResponse                               │
│  └─ MessageResponse                                    │
└─────────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Application Layer (应用层)                              │
├─────────────────────────────────────────────────────────┤
│  Application Services (用例编排)                         │
│  ├─ ConversationAppService                             │
│  │   ├─ start_conversation()                          │
│  │   ├─ send_message()                                │
│  │   ├─ stream_message()                              │
│  │   └─ get_history()                                 │
│  │                                                      │
│  ├─ AgentAppService                                    │
│  │   ├─ register_agent()                              │
│  │   ├─ execute_agent_task()                          │
│  │   └─ get_agent_status()                            │
│  │                                                      │
│  └─ SessionAppService                                  │
│      ├─ create_session()                              │
│      ├─ list_sessions()                               │
│      └─ archive_session()                             │
│                                                          │
│  Event Handlers (事件处理)                              │
│  ├─ ConversationStartedHandler                        │
│  │   └─ 更新统计、发送通知                             │
│  ├─ MessageAddedHandler                               │
│  │   └─ 更新索引、触发webhook                          │
│  └─ ToolExecutedHandler                               │
│      └─ 记录指标、发送监控                             │
└─────────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Domain Layer (领域层)                                   │
├─────────────────────────────────────────────────────────┤
│  Aggregates (聚合)                                      │
│  ├─ Conversation (聚合根)                              │
│  │   ├─ add_message()                                 │
│  │   ├─ complete()                                    │
│  │   └─ restore_from_events()                         │
│  │                                                      │
│  └─ Session (聚合根)                                   │
│      ├─ add_conversation()                            │
│      └─ archive()                                     │
│                                                          │
│  Entities (实体)                                        │
│  ├─ Message                                            │
│  ├─ ToolExecution                                      │
│  └─ Agent                                              │
│                                                          │
│  Value Objects (值对象)                                │
│  ├─ ConversationId                                     │
│  ├─ MessageId                                          │
│  ├─ Participant                                        │
│  ├─ MessageContent                                     │
│  └─ ConversationState                                  │
│                                                          │
│  Domain Services (领域服务)                             │
│  ├─ ConversationService                               │
│  ├─ AgentService                                      │
│  └─ PermissionService                                 │
│                                                          │
│  Domain Events (领域事件)                               │
│  ├─ ConversationStarted                               │
│  ├─ MessageAdded                                      │
│  ├─ ToolExecuted                                      │
│  └─ ConversationCompleted                             │
│                                                          │
│  Repository Interfaces (仓储接口)                       │
│  ├─ ConversationRepository                            │
│  ├─ MessageRepository                                 │
│  ├─ AgentRepository                                   │
│  └─ SessionRepository                                 │
└─────────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Infrastructure Layer (基础设施层)                       │
├─────────────────────────────────────────────────────────┤
│  Repository Implementations (仓储实现)                  │
│  ├─ SQLAlchemyConversationRepository                   │
│  ├─ SQLAlchemyMessageRepository                       │
│  ├─ RedisConversationCacheRepository                  │
│  └─ ElasticsearchConversationSearchRepository         │
│                                                          │
│  Event Store (事件存储)                                 │
│  ├─ PostgresEventStore                                │
│  └─ KafkaEventBus                                     │
│                                                          │
│  External Services (外部服务)                           │
│  ├─ LLMService (LLM调用)                               │
│  ├─ VectorDBService (向量检索)                         │
│  ├─ ObjectStorageService (文件存储)                    │
│  └─ MessageQueueService (消息队列)                     │
│                                                          │
│  Cross-Cutting Concerns (横切关注点)                    │
│  ├─ Logging                                           │
│  ├─ Monitoring (Prometheus/Metrics)                   │
│  ├─ Tracing (OpenTelemetry)                           │
│  ├─ Caching (Redis)                                   │
│  └─ Security (Authentication/Authorization)           │
└─────────────────────────────────────────────────────────┘
```

#### 2.4.2 核心代码实现

**应用层服务**:

```python
# /application/services/conversation_app_service.py

from typing import List, Optional, AsyncGenerator
from datetime import datetime
import inject

class ConversationAppService:
    """对话应用服务"""
    
    @inject.autoparams()
    def __init__(
        self,
        conversation_service: ConversationService,
        event_publisher: EventPublisher,
        llm_service: 'LLMService',
        cache: 'CacheService'
    ):
        self.conversation_service = conversation_service
        self.event_publisher = event_publisher
        self.llm_service = llm_service
        self.cache = cache
    
    async def start_conversation(
        self,
        request: 'CreateConversationRequest'
    ) -> 'ConversationResponse':
        """
        创建新对话
        
        用例: 用户发起一个新的对话
        """
        
        # 1. 构建参与者
        participants = [
            Participant(
                id=request.user_id,
                name=request.user_name or request.user_id,
                type=ParticipantType.USER
            )
        ]
        
        if request.agent_id:
            # 加载Agent信息
            agent = await self._load_agent(request.agent_id)
            participants.append(
                Participant(
                    id=agent.agent_id,
                    name=agent.agent_name,
                    type=ParticipantType.AGENT
                )
            )
        
        # 2. 创建对话(领域服务)
        conversation = await self.conversation_service.start_conversation(
            chat_mode=request.chat_mode,
            goal=request.goal,
            participants=participants,
            session_id=request.session_id
        )
        
        # 3. 缓存对话
        await self.cache.set(
            f"conv:{conversation.id.value}",
            conversation.to_dict(),
            ttl=3600
        )
        
        # 4. 返回响应
        return ConversationResponse.from_entity(conversation)
    
    async def send_message(
        self,
        request: 'AddMessageRequest'
    ) -> 'MessageResponse':
        """
        发送消息
        
        用例: 用户向对话发送消息
        """
        
        conversation_id = ConversationId(request.conversation_id)
        
        # 1. 构建消息内容
        content = MessageContent(
            text=request.content,
            type=request.content_type or 'text'
        )
        
        # 2. 构建发送者
        sender = Participant(
            id=request.sender_id,
            name=request.sender_name,
            type=ParticipantType(request.sender_type)
        )
        
        # 3. 构建元数据
        metadata = MessageMetadata(
            round_index=request.round_index
        )
        
        # 4. 添加消息
        message = await self.conversation_service.add_message(
            conversation_id=conversation_id,
            sender=sender,
            content=content,
            metadata=metadata
        )
        
        # 5. 更新缓存
        await self.cache.delete(f"conv:{conversation_id.value}")
        
        return MessageResponse.from_entity(message)
    
    async def stream_message(
        self,
        request: 'StreamMessageRequest'
    ) -> AsyncGenerator['StreamMessageChunk', None]:
        """
        流式消息处理
        
        用例: 支持SSE流式响应
        """
        
        conversation_id = ConversationId(request.conversation_id)
        
        # 1. 先发送用户消息
        user_message = await self.send_message(
            AddMessageRequest(
                conversation_id=request.conversation_id,
                sender_id=request.user_id,
                sender_type="user",
                content=request.user_message
            )
        )
        
        yield StreamMessageChunk(
            type="user_message",
            data=user_message.to_dict()
        )
        
        # 2. 加载对话历史
        conversation = await self.conversation_service.get_conversation_history(
            conversation_id,
            limit=20  # 最近20条作为上下文
        )
        
        # 3. 调用LLM流式生成
        assistant_content = []
        thinking_content = []
        
        async for chunk in self.llm_service.stream_generate(
            conversation=conversation,
            user_message=user_message,
            config=request.llm_config
        ):
            if chunk.type == "content":
                assistant_content.append(chunk.text)
                yield StreamMessageChunk(
                    type="content",
                    data={"text": chunk.text}
                )
            
            elif chunk.type == "thinking":
                thinking_content.append(chunk.text)
                yield StreamMessageChunk(
                    type="thinking",
                    data={"thinking": chunk.text}
                )
            
            elif chunk.type == "tool_call":
                yield StreamMessageChunk(
                    type="tool_call",
                    data=chunk.tool_call
                )
        
        # 4. 保存助手消息
        assistant_message = await self.send_message(
            AddMessageRequest(
                conversation_id=request.conversation_id,
                sender_id=request.agent_id or "assistant",
                sender_type="assistant",
                sender_name=request.agent_name,
                content="".join(assistant_content),
                metadata={
                    "thinking": "".join(thinking_content) if thinking_content else None
                }
            )
        )
        
        yield StreamMessageChunk(
            type="done",
            data={"message_id": assistant_message.id.value}
        )
    
    async def get_conversation_history(
        self,
        request: 'GetHistoryRequest'
    ) -> 'ConversationHistoryResponse':
        """
        获取对话历史
        
        用例: 加载对话历史用于渲染
        """
        
        conversation_id = ConversationId(request.conversation_id)
        
        # 1. 尝试从缓存加载
        cached = await self.cache.get(f"conv:{conversation_id.value}")
        if cached and not request.force_refresh:
            return ConversationHistoryResponse(**cached)
        
        # 2. 从数据库加载
        conversation = await self.conversation_service.get_conversation_history(
            conversation_id,
            limit=request.limit,
            include_metadata=True
        )
        
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        # 3. 转换为响应
        response = ConversationHistoryResponse.from_entity(conversation)
        
        # 4. 更新缓存
        await self.cache.set(
            f"conv:{conversation_id.value}",
            response.dict(),
            ttl=3600
        )
        
        return response
    
    async def search_conversations(
        self,
        request: 'SearchConversationRequest'
    ) -> List['ConversationSearchResult']:
        """
        搜索对话
        
        用例: 按关键词或向量检索对话
        """
        
        # 1. 如果提供了向量,使用向量检索
        if request.query_vector:
            results = await self._vector_search(
                query_vector=request.query_vector,
                limit=request.limit
            )
        # 2. 否则使用全文检索
        else:
            results = await self._fulltext_search(
                query=request.query,
                filters=request.filters,
                limit=request.limit
            )
        
        return results
    
    async def _load_agent(self, agent_id: str) -> 'Agent':
        """加载Agent信息"""
        # 实现略
        pass
    
    async def _vector_search(
        self,
        query_vector: List[float],
        limit: int
    ) -> List['ConversationSearchResult']:
        """向量检索"""
        # 实现略
        pass
    
    async def _fulltext_search(
        self,
        query: str,
        filters: dict,
        limit: int
    ) -> List['ConversationSearchResult']:
        """全文检索"""
        # 实现略
        pass
```

**表现层控制器**:

```python
# /api/controllers/conversation_controller.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import List

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

@router.post("", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    service: ConversationAppService = Depends(get_conversation_app_service)
):
    """
    创建新对话
    
    POST /api/v1/conversations
    """
    try:
        return await service.start_conversation(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation(
    conversation_id: str,
    limit: Optional[int] = Query(50, ge=1, le=1000),
    service: ConversationAppService = Depends(get_conversation_app_service)
):
    """
    获取对话详情和历史消息
    
    GET /api/v1/conversations/{conversation_id}
    """
    request = GetHistoryRequest(
        conversation_id=conversation_id,
        limit=limit
    )
    try:
        return await service.get_conversation_history(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def add_message(
    conversation_id: str,
    request: AddMessageRequest,
    service: ConversationAppService = Depends(get_conversation_app_service)
):
    """
    向对话添加消息
    
    POST /api/v1/conversations/{conversation_id}/messages
    """
    request.conversation_id = conversation_id
    try:
        return await service.send_message(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{conversation_id}/stream")
async def stream_message(
    conversation_id: str,
    request: StreamMessageRequest,
    service: ConversationAppService = Depends(get_conversation_app_service)
):
    """
    流式消息处理(SSE)
    
    POST /api/v1/conversations/{conversation_id}/stream
    """
    request.conversation_id = conversation_id
    
    async def event_generator():
        async for chunk in service.stream_message(request):
            yield f"data: {chunk.json()}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

@router.get("", response_model=List[ConversationSummaryResponse])
async def list_conversations(
    user_id: str = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: ConversationAppService = Depends(get_conversation_app_service)
):
    """
    列出用户的对话列表
    
    GET /api/v1/conversations?user_id=xxx&status=active&limit=20&offset=0
    """
    # 实现略
    pass

@router.post("/search")
async def search_conversations(
    request: SearchConversationRequest,
    service: ConversationAppService = Depends(get_conversation_app_service)
):
    """
    搜索对话
    
    POST /api/v1/conversations/search
    """
    return await service.search_conversations(request)
```

### 2.5 仓储实现设计

#### 2.5.1 仓储接口实现

```python
# /infrastructure/persistence/sqlalchemy_conversation_repository.py

from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc
from datetime import datetime

class SQLAlchemyConversationRepository:
    """基于SQLAlchemy的对话仓储实现"""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    async def save(self, conversation: Conversation) -> None:
        """保存对话"""
        async with self.session_factory() as session:
            # 转换为ORM实体
            entity = ConversationEntity(
                conv_id=conversation.id.value,
                session_id=conversation.session_id,
                goal=conversation.goal,
                chat_mode=conversation.chat_mode,
                participants=[p.__dict__ for p in conversation.participants],
                status=conversation.state.status,
                last_message_id=conversation.state.last_message_id.value if conversation.state.last_message_id else None,
                message_count=conversation.state.message_count,
                last_active_at=conversation.state.last_active_at,
                started_at=conversation.created_at,
                updated_at=conversation.updated_at
            )
            
            session.add(entity)
            await session.commit()
    
    async def find_by_id(self, id: ConversationId) -> Optional[Conversation]:
        """根据ID查找对话"""
        async with self.session_factory() as session:
            entity = await session.query(ConversationEntity).filter_by(
                conv_id=id.value
            ).first()
            
            if not entity:
                return None
            
            return self._to_domain(entity)
    
    async def find_by_session(
        self, 
        session_id: str,
        limit: int = 100
    ) -> List[Conversation]:
        """查找会话下的所有对话"""
        async with self.session_factory() as session:
            entities = await session.query(ConversationEntity).filter_by(
                session_id=session_id,
                status="active"
            ).order_by(
                desc(ConversationEntity.last_active_at)
            ).limit(limit).all()
            
            return [self._to_domain(e) for e in entities]
    
    async def update_state(
        self,
        id: ConversationId,
        state: ConversationState
    ) -> None:
        """更新对话状态"""
        async with self.session_factory() as session:
            await session.query(ConversationEntity).filter_by(
                conv_id=id.value
            ).update({
                "status": state.status,
                "last_message_id": state.last_message_id.value if state.last_message_id else None,
                "message_count": state.message_count,
                "last_active_at": state.last_active_at,
                "updated_at": datetime.now()
            })
            
            await session.commit()
    
    def _to_domain(self, entity: ConversationEntity) -> Conversation:
        """将ORM实体转换为领域模型"""
        participants = [
            Participant(**p) 
            for p in entity.participants
        ]
        
        return Conversation(
            id=ConversationId(entity.conv_id),
            session_id=entity.session_id,
            goal=entity.goal,
            chat_mode=entity.chat_mode,
            participants=participants,
            state=ConversationState(
                status=entity.status,
                last_message_id=MessageId(entity.last_message_id) if entity.last_message_id else None,
                message_count=entity.message_count,
                last_active_at=entity.last_active_at
            ),
            created_at=entity.started_at,
            updated_at=entity.updated_at
        )

class SQLAlchemyMessageRepository:
    """基于SQLAlchemy的消息仓储实现"""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    async def save(self, message: Message) -> None:
        """保存消息"""
        async with self.session_factory() as session:
            entity = MessageEntity(
                msg_id=message.id.value,
                conv_id=message.conversation_id.value,
                sender_id=message.sender.id,
                sender_type=message.sender.type,
                sender_name=message.sender.name,
                content=message.content.text,
                content_type=message.content.type,
                thinking=message.content.thinking,
                msg_index=message.metadata.round_index or 0,
                round_index=message.metadata.round_index,
                tokens_used=message.metadata.tokens,
                model_name=message.metadata.model,
                latency_ms=message.metadata.latency_ms,
                created_at=message.created_at
            )
            
            session.add(entity)
            await session.commit()
    
    async def save_batch(self, messages: List[Message]) -> None:
        """批量保存消息"""
        async with self.session_factory() as session:
            entities = [
                MessageEntity(
                    msg_id=msg.id.value,
                    conv_id=msg.conversation_id.value,
                    sender_id=msg.sender.id,
                    sender_type=msg.sender.type,
                    sender_name=msg.sender.name,
                    content=msg.content.text,
                    content_type=msg.content.type,
                    thinking=msg.content.thinking,
                    msg_index=msg.metadata.round_index or 0,
                    round_index=msg.metadata.round_index,
                    created_at=msg.created_at
                )
                for msg in messages
            ]
            
            session.add_all(entities)
            await session.commit()
    
    async def find_by_conversation(
        self,
        conversation_id: ConversationId,
        limit: Optional[int] = None,
        offset: int = 0,
        order: str = 'asc'
    ) -> List[Message]:
        """查找对话的所有消息"""
        async with self.session_factory() as session:
            query = session.query(MessageEntity).filter_by(
                conv_id=conversation_id.value
            )
            
            if order == 'desc':
                query = query.order_by(desc(MessageEntity.created_at))
            else:
                query = query.order_by(MessageEntity.created_at)
            
            if limit:
                query = query.limit(limit).offset(offset)
            
            entities = await query.all()
            
            return [self._to_domain(e) for e in entities]
    
    async def find_latest(
        self,
        conversation_id: ConversationId,
        limit: int = 10
    ) -> List[Message]:
        """查找最新的N条消息"""
        return await self.find_by_conversation(
            conversation_id,
            limit=limit,
            order='desc'
        )
    
    def _to_domain(self, entity: MessageEntity) -> Message:
        """将ORM实体转换为领域模型"""
        return Message(
            id=MessageId(entity.msg_id),
            conversation_id=ConversationId(entity.conv_id),
            sender=Participant(
                id=entity.sender_id,
                type=entity.sender_type,
                name=entity.sender_name
            ),
            content=MessageContent(
                text=entity.content,
                type=entity.content_type,
                thinking=entity.thinking
            ),
            metadata=MessageMetadata(
                round_index=entity.round_index,
                tokens=entity.tokens_used,
                model=entity.model_name,
                latency_ms=entity.latency_ms
            ),
            created_at=entity.created_at
        )
```

#### 2.5.2 缓存装饰器

```python
# /infrastructure/persistence/cached_conversation_repository.py

class CachedConversationRepository:
    """带缓存的对话仓储(装饰器模式)"""
    
    def __init__(
        self,
        inner_repository: ConversationRepository,
        cache: 'CacheService'
    ):
        self.inner = inner_repository
        self.cache = cache
    
    async def find_by_id(self, id: ConversationId) -> Optional[Conversation]:
        """查找对话(带缓存)"""
        
        # 1. 尝试从缓存获取
        cache_key = f"conv:{id.value}"
        cached_data = await self.cache.get(cache_key)
        
        if cached_data:
            # 从缓存恢复
            return self._from_cache(cached_data)
        
        # 2. 从数据库加载
        conversation = await self.inner.find_by_id(id)
        
        if conversation:
            # 3. 写入缓存
            await self.cache.set(
                cache_key,
                self._to_cache(conversation),
                ttl=3600
            )
        
        return conversation
    
    async def save(self, conversation: Conversation) -> None:
        """保存对话(失效缓存)"""
        
        # 1. 保存到数据库
        await self.inner.save(conversation)
        
        # 2. 失效缓存
        cache_key = f"conv:{conversation.id.value}"
        await self.cache.delete(cache_key)
    
    async def update_state(
        self,
        id: ConversationId,
        state: ConversationState
    ) -> None:
        """更新状态(失效缓存)"""
        
        await self.inner.update_state(id, state)
        
        # 失效缓存
        cache_key = f"conv:{id.value}"
        await self.cache.delete(cache_key)
    
    def _to_cache(self, conversation: Conversation) -> dict:
        """转换为缓存格式"""
        return {
            "id": conversation.id.value,
            "session_id": conversation.session_id,
            "goal": conversation.goal,
            "chat_mode": conversation.chat_mode,
            "participants": [p.__dict__ for p in conversation.participants],
            "state": {
                "status": conversation.state.status,
                "message_count": conversation.state.message_count
            },
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat()
        }
    
    def _from_cache(self, data: dict) -> Conversation:
        """从缓存恢复"""
        return Conversation(
            id=ConversationId(data["id"]),
            session_id=data.get("session_id"),
            goal=data.get("goal"),
            chat_mode=data["chat_mode"],
            participants=[
                Participant(**p) 
                for p in data["participants"]
            ],
            state=ConversationState(
                status=data["state"]["status"],
                message_count=data["state"]["message_count"]
            ),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )
```

### 2.6 Agent集成设计

#### 2.6.1 Agent适配器接口

```python
# /domain/agents/agent_adapter.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class AgentAdapter(ABC):
    """Agent适配器接口"""
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化Agent"""
        pass
    
    @abstractmethod
    async def process_message(
        self,
        conversation: Conversation,
        message: Message
    ) -> AsyncGenerator[Message, None]:
        """处理消息(流式)"""
        pass
    
    @abstractmethod
    async def load_memory(self, conversation_id: ConversationId) -> None:
        """加载记忆"""
        pass
    
    @abstractmethod
    async def save_memory(self, conversation_id: ConversationId) -> None:
        """保存记忆"""
        pass
    
    @abstractmethod
    def get_agent_info(self) -> 'AgentInfo':
        """获取Agent信息"""
        pass

class AgentInfo:
    """Agent信息"""
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        capabilities: List[str]
    ):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.capabilities = capabilities
```

#### 2.6.2 Core架构适配器

```python
# /infrastructure/agents/core_agent_adapter.py

from derisk.agent.core import ConversableAgent
from derisk.agent.core.memory.gpts import GptsMemory

class CoreAgentAdapter(AgentAdapter):
    """Core架构Agent适配器"""
    
    def __init__(self):
        self.agent: Optional[ConversableAgent] = None
        self.memory: Optional[GptsMemory] = None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化Core Agent"""
        
        self.agent = ConversableAgent(
            name=config["agent_name"],
            system_message=config.get("system_prompt"),
            llm_config=config.get("llm_config")
        )
        
        self.memory = GptsMemory()
    
    async def process_message(
        self,
        conversation: Conversation,
        message: Message
    ) -> AsyncGenerator[Message, None]:
        """处理消息"""
        
        # 加载历史到memory
        await self.load_memory(conversation.id)
        
        # 添加用户消息到memory
        utterance = {
            "speaker": message.sender.id,
            "utterance": message.content.text,
            "role": message.sender.type
        }
        self.memory.save_to_memory(utterance)
        
        # 生成回复
        response = await self.agent.generate_reply(
            messages=[{
                "role": "user",
                "content": message.content.text
            }]
        )
        
        # 构建助手消息
        assistant_message = Message(
            id=MessageId(self._generate_id()),
            conversation_id=conversation.id,
            sender=Participant(
                id=self.agent.name,
                name=self.agent.name,
                type=ParticipantType.AGENT
            ),
            content=MessageContent(
                text=response["content"],
                type="text"
            ),
            metadata=MessageMetadata(
                round_index=conversation.state.message_count
            ),
            created_at=datetime.now()
        )
        
        # 保存到memory
        self.memory.save_to_memory({
            "speaker": assistant_message.sender.id,
            "utterance": assistant_message.content.text,
            "role": "assistant"
        })
        
        yield assistant_message
    
    async def load_memory(self, conversation_id: ConversationId) -> None:
        """加载记忆"""
        
        # 从统一仓储加载历史消息
        messages = await self.message_repo.find_by_conversation(conversation_id)
        
        # 转换为memory格式
        for msg in messages:
            utterance = {
                "speaker": msg.sender.id,
                "utterance": msg.content.text,
                "role": msg.sender.type
            }
            self.memory.save_to_memory(utterance)
    
    async def save_memory(self, conversation_id: ConversationId) -> None:
        """保存记忆"""
        # Core架构的记忆已通过统一MessageRepository保存
        pass
    
    def get_agent_info(self) -> AgentInfo:
        """获取Agent信息"""
        return AgentInfo(
            agent_id=self.agent.name if self.agent else "unknown",
            agent_name=self.agent.name if self.agent else "unknown",
            agent_type="core",
            capabilities=["chat", "tool_use"]
        )
```

#### 2.6.3 Core_v2架构适配器

```python
# /infrastructure/agents/core_v2_agent_adapter.py

from derisk.agent.core_v2 import ProductionAgent
from derisk.agent.core_v2.unified_memory import UnifiedMemory

class CoreV2AgentAdapter(AgentAdapter):
    """Core_v2架构Agent适配器"""
    
    def __init__(self):
        self.agent: Optional[ProductionAgent] = None
        self.memory: Optional[UnifiedMemory] = None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化Core_v2 Agent"""
        
        self.agent = ProductionAgent(
            name=config["agent_name"],
            goal=config.get("goal"),
            context=UnifiedMemory()
        )
        
        self.memory = self.agent.context
    
    async def process_message(
        self,
        conversation: Conversation,
        message: Message
    ) -> AsyncGenerator[Message, None]:
        """处理消息(流式)"""
        
        # 加载历史到memory
        await self.load_memory(conversation.id)
        
        # 设置当前目标
        self.agent.goal = conversation.goal
        
        # 流式处理
        async for chunk in self.agent.run_stream(
            user_goal=message.content.text
        ):
            # 构建流式消息块
            if chunk.type == "thinking":
                yield self._create_thinking_chunk(chunk.content)
            
            elif chunk.type == "content":
                yield self._create_content_chunk(chunk.content)
            
            elif chunk.type == "tool_call":
                yield self._create_tool_call_chunk(chunk.tool_call)
        
        # 最终消息
        final_message = Message(
            id=MessageId(self._generate_id()),
            conversation_id=conversation.id,
            sender=Participant(
                id=self.agent.name,
                name=self.agent.name,
                type=ParticipantType.AGENT
            ),
            content=MessageContent(
                text=self.agent.final_response,
                type="text"
            ),
            metadata=MessageMetadata(
                round_index=conversation.state.message_count
            ),
            created_at=datetime.now()
        )
        
        yield final_message
    
    async def load_memory(self, conversation_id: ConversationId) -> None:
        """加载记忆"""
        messages = await self.message_repo.find_by_conversation(conversation_id)
        
        for msg in messages:
            self.memory.add_memory({
                "role": msg.sender.type,
                "content": msg.content.text,
                "thinking": msg.content.thinking
            })
    
    def get_agent_info(self) -> AgentInfo:
        """获取Agent信息"""
        return AgentInfo(
            agent_id=self.agent.name if self.agent else "unknown",
            agent_name=self.agent.name if self.agent else "unknown",
            agent_type="core_v2",
            capabilities=["chat", "tool_use", "plan", "reasoning"]
        )
```

#### 2.6.4 Agent工厂

```python
# /infrastructure/agents/agent_factory.py

from typing import Dict, Type

class AgentFactory:
    """Agent工厂"""
    
    _adapters: Dict[str, Type[AgentAdapter]] = {
        "core": CoreAgentAdapter,
        "core_v2": CoreV2AgentAdapter
    }
    
    @classmethod
    def register_adapter(
        cls,
        agent_type: str,
        adapter_class: Type[AgentAdapter]
    ) -> None:
        """注册适配器"""
        cls._adapters[agent_type] = adapter_class
    
    @classmethod
    async def create_agent(
        cls,
        agent_type: str,
        config: Dict[str, Any]
    ) -> AgentAdapter:
        """创建Agent"""
        
        adapter_class = cls._adapters.get(agent_type)
        
        if not adapter_class:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        adapter = adapter_class()
        await adapter.initialize(config)
        
        return adapter
```

### 2.7 CQRS与读写分离

#### 2.7.1 CQRS架构

```
┌─────────────────────────────────────────────────────┐
│                  Command Side (写端)                 │
├─────────────────────────────────────────────────────┤
│                                                       │
│  Commands:                                           │
│  ├─ CreateConversationCommand                       │
│  ├─ AddMessageCommand                               │
│  ├─ ExecuteToolCommand                              │
│  └─ CompleteConversationCommand                     │
│                                                       │
│  Command Handlers:                                   │
│  ├─ CreateConversationHandler                       │
│  │   └─ 验证 → 创建聚合根 → 保存 → 发布事件          │
│  ├─ AddMessageHandler                               │
│  │   └─ 加载聚合 → 添加消息 → 保存 → 发布事件        │
│  └─ ...                                              │
│                                                       │
│  Write Model:                                        │
│  ├─ conversations表                                 │
│  ├─ messages表                                      │
│  └─ conversation_events表 (事件流)                   │
│                                                       │
│  追求: 强一致性、ACID事务、规范化                    │
└─────────────────────────────────────────────────────┘
                         │
                         │ Events
                         ▼
┌─────────────────────────────────────────────────────┐
│                  Query Side (读端)                   │
├─────────────────────────────────────────────────────┤
│                                                       │
│  Queries:                                            │
│  ├─ GetConversationQuery                            │
│  ├─ GetConversationHistoryQuery                     │
│  ├─ SearchConversationsQuery                        │
│  └─ GetConversationStatsQuery                       │
│                                                       │
│  Query Handlers:                                     │
│  ├─ GetConversationHandler                          │
│  │   └─ 从读模型加载 → 组装响应                      │
│  ├─ SearchHandler                                   │
│  │   └─ 查询索引 → 返回结果                          │
│  └─ ...                                              │
│                                                       │
│  Read Models:                                        │
│  ├─ conversation_stats表 (统计视图)                 │
│  ├─ Elasticsearch索引 (搜索)                        │
│  ├─ Redis缓存 (热点数据)                            │
│  └─ 物化视图 (报表)                                 │
│                                                       │
│  追求: 最终一致性、高性能查询、反规范化             │
└─────────────────────────────────────────────────────┘
```

#### 2.7.2 实现

```python
# /application/cqrs/command.py

from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class Command(ABC):
    """命令基类"""
    command_id: str

@dataclass
class CreateConversationCommand(Command):
    """创建对话命令"""
    user_id: str
    chat_mode: str
    goal: Optional[str]
    session_id: Optional[str]
    agent_id: Optional[str]

@dataclass
class AddMessageCommand(Command):
    """添加消息命令"""
    conversation_id: str
    sender_id: str
    sender_type: str
    content: str
    metadata: dict

class CommandHandler(ABC):
    """命令处理器接口"""
    
    @abstractmethod
    async def handle(self, command: Command):
        """处理命令"""
        pass

class CreateConversationHandler(CommandHandler):
    """创建对话命令处理器"""
    
    @inject.autoparams()
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        event_publisher: EventPublisher
    ):
        self.conversation_repo = conversation_repo
        self.event_publisher = event_publisher
    
    async def handle(self, command: CreateConversationCommand):
        """处理创建对话命令"""
        
        # 1. 验证
        if not command.user_id:
            raise ValueError("user_id is required")
        
        # 2. 创建聚合
        conversation = await self._create_conversation(command)
        
        # 3. 持久化
        await self.conversation_repo.save(conversation)
        
        # 4. 发布事件
        await self.event_publisher.publish(
            ConversationStarted(
                event_id=str(uuid.uuid4()),
                occurred_at=datetime.now(),
                aggregate_id=conversation.id.value,
                goal=conversation.goal or "",
                chat_mode=conversation.chat_mode,
                participants=conversation.participants
            )
        )
        
        return conversation
    
    async def _create_conversation(self, command):
        # 实现略
        pass

# /application/cqrs/query.py

@dataclass
class Query(ABC):
    """查询基类"""
    query_id: str

@dataclass
class GetConversationQuery(Query):
    """获取对话查询"""
    conversation_id: str
    include_messages: bool = True
    message_limit: Optional[int] = None

@dataclass
class SearchConversationsQuery(Query):
    """搜索对话查询"""
    user_id: str
    keywords: str
    filters: Optional[dict] = None
    limit: int = 20

class QueryHandler(ABC):
    """查询处理器接口"""
    
    @abstractmethod
    async def handle(self, query: Query):
        """处理查询"""
        pass

class GetConversationHandler(QueryHandler):
    """获取对话查询处理器"""
    
    @inject.autoparams()
    def __init__(
        self,
        cache: 'CacheService',
        message_repo: MessageRepository,
        stats_repo: 'ConversationStatsRepository'
    ):
        self.cache = cache
        self.message_repo = message_repo
        self.stats_repo = stats_repo
    
    async def handle(self, query: GetConversationQuery):
        """处理获取对话查询"""
        
        # 1. 从缓存加载
        cache_key = f"conv_query:{query.conversation_id}"
        cached = await self.cache.get(cache_key)
        
        if cached:
            return cached
        
        # 2. 从读模型加载
        stats = await self.stats_repo.get(query.conversation_id)
        
        # 3. 加载消息(如果需要)
        messages = []
        if query.include_messages:
            messages = await self.message_repo.find_by_conversation(
                ConversationId(query.conversation_id),
                limit=query.message_limit
            )
        
        # 4. 组装响应
        response = {
            "conversation_id": query.conversation_id,
            "stats": stats,
            "messages": [m.to_dict() for m in messages]
        }
        
        # 5. 更新缓存
        await self.cache.set(cache_key, response, ttl=300)
        
        return response

# 事件处理器更新读模型

class ConversationStatsProjector:
    """对话统计投影器(更新读模型)"""
    
    @inject.autoparams()
    def __init__(self, stats_repo: 'ConversationStatsRepository'):
        self.stats_repo = stats_repo
    
    async def on_conversation_started(self, event: ConversationStarted):
        """对话开始事件处理"""
        await self.stats_repo.create(
            conv_id=event.aggregate_id,
            started_at=event.occurred_at
        )
    
    async def on_message_added(self, event: MessageAdded):
        """消息添加事件处理"""
        await self.stats_repo.increment_message_count(
            conv_id=event.aggregate_id
        )
        
        # 更新其他统计
        if event.message.content.thinking:
            await self.stats_repo.increment_thinking_count(
                conv_id=event.aggregate_id
            )
```

### 2.8 API设计最佳实践

#### 2.8.1 RESTful API设计

```
资源导向的API设计:

1. 对话资源
   POST   /api/v1/conversations              # 创建对话
   GET    /api/v1/conversations/{id}         # 获取对话
   PATCH  /api/v1/conversations/{id}         # 部分更新对话
   DELETE /api/v1/conversations/{id}         # 删除对话
   
   GET    /api/v1/conversations              # 列出对话(支持过滤、分页)

2. 消息资源
   POST   /api/v1/conversations/{id}/messages        # 添加消息
   GET    /api/v1/conversations/{id}/messages        # 获取消息列表
   GET    /api/v1/conversations/{id}/messages/{msg_id}  # 获取单条消息
   
   # 流式消息
   POST   /api/v1/conversations/{id}/messages:stream  # 流式添加消息

3. 工具执行资源
   POST   /api/v1/conversations/{id}/tool-executions  # 执行工具
   GET    /api/v1/conversations/{id}/tool-executions  # 查询工具执行记录

4. 会话资源
   POST   /api/v1/sessions                     # 创建会话
   GET    /api/v1/sessions/{id}                # 获取会话
   PATCH  /api/v1/sessions/{id}                # 更新会话
   DELETE /api/v1/sessions/{id}                # 删除会话
   GET    /api/v1/sessions/{id}/conversations  # 获取会话下的对话

5. Agent资源
   GET    /api/v1/agents                       # 列出Agent
   GET    /api/v1/agents/{id}                  # 获取Agent详情
   
6. 搜索资源
   POST   /api/v1/conversations:search         # 搜索对话
```

#### 2.8.2 API版本化

```python
# 版本化策略: URL路径版本化

# /api/v1/conversations  - 版本1
# /api/v2/conversations  - 版本2

# Request:
GET /api/v1/conversations/123

# Response:
{
  "api_version": "v1",
  "data": {
    "conv_id": "123",
    "user_id": "user_001",
    ...
  }
}

# 版本协商:
# 1. URL路径(推荐): /api/v1/...
# 2. Header: Accept: application/vnd.api+json;version=1
# 3. Query参数: /api/conversations?version=1 (不推荐)
```

#### 2.8.3 统一响应格式

```python
# /api/responses.py

from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):
    """统一API响应格式"""
    
    api_version: str = "v1"
    success: bool = True
    data: Optional[T] = None
    error: Optional[dict] = None
    metadata: Optional[dict] = None
    
    class Config:
        schema_extra = {
            "example": {
                "api_version": "v1",
                "success": True,
                "data": {
                    "conv_id": "123",
                    "user_id": "user_001"
                },
                "metadata": {
                    "timestamp": "2026-03-02T10:00:00Z",
                    "request_id": "req_123"
                }
            }
        }

class ErrorResponse(BaseModel):
    """错误响应"""
    
    code: str                            # 错误代码
    message: str                         # 错误消息
    details: Optional[List[dict]] = None # 详细错误列表
    
    class Config:
        schema_extra = {
            "example": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": [
                    {
                        "field": "user_id",
                        "message": "user_id is required"
                    }
                ]
            }
        }

class PagedResponse(APIResponse[List[T]]):
    """分页响应"""
    
    page: int
    page_size: int
    total: int
    has_next: bool

# 使用示例

@router.get("/conversations/{conversation_id}", response_model=APIResponse[ConversationResponse])
async def get_conversation(conversation_id: str):
    """获取对话"""
    try:
        conversation = await service.get_conversation(conversation_id)
        return APIResponse(
            data=conversation,
            metadata={
                "timestamp": datetime.now().isoformat()
            }
        )
    except ValueError as e:
        return APIResponse(
            success=False,
            error=ErrorResponse(
                code="NOT_FOUND",
                message=str(e)
            )
        )

@router.get("/conversations", response_model=PagedResponse[ConversationSummary])
async def list_conversations(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """列出对话(分页)"""
    result = await service.list_conversations(user_id, page, page_size)
    
    return PagedResponse(
        data=result.items,
        page=page,
        page_size=page_size,
        total=result.total,
        has_next=result.has_next
    )
```

---

## 三、前端统一渲染设计

### 3.1 数据驱动架构

```
┌─────────────────────────────────────────────────────┐
│  API Layer (数据获取层)                              │
├─────────────────────────────────────────────────────┤
│  useUnifiedConversation Hook                         │
│  ├─ fetch conversation                               │
│  ├─ fetch messages                                   │
│  └─ real-time updates via SSE                       │
└─────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│  State Management (状态管理层)                       │
├─────────────────────────────────────────────────────┤
│  ConversationContext                                 │
│  ├─ conversation state                               │
│  ├─ messages state                                   │
│  └─ dispatch actions                                 │
└─────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│  Component Layer (组件层)                            │
├─────────────────────────────────────────────────────┤
│  ConversationContainer                               │
│  ├─ ConversationHeader                               │
│  │   └─ 显示对话信息、参与者、状态                    │
│  ├─ MessageList                                      │
│  │   ├─ MessageItem                                  │
│  │   │   ├─ UserMessage                              │
│  │   │   ├─ AssistantMessage                         │
│  │   │   └─ AgentMessage                             │
│  │   │       ├─ ThinkingSection                      │
│  │   │       ├─ ToolCallsSection                     │
│  │   │       ├─ ContentSection                       │
│  │   │       └─ VisualizationSection                 │
│  │   └─ ScrollController                             │
│  └─ MessageInput                                     │
│      └─ 发送消息、上传文件、选择工具                  │
└─────────────────────────────────────────────────────┘
```

### 3.2 数据适配器

```typescript
import { Conversation, Message, Participant } from '@/types/conversation';

export class ConversationDataAdapter {
  static fromAPI(apiData: any): Conversation {
    return {
      id: apiData.conv_id,
      sessionId: apiData.session_id,
      goal: apiData.goal,
      chatMode: apiData.chat_mode,
      participants: apiData.participants.map(this.toParticipant),
      state: {
        status: apiData.status,
        messageCount: apiData.message_count,
        lastActiveAt: apiData.last_active_at
      },
      createdAt: new Date(apiData.created_at),
      updatedAt: new Date(apiData.updated_at)
    };
  }
  
  static toParticipant(data: any): Participant {
    return {
      id: data.id,
      name: data.name,
      type: data.type,
      avatar: data.avatar
    };
  }
  
  static messageFromAPI(apiData: any): Message {
    return {
      id: apiData.msg_id,
      conversationId: apiData.conv_id,
      sender: this.toParticipant(apiData.sender),
      content: {
        text: apiData.content,
        thinking: apiData.thinking,
        type: apiData.content_type
      },
      metadata: {
        roundIndex: apiData.round_index,
        tokens: apiData.tokens_used,
        latency: apiData.latency_ms
      },
      toolCalls: apiData.tool_calls?.map(this.toToolCall),
      visualization: apiData.vis_type ? {
        type: apiData.vis_type,
        data: apiData.vis_data
      } : undefined,
      createdAt: new Date(apiData.created_at)
    };
  }
  
  static toToolCall(data: any): ToolCall {
    return {
      id: data.execution_id,
      toolName: data.tool_name,
      input: data.input_params,
      output: data.output_result,
      status: data.status,
      duration: data.duration_ms
    };
  }
}
```

---

## 四、总结

### 4.1 架构优势

| 维度 | 当前架构 | 理想架构 | 改进 |
|------|---------|---------|------|
| **数据模型** | 两套表,冗余存储 | 统一领域模型 | 消除冗余,一致性提升 |
| **访问模式** | 随机访问,硬编码 | Repository模式 | 解耦业务与存储 |
| **扩展性** | 修改代码扩展 | 策略+工厂模式 | 符合开闭原则 |
| **性能** | N+1查询,无缓存 | CQRS+缓存 | 查询性能提升10x+ |
| **Agent集成** | 紧耦合 | 适配器模式 | 支持可插拔Agent |
| **API设计** | 不一致,冗余 | RESTful统一 | 易用性提升 |
| **测试性** | 难以单元测试 | 依赖注入,Mock | 测试覆盖率提升 |

### 4.2 核心设计模式

1. **领域驱动设计(DDD)**
   - 聚合根管理一致性边界
   - 领域服务封装业务逻辑
   - 值对象保证不变性

2. **命令查询分离(CQRS)**
   - 写模型:保证业务一致性
   - 读模型:优化查询性能
   - 事件驱动同步

3. **六边形架构**
   - 领域层独立
   - 端口(Port)定义接口
   - 适配器(Adapter)提供实现

4. **策略模式**
   - Agent适配器可插拔
   - 存储实现可替换
   - 扩展无需修改

### 4.3 技术亮点

1. **向量检索**: 支持语义相似对话检索
2. **事件溯源**: 状态可追溯,支持时间旅行
3. **实时流式**: SSE支持流式消息
4. **智能缓存**: 多级缓存策略
5. **监控指标**: 完整的可观测性

---

**这个理想架构方案的核心价值**:

✅ **彻底消除冗余**: 单一数据源,统一访问  
✅ **架构清晰**: DDD分层,职责明确  
✅ **高度解耦**: 依赖倒置,易于测试  
✅ **性能优化**: CQRS+缓存+索引  
✅ **易于扩展**: 符合开闭原则  
✅ **Agent友好**: 适配器模式统一接入  
✅ **未来就绪**: 支持向量化、事件溯源、微服务