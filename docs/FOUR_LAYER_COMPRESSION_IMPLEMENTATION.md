# 四层上下文压缩架构 - 实现总结

## 概述

根据用户的设计要求，实现了完整的四层上下文压缩架构，解决了原生 Function Call 模式下 WorkLog 重复的问题。

## 四层架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    四层上下文压缩架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: Truncation (截断)                                      │
│  ├── 处理单个大型工具输出                                         │
│  ├── 超过阈值时截断并保存完整内容                                   │
│  └── 应用于: 当前轮次工具输出                                      │
│                                                                  │
│  Layer 2: Pruning (修剪)                                         │
│  ├── 定期清理旧的工具输出                                         │
│  ├── 标记为"compacted"并替换为占位符                               │
│  └── 应用于: 当前轮次消息历史                                      │
│                                                                  │
│  Layer 3: Compaction (压缩)                                      │
│  ├── 上下文窗口接近限制时触发                                      │
│  ├── 使用 LLM 生成历史摘要                                        │
│  ├── 归档旧章节，保留最近消息                                      │
│  └── 应用于: 当前轮次消息历史                                      │
│                                                                  │
│  Layer 4: Multi-Turn History (跨轮次历史)                         │
│  ├── 管理多轮对话历史                                             │
│  ├── 历史轮次: 压缩为摘要 (用户提问 + WorkLog摘要 + 答案摘要)       │
│  ├── 当前轮次: 原生 Function Call 模式，tool messages 直接传递     │
│  └── 应用于: 跨轮次历史注入 memory 变量                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 核心改进

### 1. 解决重复问题

**之前的问题:**
- `memory` 变量包含当前轮次的 WorkLog
- 原生 Function Call 也传递 tool messages
- 两者重复，浪费 token

**现在的设计:**
- **历史轮次**: 通过 `memory` 变量以压缩摘要形式提供
- **当前轮次**: 仅通过原生 tool messages 传递
- **无重复**: `memory` 不再包含当前轮次详细信息

### 2. 消息流程

```
历史轮次 (已压缩存档):
├── 第1轮: 用户提问1 + WorkLog摘要1 + 答案摘要1
├── 第2轮: 用户提问2 + WorkLog摘要2 + 答案摘要2
└── ... (通过 memory 变量注入)

当前轮次 (原生 Function Call):
├── System Prompt
├── User: 当前提问 + memory变量(历史摘要)
├── Assistant: 思考
├── Tool Messages: 工具1结果
├── Tool Messages: 工具2结果
└── ... (直接传递，不通过 memory)
```

## 实现文件

### 新增文件

1. **`layer4_conversation_history.py`**
   - `ConversationHistoryManager`: Layer 4 核心管理器
   - `ConversationRound`: 对话轮次数据模型
   - `WorkLogSummary`: WorkLog 摘要
   - `Layer4CompressionConfig`: Layer 4 配置

2. **`tests/test_layer4_compression.py`**
   - Layer 4 功能测试脚本

### 修改文件

1. **`compaction_pipeline.py`**
   - 更新文档为四层架构
   - 添加 Layer 4 配置参数
   - 添加 Layer 4 方法:
     - `get_or_create_history_manager()`
     - `start_conversation_round()`
     - `complete_conversation_round()`
     - `get_layer4_history_for_prompt()`

2. **`react_master_agent.py`** (core)
   - 修改 `var_memory` 注入 Layer 4 历史
   - 修改 `load_thinking_messages` 启动新轮次
   - 修改 `act` 完成轮次
   - 添加 `_get_layer4_history_for_memory()`

3. **`base_builtin_agent.py`** (core_v2)
   - 添加 Layer 4 支持方法
   - 启用四层压缩管道

4. **`agent_base.py`** (core_v2)
   - 修改 `run` 方法支持 Layer 4
   - 添加 `_start_conversation_round()`
   - 添加 `_complete_conversation_round()`

5. **`enhanced_agent.py`** (core_v2)
   - `ProductionAgent` 添加 Layer 4 支持

6. **`memory/__init__.py`**
   - 导出 Layer 4 相关类

## 关键 API

### ConversationHistoryManager

```python
# 启动新轮次
round = await manager.start_new_round(
    user_question="What is the weather?",
    user_context={"location": "Beijing"}
)

# 更新 WorkLog
await manager.update_current_round_worklog(
    worklog_entries=[...],
    summary=WorkLogSummary(...)
)

# 完成轮次
await manager.complete_current_round(
    ai_response="The weather is sunny.",
    ai_thinking="..."
)

# 获取历史摘要（用于 prompt）
history = await manager.get_history_for_prompt()
```

### UnifiedCompactionPipeline

```python
# Layer 4 方法
await pipeline.start_conversation_round(question, context)
await pipeline.complete_conversation_round(response, thinking)
history = await pipeline.get_layer4_history_for_prompt()
```

## 配置参数

### Layer 4 配置 (UnifiedCompactionConfig)

```python
enable_layer4_compression: bool = True          # 启用第四层压缩
max_rounds_before_compression: int = 3          # 保留最近3轮不压缩
max_total_rounds: int = 10                      # 最多保留10轮历史
layer4_compression_token_threshold: int = 8000  # 压缩触发阈值
layer4_chars_per_token: int = 4

# 摘要长度限制
max_question_summary_length: int = 200
max_response_summary_length: int = 300
max_findings_length: int = 300
```

## 向后兼容性

- **默认启用**: `enable_layer4_compression=True`
- **降级机制**: Layer 4 失败时自动降级到 WorkLog
- **配置控制**: 可通过配置禁用 Layer 4

## 优势

1. **无重复**: 历史轮次和当前轮次职责分离
2. **省 token**: 历史轮次以摘要形式存储
3. **更清晰**: 当前轮次使用原生 Function Call
4. **可扩展**: 支持任意多轮对话历史
5. **向后兼容**: 失败时自动降级

## 待办事项

1. **性能测试**: 验证大规模对话的性能
2. **持久化存储**: 实现数据库存储接口
3. **监控指标**: 添加 Layer 4 专项监控
4. **文档更新**: 更新架构文档和 API 文档
5. **单元测试**: 完善测试覆盖率

## 文件变更清单

```
packages/derisk-core/src/derisk/agent/core/memory/
├── __init__.py                          [修改] 导出 Layer 4 类
├── compaction_pipeline.py                [修改] 添加 Layer 4 支持
├── layer4_conversation_history.py        [新增] Layer 4 实现
└── tests/
    └── test_layer4_compression.py        [新增] 测试脚本

packages/derisk-core/src/derisk/agent/expand/react_master_agent/
└── react_master_agent.py                 [修改] 集成 Layer 4

packages/derisk-core/src/derisk/agent/core_v2/
├── agent_base.py                         [修改] 支持 Layer 4
├── enhanced_agent.py                     [修改] ProductionAgent 支持
└── builtin_agents/
    └── base_builtin_agent.py             [修改] 启用 Layer 4
```

## 总结

四层压缩架构成功实现了：
1. ✅ Layer 4 (跨轮次历史压缩)
2. ✅ 解决 WorkLog 与 tool messages 重复问题
3. ✅ 支持 core 和 core_v2 所有 Agent
4. ✅ 向后兼容，可配置，带降级机制
