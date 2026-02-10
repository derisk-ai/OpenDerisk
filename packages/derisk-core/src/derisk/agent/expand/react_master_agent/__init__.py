"""
ReActMaster Agent - 最佳实践的 ReAct 范式 Agent 实现

本模块提供了一个增强型 ReAct Agent，具备以下核心特性：

1. **末日循环检测 (Doom Loop Detection)**
   - 智能检测工具调用的重复模式
   - 识别相似参数调用
   - 通过权限系统请求用户确认

2. **上下文压缩 (Session Compaction)**
   - 自动检测上下文窗口溢出
   - 使用 LLM 生成对话摘要
   - 智能保留关键信息

3. **工具输出截断 (Tool Output Truncation)**
   - 自动截断大型输出（默认 2000 行 / 50KB）
   - 保存完整输出到临时文件
   - 提供智能处理建议

4. **历史记录修剪 (History Pruning)**
   - 定期清理旧的工具输出
   - 智能分类消息重要性
   - 保留系统消息和用户消息

## 使用示例

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建 Agent
agent = ReActMasterAgent(
    enable_doom_loop_detection=True,
    doom_loop_threshold=3,
    enable_session_compaction=True,
    context_window=128000,
    enable_output_truncation=True,
    enable_history_pruning=True,
)

# 使用
await agent.act(message, sender)
```
"""

from .react_master_agent import ReActMasterAgent, ReActMasterParser
from .doom_loop_detector import (
    DoomLoopDetector,
    IntelligentDoomLoopDetector,
    DoomLoopCheckResult,
    DoomLoopAction,
)
from .session_compaction import (
    SessionCompaction,
    CompactionResult,
    CompactionConfig,
    TokenEstimator,
)
from .prune import (
    HistoryPruner,
    PruneResult,
    PruneConfig,
    MessageClassifier,
    prune_messages,
)
from .truncation import (
    Truncator,
    TruncationResult,
    TruncationConfig,
    ToolOutputWrapper,
    truncate_output,
    create_truncator_with_fs,
)
from .prompt import (
    REACT_MASTER_SYSTEM_TEMPLATE,
    REACT_MASTER_USER_TEMPLATE,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE,
)

__version__ = "1.0.0"

__all__ = [
    # 主要类
    "ReActMasterAgent",
    "ReActMasterParser",

    # DoomLoop 检测
    "DoomLoopDetector",
    "IntelligentDoomLoopDetector",
    "DoomLoopCheckResult",
    "DoomLoopAction",

    # 会话压缩
    "SessionCompaction",
    "CompactionResult",
    "CompactionConfig",
    "TokenEstimator",

    # 历史修剪
    "HistoryPruner",
    "PruneResult",
    "PruneConfig",
    "MessageClassifier",
    "prune_messages",

    # 输出截断
    "Truncator",
    "TruncationResult",
    "TruncationConfig",
    "ToolOutputWrapper",
    "truncate_output",
    "create_truncator_with_fs",

    # 提示模板
    "REACT_MASTER_SYSTEM_TEMPLATE",
    "REACT_MASTER_USER_TEMPLATE",
    "REACT_MASTER_WRITE_MEMORY_TEMPLATE",
]
