# Core V2 架构 Hierarchical Context 集成指南

## 概述

已成功为 Core V2 架构的 `ProductionAgent` 和 `ReActReasoningAgent` 集成 `UnifiedContextMiddleware`，实现完整的分层上下文管理能力。

## 架构关系

```
AgentBase
├── UnifiedMemoryManager (对话历史、知识存储)
│   ├── WORKING: 工作记忆
│   ├── EPISODIC: 情景记忆
│   └── SEMANTIC: 语义记忆
│
└── UnifiedContextMiddleware (通过ProductionAgent)
    ├── HierarchicalContextV2Integration
    │   ├── WorkLog → Section转换
    │   ├── 智能压缩（LLM/Rules/Hybrid）
    │   └── 历史回溯工具
    └── GptsMemory + AgentFileSystem协调
```

## 核心特性

### 1. 自动 WorkLog 管理
- ✅ 工具执行自动记录到 hierarchical context
- ✅ WorkLog → Section 智能转换
- ✅ 按任务阶段自动分类（探索/开发/调试/优化/收尾）

### 2. 智能压缩
- ✅ 超过阈值自动触发压缩
- ✅ 三种策略：LLM_SUMMARY / RULE_BASED / HYBRID
- ✅ 优先级判断：CRITICAL / HIGH / MEDIUM / LOW

### 3. 历史回溯
- ✅ 自动注入 recall 工具
- ✅ 支持 section/chapter 查询
- ✅ 关键词搜索历史

### 4. 与 Message List 关系
- ✅ Message List 保持不变（存储对话历史）
- ✅ Hierarchical Context 补充工具执行记录
- ✅ 在构建 LLM Prompt 时合并两者

## 使用方法

### 1. 基础使用（自动启用）

```python
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

# 创建 Agent（默认启用 hierarchical context）
agent = ReActReasoningAgent.create(
    name="my-react-agent",
    model="gpt-4",
    api_key="sk-xxx",
    api_base="https://api.openai.com/v1",
    max_steps=30,
    enable_hierarchical_context=True,  # 默认为 True
)

# 初始化 hierarchical context
await agent.init_hierarchical_context(
    conv_id="conversation-123",
    task_description="分析代码并生成文档",
    gpts_memory=gpts_memory,  # 可选
    agent_file_system=afs,     # 可选
)

# 运行 Agent
async for chunk in agent.run("帮我分析这个项目的架构"):
    print(chunk, end="")

# 查看统计信息
stats = agent.get_statistics()
print(f"章节数: {stats['hierarchical_context_stats']['chapter_count']}")
```

### 2. 自定义配置

```python
from derisk.agent.shared.hierarchical_context import HierarchicalContextConfig
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

# 自义配置
hc_config = HierarchicalContextConfig(
    max_chapter_tokens=10000,
    max_section_tokens=2000,
    recent_chapters_full=2,
    middle_chapters_index=3,
    early_chapters_summary=5,
)

# 创建 Agent
agent = ReActReasoningAgent.create(
    name="my-react-agent",
    model="gpt-4",
    api_key="sk-xxx",
    enable_hierarchical_context=True,
    hc_config=hc_config,
)
```

### 3. 手动记录步骤

```python
# 工具执行后自动记录（已集成到 act() 方法）
result = await agent.act("read", {"file_path": "/path/to/file.py"})

# 手动记录额外步骤（如果需要）
await agent.record_step_to_context(
    tool_name="custom_action",
    tool_args={"param": "value"},
    result=ToolResult(success=True, output="完成"),
)
```

### 4. 获取上下文文本

```python
# 获取 hierarchical context 文本
context_text = agent.get_hierarchical_context_text()

# 手动构建 LLM Prompt
system_prompt = f"""
你是一个 AI 助手。

## 历史上下文

{context_text}

请根据上下文回答用户问题。
"""
```

## 工作原理

### 1. 工具执行流程

```python
async def act(self, tool_name: str, tool_args: Dict, **kwargs):
    # 1. 执行工具
    result = await self.execute_tool(tool_name, tool_args)
    
    # 2. 自动记录到 hierarchical context
    await self.record_step_to_context(tool_name, tool_args, result)
    
    # 3. 返回结果
    return result
```

### 2. LLM Prompt 构建

```python
async def decide(self, message: str, **kwargs):
    # 1. 构建系统提示
    system_prompt = self._build_system_prompt()
    
    # 2. 添加 hierarchical context
    hierarchical_context = self.get_hierarchical_context_text()
    if hierarchical_context:
        system_prompt = f"{system_prompt}\n\n## 历史上下文\n\n{hierarchical_context}"
    
    # 3. 调用 LLM
    response = await self.llm.generate(
        messages=[
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=message)
        ],
        tools=tools,
    )
```

### 3. WorkLog → Section 转换

```python
# 自动根据工具类型判断任务阶段
exploration_tools = {"read", "glob", "grep", "search", "think"}
development_tools = {"write", "edit", "bash", "execute", "run"}

# 自动判断优先级
if tool_name in ["write", "edit", "bash"]:
    priority = ContentPriority.HIGH
elif result.success:
    priority = ContentPriority.MEDIUM
else:
    priority = ContentPriority.LOW
```

## 性能优化

### 1. 缓存机制
- ✅ ContextLoadResult 缓存
- ✅ 避免重复加载
- ✅ 异步并发控制

### 2. 智能压缩
- ✅ Token 阈值触发（默认 40000）
- ✅ 优先保留高优先级内容
- ✅ 最近章节完整保留

### 3. 延迟初始化
- ✅ 仅在需要时初始化
- ✅ 可选依赖（import 失败不影响运行）
- ✅ 向下兼容

## 配置参数

### HierarchicalContextConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_chapter_tokens | int | 10000 | 单章节最大 token 数 |
| max_section_tokens | int | 2000 | 单步骤最大 token 数 |
| recent_chapters_full | int | 2 | 最近N个章节完整保留 |
| middle_chapters_index | int | 3 | 中间章节索引级 |
| early_chapters_summary | int | 5 | 早期章节摘要级 |

### ProductionAgent 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| enable_hierarchical_context | bool | True | 是否启用分层上下文 |
| hc_config | HierarchicalContextConfig | None | 自定义配置 |

## 常见问题

### Q1: 是否必须初始化 hierarchical context？

**A**: 不是必须的。如果不初始化，Agent 仍然可以正常工作，只是缺少历史工具执行记录。建议在需要长程任务的场景下初始化。

### Q2: 与 UnifiedMemoryManager 的关系？

**A**: 两者互补：
- `UnifiedMemoryManager`: 管理对话历史、知识存储
- `UnifiedContextMiddleware`: 管理工具执行记录、历史压缩

### Q3: 如何禁用 hierarchical context？

**A**: 创建 Agent 时设置参数：
```python
agent = ReActReasoningAgent.create(
    name="my-agent",
    enable_hierarchical_context=False,
)
```

### Q4: 内存占用如何？

**A**: 
- 每个会话约 100KB - 500KB（取决于历史长度）
- 智能压缩控制内存增长
- 建议设置 `max_chapter_tokens` 限制

### Q5: 是否支持持久化？

**A**: 是的，通过 `AgentFileSystem` 持久化：
```python
await agent.init_hierarchical_context(
    conv_id="conv-123",
    gpts_memory=gpts_memory,
    agent_file_system=afs,  # 持久化支持
)
```

## 迁移指南

### 从旧版 ReActMasterAgent 迁移

```python
# 旧版（core 架构）
from derisk.agent.expand.react_master_agent import ReActMasterAgent

agent = ReActMasterAgent(
    enable_work_log=True,  # 旧版 work log
)

# 新版（core_v2 架构）
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

agent = ReActReasoningAgent.create(
    name="react-agent",
    enable_hierarchical_context=True,  # 新版 hierarchical context
)
```

### 功能对比

| 功能 | 旧版 ReActMasterAgent | 新版 ReActReasoningAgent |
|------|----------------------|-------------------------|
| WorkLog 记录 | ✅ WorkLogManager | ✅ UnifiedContextMiddleware |
| 历史压缩 | ✅ 手动压缩 | ✅ 智能压缩（自动） |
| 历史回溯 | ❌ 不支持 | ✅ recall 工具 |
| 章节索引 | ❌ 不支持 | ✅ 自动章节分类 |
| 优先级判断 | ❌ 不支持 | ✅ 自动优先级 |

## 测试验证

### 单元测试

```python
import pytest
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

@pytest.mark.asyncio
async def test_hierarchical_context_integration():
    agent = ReActReasoningAgent.create(
        name="test-agent",
        api_key="test-key",
        enable_hierarchical_context=True,
    )
    
    # 初始化
    await agent.init_hierarchical_context(
        conv_id="test-conv",
        task_description="测试任务",
    )
    
    # 执行工具
    result = await agent.act("read", {"file_path": "/test.py"})
    
    # 验证记录
    context_text = agent.get_hierarchical_context_text()
    assert len(context_text) > 0
    
    # 验证统计
    stats = agent.get_statistics()
    assert "hierarchical_context_stats" in stats
```

### 集成测试

```bash
# 运行测试
pytest tests/test_hierarchical_context_integration.py -v

# 覆盖率检查
pytest tests/test_hierarchical_context_integration.py --cov=derisk.agent.core_v2
```

## 总结

✅ **完成集成**：ProductionAgent 和 ReActReasoningAgent 已完整集成 UnifiedContextMiddleware

✅ **向下兼容**：所有改动保持向下兼容，默认启用但可选

✅ **自动管理**：工具执行自动记录、自动压缩、自动分类

✅ **易于使用**：简单 API，开箱即用

✅ **高性能**：缓存机制、异步加载、智能压缩

**推荐使用场景**：
- 长程任务（多轮对话、复杂项目）
- 需要历史回溯的场景
- 需要工具执行历史管理的场景

**不推荐场景**：
- 简单单轮对话（可禁用以节省内存）
- 对历史不敏感的任务