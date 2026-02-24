# ReActMaster Agent 功能文档

## 概述

ReActMaster Agent 是一个增强型的 ReAct 范式 Agent，集成了多个强大的功能模块。

---

## 核心功能

### 1. Doom Loop 检测

**功能：** 智能检测工具调用的重复模式，防止无限循环

- 支持精确匹配检测
- 支持相似参数检测
- 支持循环调用模式检测（A→B→A→B）
- 通过权限系统请求用户确认

**文件：** `doom_loop_detector.py`

### 2. 上下文压缩

**功能：** 自动检测上下文窗口溢出并生成摘要

- Token 估算和监控
- 自动触发压缩（默认阈值的 80%）
- 使用 LLM 生成高质量摘要
- 智能保留关键信息

**文件：** `session_compaction.py`

### 3. 工具输出截断 (Truncate.output)

**功能：** 自动截断大型输出并保存到文件

- 默认限制：2000 行 / 50KB
- 自动保存完整输出到文件系统
- 提供智能处理建议
- 支持读取完整输出

**文件：** `truncation.py`

### 4. 历史记录修剪 (Prune)

**功能：** 定期清理旧的、不相关的工具调用输出

- 智能分类消息重要性
- Token 基础的修剪策略
- 保留系统消息和用户消息
- 标记已压缩的消息

**文件：** `prune.py`

### 5. WorkLog 管理系统

**功能：** 替代传统 memory 的结构化工作日志

**核心特性：**
- 记录所有工具调用的完整信息
- 自动支持大结果归档到文件系统（>10KB）
- 提供标签系统，便于分类和过滤
- 自动历史压缩（超出 LLM 窗口时）

**文件：** `work_log.py`

**快速使用：**
```python
from derisk.agent.expand.react_master_agent import WorkLogManager

# 创建 WorkLog 管理器
work_log = WorkLogManager("agent_id", "session_id")

# 记录动作
await work_log.record_action(tool_name, args, action_output, tags=[])

# 获取上下文（用于 prompt）
context = await work_log.get_context_for_prompt()
```

### 6. 阶段式 Prompt 管理

**功能：** 根据任务的不同阶段动态调整 prompt

**支持的阶段：**
- EXPLORATION（探索阶段）
- PLANNING（规划阶段）
- EXECUTION（执行阶段）
- REFINEMENT（优化阶段）
- VERIFICATION（验证阶段）
- REPORTING（报告阶段）
- COMPLETE（完成）

**核心特性：**
- 全自动阶段检测（基于调用次数、成功率等）
- 手动阶段控制
- 每个阶段特定的 prompt 指导
- 阶段历史记录

**文件：** `phase_manager.py`

**快速使用：**
```python
from derisk.agent.expand.react_master_agent import PhaseManager, TaskPhase

# 全自动模式
phase_manager = PhaseManager(auto_phase_detection=True)

# 记录操作
await phase_manager.record_action("search", success=True)

# 查看当前阶段
print(phase_manager.current_phase.value)
```

### 7. 报告生成系统

**功能：** 基于工作日志生成多种格式的报告

**报告类型：**
- SUMMARY（摘要报告）
- DETAILED（详细报告）
- TECHNICAL（技术报告）
- EXECUTIVE（执行摘要）
- PROGRESS（进度报告）
- FINAL（最终报告）

**输出格式：**
- Markdown
- HTML
- JSON
- 纯文本

**核心特性：**
- 自动提取关键信息
- 支持人工和 AI 增强摘要
- 集成 WorkLog 数据

**文件：** `report_generator.py`

**快速使用：**
```python
# 简单报告
from derisk.agent.expand.react_master_agent import generate_simple_report

report = await generate_simple_report(work_log, "agent_id", "task_id")

# 灵活报告
from derisk.agent.expand.react_master_agent.report_generator import ReportGenerator

generator = ReportGenerator(work_log, "agent_id", "task_id")
report = await generator.generate_report(
    report_type=ReportType.DETAILED,  # 6种类型
    report_format=ReportFormat.MARKDOWN,  # 4种格式
)
```

---

## 文件结构

```
react_master_agent/
├── __init__.py                      # 导出所有类和函数
├── react_master_agent.py             # 主 Agent 实现
├── work_log.py                      # WorkLog 管理
├── phase_manager.py                  # 阶段管理
├── report_generator.py               # 报告生成
├── doom_loop_detector.py             # Doom Loop 检测
├── session_compaction.py             # 会话压缩
├── prune.py                          # 历史修剪
├── truncation.py                     # 输出截断
├── prompt.py                         # Prompt 模板
├── phase_algorithm_explained.py      # 算法详解
└── example_usage.py                  # 使用示例
```

---

## 快速开始

### 使用 Agent

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建 Agent
agent = ReActMasterAgent(
    enable_doom_loop_detection=True,
    doom_loop_threshold=3,
    enable_session_compaction=True,
    enable_output_truncation=True,
    enable_history_pruning=True,
)

# 使用
await agent.act(message, sender)
```

### 独立使用增强功能

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

# 记录和使用
await phase_manager.record_action("search", True)
await work_log.record_action(...)
context = await work_log.get_context_for_prompt()
report = await generator.generate_report()
```

---

## 最佳实践

| 方案 | 优点 | 适用场景 |
|------|------|----------|
| **完整 Agent** | 开箱即用 | 标准任务 |
| **WorkLog** | 结构化记录 | 需要详细日志 |
| **阶段管理** | 多阶段任务 | 复杂流程 |
| **报告生成** | 灵活报告 | 需要输出 |

---

## 版本信息

**版本号：** 2.1.0

**新增功能（相对 2.0）：**
- WorkLog 管理系统
- 阶段式 Prompt 管理
- 报告生成系统

**保留功能：**
- Doom Loop 检测
- SessionCompaction
- HistoryPruning
- Truncate.output