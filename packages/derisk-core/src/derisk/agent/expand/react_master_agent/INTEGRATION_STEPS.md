# ReActMasterAgent 集成操作手册

本文档提供将 WorkLog、PhaseManager 和 ReportGenerator 集成到 ReActMasterAgent 的具体操作步骤。

---

## ✅ 已完成的修改

### 1. ✅ 导入语句已添加

位置：`react_master_agent.py` 第 48-50 行
```python
from .work_log import WorkLogManager, create_work_log_manager
from .phase_manager import PhaseManager, TaskPhase, create_phase_manager
from .report_generator import ReportGenerator, ReportType, ReportFormat
```

### 2. ✅ 配置参数已添加

位置：`react_master_agent.py` 第 137-155 行（组件配置部分后面）

```python
# 新功能配置 -> WorkLog、Phase、ReportGenerator 集成配置
enable_work_log: bool = True
enable_phase_management: bool = True
enable_auto_report: bool = True

# WorkLog 配置
work_log_context_window: int = 128000
work_log_compression_ratio: float = 0.7
work_log_large_result_threshold: int = 10 * 1024  # 10KB

# Phase 配置
phase_auto_detection: bool = True
phase_enable_prompts: bool = True

# Report 配置
report_auto_generate: bool = False
report_default_type: str = "detailed"
report_default_format: str = "markdown"
```

### 3. ✅ `_initialize_components` 已更新

位置：`react_master_agent.py` 第 162-231 行，在第 4 步（Truncator 初始化）之后添加了：

```python
# 5. 初始化 WorkLog 管理器（延迟初始化）
if self.enable_work_log:
    self._work_log_manager = None
    self._work_log_initialized = False
    logger.info("WorkLog enabled (will initialize on demand)")
else:
    self._work_log_manager = None
    self._work_log_initialized = False

# 6. 初始化阶段管理器
if self.enable_phase_management:
    self._phase_manager = PhaseManager(
        auto_phase_detection=self.phase_auto_detection,
        enable_phase_prompts=self.phase_enable_prompts,
    )
    logger.info(f"PhaseManager initialized (auto_detection={self.phase_auto_detection})")
else:
    self._phase_manager = None

# 7. 准备报告生成器（延迟初始化）
if self.enable_auto_report:
    self._report_generator = None
    logger.info("ReportGenerator enabled (will initialize on demand)")
else:
    self._report_generator = None
```

---

## 📝 待添加的方法

需要在 `async def _ask_user_permission` 方法之后、`async def _ensure_agent_file_system` 方法之前添加以下辅助方法：

### 方法列表：

1. `_ensure_work_log_manager()` - 确保WorkLog已初始化
2. `_record_action_to_work_log()` - 记录操作到WorkLog
3. `_is_terminate_action()` - 判断是否为终止动作
4. `get_work_log_stats()` - 获取WorkLog统计
5. `get_work_log_context()` - 获取WorkLog上下文
6. `generate_report()` - 手动生成报告
7. `get_current_phase()` - 获取当前阶段
8. `set_phase()` - 手动设置阶段

---

## 📂 方法代码

### 1. WorkLog 相关方法

```python
async def _ensure_work_log_manager(self):
    """确保 WorkLog 管理器已初始化（异步）"""
    if not self.enable_work_log:
        return
    
    if self._work_log_manager and self._work_log_initialized:
        return
    
    # 准备参数
    conv_id = "default"
    session_id = "default"
    
    if self.not_null_agent_context:
        conv_id = self.not_null_agent_context.conv_id or "default"
        session_id = self.not_null_agent_context.conv_session_id or conv_id
    
    # 获取或创建 AgentFileSystem
    afs = await self._ensure_agent_file_system()
    
    # 创建 WorkLog 管理器
    self._work_log_manager = await create_work_log_manager(
        agent_id=self.name,
        session_id=session_id,
        agent_file_system=afs,
        context_window_tokens=self.work_log_context_window,
        compression_threshold_ratio=self.work_log_compression_ratio,
    )
    
    self._work_log_initialized = True
    logger.info(f"WorkLogManager initialized for agent {self.name}")

async def _record_action_to_work_log(
    self,
    tool_name: str,
    args: Optional[Dict[str, Any]],
    action_output: ActionOutput,
    tags: Optional[List[str]] = None,
):
    """记录动作到 WorkLog"""
    if not self.enable_work_log or not self._work_log_manager or not self._work_log_initialized:
        return
    
    await self._work_log_manager.record_action(
        tool_name=tool_name,
        args=args,
        action_output=action_output,
        tags=tags or [],
    )

async def get_work_log_stats(self) -> Dict[str, Any]:
    """获取 WorkLog 统计"""
    if self.enable_work_log:
        await self._ensure_work_log_manager()
        if self._work_log_manager:
            return await self._work_log_manager.get_stats()
    return {}

async def get_work_log_context(self, max_entries: int = 50) -> str:
    """获取 WorkLog 上下文"""
    if self.enable_work_log:
        await self._ensure_work_log_manager()
        if self._work_log_manager:
            return await self._work_log_manager.get_context_for_prompt(max_entries=max_entries)
    return ""
```

### 2. PhaseManager 相关方法

```python
def get_current_phase(self) -> Optional[str]:
    """获取当前阶段"""
    if self.enable_phase_management and self._phase_manager:
        return self._phase_manager.current_phase.value
    return None

def set_phase(self, phase: str, reason: str = ""):
    """手动设置阶段"""
    if self.enable_phase_management and self._phase_manager:
        phase_enum = TaskPhase(phase.lower())
        self._phase_manager.set_phase(phase_enum, reason)
    else:
        logger.warning("PhaseManager is not enabled")

def record_phase_action(self, tool_name: str, success: bool):
    """记录阶段动作（记录后自动调用）"""
    if self.enable_phase_management and self._phase_manager:
        self._phase_manager.record_action(tool_name, success)
```

### 3. ReportGenerator 相关方法

```python
async def _ensure_report_generator(self):
    """确保报告生成器已初始化"""
    if not self.enable_auto_report:
        return
    
    if self._report_generator is not None:
        return
    
    await self._ensure_work_log_manager()
    
    if not self._work_log_manager or not self._work_log_initialized:
        logger.warning("WorkLog must be initialized for report generation")
        return
    
    self._report_generator = ReportGenerator(
        work_log_manager=self._work_log_manager,
        agent_id=self.name,
        task_id=self.not_null_agent_context.conv_id if self.not_null_agent_context else "unknown",
    )
    
    logger.info("ReportGenerator initialized")

async def generate_report(
    self,
    report_type: str = "detailed",
    report_format: str = "markdown",
    save_to_file: bool = False,
) -> str:
    """
    手动生成报告
    
    Args:
        report_type: 报告类型
        report_format: 报告格式
        save_to_file: 是否保存到文件系统
    
    Returns:
        报告内容字符串
    """
    await self._ensure_report_generator()
    
    if not self._report_generator:
        raise Exception("ReportGenerator is not enabled or not initialized")
    
    try:
        report_type_enum = ReportType(report_type.lower())
    except ValueError:
        report_type_enum = ReportType.DETAILED
    
    try:
        report_format_enum = ReportFormat(report_format.lower())
    except ValueError:
        report_format_enum = ReportFormat.MARKDOWN
    
    report = await self._report_generator.generate_report(
        report_type=report_type_enum,
        report_format=report_format_enum,
    )
    
    # 转换为字符串
    if report_format_enum == ReportFormat.MARKDOWN:
        report_content = report.to_markdown()
    elif report_format_enum == ReportFormat.HTML:
        report_content = report.to_html()
    elif report_format_enum == ReportFormat.JSON:
        report_content = report.to_json()
    else:
        report_content = report.to_plain_text()
    
    # 保存到文件（如果需要）
    if save_to_file:
        await self._save_report_to_file(report_content, report_format_enum)
    
    return report_content

async def _save_report_to_file(self, content: str, report_format: ReportFormat):
    """保存报告到文件"""
    import time
    timestamp = int(time.time())
    extension = "md" if report_format == ReportFormat.MARKDOWN else "json" if report_format == ReportFormat.JSON else "html"
    report_key = f"{self.name}_report_{timestamp}"
    
    afs = await self._ensure_agent_file_system()
    if afs:
        await afs.save_file(
            file_key=report_key,
            data=content,
            file_type="report",
            extension=extension,
        )
        logger.info(f"Report saved to {report_key}")
```

### 4. 辅助方法

```python
def _is_terminate_action(self, reply_message: AgentMessage) -> bool:
    """判断是否为 terminate action"""
    if not reply_message or not reply_message.content:
        return False
    content_lower = reply_message.content.lower()
    return any(
        word in content_lower
        for word in ["terminate", "finish", "complete", "end", "done", "stop"]
    )
```

---

## 🔧 关键集成点

### 1. 在 `_load_thinking_messages` 中注入 WorkLog 和阶段上下文

找到 `_load_thinking_messages` 方法，在返回之前添加：

```python
# 获取基础消息
(messages, context, system_prompt, user_prompt) = await super()._load_thinking_messages(...)  # 假设这行已经存在

if not messages:
    return messages, context, system_prompt, user_prompt

# ========== 注入 WorkLog 上下文 ==========
if self.enable_work_log and self._work_log_manager and self._work_log_initialized:
    work_log_context = await self._work_log_manager.get_context_for_prompt(
        max_entries=50,
        include_summaries=True,
    )
    
    if context is None:
        context = {}
    context["work_log"] = work_log_context
    
    # 注入到 user_prompt
    if user_prompt:
        user_prompt = user_prompt.replace("{work_log}", work_log_context)
        
        stats = await self._work_log_manager.get_stats()
        if stats.get('compressed_summaries', 0) > 0:
            notification = f"""
[W Work Log Compressed]

Previous work history has been summarized to preserve context.
- Compressed entries: {stats.get('active_entries', 0)}

Refer to the summary for context about earlier operations.
"""
            user_prompt = user_prompt.replace(re.compile(r"", re.IGNORECASE), notification)

# ========== 注入阶段上下文 ==========
if self.enable_phase_management and self._phase_manager:
    phase_prompt = self._phase_manager.get_phase_prompt()
    
    if phase_prompt:
        msg = AgentMessage(
            role="system",
            content=phase_prompt,
        )
        # 在系统消息之后插入
        if len(messages) > 1:
            messages.insert(1, msg)
        else:
            messages.append(msg)

return messages, context, system_prompt, user_prompt
```

### 2. 在 `act` 或 `generate_reply` 方法中记录操作

找到 Agent 执行工具的地方，在 action 执行后添加调用：

```python
# 在工具执行成功后
tool_name = action_output.action or "unknown"
tool_args = {}  # 从上下文获取

# 记录到 WorkLog
await self._record_action_to_work_log(tool_name, tool_args, action_output)

# 记录到 PhaseManager
self.record_phase_action(tool_name, action_output.is_exe_success)
```

### 3. 在任务结束时生成报告

在 terminate action 或任务完成后：

```python
if self._is_terminate_action(reply_message):
    # 自动生成报告（如果配置了）
    if self.report_auto_generate:
        await self.generate_report(
            report_type=self.report_default_type,
            report_format=self.report_default_format,
            save_to_file=True,
        )
    
    # 切换阶段到完成
    self.set_phase("complete", reason="任务完成")
```

---

## 📝 完整的操作步骤

由于需要修改的方法较多，建议的添加顺序：

1. **在 `_ask_user_permission` 方法后（约第232行后）添加**：
   - `_ensure_work_log_manager()`
   - `_record_action_to_work_log()`
   - `_is_terminate_action()`

2. **在文件末尾（约第870行前）添加公开方法**：
   - `get_work_log_stats()`
   - `get_work_log_context()`
   - `generate_report()`
   - `get_current_phase()`
   - `set_phase()`
   - `record_phase_action()`
   - `_ensure_report_generator()`
   - `_save_report_to_file()`

3. **找到并修改 `_load_thinking_messages` 方法**：
   - 在返回之前添加 WorkLog 和阶段上下文注入代码

4. **找到 `act` 或工具执行的方法，添加记录调用**

---

## ✅ 验证步骤

添加完成后，按以下步骤验证：

### 1. 验证配置
```python
agent = ReActMasterAgent(
    enable_work_log=True,
    enable_phase_management=True,
    enable_auto_report=True,
)

# 检查配置
assert agent.enable_work_log == True
assert agent.enable_phase_management == True
assert agent.enable_auto_report == True
```

### 2. 验证初始化
```python
await agent._initialize_components()

# 检查初始化
assert agent._phase_manager is not None  # 如果启用
assert agent._work_log_manager is None  # 这是正常的，延迟初始化
assert agent._report_generator is None  # 这是正常的，延迟初始化
```

### 3. 验证异步初始化
```python
await agent._ensure_work_log_manager()
assert agent._work_log_manager is not None
assert agent._work_log_initialized == True
```

### 4. 验证功能使用
```python
# 记录操作
await agent._record_action_to_work_log("search", {}, action_output)

# 查询阶段
phase = agent.get_current_phase()
print(f"Current phase: {phase}")

# 生成报告
report = await agent.generate_report("detailed", "markdown")
print(report)
```

---

## 🚀 使用示例

### 完整使用

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建 Agent
agent = await ReActMasterAgent(
    # 现有配置
    enable_doom_loop_detection=True,
    doom_loop_threshold=3,
    enable_session_compaction=True,
    enable_output_truncation=True,
    enable_history_pruning=True,
    
    # 新功能配置
    enable_work_log=True,
    work_log_compression_ratio=0.7,
    
    enable_phase_management=True,
    phase_auto_detection=True,
    
    enable_auto_report=True,
    report_default_type="detailed",
    
).bind(context).bind(llm_config).bind(agent_memory).bind(tools).build()

# 使用
await agent.act(message, sender)

# 功能：自动
# - WorkLog 自动记录所有操作
# - PhaseManager 自动切换阶段
# - 任务完成时自动生成报告

# 功能：手动查询
stats = await agent.get_work_log_stats()
context = await agent.get_work_log_context(50)
phase = agent.get_current_phase()
report = await agent.generate_report("detailed", "markdown")
```

---

## 📊 集成完成后的功能特性

| 特性 | 在 ReActMasterAgent 中的状态 |
|------|----------------------------|
| Doom Loop 检测 | ✅ 已集成 |
| 上下文压缩 | ✅ 已集成 |
| 工具输出截断 | ✅ 已集成 |
| 历史记录修剪 | ✅ 已集成 |
| **WorkLog** | ✅ **待集成** |
| **PhaseManager** | ✅ **待集成** |
| **ReportGenerator** | ✅ **待集成** |

---

## 📈 下一步

按照上述步骤添加方法后，ReActMasterAgent 将自动包含所有 7 个特性！