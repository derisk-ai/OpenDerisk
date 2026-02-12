# ReActMasterAgent 集成指南

本文档说明如何将 WorkLog、PhaseManager 和 ReportGenerator 集成到现有的 ReActMasterAgent 中。

---

## 1. 修改导入说明

由于已经在 `react_master_agent/__init__.py` 中导出了这三个模块，所以在 ReActMasterAgent 中添加以下导入：

```python
# 新增模块导入
from .work_log import WorkLogManager, create_work_log_manager
from .phase_manager import PhaseManager, TaskPhase, create_phase_manager
from .report_generator import ReportGenerator, ReportType, ReportFormat
```

---

## 2. 在 ReActMasterAgent 中添加配置参数

在 ReActMasterAgent 类定义中添加新参数：

```python
class ReActMasterAgent(ConversableAgent):
    # 现有配置...
    enable_doom_loop_detection: bool = True
    enable_session_compaction: bool = True
    enable_output_truncation: bool = True
    enable_history_pruning: bool = True
    
    # 新增配置 -> WorkLog, Phase, ReportGenerator 集成配置
    enable_work_log: bool = True
    enable_phase_management: bool = True
    enable_auto_report: bool = True
    
    # WorkLog 配置
    work_log_context_window: int = 128000
    work_log_compression_ratio: float = 0.7
    
    # Phase 配置
    phase_auto_detection: bool = True
    phase_enable_prompts: bool = True
    
    # Report 配置
    report_auto_generate: bool = False  # 默认不自动生成，可在任务结束时手动调用
    report_default_type: str = "detailed"
    report_default_format: str = "markdown"
```

---

## 3. 修改 _initialize_components 方法

在 `_initialize_components` 方法末尾添加新组件初始化：

```python
def _initialize_components(self):
    """初始化核心组件"""
    # 现有组件初始化代码...
    
    # 5. 初始化 WorkLog 管理器
    if self.enable_work_log:
        self._work_log_manager = None
        self._work_log_initialized = False
        logger.info("WorkLog enabled (will initialize on demand)")
    
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
        self._report_generator = None  # 将在需要时初始化
        logger.info("ReportGenerator enabled (will initialize on demand)")
    else:
        self._report_generator = None
```

---

## 4. 重写 generate_reply 方法

在 ReActMasterAgent 类中添加以下方法：

```python
async def generate_reply(
    self,
    received_message: AgentMessage,
    sender: Agent,
    reviewer: Optional[Agent] = None,
    rely_messages: Optional[List[AgentMessage]] = None,
    historical_dialogues: Optional[List[AgentMessage]] = None,
    is_retry_chat: bool = False,
    last_speaker_name: Optional[str] = None,
    **kwargs,
) -> AgentMessage:
    """
    重写 generate_reply 集成新功能
    
    流程：
    1. 确保 WorkLog 已初始化
    2. 更新阶段状态
    3. 调用父类的 generate_reply
    4. 记录工具调用到 WorkLog
    5. 更新阶段状态
    """
    
    # ========== 1. 初始化新功能组件 ==========
    await self._ensure_work_log_manager()
    
    # ========== 2. 更新阶段状态（如果有）==========
    if self._phase_manager:
        # 可以根据消息内容推测初始阶段
        if received_message.current_goal and len(self.memory.gpts_memory.messages(self.not_null_agent_context.conv_id)) <= 2:
            # 第一条消息，设置为探索阶段
            self._phase_manager.set_phase(TaskPhase.EXPLORATION, reason="任务开始")
    
    # ========== 3. 调用父类的 generate_reply ==========
    reply_message = await super().generate_reply(
        received_message=received_message,
        sender=sender,
        reviewer=reviewer,
        rely_messages=rely_messages,
        historical_dialogues=historical_dialogues,
        is_retry_chat=is_retry_chat,
        last_speaker_name=last_speaker_name,
        **kwargs,
    )
    
    # ========== 4. 记录操作到 WorkLog ==========
    if self._work_log_manager and reply_message:
        # 记录本次消息到 WorkLog
        await self._record_message_to_work_log(reply_message, received_message)
    
    # ========== 5. 更新阶段状态（根据操作结果）==========
    if self._phase_manager:
        # 如果是 terminate action，切换到报告阶段
        if self._is_terminate_action(reply_message):
            await self._generate_and_save_report()
            self._phase_manager.set_phase(TaskPhase.COMPLETE, reason="任务完成")
    
    return reply_message

# ========== 辅助方法 ==========

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

async def _record_message_to_work_log(
    self,
    reply_message: AgentMessage,
    received_message: AgentMessage,
):
    """记录消息到 WorkLog"""
    if not self._work_log_manager or not self._work_log_initialized:
        return
    
    # 提取工具调用信息
    # 这里需要从 reply_message 或 context 中提取实际执行的 action
    # 简化实现：记录消息本身
    await self._work_log_manager.record_action(
        tool_name="agent_reply",
        args={
            "reply_content": reply_message.content[:200] if reply_message.content else "",
            "received_content": received_message.content[:200] if received_message.content else "",
        },
        action_output=ActionOutput(
            action_id=reply_message.message_id,
            name="agent_reply",
            is_exe_success=True,
            content=reply_message.content or "",
        ),
        tags=["agent_reply"],
    )

def _is_terminate_action(self, reply_message: AgentMessage) -> bool:
    """判断是否为 terminate action"""
    if not reply_message or not reply_message.content:
        return False
    return any(
        word in reply_message.content.lower()
        for word in ["terminate", "finish", "complete", "end", "done"]
    )

async def _ensure_report_generator(self):
    """确保报告生成器已初始化"""
    if self._report_generator is not None:
        return
    
    if not self.enable_auto_report:
        return
    
    await self._ensure_work_log_manager()
    
    self._report_generator = ReportGenerator(
        work_log_manager=self._work_log_manager,
        agent_id=self.name,
        task_id=self.not_null_agent_context.conv_id if self.not_null_agent_context else "unknown",
    )
    
    logger.info("ReportGenerator initialized")

async def _generate_and_save_report(self):
    """生成并保存报告"""
    if not self.enable_auto_report or not self._work_log_manager:
        return
    
    await self._ensure_report_generator()
    
    if not self._report_generator:
        return
    
    # 生成报告
    report_type = ReportType.DETAILED
    report_format = ReportFormat.MARKDOWN
    
    report = await self._report_generator.generate_report(
        report_type=report_type,
        report_format=report_format,
    )
    
    # 转换为字符串
    if report_format == ReportFormat.MARKDOWN:
        report_content = report.to_markdown()
    elif report_format == ReportFormat.HTML:
        report_content = report.to_html()
    elif report_format == ReportFormat.JSON:
        report_content = report.to_json()
    else:
        report_content = report.to_plain_text()
    
    # 保存报告（通过 AgentFileSystem）
    if self._agent_file_system:
        import time
        timestamp = int(time.time())
        report_key = f"{self.name}_report_{timestamp}"
        
        await self._agent_file_system.save_file(
            file_key=report_key,
            data=report_content,
            file_type="report",
            extension="md",
        )
        
        logger.info(f"Report saved to {report_key}")
    
    return report_content

# ========== 可供外部调用的方法 ==========

async def get_work_log_stats(self) -> Dict:
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

async def generate_report(
    self,
    report_type: str = "detailed",
    report_format: str = "markdown",
) -> str:
    """手动生成报告"""
    await self._ensure_report_generator()
    if not self._report_generator:
        raise Exception("ReportGenerator not enabled")
    
    report_type_enum = ReportType(report_type.lower())
    report_format_enum = ReportFormat(report_format.lower())
    
    report = await self._report_generator.generate_report(
        report_type=report_type_enum,
        report_format=report_format_enum,
    )
    
    if report_format_enum == ReportFormat.MARKDOWN:
        return report.to_markdown()
    elif report_format_enum == ReportFormat.HTML:
        return report.to_html()
    elif report_format_enum == ReportFormat.JSON:
        return report.to_json()
    else:
        return report.to_plain_text()

def get_current_phase(self) -> Optional[str]:
    """获取当前阶段"""
    if self._phase_manager:
        return self._phase_manager.current_phase.value
    return None

def set_phase(self, phase: str, reason: str = ""):
    """手动设置阶段"""
    if self._phase_manager:
        phase_enum = TaskPhase(phase.lower())
        self._phase_manager.set_phase(phase_enum, reason)
```

---

## 5. 更新 _load_thinking_messages 方法

重写或扩展 `_load_thinking_messages` 方法以注入 WorkLog 和阶段上下文：

```python
async def _load_thinking_messages(
    self,
    received_message: AgentMessage,
    sender: Agent,
    rely_messages: Optional[List[AgentMessage]] = None,
    **kwargs,
) -> Tuple[List[AgentMessage], Optional[Dict], Optional[str], Optional[str]]:
    """
    加载思考消息，集成新功能上下文
    """
    
    # 调用父类方法获取基础消息
    (
        messages,
        context,
        system_prompt,
        user_prompt,
    ) = await super()._load_thinking_messages(
        received_message, sender, rely_messages, **kwargs
    )
    
    if not messages:
        return messages, context, system_prompt, user_prompt
    
    # ========== 注入 WorkLog 上下文 ==========
    if self.enable_work_log and self._work_log_manager:
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
            
            # 添加压缩通知
            stats = await self._work_log_manager.get_stats()
            if stats.get('compressed_summaries', 0) > 0:
                notification = """
\n[Work Log Compressed]

Previous work history has been summarized to preserve context.
- Compressed entries: {compressed_count}

Refer to the summary for context about earlier operations.
""".format(compressed_count=stats.get('active_entries', 0))
                user_prompt = user_prompt.replace("", notification)
    
    # ========== 注入阶段上下文 ==========
    if self.enable_phase_management and self._phase_manager:
        phase_prompt = self._phase_manager.get_phase_prompt()
        
        # 添加到 messages
        if phase_prompt:
            # 可以插入到 messages 列表的开头
            msg = AgentMessage(
                role="system",
                content=phase_prompt,
            )
            messages.insert(1, msg)  # 在系统消息之后插入
    
    return messages, context, system_prompt, user_prompt
```

---

## 6. 在 action 执行后记录到 WorkLog

在现有工具调用执行逻辑中添加 WorkLog 记录。通常工具执行会在 `ReActAction.run()` 中进行处理。

为了集成到现有代码中，可以考虑以下方式：

### 方式A：在 ReActAction 子类中集成

为每个 Action 类添加 WorkLog 记录：

```python
class ReActActionEnhanced(ReActAction):
    """增强的 ReActAction，支持 WorkLog"""
    
    async def run(self, **kwargs) -> ActionOutput:
        result = await super().run(**kwargs)
        
        # 记录到 WorkLog
        agent = kwargs.get("agent")
        if agent and hasattr(agent, "_work_log_manager"):
            args = kwargs.get("params", {})
            await agent._work_log_manager.record_action(
                tool_name=result.action or self.name,
                args=args if isinstance(args, dict) else {},
                action_output=result,
            )
        
        return result
```

### 方式B：在 ReActMasterAgent 的 _a_init_reply_message 中添加（简化实现）

修改已有的 `_a_init_reply_message` 方法，使其包含 WorkLog 和阶段记录。

---

## 7. 使用示例

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建 Agent（自动启用所有新功能）
agent = await ReActMasterAgent(
    # 现有配置
    enable_doom_loop_detection=True,
    enable_session_compaction=True,
    enable_output_truncation=True,
    enable_history_pruning=True,
    
    # 新功能配置
    enable_work_log=True,
    enable_phase_management=True,
    enable_auto_report=True,
    
).bind(context).bind(llm_config).bind(agent_memory).bind(tools).build()

# 自动集成：
# 1. WorkLog 会自动记录所有操作
# 2. PhaseManager 会自动切换阶段
# 3. 当 task 完成时自动生成报告

# 手动查询
stats = await agent.get_work_log_stats()
context = await agent.get_work_log_context(50)
phase = agent.get_current_phase()

# 手动生成报告
report = await agent.generate_report("detailed", "markdown")
```

---

## 8. 注意事项

1. **顺序依赖**：`_ensure_work_log_manager` 和 `_ensure_report_generator` 是异步的，需要使用 `await`
2. **避免重复初始化**：使用标识位 `_work_log_initialized` 避免重复初始化
3. **错误处理**：新功能都应该支持禁用（通过 `_enable_xxx` 配置）
4. **性能影响**：WorkLog 记录和阶段计算应该轻量级，不要阻塞主流程
5. **向后兼容**：所有新功能都应该可通过配置禁用，保持与原有实现的兼容

---

## 9. 版本更新

更新版本号：

```python
# 在 __init__.py 中更新
__version__ = "2.1.0"
```

在 `FEATURES.md` 中补充新功能的说明。

---