# 历史对话记录架构分析与重构方案

> 文档版本: v1.0  
> 创建日期: 2026-03-02  
> 作者: Architecture Analysis Team

---

## 目录

- [一、现状分析](#一现状分析)
- [二、核心问题解析](#二核心问题解析)
- [三、重构方案设计](#三重构方案设计)
- [四、数据迁移方案](#四数据迁移方案)
- [五、实施路线图](#五实施路线图)
- [六、风险评估](#六风险评估)

---

## 一、现状分析

### 1.1 双表架构概览

当前系统存在两套历史对话记录存储方案：

#### 1.1.1 chat_history 表体系

**数据库Schema位置**：
- `/assets/schema/derisk.sql` (第40-76行)
- `/scripts/mysql_ddl.sql` (第27-76行)

**核心表结构**：

```sql
-- 对话主表
CREATE TABLE chat_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    conv_uid VARCHAR(255) UNIQUE NOT NULL,    -- 对话唯一标识
    chat_mode VARCHAR(50),                      -- 对话模式
    summary VARCHAR(255),                       -- 对话摘要
    user_name VARCHAR(100),                     -- 用户名
    messages LONGTEXT,                          -- 完整对话历史(JSON)
    message_ids LONGTEXT,                       -- 消息ID列表
    sys_code VARCHAR(255),                      -- 系统编码
    app_code VARCHAR(255),                      -- 应用编码
    gmt_create DATETIME,
    gmt_modified DATETIME
);

-- 消息详情表
CREATE TABLE chat_history_message (
    id INT PRIMARY KEY AUTO_INCREMENT,
    conv_uid VARCHAR(255),                      -- 关联对话
    index INT,                                  -- 消息索引
    round_index INT,                            -- 轮次索引
    message_detail LONGTEXT,                    -- 消息详情(JSON)
    gmt_create DATETIME,
    gmt_modified DATETIME
);
```

**模型与DAO位置**：
- 模型定义：`/packages/derisk-core/src/derisk/storage/chat_history/chat_history_db.py`
  - `ChatHistoryEntity` (第25-66行)
  - `ChatHistoryMessageEntity` (第68-96行)
- DAO实现：`ChatHistoryDao` (第98-212行)

**核心使用场景**：
1. **Conversation Serve组件**：基础对话服务的存储承载
2. **Editor API**：编辑器场景的历史消息管理
3. **Application Service**：热门应用统计与展示

**关键代码路径**：
```python
# 1. 创建对话
# /derisk_serve/conversation/service/service.py:111
storage_conv = StorageConversation(
    conv_uid=request.conv_uid,
    chat_mode=request.chat_mode,
    user_name=request.user_name,
    conv_storage=conv_storage,
    message_storage=message_storage,
)

# 2. 保存消息
# /derisk/core/interface/message.py:1357
self.message_storage.save_list(messages_to_save)

# 3. 存储适配器转换
# /derisk/storage/chat_history/storage_adapter.py:27
entity = adapter.to_storage_format(storage_conv)
```

#### 1.1.2 gpts_conversations 表体系

**数据库Schema位置**：
- `/assets/schema/derisk.sql` (第113-318行)
- `/scripts/mysql_ddl.sql` (第157-318行)

**核心表结构**：

```sql
-- GPT会话主表
CREATE TABLE gpts_conversations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    conv_id VARCHAR(255) UNIQUE NOT NULL,      -- 对话ID
    conv_session_id VARCHAR(255),               -- 会话ID(可分组)
    user_goal TEXT,                             -- 用户目标
    gpts_name VARCHAR(255),                     -- GPT名称
    team_mode VARCHAR(50),                      -- 团队模式
    state VARCHAR(50),                          -- 状态
    max_auto_reply_round INT,                   -- 最大自动回复轮次
    auto_reply_count INT,                       -- 自动回复计数
    user_code VARCHAR(255),                     -- 用户编码
    sys_code VARCHAR(255),                      -- 系统编码
    vis_render TEXT,                            -- 可视化渲染配置
    extra TEXT,                                 -- 扩展信息
    gmt_create DATETIME,
    gmt_modified DATETIME
);

-- GPT消息表
CREATE TABLE gpts_messages (
    id INT PRIMARY KEY AUTO_INCREMENT,
    conv_id VARCHAR(255),
    conv_session_id VARCHAR(255),
    message_id VARCHAR(255),
    sender VARCHAR(255),                        -- 发送者
    sender_name VARCHAR(100),                   -- 发送者名称
    receiver VARCHAR(255),                      -- 接收者
    receiver_name VARCHAR(100),                 -- 接收者名称
    rounds INT,                                 -- 轮次
    content LONGTEXT,                           -- 消息内容
    thinking LONGTEXT,                          -- 思考过程
    tool_calls LONGTEXT,                        -- 工具调用(JSON)
    observation LONGTEXT,                       -- 观察结果
    system_prompt LONGTEXT,                     -- 系统提示
    user_prompt LONGTEXT,                       -- 用户提示
    context LONGTEXT,                           -- 上下文
    review_info LONGTEXT,                       -- 审查信息
    action_report LONGTEXT,                     -- 动作报告
    resource_info LONGTEXT,                     -- 资源信息
    metrics TEXT,                               -- 指标
    gmt_create DATETIME,
    gmt_modified DATETIME
);
```

**模型与DAO位置**：
- 会话DAO：`/packages/derisk-serve/src/derisk_serve/agent/db/gpts_conversations_db.py`
  - `GptsConversationsEntity` (第18-59行)
  - `GptsConversationsDao` (第62-158行)
- 消息DAO：`/packages/derisk-serve/src/derisk_serve/agent/db/gpts_messages_db.py`
  - `GptsMessagesEntity` (第28-153行)
  - `GptsMessagesDao` (第156-419行)

**核心使用场景**：
1. **Agent Chat**：智能体对话的会话管理
2. **Multi-Agent协作**：多智能体场景的状态同步
3. **Application管理**：应用级别的对话管理

**关键代码路径**：
```python
# /derisk_serve/agent/agents/chat/agent_chat.py

# 1. 初始化Agent对话历史 (第416-434行)
async def _initialize_agent_conversation(self):
    gpts_conversations = await self.gpts_conversations.get_by_session_id_asc(
        conv_session_id
    )
    
    if gpts_conversations:
        # 恢复历史会话
        for conv in gpts_conversations:
            await self._load_conversation_history(conv)
    
# 2. 加载消息并恢复记忆 (第552-590行)
async def _load_conversation_history(self, conv):
    messages = await self.gpts_messages.get_by_conv_id(conv.conv_id)
    
    for msg in messages:
        utterance = await self.memory.read_from_memory(
            message=msg.content,
            user=msg.sender,
        )
        self.memory.save_to_memory(utterance)

# 3. 创建新会话记录 (第594-617行)
await self.gpts_conversations.a_add(
    GptsConversationsEntity(
        conv_id=agent_conv_id,
        conv_session_id=conv_id,
        user_goal=user_goal,
        gpts_name=self.name,
        ...
    )
)
```

---

### 1.2 双架构Agent体系

#### 1.2.1 Core架构

**架构位置**：`/packages/derisk-core/src/derisk/agent/core/`

**核心组件**：
```
core/
├── base_agent.py           # 基础Agent
├── base_team.py            # 团队协作
├── action/                 # 动作执行
├── context_lifecycle/      # 上下文生命周期
├── execution/              # 执行引擎
├── memory/                 # 记忆管理
│   └── gpts.py            # GPT记忆实现
├── plan/                   # 规划模块
├── profile/                # 配置管理
├── reasoning/              # 推理模块
├── sandbox/                # 沙箱环境
└── tools/                  # 工具集成
```

**记忆系统**：
- 使用 `StorageConversation` 管理对话
- 关联 `chat_history` 表体系
- 支持会话持久化和恢复

**关键类**：
```python
# /derisk/agent/core/base_agent.py
class ConversableAgent:
    def __init__(self, ...):
        self.memory = GptsMemory()
    
    def initiate_chat(self, recipient, message, ...):
        # 使用 StorageConversation
        conversation = StorageConversation(...)
```

#### 1.2.2 Core_v2架构

**架构位置**：`/packages/derisk-core/src/derisk/agent/core_v2/`

**核心组件**：
```
core_v2/
├── production_agent.py     # 生产级Agent
├── agent_base.py          # Agent基类
├── builtin_agents/        # 内置Agent实现
│   ├── react_reasoning_agent.py
│   └── ...
├── context_lifecycle/     # 上下文生命周期
├── integration/           # 集成模块
├── multi_agent/           # 多Agent协作
├── tools_v2/             # 新版工具系统
├── unified_memory/       # 统一记忆管理
└── visualization/        # 可视化支持
    └── vis_adapter.py
```

**记忆系统**：
- 使用 `unified_memory/` 统一管理
- 关联 `gpts_conversations` + `gpts_messages`
- 内置错误恢复机制
- 增强的可视化支持

**关键类**：
```python
# /derisk/agent/core_v2/production_agent.py
class ProductionAgent(BaseBuiltinAgent):
    def __init__(self, ...):
        self.memory = UnifiedMemory()
        self.goal_manager = GoalManager()
        self.recovery_coordinator = RecoveryCoordinator()
        
    async def run(self, user_goal, ...):
        # 使用 GptsMemory 加载历史
        await self.load_conversation_history(conv_id)
```

---

### 1.3 历史消息处理流程对比

#### 1.3.1 存储流程对比

**chat_history存储流程**：

```
用户输入消息
    ↓
StorageConversation.add_user_message()
    ↓
message.save_to_storage()
    ↓
MessageStorage.save_list()
    ↓
ChatHistoryDao.raw_update()
    ↓
① 更新 chat_history.messages 字段 (完整JSON)
② 写入 chat_history_message 表 (单条记录)
```

**gpts_conversations存储流程**：

```
Agent处理消息
    ↓
AgentChat.aggregation_chat()
    ↓
_initialize_agent_conversation()
    ↓
GptsConversationsDao.a_add()
    ↓
① 写入 gpts_conversations 表 (会话元数据)
② GptsMessagesDao 批量写入消息
    ↓
写入 gpts_messages 表 (详细消息字段)
```

**流程差异点**：

| 维度 | chat_history | gpts_conversations |
|------|-------------|-------------------|
| 存储粒度 | 对话级别 | 会话+消息级别 |
| 消息格式 | JSON序列化 | 结构化字段 |
| 写入时机 | 每次对话结束 | 实时流式写入 |
| 扩展字段 | message_detail JSON | 独立字段(thinking, tool_calls等) |

#### 1.3.2 读取流程对比

**chat_history读取流程**：

```
API请求: /api/v1/serve/conversation/query
    ↓
ConversationService.get(conv_uid)
    ↓
ServeDao.get_one(conv_uid)
    ↓
ChatHistoryDao.get_by_uid()
    ↓
加载 ChatHistoryEntity
    ↓
加载 chat_history_message 列表
    ↓
StorageConversation.from_storage_format()
    ↓
返回前端渲染
```

**gpts_conversations读取流程**：

```
Agent初始化
    ↓
AgentChat._initialize_agent_conversation()
    ↓
GptsConversationsDao.get_by_session_id_asc()
    ↓
加载会话列表
    ↓
判断恢复策略
    ↓
GptsMessagesDao.get_by_conv_id()
    ↓
加载消息列表
    ↓
memory.load_persistent_memory()
    ↓
恢复Agent记忆状态
```

---

### 1.4 前端渲染展示架构

#### 1.4.1 数据获取层

**API调用Hook**：
- `/web/src/hooks/use-chat.ts`

```typescript
export function useChat() {
  // 支持V1/V2 Agent版本
  const { agentVersion } = useAgentContext();
  
  // SSE流式响应处理
  const { messages, isLoading, sendMessage } = useSSEChat({
    agentVersion,
    onMessage: (msg) => {
      // 实时更新消息
      updateChatContent(msg);
    }
  });
  
  return { messages, sendMessage };
}
```

**API端点**：
- `/api/v1/serve/conversation/messages` - 获取chat_history消息
- `/api/v1/app/conversations` - 获取gpts_conversations消息

#### 1.4.2 组件渲染层

**核心组件结构**：

```
/pages/chat
  ↓
ChatContentContainer
  ↓
HomeChat / ChatContent
  ↓
MessageList
  ├─ UserMessage (用户消息)
  └─ AssistantMessage (助手消息)
      ├─ Markdown渲染 (@antv/gpt-vis)
      └─ VisComponents可视化组件
          ├─ VisStepCard (步骤卡片)
          ├─ VisMsgCard (消息卡片)
          ├─ VisCodeIde (代码编辑器)
          ├─ VisRunningWindow (运行窗口)
          ├─ VisPlan (计划展示)
          ├─ VisReview (审查组件)
          └─ ... 20+可视化组件
```

**关键组件路径**：
- 主容器：`/web/src/components/chat/chat-content-container.tsx`
- 消息渲染：`/web/src/components/chat/content/chat-content.tsx`
- 可视化组件：`/web/src/components/chat/chat-content-components/VisComponents/`

**渲染逻辑**：

```typescript
// /web/src/components/chat/content/chat-content.tsx

function ChatContent({ content }: ChatContentProps) {
  const { visRender } = useVisRender();
  
  return (
    <div className="chat-content">
      <MarkdownRender
        content={content.markdown}
        components={{
          // 自定义可视化组件渲染
          vis: ({ node }) => visRender(node),
        }}
      />
    </div>
  );
}

function visRender(node: VisNode) {
  switch (node.type) {
    case 'step':
      return <VisStepCard data={node.data} />;
    case 'code':
      return <VisCodeIde data={node.data} />;
    case 'plan':
      return <VisPlan data={node.data} />;
    // ... 其他组件
  }
}
```

#### 1.4.3 数据结构差异

**chat_history消息格式**：
```json
{
  "role": "user",
  "content": "用户输入内容",
  "context": {
    "conv_uid": "xxx",
    "user_name": "user1"
  }
}
```

**gpts_messages字段映射**：
```json
{
  "sender": "user",
  "content": "用户输入内容",
  "chat_mode": "chat_agent",
  "thinking": "思考过程",
  "tool_calls": [
    {
      "tool_name": "python",
      "args": {...},
      "result": "执行结果"
    }
  ],
  "observation": "观察结果",
  "action_report": {
    "action": "python_execute",
    "status": "success"
  }
}
```

---

## 二、核心问题解析

### 2.1 数据结构冗余

#### 2.1.1 字段级冗余

| 功能 | chat_history | gpts_conversations | 冗余程度 |
|------|-------------|-------------------|---------|
| 会话标识 | `conv_uid` | `conv_id` + `conv_session_id` | **高** - 概念相同,字段不同 |
| 用户标识 | `user_name` | `user_code` | **高** - 同一含义 |
| 应用标识 | `app_code` | `gpts_name` | **高** - 同一含义 |
| 系统标识 | `sys_code` | `sys_code` | **完全重复** |
| 对话目标 | `summary` | `user_goal` | **中** - 概念相似 |
| 创建时间 | `gmt_create` | `gmt_create` | **完全重复** |
| 修改时间 | `gmt_modified` | `gmt_modified` | **完全重复** |

#### 2.1.2 消息存储冗余

**chat_history方式**：
```
chat_history表
  └─ messages字段 (LONGTEXT) ★ 冗余点1: 存储完整对话历史JSON
  └─ chat_history_message表
       └─ message_detail字段 - 单条消息JSON
```

**gpts_conversations方式**：
```
gpts_conversations表
  └─ 仅存储会话元数据 ✓ 更合理
  
gpts_messages表
  └─ 详细字段:
       - content (消息内容)
       - thinking (思考过程)
       - tool_calls (工具调用JSON)
       - observation (观察结果)
       - action_report (动作报告)
       - ...
```

**冗余问题**：
1. `chat_history.messages` 字段与 `chat_history_message` 表重复
2. 同一轮对话在两个表系统中都有记录
3. Agent场景下,`gpts_messages` 的结构化设计更优

### 2.2 架构层面的冗余

#### 2.2.1 双重记忆系统

```
Core架构记忆系统:
  └─ StorageConversation (接口层)
      └─ ChatHistoryDao (DAO层)
          └─ chat_history + chat_history_message (数据层)

Core_v2架构记忆系统:
  └─ UnifiedMemory (接口层)
      └─ GptsMemory (实现层)
          └─ GptsConversationsDao + GptsMessagesDao (DAO层)
              └─ gpts_conversations + gpts_messages (数据层)
```

**问题**：
- 两套独立的记忆系统
- 无法跨架构共享历史
- 学习和维护成本高

#### 2.2.2 Agent Chat的双重存储案例

**代码位置**：`/derisk_serve/agent/agents/chat/agent_chat.py`

```python
class AgentChat:
    async def aggregation_chat(self, ...):
        # ① 创建StorageConversation (写入chat_history)
        # 第89-112行
        storage_conv = await StorageConversation(
            conv_uid=conv_id,
            chat_mode="chat_agent",
            user_name=user_name,
            conv_storage=conv_serve.conv_storage,
            message_storage=conv_serve.message_storage,
        ).async_load()
        
        # ② 创建GptsConversations (写入gpts_conversations)
        # 第594-617行
        agent_conv_id = str(uuid.uuid4())
        await self.gpts_conversations.a_add(
            GptsConversationsEntity(
                conv_id=agent_conv_id,
                conv_session_id=conv_id,  # 关联到chat_history的conv_uid
                user_goal=user_goal,
                gpts_name=self.name,
                team_mode=team_context.mode if team_context else None,
                state=ConvertMessageUtils.get_conv_state(False, True),
                max_auto_reply_round=self.max_auto_reply_round,
                auto_reply_count=0,
                user_code=user_name,
                sys_code=sys_code,
                vis_render={},
                extra={},
            )
        )
```

**问题解析**：
1. 同一次对话创建了两个记录：
   - `chat_history` 记录 (conv_uid)
   - `gpts_conversations` 记录 (conv_id)
2. 通过 `conv_session_id` 关联,但数据冗余
3. 每次Agent对话需要维护两套数据一致性

#### 2.2.3 消息的双重表示问题

**同一消息存在于多个位置**：

```
消息来源: 用户输入 "你好"
    ↓
存储路径1: chat_history.messages字段
    JSON: {"role": "user", "content": "你好", ...}
    ↓
存储路径2: chat_history_message.message_detail
    JSON: {"role": "user", "content": "你好", ...}
    ↓
存储路径3: gpts_messages.content字段
    VARCHAR: "你好"
    + gpts_messages.sender: "user"
    + gpts_messages.rounds: 0
```

**问题**：
- 三处存储,一致性难以保证
- 更新时需要同步多处
- 查询效率低(需跨表join或多次查询)

### 2.3 API层冗余

#### 2.3.1 多套API并存

```
/api/v1/serve/conversation/*  
  → ConversationService 
  → chat_history表
  
/api/v1/app/*
  → ApplicationService
  → gpts_conversations表
  
/api/v1/chat/completions
  → 可能兼容两种模式
  → 看具体实现选择表
```

**问题**：
- 前端需要识别使用哪套API
- 接口返回数据结构不一致
- 文档维护成本高

#### 2.3.2 返回数据结构差异

**chat_history API返回**：
```json
{
  "conv_uid": "xxx",
  "chat_mode": "chat_normal",
  "summary": "对话摘要",
  "messages": [
    {
      "role": "user",
      "content": "..."
    }
  ]
}
```

**gpts_conversations API返回**：
```json
{
  "conv_id": "xxx",
  "conv_session_id": "yyy",
  "user_goal": "...",
  "state": "complete",
  "messages": [
    {
      "message_id": "msg_xxx",
      "sender": "user",
      "content": "...",
      "thinking": "...",
      "tool_calls": [...],
      "rounds": 0
    }
  ]
}
```

**前端适配成本**：
```typescript
// 前端需要根据不同API适配渲染逻辑
function renderConversation(api: string, data: any) {
  if (api.includes('serve/conversation')) {
    return renderFromChatHistory(data);
  } else if (api.includes('app')) {
    return renderFromGptsConversations(data);
  }
}
```

### 2.4 可视化渲染冲突

#### 2.4.1 数据来源不一致

**部分可视化依赖chat_history**：
```typescript
// 简单对话场景使用 chat_history
const messages = await fetch('/api/v1/serve/conversation/messages');
```

**部分可视化依赖gpts_messages**：
```typescript
// Agent对话场景使用 gpts_messages
const messages = await fetch('/api/v1/app/conversations');
```

**问题**：
- 前端需要判断数据来源
- 可视化组件需要适配两套数据结构
- 状态管理复杂

#### 2.4.2 vis_render字段的处理

**chat_history**: 无 `vis_render` 字段
**gpts_conversations**: 有 `vis_render` 字段

```sql
-- gpts_conversations表中的vis_render字段
vis_render TEXT -- 存储可视化渲染配置JSON
```

**前端处理差异**：
```typescript
// chat_history场景: 无特殊可视化配置
function renderChatHistory(data) {
  return data.messages.map(msg => (
    <Message content={msg.content} />
  ));
}

// gpts_conversations场景: 需处理vis_render
function renderGptsConv(data) {
  const visConfig = JSON.parse(data.vis_render || '{}');
  
  return data.messages.map(msg => (
    <Message 
      content={msg.content}
      visConfig={visConfig[msg.message_id]}
    />
  ));
}
```

---

## 三、重构方案设计

### 3.1 设计原则

#### 3.1.1 核心原则

1. **统一数据模型**
   - 单一数据源原则
   - 消除数据冗余
   - 保持数据一致性

2. **兼容性优先**
   - 保证现有功能不受影响
   - 提供平滑迁移路径
   - 保持API向后兼容

3. **架构清晰**
   - Core_v2架构为主,Core架构兼容
   - 统一记忆系统设计
   - 明确模块职责边界

4. **性能优化**
   - 减少JOIN查询
   - 优化索引设计
   - 支持水平扩展

#### 3.1.2 技术选型

- **数据库**: MySQL 8.0+ (保持现有技术栈)
- **ORM**: SQLAlchemy (现有)
- **缓存**: Redis (用于会话状态缓存)
- **迁移工具**: Flyway/Alembic

### 3.2 统一数据模型设计

#### 3.2.1 新表结构设计

**策略**: 合并两套表,保留gpts_conversations的结构化设计优势

```sql
-- 1. 统一对话表 (合并 chat_history + gpts_conversations)
CREATE TABLE unified_conversations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 基础标识
    conv_id VARCHAR(255) UNIQUE NOT NULL,          -- 会话唯一标识
    parent_conv_id VARCHAR(255),                   -- 父会话ID(支持多轮对话树)
    session_id VARCHAR(255),                       -- 会话分组ID
    
    -- 用户与应用信息
    user_id VARCHAR(255) NOT NULL,                 -- 统一为user_id
    app_id VARCHAR(255),                           -- 应用ID(原app_code/gpts_name)
    sys_code VARCHAR(255),                         -- 系统编码
    
    -- 对话目标与状态
    goal TEXT,                                     -- 对话目标(原summary/user_goal)
    chat_mode VARCHAR(50) DEFAULT 'chat_normal',   -- 对话模式
    agent_type VARCHAR(50),                        -- Agent类型(core/core_v2)
    state VARCHAR(50) DEFAULT 'active',            -- 状态
    
    -- Agent配置
    team_mode VARCHAR(50),                         -- 团队协作模式
    max_replay_round INT DEFAULT 10,               -- 最大回复轮次
    current_round INT DEFAULT 0,                   -- 当前轮次
    
    -- 可视化与扩展
    vis_config TEXT,                               -- 可视化配置(JSON)
    metadata TEXT,                                 -- 元数据(JSON)
    tags JSON,                                     -- 标签数组
    
    -- 时间戳
    started_at DATETIME,                           -- 开始时间
    ended_at DATETIME,                             -- 结束时间
    gmt_create DATETIME DEFAULT CURRENT_TIMESTAMP,
    gmt_modified DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_user_id (user_id),
    INDEX idx_session_id (session_id),
    INDEX idx_app_id (app_id),
    INDEX idx_state (state),
    INDEX idx_gmt_create (gmt_create)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 统一消息表 (合并 chat_history_message + gpts_messages)
CREATE TABLE unified_messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 关联信息
    conv_id VARCHAR(255) NOT NULL,                 -- 关联会话
    parent_msg_id VARCHAR(255),                    -- 父消息ID
    
    -- 消息标识
    message_id VARCHAR(255) UNIQUE NOT NULL,       -- 消息唯一ID
    message_index INT,                             -- 消息索引
    round_index INT,                               -- 轮次索引
    
    -- 发送者/接收者
    sender_type VARCHAR(50) NOT NULL,              -- user/assistant/system/agent
    sender_id VARCHAR(255),                        -- 发送者ID
    sender_name VARCHAR(255),                      -- 发送者名称
    receiver_type VARCHAR(50),                     -- 接收者类型
    receiver_id VARCHAR(255),                      -- 接收者ID
    
    -- 消息内容
    content LONGTEXT,                              -- 消息正文
    content_type VARCHAR(50) DEFAULT 'text',       -- 内容类型
    
    -- 扩展内容字段 (借鉴gpts_messages设计)
    thinking_process LONGTEXT,                     -- 思考过程
    tool_calls JSON,                               -- 工具调用列表
    observation LONGTEXT,                          -- 观察结果
    context JSON,                                  -- 上下文信息
    
    -- Prompt管理
    system_prompt TEXT,                            -- 系统提示
    user_prompt TEXT,                              -- 用户提示
    
    -- 结果与报告
    action_report JSON,                            -- 动作执行报告
    execution_metrics JSON,                        -- 执行指标
    
    -- 可视化
    vis_type VARCHAR(50),                          -- 可视化类型
    vis_data JSON,                                 -- 可视化数据
    vis_rendered BOOLEAN DEFAULT FALSE,            -- 是否已渲染
    
    -- 元数据
    extra JSON,                                    -- 扩展字段
    tags JSON,                                     -- 标签
    
    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_conv_id (conv_id),
    INDEX idx_message_id (message_id),
    INDEX idx_sender (sender_type, sender_id),
    INDEX idx_round (conv_id, round_index),
    INDEX idx_created_at (created_at),
    
    FOREIGN KEY (conv_id) REFERENCES unified_conversations(conv_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 会话状态表 (新增,用于实时状态管理)
CREATE TABLE conversation_states (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conv_id VARCHAR(255) UNIQUE NOT NULL,
    
    -- 状态信息
    status VARCHAR(50) DEFAULT 'active',           -- active/paused/completed/failed
    last_message_id VARCHAR(255),
    last_active_at DATETIME,
    
    -- Agent状态 (针对Agent场景)
    agent_status JSON,                             -- Agent运行状态
    pending_actions JSON,                          -- 待执行动作
    
    -- 缓存字段
    summary TEXT,                                  -- 对话摘要(可缓存)
    key_points JSON,                               -- 关键点
    
    -- 统计字段
    message_count INT DEFAULT 0,
    token_count INT DEFAULT 0,
    
    -- 时间戳
    gmt_create DATETIME DEFAULT CURRENT_TIMESTAMP,
    gmt_modified DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_status (status),
    INDEX idx_last_active (last_active_at),
    
    FOREIGN KEY (conv_id) REFERENCES unified_conversations(conv_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 3.2.2 字段映射关系

**chat_history → unified_conversations 映射**：

| chat_history字段 | unified_conversations字段 | 转换说明 |
|-----------------|-------------------------|---------|
| conv_uid | conv_id | 直接映射 |
| chat_mode | chat_mode | 直接映射 |
| summary | goal | 重命名 |
| user_name | user_id | 统一为user_id |
| app_code | app_id | 重命名 |
| sys_code | sys_code | 直接映射 |
| messages | (删除) | 迁移到unified_messages |

**gpts_conversations → unified_conversations 映射**：

| gpts_conversations字段 | unified_conversations字段 | 转换说明 |
|---------------------|-------------------------|---------|
| conv_id | conv_id | 直接映射 |
| conv_session_id | session_id | 重命名 |
| user_goal | goal | 重命名 |
| user_code | user_id | 统一为user_id |
| gpts_name | app_id | 重命名 |
| sys_code | sys_code | 直接映射 |
| team_mode | team_mode | 直接映射 |
| state | state | 直接映射 |
| vis_render | vis_config | 重命名 |
| extra | metadata | 重命名 |

**chat_history_message → unified_messages 映射**：

| chat_history_message字段 | unified_messages字段 | 转换说明 |
|------------------------|-------------------|---------|
| conv_uid | conv_id | 直接映射 |
| message_detail(JSON) | 各字段 | 拆分映射 |

**gpts_messages → unified_messages 映射**：

| gpts_messages字段 | unified_messages字段 | 转换说明 |
|-----------------|-------------------|---------|
| conv_id | conv_id | 直接映射 |
| message_id | message_id | 直接映射 |
| sender | sender_type + sender_id | 拆分 |
| sender_name | sender_name | 直接映射 |
| content | content | 直接映射 |
| thinking | thinking_process | 重命名 |
| tool_calls | tool_calls | 直接映射 |
| observation | observation | 直接映射 |
| action_report | action_report | 直接映射 |
| metrics | execution_metrics | 重命名 |

### 3.3 统一记忆系统设计

#### 3.3.1 架构设计

**统一记忆管理器**：`/packages/derisk-core/src/derisk/agent/unified_memory/`

```python
# unified_memory_manager.py

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class UnifiedMessage:
    """统一消息模型"""
    message_id: str
    conv_id: str
    sender_type: str  # user/assistant/system/agent
    sender_id: Optional[str]
    sender_name: Optional[str]
    content: str
    content_type: str = 'text'
    
    # 扩展字段
    thinking_process: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    observation: Optional[str] = None
    context: Optional[Dict] = None
    
    # 可视化
    vis_type: Optional[str] = None
    vis_data: Optional[Dict] = None
    
    # 元数据
    round_index: Optional[int] = None
    created_at: Optional[datetime] = None
    extra: Optional[Dict] = None
    
@dataclass
class UnifiedConversation:
    """统一会话模型"""
    conv_id: str
    user_id: str
    app_id: Optional[str]
    goal: Optional[str]
    chat_mode: str = 'chat_normal'
    agent_type: str = 'core'  # core or core_v2
    state: str = 'active'
    
    messages: List[UnifiedMessage] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.metadata is None:
            self.metadata = {}

class UnifiedMemoryInterface(ABC):
    """统一记忆接口"""
    
    @abstractmethod
    async def create_conversation(
        self, 
        user_id: str,
        goal: Optional[str] = None,
        chat_mode: str = 'chat_normal',
        agent_type: str = 'core',
        **kwargs
    ) -> UnifiedConversation:
        """创建新会话"""
        pass
    
    @abstractmethod
    async def load_conversation(self, conv_id: str) -> Optional[UnifiedConversation]:
        """加载会话及其历史消息"""
        pass
    
    @abstractmethod
    async def save_message(
        self, 
        conv_id: str,
        message: UnifiedMessage
    ) -> bool:
        """保存消息"""
        pass
    
    @abstractmethod
    async def get_messages(
        self,
        conv_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[UnifiedMessage]:
        """获取消息列表"""
        pass
    
    @abstractmethod
    async def update_conversation_state(
        self,
        conv_id: str,
        state: str,
        **updates
    ) -> bool:
        """更新会话状态"""
        pass
    
    @abstractmethod
    async def delete_conversation(self, conv_id: str) -> bool:
        """删除会话及其消息"""
        pass


class UnifiedMemoryManager(UnifiedMemoryInterface):
    """统一记忆管理器实现"""
    
    def __init__(self):
        from derisk.storage.unified_storage import (
            UnifiedConversationDao,
            UnifiedMessageDao,
            ConversationStateDao
        )
        self.conv_dao = UnifiedConversationDao()
        self.msg_dao = UnifiedMessageDao()
        self.state_dao = ConversationStateDao()
        
    async def create_conversation(
        self, 
        user_id: str,
        goal: Optional[str] = None,
        chat_mode: str = 'chat_normal',
        agent_type: str = 'core',
        **kwargs
    ) -> UnifiedConversation:
        """创建新会话"""
        import uuid
        conv_id = str(uuid.uuid4())
        
        # 创建会话记录
        conv_entity = await self.conv_dao.create(
            conv_id=conv_id,
            user_id=user_id,
            goal=goal,
            chat_mode=chat_mode,
            agent_type=agent_type,
            started_at=datetime.now(),
            **kwargs
        )
        
        # 初始化状态
        await self.state_dao.create(
            conv_id=conv_id,
            status='active'
        )
        
        return UnifiedConversation(
            conv_id=conv_id,
            user_id=user_id,
            goal=goal,
            chat_mode=chat_mode,
            agent_type=agent_type
        )
    
    async def load_conversation(self, conv_id: str) -> Optional[UnifiedConversation]:
        """加载会话"""
        # 加载会话基本信息
        conv_entity = await self.conv_dao.get_by_conv_id(conv_id)
        if not conv_entity:
            return None
        
        # 加载消息列表
        messages = await self.get_messages(conv_id)
        
        return UnifiedConversation(
            conv_id=conv_entity.conv_id,
            user_id=conv_entity.user_id,
            app_id=conv_entity.app_id,
            goal=conv_entity.goal,
            chat_mode=conv_entity.chat_mode,
            agent_type=conv_entity.agent_type,
            state=conv_entity.state,
            messages=messages,
            metadata=conv_entity.metadata or {}
        )
    
    async def save_message(
        self, 
        conv_id: str,
        message: UnifiedMessage
    ) -> bool:
        """保存消息"""
        # 保存消息实体
        await self.msg_dao.create(
            conv_id=conv_id,
            message_id=message.message_id,
            sender_type=message.sender_type,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            content=message.content,
            content_type=message.content_type,
            thinking_process=message.thinking_process,
            tool_calls=message.tool_calls,
            observation=message.observation,
            context=message.context,
            vis_type=message.vis_type,
            vis_data=message.vis_data,
            round_index=message.round_index,
            extra=message.extra
        )
        
        # 更新会话状态
        await self.state_dao.update(
            conv_id=conv_id,
            last_message_id=message.message_id,
            last_active_at=datetime.now(),
            message_count=self.state_dao.get_message_count(conv_id) + 1
        )
        
        return True
    
    async def get_messages(
        self,
        conv_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[UnifiedMessage]:
        """获取消息列表"""
        msg_entities = await self.msg_dao.list_by_conv_id(
            conv_id=conv_id,
            limit=limit,
            offset=offset
        )
        
        return [
            UnifiedMessage(
                message_id=msg.message_id,
                conv_id=msg.conv_id,
                sender_type=msg.sender_type,
                sender_id=msg.sender_id,
                sender_name=msg.sender_name,
                content=msg.content,
                content_type=msg.content_type,
                thinking_process=msg.thinking_process,
                tool_calls=msg.tool_calls,
                observation=msg.observation,
                context=msg.context,
                vis_type=msg.vis_type,
                vis_data=msg.vis_data,
                round_index=msg.round_index,
                created_at=msg.created_at,
                extra=msg.extra
            )
            for msg in msg_entities
        ]
    
    async def update_conversation_state(
        self,
        conv_id: str,
        state: str,
        **updates
    ) -> bool:
        """更新会话状态"""
        await self.conv_dao.update(
            conv_id=conv_id,
            state=state,
            **updates
        )
        
        await self.state_dao.update(
            conv_id=conv_id,
            status=state,
            **updates
        )
        
        return True
    
    async def delete_conversation(self, conv_id: str) -> bool:
        """删除会话"""
        # 删除消息
        await self.msg_dao.delete_by_conv_id(conv_id)
        
        # 删除状态
        await self.state_dao.delete(conv_id)
        
        # 删除会话
        await self.conv_dao.delete(conv_id)
        
        return True
```

#### 3.3.2 Core架构适配器

**位置**：`/packages/derisk-core/src/derisk/agent/unified_memory/core_adapter.py`

```python
from derisk.agent.unified_memory import (
    UnifiedMemoryManager,
    UnifiedConversation,
    UnifiedMessage
)
from derisk.core.interface.message import StorageConversation

class CoreMemoryAdapter:
    """Core架构记忆适配器"""
    
    def __init__(self):
        self.unified_memory = UnifiedMemoryManager()
    
    async def create_storage_conversation(
        self,
        conv_uid: str,
        chat_mode: str,
        user_name: str,
        sys_code: Optional[str] = None,
        app_code: Optional[str] = None,
        **kwargs
    ) -> StorageConversation:
        """创建兼容Core架构的StorageConversation"""
        
        # 使用统一记忆系统创建会话
        unified_conv = await self.unified_memory.create_conversation(
            user_id=user_name,  # 映射user_name -> user_id
            goal=kwargs.get('summary'),
            chat_mode=chat_mode,
            agent_type='core',
            app_id=app_code,
            sys_code=sys_code,
            conv_id=conv_uid,  # 复用conv_uid
            **kwargs
        )
        
        # 转换为StorageConversation格式
        storage_conv = StorageConversation(
            conv_uid=conv_uid,
            chat_mode=chat_mode,
            user_name=user_name,
            sys_code=sys_code,
            app_code=app_code,
            conv_storage=None,  # 不再需要单独的conv_storage
            message_storage=None,  # 不再需要单独的message_storage
        )
        
        # 注入统一记忆管理器
        storage_conv._unified_memory = self.unified_memory
        storage_conv._unified_conv = unified_conv
        
        return storage_conv
    
    async def save_message_to_unified(
        self,
        conv_uid: str,
        message: dict
    ) -> bool:
        """将Core消息保存到统一记忆系统"""
        
        # 构造统一消息
        unified_msg = UnifiedMessage(
            message_id=message.get('message_id', str(uuid.uuid4())),
            conv_id=conv_uid,
            sender_type=message.get('role', 'user'),
            sender_id=message.get('user_name'),
            sender_name=message.get('user_name'),
            content=message.get('content', ''),
            content_type='text',
            context=message.get('context'),
            extra=message.get('extra')
        )
        
        return await self.unified_memory.save_message(conv_uid, unified_msg)
    
    async def load_from_unified(
        self,
        conv_uid: str
    ) -> Optional[StorageConversation]:
        """从统一记忆系统加载StorageConversation"""
        
        # 加载统一会话
        unified_conv = await self.unified_memory.load_conversation(conv_uid)
        if not unified_conv:
            return None
        
        # 转换为StorageConversation
        storage_conv = await self.create_storage_conversation(
            conv_uid=conv_uid,
            chat_mode=unified_conv.chat_mode,
            user_name=unified_conv.user_id,
            sys_code=unified_conv.metadata.get('sys_code'),
            app_code=unified_conv.app_id
        )
        
        # 加载消息
        messages = unified_conv.messages or []
        for msg in messages:
            storage_conv.add_message(
                role=msg.sender_type,
                content=msg.content,
                **msg.extra or {}
            )
        
        return storage_conv
```

#### 3.3.3 Core_v2架构适配器

**位置**：`/packages/derisk-core/src/derisk/agent/unified_memory/core_v2_adapter.py`

```python
from derisk.agent.unified_memory import (
    UnifiedMemoryManager,
    UnifiedConversation,
    UnifiedMessage
)

class CoreV2MemoryAdapter:
    """Core_v2架构记忆适配器"""
    
    def __init__(self):
        self.unified_memory = UnifiedMemoryManager()
    
    async def initialize_agent_conversation(
        self,
        conv_session_id: str,
        agent_name: str,
        user_goal: str,
        user_id: str,
        sys_code: Optional[str] = None,
        team_mode: Optional[str] = None,
        **kwargs
    ) -> UnifiedConversation:
        """初始化Agent对话(替换原agent_chat.py的逻辑)"""
        
        # 检查是否已有历史会话
        existing_conv = await self.unified_memory.load_conversation(conv_session_id)
        
        if existing_conv and existing_conv.agent_type == 'core_v2':
            # 恢复历史会话
            return existing_conv
        
        # 创建新会话
        unified_conv = await self.unified_memory.create_conversation(
            user_id=user_id,
            goal=user_goal,
            chat_mode='chat_agent',
            agent_type='core_v2',
            app_id=agent_name,
            sys_code=sys_code,
            team_mode=team_mode,
            session_id=conv_session_id,  # 支持session分组
            **kwargs
        )
        
        return unified_conv
    
    async def save_agent_message(
        self,
        conv_id: str,
        sender: str,
        receiver: Optional[str],
        content: str,
        thinking: Optional[str] = None,
        tool_calls: Optional[List[Dict]] = None,
        observation: Optional[str] = None,
        action_report: Optional[Dict] = None,
        round_index: Optional[int] = None,
        **kwargs
    ) -> bool:
        """保存Agent消息(替换原GptsMessagesDao)"""
        
        # 解析sender信息
        if '::' in sender:
            sender_type, sender_id = sender.split('::', 1)
        else:
            sender_type = 'agent'
            sender_id = sender
        
        # 构造统一消息
        unified_msg = UnifiedMessage(
            message_id=kwargs.get('message_id', str(uuid.uuid4())),
            conv_id=conv_id,
            sender_type=sender_type,
            sender_id=sender_id,
            sender_name=kwargs.get('sender_name', sender),
            content=content,
            content_type='text',
            thinking_process=thinking,
            tool_calls=tool_calls,
            observation=observation,
            context=kwargs.get('context'),
            vis_type=kwargs.get('vis_type'),
            vis_data=kwargs.get('vis_data'),
            round_index=round_index,
            extra={
                'action_report': action_report,
                'receiver': receiver,
                **kwargs.get('extra', {})
            }
        )
        
        return await self.unified_memory.save_message(conv_id, unified_msg)
    
    async def load_agent_history(
        self,
        conv_id: str,
        agent_name: Optional[str] = None
    ) -> List[UnifiedMessage]:
        """加载Agent历史消息"""
        
        messages = await self.unified_memory.get_messages(conv_id)
        
        # 可选: 过滤特定Agent的消息
        if agent_name:
            messages = [
                msg for msg in messages
                if msg.sender_id == agent_name or msg.sender_name == agent_name
            ]
        
        return messages
    
    async def restore_agent_memory(
        self,
        conv_id: str,
        memory_instance
    ) -> bool:
        """恢复Agent记忆状态"""
        
        messages = await self.load_agent_history(conv_id)
        
        for msg in messages:
            # 构造utterance格式
            utterance = {
                'speaker': msg.sender_id or msg.sender_name,
                'utterance': msg.content,
                'role': msg.sender_type,
                'round_index': msg.round_index
            }
            
            # 恢复到memory实例
            memory_instance.save_to_memory(utterance)
        
        return True
```

### 3.4 前端统一渲染方案

#### 3.4.1 统一数据接口

**后端API统一**：`/api/v1/unified/conversations`

```python
# /derisk_serve/conversation/api/unified_endpoints.py

from fastapi import APIRouter, Depends
from derisk.agent.unified_memory import UnifiedMemoryManager

router = APIRouter()

@router.get("/conversations/{conv_id}")
async def get_conversation(
    conv_id: str,
    include_messages: bool = True,
    memory: UnifiedMemoryManager = Depends()
):
    """获取统一会话详情"""
    conv = await memory.load_conversation(conv_id)
    
    if not conv:
        return {"error": "Conversation not found"}
    
    response = {
        "conv_id": conv.conv_id,
        "user_id": conv.user_id,
        "app_id": conv.app_id,
        "goal": conv.goal,
        "chat_mode": conv.chat_mode,
        "agent_type": conv.agent_type,
        "state": conv.state,
        "started_at": conv.metadata.get('started_at'),
        "message_count": len(conv.messages) if conv.messages else 0
    }
    
    if include_messages:
        response["messages"] = [
            {
                "message_id": msg.message_id,
                "sender_type": msg.sender_type,
                "sender_name": msg.sender_name,
                "content": msg.content,
                "thinking": msg.thinking_process,
                "tool_calls": msg.tool_calls,
                "observation": msg.observation,
                "vis_type": msg.vis_type,
                "vis_data": msg.vis_data,
                "round_index": msg.round_index,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in (conv.messages or [])
        ]
    
    return response

@router.get("/conversations/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    limit: Optional[int] = 50,
    offset: int = 0,
    memory: UnifiedMemoryManager = Depends()
):
    """获取会话消息列表"""
    messages = await memory.get_messages(conv_id, limit=limit, offset=offset)
    
    return {
        "conv_id": conv_id,
        "messages": [
            {
                "message_id": msg.message_id,
                "sender_type": msg.sender_type,
                "sender_name": msg.sender_name,
                "content": msg.content,
                "thinking": msg.thinking_process,
                "tool_calls": msg.tool_calls,
                "observation": msg.observation,
                "vis_type": msg.vis_type,
                "vis_data": msg.vis_data,
                "round_index": msg.round_index,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in messages
        ],
        "total": len(messages),
        "limit": limit,
        "offset": offset
    }

@router.post("/conversations")
async def create_conversation(
    user_id: str,
    goal: Optional[str] = None,
    chat_mode: str = 'chat_normal',
    agent_type: str = 'core',
    memory: UnifiedMemoryManager = Depends()
):
    """创建新会话"""
    conv = await memory.create_conversation(
        user_id=user_id,
        goal=goal,
        chat_mode=chat_mode,
        agent_type=agent_type
    )
    
    return {
        "conv_id": conv.conv_id,
        "user_id": conv.user_id,
        "goal": conv.goal,
        "chat_mode": conv.chat_mode,
        "agent_type": conv.agent_type,
        "state": conv.state
    }
```

#### 3.4.2 前端统一Hook

**位置**：`/web/src/hooks/use-unified-chat.ts`

```typescript
import { useQuery, useMutation } from 'react-query';
import { useState, useCallback } from 'react';

export interface UnifiedMessage {
  message_id: string;
  sender_type: 'user' | 'assistant' | 'agent' | 'system';
  sender_name?: string;
  content: string;
  thinking?: string;
  tool_calls?: any[];
  observation?: string;
  vis_type?: string;
  vis_data?: any;
  round_index?: number;
  created_at?: string;
}

export interface UnifiedConversation {
  conv_id: string;
  user_id: string;
  app_id?: string;
  goal?: string;
  chat_mode: string;
  agent_type: 'core' | 'core_v2';
  state: string;
  messages?: UnifiedMessage[];
  message_count?: number;
}

export function useUnifiedChat(conv_id?: string) {
  const [messages, setMessages] = useState<UnifiedMessage[]>([]);
  
  // 加载会话
  const { data: conversation, isLoading } = useQuery<UnifiedConversation>(
    ['conversation', conv_id],
    async () => {
      if (!conv_id) return null;
      
      const response = await fetch(`/api/v1/unified/conversations/${conv_id}`);
      return response.json();
    },
    {
      enabled: !!conv_id,
      onSuccess: (data) => {
        if (data?.messages) {
          setMessages(data.messages);
        }
      }
    }
  );
  
  // 发送消息
  const sendMessage = useCallback(async (content: string, options?: any) => {
    const msg_id = `msg_${Date.now()}`;
    
    // 乐观更新
    const userMessage: UnifiedMessage = {
      message_id: msg_id,
      sender_type: 'user',
      content,
      created_at: new Date().toISOString()
    };
    
    setMessages(prev => [...prev, userMessage]);
    
    try {
      // SSE流式请求
      const response = await fetch(`/api/v1/unified/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conv_id,
          content,
          ...options
        })
      });
      
      // 处理SSE流
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      let assistantMessage: UnifiedMessage = {
        message_id: `msg_${Date.now()}_assistant`,
        sender_type: 'assistant',
        content: '',
        created_at: new Date().toISOString()
      };
      
      setMessages(prev => [...prev, assistantMessage]);
      
      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));
            
            // 更新助手消息
            if (data.type === 'content') {
              assistantMessage.content += data.content;
              setMessages(prev => {
                const newMessages = [...prev];
                const lastIndex = newMessages.length - 1;
                newMessages[lastIndex] = { ...assistantMessage };
                return newMessages;
              });
            } else if (data.type === 'thinking') {
              assistantMessage.thinking = data.thinking;
            } else if (data.type === 'tool_call') {
              assistantMessage.tool_calls = assistantMessage.tool_calls || [];
              assistantMessage.tool_calls.push(data.tool_call);
            } else if (data.type === 'vis') {
              assistantMessage.vis_type = data.vis_type;
              assistantMessage.vis_data = data.vis_data;
            }
          }
        }
      }
      
    } catch (error) {
      console.error('Failed to send message:', error);
      // 回滚乐观更新
      setMessages(prev => prev.filter(m => m.message_id !== msg_id));
    }
  }, [conv_id]);
  
  return {
    conversation,
    messages,
    isLoading,
    sendMessage
  };
}
```

#### 3.4.3 统一渲染组件

**位置**：`/web/src/components/chat/UnifiedChatContent.tsx`

```typescript
import React from 'react';
import { UnifiedMessage } from '@/hooks/use-unified-chat';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';
import { AgentMessage } from './AgentMessage';
import { VisComponents } from './VisComponents';

interface UnifiedChatContentProps {
  messages: UnifiedMessage[];
  agentType?: 'core' | 'core_v2';
}

export function UnifiedChatContent({ 
  messages, 
  agentType = 'core' 
}: UnifiedChatContentProps) {
  
  return (
    <div className="unified-chat-content">
      {messages.map((message) => {
        // 根据sender_type和时间判断角色
        if (message.sender_type === 'user') {
          return (
            <UserMessage
              key={message.message_id}
              content={message.content}
              senderName={message.sender_name}
              createdAt={message.created_at}
            />
          );
        }
        
        if (message.sender_type === 'agent') {
          return (
            <AgentMessage
              key={message.message_id}
              content={message.content}
              thinking={message.thinking}
              toolCalls={message.tool_calls}
              observation={message.observation}
              senderName={message.sender_name}
              visType={message.vis_type}
              visData={message.vis_data}
              createdAt={message.created_at}
            />
          );
        }
        
        // assistant或system
        return (
          <AssistantMessage
            key={message.message_id}
            content={message.content}
            thinking={message.thinking}
            toolCalls={message.tool_calls}
            observation={message.observation}
            visType={message.vis_type}
            visData={message.vis_data}
            createdAt={message.created_at}
          />
        );
      })}
    </div>
  );
}

// Agent消息组件
function AgentMessage({ 
  content, 
  thinking, 
  toolCalls, 
  observation,
  visType,
  visData,
  senderName,
  createdAt 
}: AgentMessageProps) {
  return (
    <div className="agent-message">
      <div className="message-header">
        <span className="agent-name">{senderName || 'Agent'}</span>
        <span className="timestamp">{formatTime(createdAt)}</span>
      </div>
      
      {/* 思考过程 */}
      {thinking && (
        <div className="thinking-section">
          <Collapsible title="思考过程">
            <Markdown content={thinking} />
          </Collapsible>
        </div>
      )}
      
      {/* 工具调用 */}
      {toolCalls && toolCalls.length > 0 && (
        <div className="tool-calls-section">
          <Collapsible title={`工具调用 (${toolCalls.length})`}>
            {toolCalls.map((call, index) => (
              <ToolCallCard key={index} toolCall={call} />
            ))}
          </Collapsible>
        </div>
      )}
      
      {/* 消息内容 */}
      <div className="message-content">
        <Markdown content={content} />
      </div>
      
      {/* 可视化组件 */}
      {visType && visData && (
        <div className="visualization-section">
          <VisComponents type={visType} data={visData} />
        </div>
      )}
      
      {/* 观察结果 */}
      {observation && (
        <div className="observation-section">
          <Collapsible title="观察结果">
            <Markdown content={observation} />
          </Collapsible>
        </div>
      )}
    </div>
  );
}
```

---

## 四、数据迁移方案

### 4.1 迁移策略

采用 **双写+分步迁移** 策略:

```
Phase 1: 新建统一表 + 双写
    ↓
Phase 2: 历史数据迁移
    ↓
Phase 3: 读切换到新表
    ↓
Phase 4: 停止双写,下线旧表
```

### 4.2 Phase 1: 双写阶段

**目标**: 新建统一表,所有写入操作同时写入新旧两套表

**实施步骤**:

1. **创建统一表** (执行SQL DDL)

2. **修改DAO层实现双写**

```python
# /derisk/storage/chat_history/chat_history_db.py

class ChatHistoryDao:
    async def raw_update(self, entity: ChatHistoryEntity):
        # 原有写入chat_history
        with self.session() as session:
            session.merge(entity)
            session.commit()
        
        # 新增: 同步写入unified_conversations和unified_messages
        await self._sync_to_unified(entity)
    
    async def _sync_to_unified(self, entity: ChatHistoryEntity):
        """同步到统一记忆系统"""
        from derisk.storage.unified_storage import (
            UnifiedConversationDao,
            UnifiedMessageDao
        )
        
        unified_conv_dao = UnifiedConversationDao()
        unified_msg_dao = UnifiedMessageDao()
        
        # 检查是否已存在
        existing = await unified_conv_dao.get_by_conv_id(entity.conv_uid)
        if not existing:
            # 创建统一会话
            await unified_conv_dao.create(
                conv_id=entity.conv_uid,
                user_id=entity.user_name,
                goal=entity.summary,
                chat_mode=entity.chat_mode,
                agent_type='core',
                app_id=entity.app_code,
                sys_code=entity.sys_code,
                started_at=entity.gmt_create,
                metadata={'source': 'chat_history'}
            )
        
        # 同步消息
        if entity.messages:
            messages = json.loads(entity.messages)
            for idx, msg in enumerate(messages):
                await unified_msg_dao.create(
                    conv_id=entity.conv_uid,
                    message_id=f"msg_{entity.conv_uid}_{idx}",
                    sender_type=msg.get('role', 'user'),
                    content=msg.get('content', ''),
                    message_index=idx,
                    extra={'source': 'chat_history'}
                )
```

```python
# /derisk_serve/agent/db/gpts_conversations_db.py

class GptsConversationsDao:
    async def a_add(self, entity: GptsConversationsEntity):
        # 原有写入gpts_conversations
        async with self.async_session() as session:
            session.add(entity)
            await session.commit()
        
        # 新增: 同步写入unified_conversations
        await self._sync_to_unified(entity)
    
    async def _sync_to_unified(self, entity: GptsConversationsEntity):
        """同步到统一记忆系统"""
        from derisk.storage.unified_storage import UnifiedConversationDao
        
        unified_conv_dao = UnifiedConversationDao()
        
        # 创建统一会话
        await unified_conv_dao.create(
            conv_id=entity.conv_id,
            session_id=entity.conv_session_id,
            user_id=entity.user_code,
            goal=entity.user_goal,
            chat_mode='chat_agent',
            agent_type='core_v2',
            app_id=entity.gpts_name,
            team_mode=entity.team_mode,
            state=entity.state,
            sys_code=entity.sys_code,
            vis_config=entity.vis_render,
            metadata={'source': 'gpts_conversations', **(entity.extra or {})}
        )
```

3. **部署双写版本**
   - 灰度发布,先切10%流量
   - 监控双写性能和数据一致性
   - 逐步扩大到100%

### 4.3 Phase 2: 历史数据迁移

**目标**: 将双写之前的历史数据迁移到新表

**迁移脚本**:

```python
# /scripts/migrate_to_unified_memory.py

import asyncio
from tqdm import tqdm
from datetime import datetime

class DataMigration:
    def __init__(self):
        from derisk.storage.chat_history.chat_history_db import ChatHistoryDao
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao
        from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
        from derisk.storage.unified_storage import (
            UnifiedConversationDao,
            UnifiedMessageDao
        )
        
        self.chat_history_dao = ChatHistoryDao()
        self.gpts_conv_dao = GptsConversationsDao()
        self.gpts_msg_dao = GptsMessagesDao()
        self.unified_conv_dao = UnifiedConversationDao()
        self.unified_msg_dao = UnifiedMessageDao()
    
    async def migrate_chat_history(self, batch_size=1000):
        """迁移chat_history数据"""
        print(f"[{datetime.now()}] 开始迁移 chat_history...")
        
        offset = 0
        total = await self.chat_history_dao.count()
        
        with tqdm(total=total, desc="Migrating chat_history") as pbar:
            while offset < total:
                # 分批读取
                entities = await self.chat_history_dao.list_batch(
                    limit=batch_size,
                    offset=offset
                )
                
                for entity in entities:
                    try:
                        # 检查是否已迁移
                        existing = await self.unified_conv_dao.get_by_conv_id(
                            entity.conv_uid
                        )
                        
                        if existing:
                            # 已存在,跳过
                            pbar.update(1)
                            continue
                        
                        # 迁移会话
                        await self._migrate_chat_history_conv(entity)
                        
                        # 迁移消息
                        await self._migrate_chat_history_messages(entity)
                        
                        pbar.update(1)
                        
                    except Exception as e:
                        print(f"迁移失败 conv_uid={entity.conv_uid}: {e}")
                        pbar.update(1)
                
                offset += batch_size
        
        print(f"[{datetime.now()}] chat_history 迁移完成")
    
    async def _migrate_chat_history_conv(self, entity):
        """迁移单个chat_history会话"""
        await self.unified_conv_dao.create(
            conv_id=entity.conv_uid,
            user_id=entity.user_name,
            goal=entity.summary,
            chat_mode=entity.chat_mode,
            agent_type='core',
            app_id=entity.app_code,
            sys_code=entity.sys_code,
            started_at=entity.gmt_create,
            ended_at=entity.gmt_modified,
            metadata={
                'source': 'chat_history_migration',
                'migrated_at': datetime.now().isoformat()
            }
        )
    
    async def _migrate_chat_history_messages(self, entity):
        """迁移chat_history消息"""
        # 从chat_history_message表读取
        msg_entities = await self.chat_history_dao.get_messages(entity.conv_uid)
        
        for idx, msg_entity in enumerate(msg_entities):
            msg_detail = json.loads(msg_entity.message_detail)
            
            await self.unified_msg_dao.create(
                conv_id=entity.conv_uid,
                message_id=f"msg_{entity.conv_uid}_{idx}",
                sender_type=msg_detail.get('role', 'user'),
                sender_id=msg_detail.get('user_name'),
                sender_name=msg_detail.get('user_name'),
                content=msg_detail.get('content', ''),
                content_type='text',
                message_index=idx,
                round_index=msg_entity.round_index,
                context=msg_detail.get('context'),
                extra={
                    'source': 'chat_history_migration',
                    'original_id': msg_entity.id
                }
            )
    
    async def migrate_gpts_conversations(self, batch_size=1000):
        """迁移gpts_conversations数据"""
        print(f"[{datetime.now()}] 开始迁移 gpts_conversations...")
        
        offset = 0
        total = await self.gpts_conv_dao.count()
        
        with tqdm(total=total, desc="Migrating gpts_conversations") as pbar:
            while offset < total:
                # 分批读取
                entities = await self.gpts_conv_dao.list_batch(
                    limit=batch_size,
                    offset=offset
                )
                
                for entity in entities:
                    try:
                        # 检查是否已迁移
                        existing = await self.unified_conv_dao.get_by_conv_id(
                            entity.conv_id
                        )
                        
                        if existing:
                            # 已存在,跳过
                            pbar.update(1)
                            continue
                        
                        # 迁移会话
                        await self._migrate_gpts_conv(entity)
                        
                        # 迁移消息
                        await self._migrate_gpts_messages(entity)
                        
                        pbar.update(1)
                        
                    except Exception as e:
                        print(f"迁移失败 conv_id={entity.conv_id}: {e}")
                        pbar.update(1)
                
                offset += batch_size
        
        print(f"[{datetime.now()}] gpts_conversations 迁移完成")
    
    async def _migrate_gpts_conv(self, entity):
        """迁移单个gpts会话"""
        await self.unified_conv_dao.create(
            conv_id=entity.conv_id,
            session_id=entity.conv_session_id,
            user_id=entity.user_code,
            goal=entity.user_goal,
            chat_mode='chat_agent',
            agent_type='core_v2',
            app_id=entity.gpts_name,
            team_mode=entity.team_mode,
            state=entity.state,
            sys_code=entity.sys_code,
            vis_config=entity.vis_render,
            started_at=entity.gmt_create,
            ended_at=entity.gmt_modified,
            metadata={
                'source': 'gpts_conversations_migration',
                'migrated_at': datetime.now().isoformat(),
                **(entity.extra or {})
            }
        )
    
    async def _migrate_gpts_messages(self, entity):
        """迁移gpts消息"""
        # 从gpts_messages表读取
        msg_entities = await self.gpts_msg_dao.list_by_conv_id(entity.conv_id)
        
        for msg in msg_entities:
            # 解析sender
            if '::' in (msg.sender or ''):
                sender_type, sender_id = msg.sender.split('::', 1)
            else:
                sender_type = 'agent'
                sender_id = msg.sender
            
            await self.unified_msg_dao.create(
                conv_id=msg.conv_id,
                message_id=msg.message_id,
                sender_type=sender_type,
                sender_id=sender_id,
                sender_name=msg.sender_name,
                receiver_type=msg.receiver if msg.receiver else None,
                receiver_id=msg.receiver_name,
                content=msg.content or '',
                content_type='text',
                thinking_process=msg.thinking,
                tool_calls=json.loads(msg.tool_calls) if msg.tool_calls else None,
                observation=msg.observation,
                context=json.loads(msg.context) if msg.context else None,
                system_prompt=msg.system_prompt,
                user_prompt=msg.user_prompt,
                action_report=json.loads(msg.action_report) if msg.action_report else None,
                execution_metrics=json.loads(msg.metrics) if msg.metrics else None,
                vis_type=self._parse_vis_type(msg),
                vis_data=self._parse_vis_data(msg),
                round_index=msg.rounds,
                created_at=msg.gmt_create,
                extra={
                    'source': 'gpts_messages_migration',
                    'original_id': msg.id
                }
            )
    
    def _parse_vis_type(self, msg):
        """解析可视化类型"""
        # 从action_report或其他字段推断
        if msg.action_report:
            report = json.loads(msg.action_report)
            return report.get('vis_type')
        return None
    
    def _parse_vis_data(self, msg):
        """解析可视化数据"""
        # 从action_report或其他字段推断
        if msg.action_report:
            report = json.loads(msg.action_report)
            return report.get('vis_data')
        return None
    
    async def run(self):
        """执行完整迁移"""
        print("=" * 50)
        print("开始数据迁移")
        print("=" * 50)
        
        # 1. 迁移chat_history
        await self.migrate_chat_history()
        
        # 2. 迁移gpts_conversations
        await self.migrate_gpts_conversations()
        
        # 3. 数据校验
        await self.validate_migration()
        
        print("=" * 50)
        print("数据迁移完成")
        print("=" * 50)
    
    async def validate_migration(self):
        """校验迁移数据"""
        print(f"[{datetime.now()}] 开始数据校验...")
        
        # 校验会话数量
        chat_history_count = await self.chat_history_dao.count()
        gpts_conv_count = await self.gpts_conv_dao.count()
        unified_count = await self.unified_conv_dao.count()
        
        expected_count = chat_history_count + gpts_conv_count
        
        print(f"chat_history 会话数: {chat_history_count}")
        print(f"gpts_conversations 会话数: {gpts_conv_count}")
        print(f"unified_conversations 会话数: {unified_count}")
        print(f"预期总数: {expected_count}")
        
        if unified_count != expected_count:
            print(f"❌ 校验失败: 数量不一致")
            return False
        
        # 抽样校验
        sample_size = 100
        print(f"抽样校验 {sample_size} 条...")
        
        # 随机抽取会比较复杂,这里简化为校验前100条
        for i in range(min(sample_size, chat_history_count)):
            conv = await self.chat_history_dao.get_by_index(i)
            unified = await self.unified_conv_dao.get_by_conv_id(conv.conv_uid)
            
            if not unified:
                print(f"❌ 校验失败: conv_uid={conv.conv_uid} 未找到")
                return False
            
            if unified.user_id != conv.user_name:
                print(f"❌ 校验失败: conv_uid={conv.conv_uid} user_id不匹配")
                return False
        
        print(f"✅ 数据校验通过")
        return True

if __name__ == '__main__':
    migration = DataMigration()
    asyncio.run(migration.run())
```

**执行迁移**:

```bash
# 1. 创建统一表
mysql -u root -p derisk < /sql/create_unified_tables.sql

# 2. 执行迁移脚本
python /scripts/migrate_to_unified_memory.py

# 3. 校验迁移结果
python /scripts/validate_unified_migration.py
```

### 4.4 Phase 3: 读切换

**目标**: 将读操作切换到统一表,保持旧表只写

**实施步骤**:

1. **修改所有读取DAO**

```python
# /derisk_serve/conversation/service/service.py

class ConversationService:
    def __init__(self):
        # 旧: 使用ChatHistoryDao
        # self.dao = ChatHistoryDao()
        
        # 新: 使用UnifiedConversationDao
        from derisk.storage.unified_storage import UnifiedConversationDao
        self.dao = UnifiedConversationDao()
    
    async def get(self, conv_uid: str) -> Optional[ConversationResponse]:
        """获取会话"""
        # 从统一表读取
        conv = await self.dao.get_by_conv_id(conv_uid)
        
        if not conv:
            return None
        
        # 转换为Response格式
        return ConversationResponse(
            conv_uid=conv.conv_id,
            chat_mode=conv.chat_mode,
            user_name=conv.user_id,
            summary=conv.goal,
            app_code=conv.app_id,
            sys_code=conv.sys_code,
            messages=await self._load_messages(conv.conv_id)
        )
```

2. **更新前端API调用**

```typescript
// 修改所有历史消息加载接口
// 旧: /api/v1/serve/conversation/messages
// 新: /api/v1/unified/conversations/{conv_id}/messages

export async function loadConversation(convId: string) {
  const response = await fetch(`/api/v1/unified/conversations/${convId}`);
  return response.json();
}
```

3. **灰度切换**
   - 先切10%读流量到新表
   - 监控性能和错误率
   - 逐步扩大到100%

### 4.5 Phase 4: 下线旧表

**目标**: 停止双写,下线旧表

**实施步骤**:

1. **移除双写代码**

```python
# 删除所有 _sync_to_unified 方法调用
# 仅保留写入统一表的逻辑
```

2. **下线旧表API**

```python
# 弃用旧API
# /api/v1/serve/conversation/* → 返回410 Gone
# /api/v1/app/conversations → 重定向到 /api/v1/unified/conversations
```

3. **归档旧表**

```sql
-- 重命名旧表为归档表
RENAME TABLE chat_history TO chat_history_archived;
RENAME TABLE chat_history_message TO chat_history_message_archived;
RENAME TABLE gpts_conversations TO gpts_conversations_archived;
RENAME TABLE gpts_messages TO gpts_messages_archived;
RENAME TABLE gpts_messages_system TO gpts_messages_system_archived;
RENAME TABLE gpts_plans TO gpts_plans_archived;
RENAME TABLE gpts_work_log TO gpts_work_log_archived;
RENAME TABLE gpts_kanban TO gpts_kanban_archived;
```

4. **清理代码**

```
删除以下代码文件或目录:
- /derisk/storage/chat_history/ (保留适配器一段时间)
- /derisk_serve/agent/db/gpts_conversations_db.py
- /derisk_serve/agent/db/gpts_messages_db.py
- 相关的测试文件
```

---

## 五、实施路线图

### 5.1 时间规划

```
Week 1-2:   方案设计与评审
    ├─ 设计文档评审
    ├─ 技术方案确认
    └─ 任务拆解与排期

Week 3-4:   统一表创建与DAO实现
    ├─ 数据库表创建
    ├─ UnifiedMemoryManager实现
    ├─ Core/Core_v2适配器实现
    └─ 单元测试

Week 5-6:   双写阶段
    ├─ 修改现有DAO为双写
    ├─ 集成测试
    ├─ 灰度发布(10% -> 100%)
    └─ 监控与修复

Week 7-8:   历史数据迁移
    ├─ 迁移脚本开发
    ├─ 迁移执行
    ├─ 数据校验
    └─ 异常数据处理

Week 9-10:  读切换
    ├─ API层改造
    ├─ 前端适配
    ├─ 灰度切换
    └─ 性能优化

Week 11-12: 下线旧表
    ├─ 移除双写代码
    ├─ 下线旧API
    ├─ 归档旧表
    └─ 清理代码

Week 13-14: 验收与优化
    ├─ 全面回归测试
    ├─ 性能压测
    ├─ 文档更新
    └─ 经验总结
```

### 5.2 关键里程碑

| 里程碑 | 完成时间 | 验收标准 |
|--------|---------|---------|
| M1: 设计评审通过 | Week 2 | 技术方案获团队认可 |
| M2: 统一表可用 | Week 4 | DAO和单元测试通过 |
| M3: 双写稳定运行 | Week 6 | 灰度100%无严重问题 |
| M4: 历史数据迁移完成 | Week 8 | 数据校验100%通过 |
| M5: 读切换完成 | Week 10 | 前端功能正常 |
| M6: 旧表下线 | Week 12 | 无功能回退 |
| M7: 项目验收 | Week 14 | 全面测试通过 |

### 5.3 团队分工

| 角色 | 职责 | 人员 |
|------|------|------|
| 架构师 | 方案设计、技术决策、Code Review | TBD |
| 后端开发 | DAO改造、API开发、迁移脚本 | TBD |
| 前端开发 | 统一渲染组件、API适配 | TBD |
| 测试工程师 | 测试用例、回归测试、性能测试 | TBD |
| DBA | 数据库变更、迁移执行、性能优化 | TBD |
| 运维工程师 | 发布部署、监控告警 | TBD |

---

## 六、风险评估

### 6.1 技术风险

#### 风险1: 数据迁移不一致

**描述**: 历史数据迁移过程中可能出现数据丢失或错误

**概率**: 中  
**影响**: 高

**应对措施**:
1. 迁移前全量备份
2. 分批迁移,每批校验
3. 保留旧表一段时间,支持快速回退
4. 制定数据修复脚本

#### 风险2: 性能下降

**描述**: 统一表结构可能导致查询性能下降

**概率**: 中  
**影响**: 中

**应对措施**:
1. 充分的索引设计
2. 引入Redis缓存热点数据
3. 分库分表预留方案
4. 性能压测提前验证

#### 风险3: 双写一致性问题

**描述**: 双写期间可能因网络或故障导致数据不一致

**概率**: 低  
**影响**: 高

**应对措施**:
1. 双写失败不影响主流程
2. 定期对账任务,发现不一致自动修复
3. 双写监控告警

### 6.2 业务风险

#### 风险4: 功能回退

**描述**: 重构可能导致部分功能不可用

**概率**: 中  
**影响**: 高

**应对措施**:
1. 全面的回归测试
2. 灰度发布,逐步切流量
3. 快速回滚机制
4. 用户通知和FAQ准备

#### 风险5: 兼容性问题

**描述**: 可能存在依赖旧表的隐藏功能

**概率**: 中  
**影响**: 中

**应对措施**:
1. 全面的代码审查
2. 集成测试覆盖所有场景
3. Beta测试用户收集反馈

### 6.3 项目风险

#### 风险6: 进度延期

**描述**: 项目复杂度高,可能延期

**概率**: 中  
**影响**: 中

**应对措施**:
1. 合理的缓冲时间
2. 分阶段交付,优先保证核心功能
3. 定期进度同步,及时调整

---

## 七、总结

### 7.1 核心价值

1. **消除数据冗余**: 从两套表系统合并为统一表系统,减少存储成本和维护复杂度
2. **统一架构**: Core和Core_v2使用统一记忆系统,降低学习成本
3. **髅架清晰**: 明确的数据模型和接口定义,便于后续扩展
4. **性能优化**: 结构化字段设计,提升查询效率
5. **易维护**: 单一数据源,减少数据一致性问题

### 7.2 关键成果

- 统一数据模型: `unified_conversations` + `unified_messages` + `conversation_states`
- 统一记忆系统: `UnifiedMemoryManager` + Core/Core_v2适配器
- 统一API接口: `/api/v1/unified/*`
- 统一前端渲染: `UnifiedChatContent`组件
- 完整迁移方案: 双写 → 数据迁移 → 读切换 → 下线旧表

### 7.3 后续展望

1. **支持更多场景**: 扩展统一模型支持更多对话场景
2. **智能化增强**: 基于统一数据模型实现智能摘要、知识抽取等
3. **多租户隔离**: 增强多租户数据隔离能力
4. **国际化支持**: 支持多语言对话历史存储

---

## 附录

### A. 相关文档

- [数据库Schema设计文档](./unified_memory_schema.md)
- [UnifiedMemoryManager API文档](./unified_memory_api.md)
- [迁移操作手册](./migration_guide.md)

### B. 代码位置

- 统一表SQL: `/sql/create_unified_tables.sql`
- UnifiedMemoryManager: `/packages/derisk-core/src/derisk/agent/unified_memory/`
- Core适配器: `/packages/derisk-core/src/derisk/agent/unified_memory/core_adapter.py`
- Core_v2适配器: `/packages/derisk-core/src/derisk/agent/unified_memory/core_v2_adapter.py`
- 迁移脚本: `/scripts/migrate_to_unified_memory.py`

### C. 监控指标

**双写阶段**:
- 双写成功率
- 双写延迟
- 数据对账不一致数量

**读切换阶段**:
- API响应时间
- 错误率
- 数据库查询性能

**旧表下线后**:
- 存储空间节省
- 查询性能提升
- 系统稳定性

---

**文档更新记录**:

| 版本 | 日期 | 更新内容 | 作者 |
|------|------|---------|------|
| v1.0 | 2026-03-02 | 初始版本 | Architecture Team |