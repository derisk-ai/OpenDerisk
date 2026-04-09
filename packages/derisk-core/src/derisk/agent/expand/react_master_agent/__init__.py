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

5. **阶段式 Prompt 管理**
   - 支持多阶段任务执行（探索/规划/执行/优化/验证/报告）
   - 自动阶段切换或手动控制
   - 每个阶段不同的 prompt 指导

6. **WorkLog 管理系统**
   - 结构化的工作日志记录
   - 大结果自动归档到文件系统
   - 自动历史压缩（超出 LLM 窗口时）
   - 替代传统 memory 机制

7. **报告生成系统**
   - 支持 6 种报告类型（摘要/详细/技术/执行/进度/最终）
   - 支持 4 种输出格式（Markdown/HTML/JSON/纯文本）
   - AI 增强摘要分析

8. **Kanban 任务规划**（从 PDCAAgent 合并）
   - 结构化的任务规划
   - 阶段状态管理
   - 交付物 Schema 验证
   - 探索限制机制

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

# 启用 Kanban 模式（从 PDCAAgent 迁移）
agent = ReActMasterAgent(
    enable_kanban=True,
    kanban_exploration_limit=2,
)

# 使用
await agent.act(message, sender)
```

## PDCAAgent 迁移指南

如果你之前使用 PDCAAgent，现在可以通过以下方式迁移：

```python
# 旧代码 (PDCAAgent)
from derisk.agent.expand.pdca_agent import PDCAAgent

agent = PDCAAgent()

# 新代码 (ReActMasterAgent with Kanban)
from derisk.agent.expand.react_master_agent import ReActMasterAgent

agent = ReActMasterAgent(enable_kanban=True)

# API 兼容
await agent.create_kanban(mission, stages)
await agent.submit_deliverable(stage_id, deliverable, reflection)
await agent.read_deliverable(stage_id)
status = await agent.get_kanban_status()
```
"""

from .react_master_agent import ReActMasterAgent
from .work_log import (
    WorkLogManager,
    create_work_log_manager,
    WorkEntry,
    WorkLogSummary,
    WorkLogStatus,
    WorkLogCompressionCache,
)

from .phase_manager import (
    PhaseManager,
    TaskPhase,
    PhaseContext,
    create_phase_manager,
)

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
from .kanban_manager import (
    KanbanManager,
    Kanban,
    Stage,
    StageStatus,
    WorkEntry as KanbanWorkEntry,
    validate_deliverable_schema,
    create_kanban_manager,
)
from .prompt import (
    REACT_MASTER_SYSTEM_TEMPLATE,
    REACT_MASTER_USER_TEMPLATE,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE,
    REACT_MASTER_USER_TEMPLATE_ENHANCED,
    REACT_MASTER_WORKLOG_TEMPLATE,
    REACT_MASTER_WORKLOG_COMPRESSED_NOTIFICATION,
    REACT_MASTER_SYSTEM_TEMPLATE_CN,
    REACT_MASTER_USER_TEMPLATE_CN,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE_CN,
    DOOM_LOOP_WARNING_PROMPT_CN,
    TOOL_TRUNCATION_REMINDER_CN,
    COMPACTION_NOTIFICATION_CN,
    PRUNE_NOTIFICATION_CN,
    REACT_PARSE_ERROR_PROMPT_CN,
)
from .todo_tools import (
    todowrite,
    todoread,
    get_todo_tools,
    TodoAnalytics,
    get_todo_analytics,
    generate_todo_report,
    get_todo_report_for_reportgenerator,
)

__version__ = "2.3.0"

__all__ = [
    "ReActMasterAgent",
    "WorkLogManager",
    "create_work_log_manager",
    "WorkEntry",
    "WorkLogSummary",
    "WorkLogStatus",
    "PhaseManager",
    "TaskPhase",
    "PhaseContext",
    "create_phase_manager",
    "ReportGenerator",
    "ReportAgent",
    "Report",
    "ReportSection",
    "ReportMetadata",
    "ReportFormat",
    "ReportType",
    "create_report_generator",
    "generate_simple_report",
    "DoomLoopDetector",
    "IntelligentDoomLoopDetector",
    "DoomLoopCheckResult",
    "DoomLoopAction",
    "SessionCompaction",
    "CompactionResult",
    "CompactionConfig",
    "TokenEstimator",
    "HistoryPruner",
    "PruneResult",
    "PruneConfig",
    "MessageClassifier",
    "prune_messages",
    "Truncator",
    "TruncationResult",
    "TruncationConfig",
    "ToolOutputWrapper",
    "truncate_output",
    "create_truncator_with_fs",
    "KanbanManager",
    "Kanban",
    "Stage",
    "StageStatus",
    "KanbanWorkEntry",
    "validate_deliverable_schema",
    "create_kanban_manager",
    "REACT_MASTER_SYSTEM_TEMPLATE",
    "REACT_MASTER_USER_TEMPLATE",
    "REACT_MASTER_WRITE_MEMORY_TEMPLATE",
    "REACT_MASTER_USER_TEMPLATE_ENHANCED",
    "REACT_MASTER_WORKLOG_TEMPLATE",
    "REACT_MASTER_WORKLOG_COMPRESSED_NOTIFICATION",
    "REACT_MASTER_SYSTEM_TEMPLATE_CN",
    "REACT_MASTER_USER_TEMPLATE_CN",
    "REACT_MASTER_WRITE_MEMORY_TEMPLATE_CN",
    "DOOM_LOOP_WARNING_PROMPT_CN",
    "TOOL_TRUNCATION_REMINDER_CN",
    "COMPACTION_NOTIFICATION_CN",
    "PRUNE_NOTIFICATION_CN",
    "REACT_PARSE_ERROR_PROMPT_CN",
    "todowrite",
    "todoread",
    "get_todo_tools",
    "TodoAnalytics",
    "get_todo_analytics",
    "generate_todo_report",
    "get_todo_report_for_reportgenerator",
]
