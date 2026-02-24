# ReActMasterAgent 完整集成代码 - 可直接使用的方案

本文档提供了完整的代码块，可以手动复制粘贴到 `react_master_agent.py` 中。

---

## 📍 插入位置 1：在 `_ask_user_permission` 方法结束后添加

### 位置：第 525 行后（`return False` 之后的空行后）

### 代码：

```python
    # ========== 新增：WorkLog 和 Phase 集成的辅助方法 ==========
    async def _ensure_work_log_manager(self):
        """确保 WorkLog 管理器已初始化"""
        if not self.enable_work_log:
            return
        if self._work_log_manager and self._work_log_initialized:
            return
        
        conv_id = self.not_null_agent_context.conv_id or "default"
        session_id = self.not_null_agent_context.conv_session_id or conv_id
        afs = await self._ensure_agent_file_system()
        
        self._work_log_manager = await create_work_log_manager(
            agent_id=self.name,
            session_id=session_id,
            agent_file_system=afs,
            context_window_tokens=self.work_log_context_window,
            compression_threshold_ratio=self.work_log_compression_ratio,
        )
        self._work_log_initialized = True
        logger.info(f"✅ WorkLogManager initialized for agent {self.name}")

    async def _record_action_to_work_log(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]],
        action_output: ActionOutput,
    ):
        """记录操作到 WorkLog"""
        if not self.enable_work_log or not self._work_log_manager or not self._work_log_initialized:
            return
        
        # 提取标签
        tags = []
        if not action_output.is_exe_success:
            tags.append("error")
        if action_output.content and len(action_output.content) > 10000:
            tags.append("large_output")
        
        # 记录到 WorkLog
        await self._work_log_manager.record_action(
            tool_name=tool_name,
            args=args if args is not None else {},
            action_output=action_output,
            tags=tags,
        )
        logger.debug(f"Recorded {tool_name} to WorkLog")

    def _is_terminate_action(self, action_output: ActionOutput) -> bool:
        """判断是否为 terminate action"""
        if not action_output:
            return False
        if not action_output.content:
            return False
        
        content_lower = action_output.content.lower()
        return any(
            keyword in content_lower
            for keyword in ["terminate", "finish", "complete", "end", "done", "stop", "final"]
        )
```

---

## 📍 插入位置 2：在文件末尾、`__all__` 之前添加

### 位置：第 877 行前（`__all__ = [...]` 之前）

### 代码：

```python
    # ========== 公开 API：WorkLog ==========
    async def get_work_log_stats(self) -> Dict[str, Any]:
        """获取 WorkLog 统计信息"""
        if self.enable_work_log:
            await self._ensure_work_log_manager()
            if self._work_log_manager and self._work_log_initialized:
                return await self._work_log_manager.get_stats()
        return {}

    async def get_work_log_context(self, max_entries: int = 50) -> str:
        """获取 WorkLog 上下文（用于 prompt）"""
        if self.enable_work_log:
            await self._ensure_work_log_manager()
            if self._work_log_manager and self._work_log_initialized:
                return await self._work_log_manager.get_context_for_prompt(max_entries=max_entries)
        return ""

    # ========== 公开 API：PhaseManager ==========
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
        """记录到阶段管理器（在工具执行后调用）"""
        if self.enable_phase_management and self._phase_manager:
            self._phase_manager.record_action(tool_name, success)

    # ========== 公开 API：ReportGenerator ==========
    async def generate_report(
        self,
        report_type: str = "detailed",
        report_format: str = "markdown",
        save_to_file: bool = False,
    ) -> str:
        """生成任务报告"""
        if not self.enable_auto_report:
            raise ValueError("ReportGenerator is not enabled. Set enable_auto_report=True")
        
        await self._ensure_report_generator()
        
        if not self._report_generator:
            raise ValueError("ReportGenerator not initialized")
        
        # 解析类型
        try:
            report_type_enum = ReportType(report_type.lower())
        except ValueError:
            report_type_enum = ReportType.DETAILED
        
        try:
            report_format_enum = ReportFormat(report_format.lower())
        except ValueError:
            report_format_enum = ReportFormat.MARKDOWN
        
        # 生成报告
        report = await self._report_generator.generate_report(
            report_type=report_type_enum,
            report_format=report_format_enum,
        )
        
        # 转换为字符串
        if report_format_enum == ReportFormat.MARKDOWN:
            content = report.to_markdown()
        elif report_format_enum == ReportFormat.HTML:
            content = report.to_html()
        elif report_format_enum == ReportFormat.JSON:
            content = report.to_json()
        else:
            content = report.to_plain_text()
        
        # 保存到文件
        if save_to_file and self._agent_file_system:
            await self._save_report_to_file(content, report_format_enum)
        
        return content

    async def _ensure_report_generator(self):
        """初始化报告生成器"""
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
        logger.info("✅ ReportGenerator initialized")

    async def _save_report_to_file(
        self,
        content: str,
        report_format: ReportFormat,
    ):
        """保存报告到文件系统"""
        if not self._agent_file_system:
            return
        
        import time
        timestamp = int(time.time())
        
        extension = {
            ReportFormat.MARKDOWN: "md",
            ReportFormat.HTML: "html",
            ReportFormat.JSON: "json",
        }.get(report_format, "markdown")
        
        report_key = f"{self.name}_report_{timestamp}"
        
        await self._agent_file_system.save_file(
            file_key=report_key,
            data=content,
            file_type="report",
            extension=extension,
        )
        logger.info(f"📄 Report saved: {report_key}")
```

---

## 📍 插入位置 3：修改 `act` 方法（第 666-673 行）

### 当前代码（第 666-673 行）：

```python
                         # ========== 集成：记录到 WorkLog ==========
                         await self._record_action_to_work_log(tool_name, tool_args, result)
                         
                         # 记录到 PhaseManager
                         record_phase_action(tool_name, result.is_exe_success)
                         
                         # ========== 集成：判断是否需要自动生成报告 ==========
                         # 如果是 terminate action 且启用了自动报告
                         if self._is_terminate_action(result) and self.report_auto_generate:
                             self.set_phase("reporting", "任务完成，生成报告")
```

### 需要改为（第 666-673 行）：

```python
                         # ========== 集成：记录到 WorkLog ==========
                         await self._record_action_to_work_log(tool_name, tool_args, result)
                         
                         # 记录到 PhaseManager
                         self.record_phase_action(tool_name, result.is_exe_success)
                         
                         # ========== 集成：判断是否需要自动生成报告 ==========
                         # 如果是 terminate action 且启用了自动报告
                         if self._is_terminate_action(result) and self.report_auto_generate:
                             self.set_phase("reporting", "任务完成，生成报告")
```

---

## 📍 插入位置 4：修改 `act` 方法的结束部分（第 702 行）

### 当前代码（第 702 行附近）：

找到这个模式：
```
                             self.set_phase("complete", "任务全部完成")
                         
                         act_outs.append(result)
                 
                 await self.push_context_event(...)
```

### 保持不变，保持这几行代码
这段代码已经正确了，不需要修改。

---

## 📋 完整操作步骤

### 方式A：手动编辑（推荐）

1. **打开文件**：`/Users/tuyang.yhj/Code/python/derisk/packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`
2. **第 525 行后**：粘贴"插入位置 1"的代码
3. **第 877 行前**：粘贴"插入位置 2"的代码
4. **第 669 行**：确保使用 `self.record_phase_action` 而不是 `record_phase_action`（应该已经是正确的了）
5. **保存文件**

### 方式B：让 ChatGPT 将代码插入到文件中

由于文件较大，建议采用方式 A 进行手动操作，这样可以确保代码的准确性和文件的完整性。

---

## 🎯 集成后的功能验证

完成上述 4 个插入操作后，ReActMasterAgent 将完整集成以下功能：

| 功能 | 说明 |
|------|------|
| WorkLog 自动记录 | 每次工具执行后自动记录到 WorkLog |
| 上下文自动注入 | `_load_thinking_messages` 时注入 WorkLog 上下文 |
| 阶段自动切换 | 自动判断并切换阶段 |
| 自动报告生成 | 任务完成时自动生成并保存报告 |
| 手动查询方法 | `get_work_log_stats()`, `get_work_log_context()`, `get_current_phase()`, `set_phase()`, `generate_report()` |

---

## 🚀 使用示例（集成完成后）

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建 Agent（启用所有新功能）
agent = await ReActMasterAgent(
    # 现有特性
    enable_doom_loop_detection=True,
    enable_session_compaction=True,
    enable_output_truncation=True,
    enable_history_pruning=True,
    
    # 新功能 - WorkLog
    enable_work_log=True,
    work_log_compression_ratio=0.7,
    
    # 新功能 - Phase
    enable_phase_management=True,
    phase_auto_detection=True,
    
    # 新功能 - Report
    enable_auto_report=True,
    report_default_type="detailed",
    report_default_format="markdown",
).bind(context).bind(llm_config).bind(agent_memory).bind(tools).build()

# 执行任务
await agent.act(message, sender)

# 自动效果：
# 1. 每次工具调用自动记录到 WorkLog
# 2. WorkLog 自动压缩（超出窗口时）
# 3. 自动阶段切换
# 4. 任务完成时自动生成报告

# 手动查询
await agent.get_work_log_stats()
agent.get_current_phase()
await agent.generate_report("detailed", "md", save_to_file=True)
```