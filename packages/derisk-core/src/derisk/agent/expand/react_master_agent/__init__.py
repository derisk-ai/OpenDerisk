"""
ReActMaster Agent - 最佳实践的 ReAct 范式 Agent 实现

本模块提供了一个增强型 ReAct Agent，具备以下核心特性：

1. **ReActMasterV2** - 基础版本，包含：
   - 末日循环检测 (Doom Loop Detection)
   - 上下文压缩 (Session Compaction)
   - 工具输出截断 (Tool Output Truncation)
   - 历史记录修剪 (History Pruning)

2. **ReActMasterV3** - 最新版本，在 V2 基础上新增：
   - WorkLog 管理系统替代传统 memory
   - 自动历史记录压缩（超出 LLM 上下文窗口时）
   - 集成文件系统进行大结果归档
   - 更好的追踪和调试能力

## ReActMasterV2 特性

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

## ReActMasterV3 特性

添加了 WorkLog 管理系统：
- 使用 WorkLog 替代传统的 memory_history
- WorkLog 自动压缩历史记录
- 大结果自动归档到文件系统
- 提供 get_work_log_stats() 等方法查询工作日志

## 使用示例

### ReActMasterV2 使用
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

### ReActMasterV3 使用
```python
from derisk.agent.expand.react_master_agent import ReActMasterV3Agent

# 创建 Agent
agent = ReActMasterV3Agent(
    context_window=128000,
    compaction_threshold_ratio=0.7,
    # 继承所有 V2 的配置
    enable_doom_loop_detection=True,
    enable_session_compaction=True,
    enable_output_truncation=True,
)

# 使用
await agent.act(message, sender)

# 查询 WorkLog
stats = await agent.get_work_log_stats()
context = await agent.get_work_log_context()
```

## WorkLog 管理器独立使用

也可以独立使用 WorkLog 管理器：

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

# 查询统计
stats = await work_log.get_stats()
```
"""

from .react_master_agent import ReActMasterAgent, ReActMasterParser
from .react_master_v3 import ReActMasterV3Agent
from .work_log import (
    WorkLogManager,
    create_work_log_manager,
    WorkEntry,
    WorkLogSummary,
    WorkLogStatus,
)
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
    REACT_MASTER_USER_TEMPLATE_ENHANCED,
    REACT_MASTER_WORKLOG_TEMPLATE,
    REACT_MASTER_WORKLOG_COMPRESSED_NOTIFICATION,
)

# 阶段管理
from .phase_manager import (
    PhaseManager,
    TaskPhase,
    PhaseContext,
    create_phase_manager,
)

# 报告生成
from .report_generator import (
    ReportGenerator,
    ReportAgent,
    Report,
    ReportSection,
    ReportMetadata,
    ReportFormat,
    ReportType,
    create_report_generator,
    generate_simple_report,
)

__version__ = "3.0.0"

__all__ = [
    # 主要类 - V2
    "ReActMasterAgent",
    "ReActMasterParser",
    # 主要类 - V3 (推荐)
    "ReActMasterV3Agent",
    # WorkLog 管理
    "WorkLogManager",
    "create_work_log_manager",
    "WorkEntry",
    "WorkLogSummary",
    "WorkLogStatus",
    # 阶段管理（新）
    "PhaseManager",
    "TaskPhase",
    "PhaseContext",
    "create_phase_manager",
    # 报告生成（新）
    "ReportGenerator",
    "ReportAgent",
    "Report",
    "ReportSection",
    "ReportMetadata",
    "ReportFormat",
    "ReportType",
    "create_report_generator",
    "generate_simple_report",
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
    "REACT_MASTER_USER_TEMPLATE_ENHANCED",
    "REACT_MASTER_WORKLOG_TEMPLATE",
    "REACT_MASTER_WORKLOG_COMPRESSED_NOTIFICATION",
]
