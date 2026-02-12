# ReActMasterV3 Agent 重构文档

## 概述

完成了 ReActMasterV2 Agent 的重构，创建了一个通用标准的 ReAct 范式 Agent - ReActMasterV3。

## 主要改进

### 1. WorkLog 管理系统

**核心特性：**
- 不使用传统的 `memory_history`，而是使用结构化的 WorkLog
- WorkLog 记录所有工具调用，包括工具名称、参数、结果、时间戳等
- 自动支持大结果归档到文件系统（超过 10KB 自动归档）
- 提供标签系统，便于分类和过滤

**文件：** `react_master_agent/work_log.py`

**主要类：**
- `WorkEntry`: 工作日志条目
- `WorkLogSummary`: 工作日志摘要
- `WorkLogStatus`: 工作日志状态枚举
- `WorkLogManager`: 工作日志管理器

### 2. 历史记录自动压缩

**核心特性：**
- 当 WorkLog 的 Token 数超过 LLM 上下文窗口的 70% 时，自动触发压缩
- 保留最新的 N 条活跃日志（默认 100 条）
- 将旧日志压缩为摘要，包含：
  - 工具调用统计
  - 成功/失败计数
  - 关键工具列表
  - 最近的重要操作
- 摘要可以持久化到文件系统

**配置参数：**
```python
WorkLogManager(
    context_window_tokens=128000,      # LLM 上下文窗口
    compression_threshold_ratio=0.7,   # 压缩阈值
    max_summary_entries=100,           # 最大保留条目数
)
```

### 3. 文件系统集成

**核心特性：**
- 与 `AgentFileSystem` 深度集成
- 大工具输出自动归档到文件系统
- WorkLog 自动持久化到文件系统
- 支持会话恢复

**文件结构：**
```
work_log_{agent_id}_{session_id}          # 工作日志 JSON
work_log_summaries_{agent_id}_{session_id} # 摘要 JSON
tool_output_{tool}_{hash}_{timestamp}     # 大结果归档
```

### 4. 保留的 ReActMasterV2 优秀特性

所有 ReActMasterV2 的特性都完整保留：

✅ **Doom Loop 检测** - 智能检测无限循环，包括相似参数检测
✅ **SessionCompaction** - 对话历史压缩
✅ **HistoryPruning** - 历史记录修剪
✅ **Truncate.output** - 工具输出截断

## 文件结构

```
react_master_agent/
├── __init__.py                    # 导出所有类和函数
├── work_log.py                    # WorkLog 管理系统（新增）
├── react_master_agent.py          # ReActMasterV2 Agent（保留）
├── react_master_v3.py             # ReActMasterV3 Agent（新增）
├── doom_loop_detector.py          # Doom Loop 检测
├── session_compaction.py          # 会话压缩
├── prune.py                       # 历史修剪
├── truncation.py                  # 输出截断
├── prompt.py                      # 提示模板
└── example_usage.py               # 使用示例（新增）
```

## 使用方法

### 基本使用

```python
from derisk.agent.expand.react_master_agent import ReActMasterV3Agent

# 创建 Agent
agent = ReActMasterV3Agent(
    context_window=128000,
    compaction_threshold_ratio=0.7,
    # 继承所有 V2 特性
    enable_doom_loop_detection=True,
    enable_session_compaction=True,
    enable_output_truncation=True,
    enable_history_pruning=True,
)

# 使用 Agent
result = await agent.act(message, sender)

# 查询 WorkLog 统计
stats = await agent.get_work_log_stats()
print(stats)
```

### 独立使用 WorkLogManager

```python
from derisk.agent.expand.react_master_agent import create_work_log_manager

# 创建管理器
work_log = await create_work_log_manager(
    agent_id="my_agent",
    session_id="session_123",
    agent_file_system=afs,
    context_window_tokens=128000,
)

# 记录动作
await work_log.record_action(
    tool_name="search",
    args={"query": "python"},
    action_output=action_result,
    tags=["search"],
)

# 获取上下文
context = await work_log.get_context_for_prompt()
```

## 配置选项

### ReActMasterV3 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context_window` | int | 128000 | LLM 上下文窗口大小（token） |
| `compaction_threshold_ratio` | float | 0.7 | 压缩阈值比例 |
| `enable_doom_loop_detection` | bool | True | 启用 Doom Loop 检测 |
| `doom_loop_threshold` | int | 3 | Doom Loop 触发阈值 |
| `enable_session_compaction` | bool | True | 启用会话压缩 |
| `enable_output_truncation` | bool | True | 启用输出截断 |
| `enable_history_pruning` | bool | True | 启用历史修剪 |

### WorkLogManager 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context_window_tokens` | int | 128000 | LLM 上下文窗口 |
| `compression_threshold_ratio` | float | 0.7 | 压缩阈值 |
| `max_summary_entries` | int | 100 | 最大保留条目数 |
| `large_result_threshold_bytes` | int | 10240 | 大结果阈值（10KB） |

## API 参考

### ReActMasterV3Agent

#### 方法

- `async get_work_log_stats() -> Dict[str, Any]` - 获取 WorkLog 统计
- `async get_work_log_context(max_entries: int = 50) -> str` - 获取 WorkLog 上下文
- `async get_full_work_log() -> Dict[str, Any]` - 获取完整 WorkLog
- `get_stats() -> Dict[str, Any]` - 获取综合统计（继承自父类）
- `async cleanup()` - 清理资源

### WorkLogManager

#### 方法

- `async initialize()` - 初始化管理器
- `async record_action(tool_name, args, action_output, tags) -> WorkEntry` - 记录动作
- `async get_context_for_prompt(max_entries=50, include_summaries=True) -> str` - 获取 prompt 上下文
- `async get_full_work_log() -> Dict[str, Any]` - 获取完整日志
- `async get_stats() -> Dict[str, Any]` - 获取统计信息
- `async clear()` - 清空日志

## 特性对比

| 特性 | ReActMasterV2 | ReActMasterV3 |
|------|---------------|---------------|
| Doom Loop 检测 | ✅ | ✅ |
| 会话压缩 | ✅ | ✅ |
| 历史修剪 | ✅ | ✅ |
| 输出截断 | ✅ | ✅ |
| WorkLog 管理 | ❌ | ✅ |
| 自动历史压缩 | ❌ | ✅ |
| 大结果归档 | ❌ | ✅ |
| 文件系统集成 | 部分 | 完整 |
| 标签系统 | ❌ | ✅ |
| 统计查询 | 部分 | 完整 |

## 迁移指南

### 从 V2 迁移到 V3

1. **导入更新：**
   ```python
   # 旧版本
   from derisk.agent.expand.react_master_agent import ReActMasterAgent
   
   # 新版本
   from derisk.agent.expand.react_master_agent import ReActMasterV3Agent
   ```

2. **创建 Agent：**
   ```python
   # 基本参数相同，V3 多了 WorkLog 相关参数
   agent = ReActMasterV3Agent(
       # V2 的所有参数都保留
       enable_doom_loop_detection=True,
       # 新参数
       context_window=128000,
       compaction_threshold_ratio=0.7,
   )
   ```

3. **新增功能：**
   ```python
   # 查询 WorkLog 统计
   stats = await agent.get_work_log_stats()
   
   # 获取 WorkLog 上下文
   context = await agent.get_work_log_context()
   ```

4. **向后兼容：**
   - V3 继承 V2，所有 V2 的功能都完全保留
   - 可以逐步使用新功能，不需要一次性迁移

## 最佳实践

### 1. 选择合适的上下文窗口大小

```python
# 短任务，快速响应
agent = ReActMasterV3Agent(context_window=64000)

# 长任务，需要保留更多历史
agent = ReActMasterV3Agent(context_window=200000)
```

### 2. 调整压缩阈值

```python
# 保守策略：尽早压缩
agent = ReActMasterV3Agent(compaction_threshold_ratio=0.6)

# 激进策略：较晚压缩
agent = ReActMasterV3Agent(compaction_threshold_ratio=0.8)
```

### 3. 启用所有保护机制

```python
agent = ReActMasterV3Agent(
    enable_doom_loop_detection=True,    # 防止无限循环
    dool_loop_threshold=3,
    enable_session_compaction=True,      # 压缩对话历史
    enable_output_truncation=True,       # 截断大输出
    enable_history_pruning=True,         # 修剪历史记录
)
```

### 4. 使用 WorkLog 进行调试

```python
# 定期检查 WorkLog 状态
stats = await agent.get_work_log_stats()
if stats['usage_ratio'] > 0.9:
    print("⚠️ WorkLog 使用率过高，考虑调整配置")

# 查看最近的操作
context = await agent.get_work_log_context(max_entries=10)
print(context)
```

## 注意事项

1. **文件系统集成：** `AgentFileSystem` 是可选的，没有它也能正常工作，但不会持久化文件
2. **压缩是异步的：** 压缩操作在后台执行，不会阻塞主流程
3. **摘要不可逆：** 压缩后的日志无法恢复完整的原始数据，只保留摘要
4. **Token 估算：** 使用简单字符比例（1 token ≈ 4 chars）估算，实际可能略有差异

## 示例代码

详细的示例代码见 `example_usage.py`，包括：
- 基本使用示例
- WorkLogManager 独立使用
- 不同配置示例
- 文件系统集成
- 查询和检查功能

## 版本历史

### v3.0.0 (当前版本)
- ✨ 新增 WorkLog 管理系统
- ✨ 新增历史记录自动压缩
- ✨ 新增大结果自动归档
- ✨ 完整的文件系统集成
- ✨ 新增丰富的查询 API
- 📝 完善的文档和示例

### v2.0.0 (保留)
- Doom Loop 检测
- SessionCompaction
- HistoryPruning
- Truncate.output

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

与主项目保持一致