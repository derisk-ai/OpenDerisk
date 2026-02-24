# ReActMaster Agent

一个基于最佳实践的 ReAct (Reasoning + Acting) 范式 Agent 实现，具备先进的上下文管理和安全机制。

## 核心特性

### 1. Doom Loop 检测机制

**末日循环**是指 Agent 陷入重复使用相同参数调用同一工具的无限循环状态。

**工作原理：**
- 监控每个工具的调用历史和参数
- 当连续调用同一工具达到阈值（默认 3 次）时触发检测
- 通过权限系统请求用户确认，防止无限循环
- 支持智能模式识别（相似参数也会触发）

**使用示例：**
```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

agent = ReActMasterAgent(
    enable_doom_loop_detection=True,
    doom_loop_threshold=3,  # 触发阈值
)
```

### 2. 上下文压缩 (Session Compaction)

当 LLM 调用的 Token 数超过上下文窗口阈值时，自动对对话历史进行智能总结。

**工作原理：**
- `isOverflow` 函数估算 Token 使用量：(input + cache + output) > usable_context
- 触发时使用专门的 Compaction Agent 生成对话摘要
- 保留最近的消息，对旧消息进行总结
- 生成浓缩的摘要替代原始消息

**使用示例：**
```python
agent = ReActMasterAgent(
    enable_session_compaction=True,
    context_window=128000,
    compaction_threshold_ratio=0.8,  # 80%阈值触发
)
```

### 3. 工具输出截断 (Truncation)

对于可能返回大量文本的工具（如 read, grep, bash），自动截断输出以保护上下文窗口。

**工作原理：**
- 输出限制：默认 2000 行和 50KB
- 完整输出保存：使用 **AgentFileSystem** 实现统一文件管理
  - 本地保存到 `agent_storage/<conv_id>/` 目录
  - 支持自动同步到远程存储（OSS）
  - 通过 `file_key` 而非文件路径引用文件
- 在截断处附加智能提示，建议 Agent 如何处理
- 提示使用 Task 工具委托 explore Agent 或直接读取文件

**使用 AgentFileSystem 的优势：**
- 统一的文件管理接口，与其他 Agent 共享
- 自动处理本地/远程文件同步
- 会话级别的文件隔离
- 支持文件元数据跟踪和恢复

**截断后的提示示例（AgentFileSystem 模式）：**
```
[输出已截断]
原始输出包含 5000 行 (256000 字节)，已超过限制。
完整输出已保存至文件: tool_output_read_xyz123_1

建议处理方式:
1. 使用 Task 工具委托给 explore Agent 来分析完整输出
2. 使用 Grep 工具搜索特定内容
3. 使用 Read 工具配合 offset/limit 参数分段读取
```

**使用 AgentFileSystem 的 Truncator：**
```python
from derisk.agent.expand.react_master_agent import create_truncator_with_fs

# 创建带有 AgentFileSystem 的截断器
truncator = create_truncator_with_fs(conv_id="my_conversation")
result = truncator.truncate(large_output, tool_name="read")

# 通过 file_key 读取完整内容
if result.file_key:
    full_content = truncator.read_truncated_content(result.file_key)
```

### 4. 历史记录修剪 (Prune)

定期清理旧的工具调用输出，管理上下文窗口使用。

**工作原理：**
- 从后向前遍历消息历史
- 当累积 Token 数超过阈值 (`PRUNE_PROTECT`)，将更早的工具输出标记为已压缩
- 保留系统消息、用户消息和关键消息
- 在构建下一次 Prompt 时忽略已压缩消息

**使用示例：**
```python
agent = ReActMasterAgent(
    enable_history_pruning=True,
    prune_protect_tokens=4000,
)
```

## 快速开始

### 基础使用

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建启用所有特性的 Agent
agent = ReActMasterAgent()

# 或者在创建时自定义配置
agent = ReActMasterAgent(
    # Doom Loop 配置
    enable_doom_loop_detection=True,
    doom_loop_threshold=3,

    # 上下文压缩配置
    enable_session_compaction=True,
    context_window=128000,
    compaction_threshold_ratio=0.8,

    # 输出截断配置
    enable_output_truncation=True,

    # 历史修剪配置
    enable_history_pruning=True,
    prune_protect_tokens=4000,
)
```

### 使用独立组件

```python
from derisk.agent.expand.react_master_agent import (
    DoomLoopDetector,
    SessionCompaction,
    HistoryPruner,
    Truncator,
)

# Doom Loop 检测
detector = DoomLoopDetector(threshold=3)
detector.record_call("read", {"path": "/test/file.txt"})
result = detector.check_doom_loop("read", {"path": "/test/file.txt"})
if result.is_doom_loop:
    print(f"检测到循环: {result.message}")

# 输出截断
truncator = Truncator(max_lines=2000, max_bytes=50*1024)
result = truncator.truncate(large_output, tool_name="read")
print(result.content)  # 截断后的内容

# 历史修剪
pruner = HistoryPruner(prune_protect=4000)
result = pruner.prune(messages)
print(f"修剪了 {result.removed_count} 条消息")

# 会话压缩
compactor = SessionCompaction(context_window=128000)
result = await compactor.compact(messages)
print(f"保存了 {result.tokens_saved} tokens")
```

## 项目结构

```
packages/derisk-core/src/derisk/agent/expand/react_master_agent/
├── __init__.py              # 模块入口，导出所有公共 API
├── react_master_agent.py    # 主 Agent 实现
├── doom_loop_detector.py    # Doom Loop 检测
├── session_compaction.py    # 上下文压缩
├── truncation.py            # 工具输出截断
├── prune.py                 # 历史记录修剪
└── prompt.py                # 提示模板
```

## API 参考

### ReActMasterAgent

主 Agent 类，集成所有特性。

**配置参数：**
- `enable_doom_loop_detection`: 启用 Doom Loop 检测
- `doom_loop_threshold`: 触发阈值（默认 3）
- `enable_session_compaction`: 启用上下文压缩
- `context_window`: 上下文窗口大小（默认 128000）
- `compaction_threshold_ratio`: 触发压缩的阈值比例（默认 0.8）
- `enable_output_truncation`: 启用输出截断
- `enable_history_pruning`: 启用历史修剪
- `prune_protect_tokens`: 修剪保护 Token 数（默认 4000）

**方法：**
- `get_stats() -> dict`: 获取运行统计
- `reset_stats()`: 重置统计
- `compress_session(force=False)`: 手动触发会话压缩

### DoomLoopDetector

检测工具调用的重复模式。

**方法：**
- `record_call(tool_name, args)`: 记录工具调用
- `check_doom_loop(tool_name, args) -> DoomLoopCheckResult`: 检查是否存在循环
- `check_and_ask_permission(...) -> bool`: 检查并请求权限
- `reset()`: 重置检测状态
- `get_stats() -> dict`: 获取统计

### Truncator

截断工具输出，支持 AgentFileSystem 统一文件管理。

**配置：**
- `max_lines`: 最大行数（默认 2000）
- `max_bytes`: 最大字节数（默认 51200 = 50KB）
- `agent_file_system`: AgentFileSystem 实例（可选）
- `use_legacy_mode`: 是否使用传统模式（可选）

**方法：**
- `truncate(content, tool_name) -> TruncationResult`: 截断内容
- `read_truncated_content(file_key) -> str`: 读取被截断的完整内容

**使用 AgentFileSystem：**
```python
from derisk.agent.expand.react_master_agent import create_truncator_with_fs

# 创建使用 AgentFileSystem 的截断器
truncator = create_truncator_with_fs(conv_id="conversation_id")
result = truncator.truncate(content, tool_name="tool_name")

# 结果包含 file_key 用于引用文件
if result.file_key:
    full_content = truncator.read_truncated_content(result.file_key)
```

### HistoryPruner

修剪历史消息。

**配置：**
- `prune_protect`: Token 保护阈值
- `min_messages_keep`: 最少保留消息数
- `max_messages_keep`: 最多保留消息数

**方法：**
- `prune(messages) -> PruneResult`: 修剪消息列表
- `prune_action_outputs(outputs)`: 修剪 ActionOutput 列表
- `get_stats() -> dict`: 获取统计

### SessionCompaction

压缩会话上下文。

**配置：**
- `context_window`: 上下文窗口大小
- `threshold_ratio`: 触发压缩的阈值比例
- `recent_messages_keep`: 保留的最近消息数

**方法：**
- `is_overflow(messages) -> (bool, TokenEstimate)`: 检查是否溢出
- `compact(messages, force=False) -> CompactionResult`: 压缩消息
- `get_stats() -> dict`: 获取统计

## 测试

运行测试：

```bash
# 运行所有测试
python -m pytest packages/derisk-core/tests/agent/react_master_agent/ -v

# 运行特定测试
python -m pytest packages/derisk-core/tests/agent/react_master_agent/test_doom_loop_detector.py -v
```

基础测试：
```python
import sys
sys.path.insert(0, 'packages/derisk-core/src')

from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建 Agent
agent = ReActMasterAgent()

# 获取统计
stats = agent.get_stats()
print(stats)
```

## 最佳实践

1. **使用 AgentFileSystem 管理文件**：在多 Agent 环境下，建议统一使用 AgentFileSystem 管理所有文件，实现文件共享和同步
2. **Doom Loop 检测**：在生产环境中总是启用，建议阈值设为 3
3. **上下文压缩**：对于长对话任务必要，可节省 50%+ tokens
4. **输出截断**：对于日志分析、文件读取等工具很重要
5. **历史修剪**：与其他特性配合使用，确保上下文窗口健康

## 注意事项

1. **AgentFileSystem 集成**：需要 AgentFileSystem 可用，否则会降级到传统模式
2. Doom Loop 检测需要配权限回调函数才能真正阻止循环
3. 上下文压缩需要 LLM 客户端才能生成智能摘要
4. 历史修剪会永久修改消息内容（添加标记）

## License

MIT License
