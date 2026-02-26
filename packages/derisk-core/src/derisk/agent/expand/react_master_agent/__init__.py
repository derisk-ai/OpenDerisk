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

## 独立使用增强功能

```python
# WorkLog 管理
from derisk.agent.expand.react_master_agent import WorkLogManager

work_log = WorkLogManager("agent_id", "session_id")

# 阶段管理
from derisk.agent.expand.react_master_agent import PhaseManager, TaskPhase

phase_manager = PhaseManager(auto_phase_detection=True)

# 报告生成
from derisk.agent.expand.react_master_agent.report_generator import ReportGenerator

generator = ReportGenerator(work_log, "agent_id", "task_id")
```
"""

from .react_master_agent import ReActMasterAgent
from .work_log import (
    WorkLogManager,
    create_work_log_manager,
    WorkEntry,
    WorkLogSummary,
    WorkLogStatus,
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

__version__ = "2.1.0"

__all__ = [
    # 主要类
    "ReActMasterAgent",
    "ReActMasterParser",
    # WorkLog 管理
    "WorkLogManager",
    "create_work_log_manager",
    "WorkEntry",
    "WorkLogSummary",
    "WorkLogStatus",
    # 阶段管理
    "PhaseManager",
    "TaskPhase",
    "PhaseContext",
    "create_phase_manager",
    # 报告生成
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
    # 中文提示模板
    "REACT_MASTER_SYSTEM_TEMPLATE_CN",
    "REACT_MASTER_USER_TEMPLATE_CN",
    "REACT_MASTER_WRITE_MEMORY_TEMPLATE_CN",
    "DOOM_LOOP_WARNING_PROMPT_CN",
    "TOOL_TRUNCATION_REMINDER_CN",
    "COMPACTION_NOTIFICATION_CN",
    "PRUNE_NOTIFICATION_CN",
    "REACT_PARSE_ERROR_PROMPT_CN",
]
