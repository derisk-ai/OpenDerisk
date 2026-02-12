# ReActMasterV3 高级功能使用指南

## 目录

1. [阶段式 Prompt 管理](#1-阶段式-prompt-管理)
2. [报告生成功能](#2-报告生成功能)
3. [完整示例](#3-完整示例)

---

## 1. 阶段式 Prompt 管理

### 概述

ReActMasterV3 支持根据任务的不同阶段动态调整 prompt，提供更精准的指导。

### 支持的阶段

```
EXPLORATION  (探索阶段) → PLANNING (规划阶段) → EXECUTION (执行阶段)
     ↓                      ↓                      ↓
REFINEMENT (优化阶段) → VERIFICATION (验证阶段) → REPORTING (报告阶段)
     ↓                      ↓                      ↓
             COMPLETE (完成)
```

### 基本使用

```python
from derisk.agent.expand.react_master_agent import (
    ReActMasterV3Agent,
    PhaseManager,
    create_phase_manager,
)

# 创建 Agent
agent = ReActMasterV3Agent(
    context_window=128000,
    compaction_threshold_ratio=0.7,
)

# 创建阶段管理器
phase_manager = create_phase_manager(
    auto_detection=True,  # 启用自动阶段检测
    enable_prompts=True,  # 启用阶段 prompt
)

# 启用阶段管理（在 ReActMasterV3 中可以集成）
# 见下面的完整示例
```

### 阶段 Prompt 自动注入

每个阶段都有特定的指导原则：

#### 探索阶段 (EXPLORATION)
```markdown
## 当前阶段：探索与理解

你正在进行**探索阶段**，主要任务是：
1. 深入理解用户的需求和目标
2. 分析问题的范围和约束条件
3. 收集必要的信息和数据
4. 识别可能的风险和挑战

**指导原则：**
- 优先使用信息收集工具（如：search, read, browse）
- 保持好奇心，多角度思考问题
- 记录所有发现和洞察
- 避免过早下结论
```

#### 规划阶段 (PLANNING)
```markdown
## 当前阶段：规划与设计

你正在进行**规划阶段**，主要任务是：
1. 基于探索结果制定清晰的执行计划
2. 将复杂任务分解为可管理的子任务
3. 确定每个子任务的优先级和依赖关系
4. 选择合适的工具和方法
```

### 手动阶段切换

```python
# 手动切换到下一个阶段
phase_manager.set_phase(
    phase_manager.TaskPhase.EXECUTION,
    reason="探索完成，开始执行计划"
)

# 查看当前阶段
current_phase = phase_manager.current_phase
print(f"当前阶段: {current_phase.value}")
```

### 自动阶段检测

阶段管理器会根据以下条件自动切换阶段：

- **工具调用次数**
- **成功率**
- **错误数量**
- **时间跨度**

示例配置：

```python
phase_manager = PhaseManager(
    auto_phase_detection=True,
    phase_transition_rules={
        TaskPhase.EXPLORATION: {
            "require_min_actions": 3,
            "require_success_rate": 0.5,
        },
        TaskPhase.EXECUTION: {
            "max_actions": 50,
        },
    },
)
```

---

## 2. 报告生成功能

### 概述

提供多种报告生成方式，从简单摘要到复杂 AI 增强报告。

### 报告类型

| 类型 | 说明 |
|------|------|
| `SUMMARY` | 简洁摘要报告 |
| `DETAILED` | 详细完整报告 |
| `TECHNICAL` | 技术分析报告 |
| `EXECUTIVE` | 执行摘要报告 |
| `PROGRESS` | 进度报告 |
| `FINAL` | 最终综合报告 |

### 报告格式

- `MARKDOWN` - Markdown 格式（推荐）
- `HTML` - HTML 网页格式
- `JSON` - JSON 数据格式
- `PLAIN_TEXT` - 纯文本格式

### 方案 1：简单报告生成

```python
from derisk.agent.expand.react_master_agent.report_generator import (
    generate_simple_report,
    ReportFormat,
)

# 假设已经有一个已初始化的 WorkLogManager
async def generate_report():
    # 生成 Markdown 格式的摘要报告
    report_md = await generate_simple_report(
        work_log_manager=agent._work_log_manager,
        agent_id=agent.name,
        task_id="task_123",
        report_format=ReportFormat.MARKDOWN,
    )
    
    print(report_md)
    
    # 保存到文件
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(report_md)
```

### 方案 2：使用 ReportGenerator（更灵活）

```python
from derisk.agent.expand.react_master_agent.report_generator import (
    ReportGenerator,
    ReportType,
    ReportFormat,
)

async def generate_detailed_report():
    # 创建报告生成器
    generator = ReportGenerator(
        work_log_manager=agent._work_log_manager,
        agent_id=agent.name,
        task_id="task_123",
    )
    
    # 生成详细报告
    report = await generator.generate_report(
        report_type=ReportType.DETAILED,
        report_format=ReportFormat.MARKDOWN,
    )
    
    # 转换为指定格式
    markdown_content = report.to_markdown()
    html_content = report.to_html()
    json_content = report.to_json()
    
    # 恢复到文件
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_content)
```

### 方案 3：使用 ReportAgent（AI 增强）

```python
from derisk.agent.expand.react_master_agent.report_generator import ReportAgent

async def generate_ai_enhanced_report():
    # 创建报告 Agent
    report_agent = ReportAgent(
        work_log_manager=agent._work_log_manager,
        agent_id=agent.name,
        task_id="task_123",
        llm_client=agent.llm_config.llm_client,  # 传入 LLM 客户端
    )
    
    # 生成 AI 增强的综合报告
    comprehensive_report = await report_agent.generate_comprehensive_report(
        report_format=ReportFormat.MARKDOWN,
        include_ai_summary=True,  # 包含 AI 生成的摘要
    )
    
    print(comprehensive_report)
```

### 方案 4：在 terminate action 中集成报告

```python
from derisk.agent.expand.actions import Terminate

async def generate_report_on_terminate():
    # 在任务完成时自动生成报告
    from derisk.agent.expand.react_master_agent.report_generator import (
        ReportGenerator,
        ReportType,
        ReportFormat,
    )
    
    generator = ReportGenerator(
        work_log_manager=agent._work_log_manager,
        agent_id=agent.name,
        task_id=agent.not_null_agent_context.conv_id,
    )
    
    # 生成最终报告
    report = await generator.generate_report(
        report_type=ReportType.FINAL,
        report_format=ReportFormat.MARKDOWN,
    )
    
    # 保存报告
    report_content = report.to_markdown()
    file_metadata = await agent.save_conclusion_file(
        content=report_content,
        file_name="task_report",
        extension="md",
    )
    
    return file_metadata
```

---

## 3. 完整示例

### 示例 1：集成阶段管理和报告生成的 Agent

```python
import asyncio
from derisk.agent.expand.react_master_agent import (
    ReActMasterV3Agent,
    PhaseManager,
    TaskPhase,
)
from derisk.agent.expand.react_master_agent.report_generator import (
    ReportGenerator,
    ReportType,
    ReportFormat,
)

class EnhancedReActAgent(ReActMasterV3Agent):
    """增强版 ReAct Agent，集成了阶段管理和报告生成"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # 初始化阶段管理器
        self.phase_manager = PhaseManager(
            auto_phase_detection=True,
            enable_phase_prompts=True,
        )
    
    async def _load_thinking_messages(self, *args, **kwargs):
        """重写以注入阶段上下文"""
        messages, context, system_prompt, user_prompt = await super()._load_thinking_messages(*args, **kwargs)
        
        # 获取当前阶段的 prompt
        phase_prompt = self.phase_manager.get_phase_prompt()
        
        # 获取 WorkLog 上下文
        if self._work_log_manager:
            work_log_context = await self._work_log_manager.get_context_for_prompt()
        else:
            work_log_context = ""
        
        # 注入到 prompt
        if context is None:
            context = {}
        
        context["phase"] = self.phase_manager.current_phase.value
        context["phase_prompt"] = phase_prompt
        
        if user_prompt:
            user_prompt = self.phase_manager.get_user_prompt_context(
                user_prompt,
                work_log_context,
            )
        
        return messages, context, system_prompt, user_prompt
    
    async def _after_action_execution(self, *args, **kwargs):
        """记录动作后更新阶段统计"""
        await super()._after_action_execution(*args, **kwargs)
        
        # 记录到阶段管理器
        if len(args) >= 2:
            tool_name = args[0]
            if len(args) >= 4:
                success = args[3].is_exe_success if hasattr(args[3], 'is_exe_success') else True
            else:
                success = True
            self.phase_manager.record_action(tool_name, success)
    
    async def generate_final_report(self) -> str:
        """生成最终报告"""
        # 切换到报告阶段
        self.phase_manager.set_phase(TaskPhase.REPORTING, reason="任务完成，生成报告")
        
        # 创建报告生成器
        generator = ReportGenerator(
            work_log_manager=self._work_log_manager,
            agent_id=self.name,
            task_id=self.not_null_agent_context.conv_id,
        )
        
        # 生成报告
        report = await generator.generate_report(
            report_type=ReportType.FINAL,
            report_format=ReportFormat.MARKDOWN,
        )
        
        return report.to_markdown()

# 使用示例
async def main():
    # 创建增强版 Agent
    agent = EnhancedReActAgent(
        context_window=128000,
        compaction_threshold_ratio=0.7,
    )
    await agent._initialize_components()
    
    # 执行任务...
    # result = await agent.act(message, sender)
    
    # 任务完成后生成报告
    report = await agent.generate_final_report()
    print(report)
    
    # 查看阶段统计
    phase_stats = agent.phase_manager.get_stats()
    print(f"阶段统计: {phase_stats}")
    
    await agent.cleanup()

# 运行
# asyncio.run(main())
```

### 示例 2：多格式报告导出

```python
async def export_multiple_formats():
    """导出多种格式的报告"""
    from derisk.agent.expand.react_master_agent.report_generator import (
        ReportGenerator,
        ReportType,
        ReportFormat,
    )
    
    generator = ReportGenerator(
        work_log_manager=agent._work_log_manager,
        agent_id=agent.name,
        task_id="task_123",
    )
    
    # 生成 PDF 报告（通过 HTML 中间格式）
    report_html = await generator.generate_report(
        report_type=ReportType.DETAILED,
        report_format=ReportFormat.HTML,
    )
    
    # 保存多种格式
    formats = [
        (ReportFormat.MARKDOWN, "report.md"),
        (ReportFormat.HTML, "report.html"),
        (ReportFormat.JSON, "report.json"),
        (ReportFormat.PLAIN_TEXT, "report.txt"),
    ]
    
    for fmt, filename in formats:
        report = await generator.generate_report(
            report_type=ReportType.DETAILED,
            report_format=fmt,
        )
        
        if fmt == ReportFormat.MARKDOWN:
            content = report.to_markdown()
        elif fmt == ReportFormat.HTML:
            content = report.to_html()
        elif fmt == ReportFormat.JSON:
            content = report.to_json()
        else:
            content = report.to_plain_text()
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"✅ Exported {filename}")
```

### 示例 3：实时进度报告

```python
async def generate_progress_report():
    """生成实时进度报告"""
    from derisk.agent.expand.react_master_agent.report_generator import (
        ReportGenerator,
        ReportType,
    )
    
    generator = ReportGenerator(
        work_log_manager=agent._work_log_manager,
        agent_id=agent.name,
        task_id="task_123",
    )
    
    # 生成进度报告
    report = await generator.generate_report(
        report_type=ReportType.PROGRESS,
        report_format=ReportFormat.MARKDOWN,
    )
    
    return report.to_markdown()

# 定期生成进度报告
async def monitor_progress():
    import asyncio
    
    while True:
        await asyncio.sleep(60)  # 每分钟
        
        progress_report = await generate_progress_report()
        print(f"\n=== Progress Report ===\n{progress_report}\n")
        
        # 检查是否完成
        if agent.phase_manager.current_phase == TaskPhase.COMPLETE:
            break
```

### 示例 4：专门在 terminate action 中生成报告

```python
from derisk.agent.expand.actions import Terminate

async def terminate_with_report(self, **kwargs):
    """扩展的 terminate action，自动生成报告"""
    
    # 先执行标准的 terminate
    result = await Terminate.run(self, **kwargs)
    
    # 生成并附加报告
    if result.is_exe_success:
        report_content = await self.generate_final_report()
        
        # 保存报告
        report_file = await self.save_conclusion_file(
            content=report_content,
            file_name=f"{self.name}_report_{int(time.time())}",
            extension="md",
        )
        
        # 添加到输出文件
        if result.output_files is None:
            result.output_files = []
        result.output_files.append(report_file)
        
        logger.info(f"✅ Report generated and saved: {report_file}")
    
    return result
```

---

## 总结

### 阶段式 Prompt 管理

✅ **优点：**
- 根据任务进展提供精准指导
- 自动化阶段检测，减少手动干预
- 提升任务执行效率

✅ **适用场景：**
- 长期、复杂的多步骤任务
- 需要明确阶段里程碑的项目
- 需要阶段性成果交付的任务

### 报告生成功能

✅ **方案选择：**

| 方案 | 优点 | 适用场景 |
|------|------|----------|
| 简单报告 (`generate_simple_report`) | 快速上手，一行代码 | 基本日志查询 |
| ReportGenerator | 灵活，支持自定义 | 需要定制报告 |
| ReportAgent | AI 增强，智能分析 | 复杂分析报告 |
| 集成到 terminate | 自动化，无缝体验 | 任务结尾自动报告 |

✅ **推荐组合：**

```python
# 场景 1：简单任务
report = await generate_simple_report(work_log, agent_id, task_id)

# 场景 2：复杂任务
agent = EnhancedReActAgent(...)  # 带阶段管理
report = await agent.generate_final_report()

# 场景 3：需要深度分析
report_agent = ReportAgent(work_log, agent_id, task_id, llm_client)
report = await report_agent.generate_comprehensive_report(include_ai_summary=True)
```

---

希望这份指南能帮助你更好地使用 ReActMasterV3 的高级功能！