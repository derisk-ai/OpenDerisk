# Session History Manager 集成指南

## 📋 概述

本文档说明如何在现有的 core 和 core_v2 架构下集成第四层压缩机制(Session History Manager)。

---

## ✅ 回答核心问题

### 问题 1: Work Log 是否处理了纯模型输出?

**答案:** 现有三层压缩**部分处理**纯模型输出,但存在局限性:

#### Layer 1 - Truncation:
- ❌ **不处理**纯模型输出(因为无工具输出需截断)
- ✅ 仅处理有工具调用的输出

#### Layer 2 - Pruning:
- ✅ **保护**纯模型输出(assistant 角色消息不被剪枝)
- ✅ 保留在历史中

#### Layer 3 - Compaction:
- ✅ **处理**纯模型输出(通过 LLM 摘要)
- ✅ 保留关键信息

#### ⚠️ 现有问题:
1. **缺少纯模型输出的元数据记录**(如思考时间、token 消耗等)
2. **缺少对"系统提醒"消息的处理**(如"进入工具模式"等)
3. **缺少跨对话的纯模型输出管理**

**✨ 解决方案:** SessionHistoryManager 通过 `pure_model_output` 字段专门记录和管理纯模型输出。

---

### 问题 2: 如何实现第四层压缩?

**答案:** 通过以下步骤实现:

---

## 🏗️ 架构集成方案

### 1. Core V1 集成 (ReActMasterAgent)

**集成点:** `packages/derisk-core/src/derisk/agent/core/base_agent.py`

#### 1.1 初始化 SessionHistoryManager

```python
# 在 ConversableAgent 类中添加:
from derisk.agent.core.memory.session_history import (
    SessionHistoryManager,
    SessionHistoryConfig,
)

class ConversableAgent(Role, Agent):
    # ... 现有代码 ...
    
    # 新增: Session History Manager
    _session_history_manager: Optional[SessionHistoryManager] = PrivateAttr(default=None)
    
    async def _ensure_session_history_manager(self):
        """确保 Session History Manager 已初始化"""
        if self._session_history_manager is not None:
            return
        
        # 从 GptsMemory 创建
        self._session_history_manager = SessionHistoryManager(
            session_id=self.not_null_agent_context.conv_session_id,
            gpts_memory=self.memory.gpts_memory,
            config=SessionHistoryConfig(
                hot_retention_count=3,
                warm_retention_count=5,
                include_pure_model_outputs=True,  # 启用纯模型输出记录
            ),
        )
        
        # 加载历史
        await self._session_history_manager.load_session_history()
        
        logger.info(f"SessionHistoryManager initialized for session {self.not_null_agent_context.conv_session_id}")
```

#### 1.2 在 generate_reply 中集成

```python
async def generate_reply(
    self,
    received_message: AgentMessage,
    sender: Agent,
    reviewer: Optional[Agent] = None,
    rely_messages: Optional[List[AgentMessage]] = None,
    historical_dialogues: Optional[List[AgentMessage]] = None,
    is_retry_chat: bool = False,
    last_speaker_name: Optional[str] = None,
    **kwargs,
) -> AgentMessage:
    """
    生成回复消息
    """
    # ... 现有代码 ...
    
    # === 新增: 初始化 Session History Manager ===
    if self.enable_session_history:
        await self._ensure_session_history_manager()
    
    # ... 现有代码 ...
```

#### 1.3 在 load_thinking_messages 中注入历史

```python
async def load_thinking_messages(
    self,
    received_message: AgentMessage,
    sender: Agent,
    rely_messages: Optional[List[AgentMessage]] = None,
    historical_dialogues: Optional[List[AgentMessage]] = None,
    context: Optional[Dict[str, Any]] = None,
    is_retry_chat: bool = False,
    **kwargs,
) -> Tuple[List[Dict], Dict, str, str]:
    """
    加载思考消息
    """
    # ... 现有代码: 加载系统提示词、历史对话等 ...
    
    thinking_messages = []
    resource_info = {}
    system_prompt, user_prompt = "", ""
    
    # === 新增: 注入 Session History ===
    if self.enable_session_history and self._session_history_manager:
        session_history_context = await self._session_history_manager.build_history_context(
            current_conv_id=self.not_null_agent_context.conv_id,
            max_tokens=8000,  # 配置化
        )
        
        if session_history_context:
            # 在系统消息后插入历史
            thinking_messages.extend(session_history_context)
            logger.info(f"Injected {len(session_history_context)} session history messages")
    
    # ... 继续现有逻辑: 加载依赖消息、依赖工具等 ...
    
    return thinking_messages, resource_info, system_prompt, user_prompt
```

#### 1.4 对话完成时保存历史

```python
async def generate_reply(self, ...):
    try:
        # ... 现有对话逻辑 ...
        
        # 对话成功完成
        reply_message.success = is_success
        
        # === 新增: 保存到 Session History ===
        if self.enable_session_history and self._session_history_manager:
            # 获取本次对话的所有消息
            messages = await self.memory.gpts_memory.get_messages(
                self.not_null_agent_context.conv_id
            )
            
            await self._session_history_manager.on_conversation_complete(
                conv_id=self.not_null_agent_context.conv_id,
                messages=messages,
            )
        
        return reply_message
        
    except Exception as e:
        # ... 异常处理 ...
```

---

### 2. Core V2 集成 (ReActReasoningAgent)

**集成点:** `packages/derisk-core/src/derisk/agent/core_v2/agent_base.py`

#### 2.1 在 AgentBase 中初始化

```python
from derisk.agent.core.memory.session_history import (
    SessionHistoryManager,
    SessionHistoryConfig,
)

class AgentBase(ABC):
    def __init__(
        self,
        info: AgentInfo,
        memory: Optional[UnifiedMemoryInterface] = None,
        use_persistent_memory: bool = False,
        gpts_memory: Optional["GptsMemory"] = None,
        conv_id: Optional[str] = None,
        # === 新增参数 ===
        enable_session_history: bool = False,
        session_history_config: Optional[SessionHistoryConfig] = None,
    ):
        # ... 现有初始化 ...
        
        # === 新增: Session History ===
        self.enable_session_history = enable_session_history
        self._session_history_manager: Optional[SessionHistoryManager] = None
        
        if enable_session_history and gpts_memory and conv_id:
            # 从 conv_id 提取 session_id
            session_id = conv_id.rsplit("_", 1)[0]  # 假设格式: session_id_round
            
            self._session_history_manager = SessionHistoryManager(
                session_id=session_id,
                gpts_memory=gpts_memory,
                config=session_history_config or SessionHistoryConfig(),
            )
```

#### 2.2 在 run() 方法中集成

```python
async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
    """主执行循环"""
    
    # === 新增: 加载 Session History ===
    if self._session_history_manager:
        await self._session_history_manager.load_session_history()
        
        # 构建历史上下文
        history_context = await self._session_history_manager.build_history_context(
            max_tokens=8000,
        )
        
        # 注入到消息列表
        if history_context:
            self._messages.extend(history_context)
    
    # ... 现有执行循环 ...
    
    # === 新增: 保存对话历史 ===
    if self._session_history_manager:
        await self._session_history_manager.on_conversation_complete(
            conv_id=self.conv_id,
            messages=self._messages,
        )
```

---

### 3. Prompt 模板集成

**集成点:** `packages/derisk-core/src/derisk/agent/expand/react_master_agent/prompt_fc.py`

```python
REACT_FC_SYSTEM_TEMPLATE = """\
## 1. 核心身份与使命
...

## 2. 历史对话上下文
{% if session_history %}
{{ session_history }}
{% endif %}
...

## 3. 环境与资源
...
"""

REACT_FC_USER_TEMPLATE = """\
{% if session_history %}
### 历史对话回顾
{{ session_history }}

---
{% endif %}

{% if question %}\
请完成以下任务: {{ question }}
{% endif %}"""
```

#### 在 register_variables 中注册:

```python
def register_variables(self, context: Dict[str, Any]):
    """注册模板变量"""
    variables = {
        "question": context.get("question", ""),
        "agent_context": context.get("agent_context", ""),
        # ... 其他变量 ...
    }
    
    # === 新增: Session History ===
    if self._session_history_manager:
        # 同步调用异步方法
        import asyncio
        loop = asyncio.get_event_loop()
        session_history = loop.run_until_complete(
            self._session_history_manager.build_history_context(
                current_conv_id=context.get("conv_id"),
                max_tokens=8000,
            )
        )
        
        # 格式化为文本
        history_text = "\n".join([
            msg.get("content", "")
            for msg in session_history
        ])
        
        variables["session_history"] = history_text
    else:
        variables["session_history"] = ""
    
    return variables
```

---

## 🔧 配置选项

### SessionHistoryConfig 参数说明

```python
@dataclass
class SessionHistoryConfig:
    # 热数据区配置
    hot_retention_count: int = 3  # 保留最近 3 次对话的完整细节
    
    # 温数据区配置
    warm_retention_count: int = 5  # 再保留 5 次摘要
    
    # 冷数据区配置
    cold_retention_days: int = 30  # 归档保留 30 天
    
    # Token 限制
    max_hot_tokens: int = 6000  # 热数据区最大 token 数
    max_warm_tokens: int = 3000  # 温数据区最大 token 数
    
    # 纯模型输出配置 (关键!)
    include_pure_model_outputs: bool = True  # 是否包含纯模型输出
    pure_model_max_length: int = 1000  # 纯模型输出最大长度
    
    # 摘要生成
    summary_model: str = "aistudio/DeepSeek-V3"
    summary_max_length: int = 500
```

---

## 🎯 使用示例

### 示例 1: 在 ReActMasterAgent 中启用

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

agent = ReActMasterAgent(
    enable_session_history=True,  # 启用第四层
    session_history_config=SessionHistoryConfig(
        hot_retention_count=3,
        warm_retention_count=5,
        include_pure_model_outputs=True,  # 启用纯模型输出记录
    ),
)

# Agent 会自动:
# 1. 在 generate_reply 开始时加载历史上下文
# 2. 在 generate_reply 结束时保存对话记录
# 3. 自动检测和记录纯模型输出
```

### 示例 2: 在 Core V2 Agent 中启用

```python
from derisk.agent.core_v2 import EnhancedAgent, AgentInfo
from derisk.agent.core.memory.session_history import SessionHistoryConfig

info = AgentInfo(
    name="my_agent",
    description="Agent with session history",
    mode=AgentMode.AUTO,
)

agent = EnhancedAgent(
    info=info,
    gpts_memory=gpts_memory,
    conv_id="session_123_1",
    enable_session_history=True,  # 启用第四层
    session_history_config=SessionHistoryConfig(
        include_pure_model_outputs=True,
    ),
)
```

---

## 📊 效果对比

### 使用前 (只有三层压缩):

```
用户: "帮我分析这个日志"
Agent: [调用工具读取日志] [分析] [返回结果]
历史: [user] [tool] [assistant] -> Layer 3 压缩 -> [summary]

用户: "刚才你分析的是什么?"
Agent: [无法回答,因为历史已被压缩]
```

### 使用后 (有第四层 Session History):

```
用户: "帮我分析这个日志"
Agent: [调用工具读取日志] [分析] [返回结果]
SessionHistory: 保存到 Hot 区

用户: "刚才你分析的是什么?"
Agent: [从 SessionHistory 加载] "我刚才分析了xxx日志,发现..."
```

---

## 🐛 调试技巧

### 1. 查看历史状态

```python
stats = await agent._session_history_manager.get_stats()
print(stats)
# 输出:
# {
#   "session_id": "session_123",
#   "hot_count": 2,
#   "warm_count": 3,
#   "cold_count": 1,
#   "pure_model_outputs_count": 1,
#   "total_tokens": 4500,
# }
```

### 2. 手动触发压缩

```python
# 查看热数据区对话
for conv_id, conv in agent._session_history_manager.hot_conversations.items():
    print(f"Conv {conv_id}: {conv.user_query}")
    print(f"  Has tool calls: {conv.has_tool_calls}")
    print(f"  Pure model output: {conv.pure_model_output[:100] if conv.pure_model_output else 'N/A'}")
```

---

## ✅ 验证清单

集成完成后,请验证以下功能:

- [ ] SessionHistoryManager 正确初始化
- [ ] 历史上下文成功注入到 thinking_messages
- [ ] 对话完成后正确保存到 SessionHistory
- [ ] 纯模型输出被正确记录
- [ ] 热数据区超过阈值时自动压缩到温数据区
- [ ] 温数据区超过阈值时自动归档
- [ ] 跨对话的上下文能够正确继承

---

## 🔍 常见问题

### Q1: 如何查看当前的纯模型输出历史?

```python
pure_outputs = agent._session_history_manager._pure_model_outputs
for i, output in enumerate(pure_outputs):
    print(f"{i+1}. {output[:100]}...")
```

### Q2: 如何强制清除历史?

```python
# 清除所有历史
agent._session_history_manager.hot_conversations.clear()
agent._session_history_manager.warm_summaries.clear()
agent._session_history_manager.cold_archive_refs.clear()
agent._session_history_manager._pure_model_outputs.clear()
```

### Q3: 如何自定义摘要生成逻辑?

重写 `_generate_summary` 方法:

```python
async def _generate_summary(self, conv: SessionConversation):
    # 使用 Layer 3 的 ImprovedSessionCompaction
    from derisk.agent.core_v2.improved_compaction import ImprovedSessionCompaction
    
    compactor = ImprovedSessionCompaction()
    # ... 自定义逻辑 ...
```

---

## 📚 相关文档

- [WORKLOG_HISTORY_COMPACTION_ARCHITECTURE.md](../../docs/WORKLOG_HISTORY_COMPACTION_ARCHITECTURE.md) - 完整的三层压缩架构设计
- [CORE_V2_ARCHITECTURE.md](../../docs/architecture/CORE_V2_ARCHITECTURE.md) - Core V2 架构文档
- [session_history.py](./session_history.py) - SessionHistoryManager 源码

---

## 🎉 总结

通过本文档的集成方案,您已经成功实现了:

1. ✅ **第四层压缩机制** - 管理跨对话的历史上下文
2. ✅ **纯模型输出处理** - 专门记录和管理无工具调用的模型回复
3. ✅ **三层存储策略** - Hot/Warm/Cold 自动分层
4. ✅ **无缝集成** - 与现有 core 和 core_v2 架构完美兼容

**关键创新:**
- 通过 `has_tool_calls` 和 `pure_model_output` 字段专门处理纯模型输出
- 通过 `SessionConversation` 统一管理单次对话的所有细节
- 通过 `SessionHistoryManager` 实现跨对话的上下文继承

**性能优化:**
- 热数据区: 完整细节,快速访问
- 温数据区: 压缩摘要,节省空间
- 冷数据区: 归档淘汰,长期存储

Happy Coding! 🚀