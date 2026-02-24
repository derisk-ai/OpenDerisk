"""
ReActMasterAgentV4 - 集成了 WorkLog、PhaseManager 和 ReportGenerator 的完整版本

这个版本继承自 ReActMasterAgent 并添加所有新功能：
- WorkLog 自动记录
- PhaseManager 自动阶段管理
- ReportGenerator 自动报告生成
"""

import logging
from typing import Any, Dict, List, Optional
from derisk._private.pydantic import Field, PrivateAttr
from derisk.agent import ActionOutput, Agent, AgentMessage, ProfileConfig
from derisk.agent.core.base_agent import ConversableAgent
from . import (
    REACT_MASTER_SYSTEM_TEMPLATE,
    REACT_MASTER_USER_TEMPLATE,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE,
    REACT_MASTER_SYSTEM_TEMPLATE_CN,
    REACT_MASTER_USER_TEMPLATE_CN,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE_CN,
)

# 导入现有类
try:
    from .react_master_agent import ReActMasterAgent
    from .work_log import WorkLogManager, create_work_log_manager
    from .phase_manager import PhaseManager, TaskPhase, create_phase_manager
    from .report_generator import ReportGenerator, ReportType, ReportFormat
except ImportError:
    # 兼容性导入
    from react_master_agent import ReActMasterAgent
    from work_log import WorkLogManager, create_work_log_manager
    from phase_manager import PhaseManager, TaskPhase, create_phase_manager
    from report_generator import ReportGenerator, ReportType, ReportFormat

logger = logging.getLogger(__name__)


class ReActMasterAgentV4(ReActMasterAgent):
    """
    ReActMasterAgentV4 - 完整集成了所有新功能的 ReAct Agent

    继承自 ReActMasterAgent，添加以下新功能：
    1. WorkLog 自动记录所有工具调用
    2. PhaseManager 自动阶段管理
    3. ReportGenerator 自动/手动报告生成

    使用方式与 ReActMasterAgent 完全相同，但额外支持：
    - 自动记录工作日志
    - 阶段式上下文管理
    - 自动生成任务报告

    公开 API：
    - get_work_log_stats() - 获取 WorkLog 统计
    - get_work_log_context() - 获取 WorkLog 上下文
    - get_current_phase() - 获取当前阶段
    - set_phase() - 设置阶段
    - generate_report() - 生成报告
    """

    profile: ProfileConfig = Field(
        default_factory=lambda: ProfileConfig(
            name="ReActMasterV4",
            role="ReActMasterV4",
            goal="一个遵循最佳实践的 ReAct 代理，通过系统化推理和工具使用高效解决复杂任务。",
            system_prompt_template=REACT_MASTER_SYSTEM_TEMPLATE_CN,
            user_prompt_template=REACT_MASTER_USER_TEMPLATE_CN,
            write_memory_template=REACT_MASTER_WRITE_MEMORY_TEMPLATE_CN,
        )
    )

    # 新功能配置（可选覆盖父类配置）
    enable_work_log: bool = True
    enable_phase_management: bool = True
    enable_auto_report: bool = False  # 默认不自动生成，避免过度资源消耗

    # WorkLog 配置
    work_log_context_window: int = 128000
    work_log_compression_ratio: float = 0.7

    # Phase 配置
    phase_auto_detection: bool = True
    phase_enable_prompts: bool = False  # 默认不注入阶段提示到 prompt

    # Report 配置
    report_default_type: str = "detailed"
    report_default_format: str = "markdown"
    report_auto_generate: bool = (
        False  # Alias for enable_auto_report for parent compatibility
    )

    def __init__(self, **kwargs):
        """初始化 ReActMasterAgentV4"""
        # 调用父类初始化
        super().__init__(**kwargs)

        # Sync report_auto_generate with enable_auto_report for parent compatibility
        self.report_auto_generate = self.enable_auto_report

        # 初始化新组件
        self._initialize_components_v4()

        logger.info(
            f"✅ ReActMasterAgentV4 agent '{self.name}' initialized with all new features"
        )

    def _initialize_components_v4(self):
        """初始化 V4 特有的组件"""
        super()._initialize_components()

        # 1. WorkLog 管理器（延迟初始化）
        if self.enable_work_log:
            self._work_log_manager_v4 = None
            self._work_log_initialized_v4 = False
        else:
            self._work_log_manager_v4 = None
            self._work_log_initialized_v4 = False

        # 2. PhaseManager
        if self.enable_phase_management:
            self._phase_manager_v4 = PhaseManager(
                auto_phase_detection=self.phase_auto_detection,
                enable_phase_prompts=self.phase_enable_prompts,
            )
            logger.info(f"✅ PhaseManager (auto_detection={self.phase_auto_detection})")
        else:
            self._phase_manager_v4 = None

        # 3. ReportGenerator（延迟初始化）
        if self.enable_auto_report:
            self._report_generator_v4 = None
        else:
            self._report_generator_v4 = None

    async def _ensure_work_log_v4(self):
        """确保 WorkLog 管理器已初始化（异步）"""
        if not self.enable_work_log:
            return

        if self._work_log_manager_v4 and self._work_log_initialized_v4:
            return

        # 准备参数
        conv_id = "default"
        session_id = "default"

        if self.not_null_agent_context:
            conv_id = self.not_null_agent_context.conv_id or "default"
            session_id = self.not_null_agent_context.conv_session_id or conv_id

        # 获取 AgentFileSystem
        afs = await self._ensure_agent_file_system()

        # 创建 WorkLog 管理器
        from derisk.agent.expand.react_master_agent.work_log import (
            create_work_log_manager,
        )

        self._work_log_manager_v4 = await create_work_log_manager(
            agent_id=self.name,
            session_id=session_id,
            agent_file_system=afs,
            context_window_tokens=self.work_log_context_window,
            compression_threshold_ratio=self.work_log_compression_ratio,
        )

        self._work_log_initialized_v4 = True
        logger.info(f"✅ WorkLogManager initialized")

    async def _record_action_to_work_log(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]],
        action_output: ActionOutput,
    ):
        """记录操作到 WorkLog"""
        if (
            not self.enable_work_log
            or not self._work_log_manager_v4
            or not self._work_log_initialized_v4
        ):
            return

        # 提取标签
        tags = []
        if not action_output.is_exe_success:
            tags.append("error")
        if action_output.content and len(action_output.content) > 10000:
            tags.append("large_output")

        # 记录到 WorkLog
        await self._work_log_manager_v4.record_action(
            tool_name=tool_name,
            args=args if args is not None else {},
            action_output=action_output,
            tags=tags,
        )

        logger.debug(f"✅ Recorded {tool_name} to WorkLog")

    def _is_terminate_action(self, action_output: ActionOutput) -> bool:
        """判断是否为 terminate action"""
        if not action_output:
            return False
        if not action_output.content:
            return False

        content_lower = action_output.content.lower()
        return any(
            keyword in content_lower
            for keyword in [
                "terminate",
                "finish",
                "complete",
                "end",
                "done",
                "stop",
                "final",
            ]
        )

    # ====================== 公开 API 方法 ======================

    async def get_work_log_stats(self) -> Dict[str, Any]:
        """获取 WorkLog 统计信息"""
        if self.enable_work_log:
            await self._ensure_work_log_v4()
            if self._work_log_manager_v4 and self._work_log_initialized_v4:
                return await self._work_log_manager_v4.get_stats()
        return {}

    async def get_work_log_context(self, max_entries: int = 50) -> str:
        """获取 WorkLog 上下文（用于 prompt）"""
        if self.enable_work_log:
            await self._ensure_work_log_v4()
            if self._work_log_manager_v4 and self._work_log_initialized_v4:
                return await self._work_log_manager_v4.get_context_for_prompt(
                    max_entries=max_entries
                )
        return ""

    def get_current_phase(self) -> Optional[str]:
        """获取当前阶段"""
        if self.enable_phase_management and self._phase_manager_v4:
            return self._phase_manager_v4.current_phase.value
        return None

    def set_phase(self, phase: str, reason: str = ""):
        """手动设置阶段"""
        if self.enable_phase_management and self._phase_manager_v4:
            phase_enum = TaskPhase(phase.lower())
            self._phase_manager_v4.set_phase(phase_enum, reason)
            logger.info(f"Phase set to {phase}: {reason}")
        else:
            logger.warning("PhaseManager is not enabled")

    def record_phase_action(self, tool_name: str, success: bool):
        """记录到阶段管理器（在工具执行后调用）"""
        if self.enable_phase_management and self._phase_manager_v4:
            self._phase_manager_v4.record_action(tool_name, success)

    async def generate_report(
        self,
        report_type: str = "detailed",
        report_format: str = "markdown",
        save_to_file: bool = False,
    ) -> str:
        """
        生成任务报告

        Args:
            report_type: 报告类型（summary/detailed/technical/executive/progress/final）
            report_format: 报告格式（markdown/html/json/plain）
            save_to_file: 是否保存到文件系统

        Returns:
            报告内容字符串
        """
        if not self.enable_auto_report:
            raise ValueError(
                "ReportGenerator is not enabled. Set enable_auto_report=True"
            )

        await self._ensure_work_log_v4()

        if not self._work_log_manager_v4 or not self._work_log_initialized:
            raise ValueError("WorkLog must be initialized for report generation")

        # 初始化报告生成器
        from derisk.agent.expand.react_master_agent.report_generator import (
            ReportGenerator,
        )

        self._report_generator_v4 = ReportGenerator(
            work_log_manager=self._work_log_manager_v4,
            agent_id=self.name,
            task_id=self.not_null_agent_context.conv_id
            if self.not_null_agent_context
            else "unknown",
            llm_client=None,  # 不使用 AI 增强
        )

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
        report = await self._report_generator_v4.generate_report(
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
        if save_to_file:
            await self._save_report_to_file_v4(content, report_format_enum)

        logger.info(f"✅ Report generated: {report_type}/{report_format}")
        return content

    async def _save_report_to_file_v4(
        self,
        content: str,
        report_format: ReportFormat,
    ):
        """保存报告到文件系统"""
        if not self._agent_file_system:
            logger.warning("AgentFileSystem not available, cannot save report to file")
            return

        import time

        timestamp = int(time.time())

        extension = {
            ReportFormat.MARKDOWN: "md",
            ReportFormat.HTML: "html",
            ReportFormat.JSON: "json",
        }.get(report_format, "md")

        report_key = f"{self.name}_report_{timestamp}"

        await self._agent_file_system.save_file(
            file_key=report_key,
            data=content,
            file_type="report",
            extension=extension,
        )

        logger.info(f"📄 Report saved: {report_key}")

    # ====================== 重写关键方法 ======================

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
        重写 generate_reply，集成新功能

        流程：
        1. 调用父类 generate_reply
        2. 记录工具调用到 WorkLog
        3. 记录到 PhaseManager
        4. 判断是否需要自动生成报告
        """

        # ========== 1. 确保 WorkLog 已初始化 ==========
        await self._ensure_work_log_v4()

        # 初始阶段设置（如果是第一条消息）
        if self.enable_phase_management and self._phase_manager_v4:
            messages = await self.memory.gpts_memory.get_messages(
                self.not_null_agent_context.conv_id
            )
            if len(messages) <= 2:  # 系统消息 + 第一条消息
                self.set_phase("exploration", "任务开始")

        # ========== 2. 调用父类的 generate_reply（.action\V 在其中处理） ==========
        # 注意：ReActMasterAgent 可能没有 generate_reply，或者使用 act 方法
        # 我们应该在 act 方法中拦截 action 结果，而不是这里
        # 所以这个方法暂时只负责初始化和阶段设置

        # 实际的 action 记录将在需要通过重写 act 方法或通过 hook 机制实现
        # 这里我们简化处理，只完成初始化

        # 由于父类可能使用其他机制，我们通过检查是否有 generate_reply 再决定是否重写
        try:
            # 尝试调用父类的 generate_reply
            reply = await super().generate_reply(
                received_message=received_message,
                sender=sender,
                reviewer=reviewer,
                rely_messages=rely_messages,
                historical_dialogues=historical_dialogues,
                is_retry_chat=is_retry_chat,
                last_speaker_name=last_speaker_name,
                **kwargs,
            )
            return reply
        except AttributeError:
            # 如果父类没有 generate_reply，直接调用基类
            logger.debug(
                "Parent class doesn't have generate_reply, falling back to base"
            )
            return await super(ConversableAgent, self).generate_reply(
                received_message=received_message,
                sender=sender,
                reviewer=reviewer,
                rely_messages=rely_messages,
                historical_dialogues=historical_dialogues,
                is_retry_chat=is_retry_chat,
                last_speaker_name=last_speaker_name,
                **kwargs,
            )

    async def act(
        self,
        message: AgentMessage,
        sender,
        reviewer: Optional[Agent] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> List[ActionOutput]:
        """
        重写 act 方法，集成 WorkLog 和 Phase 记录

        这是最关键的重写点，在这里我们可以拦截所有 action 执行结果
        """
        # 统一组件初始化
        await self._ensure_work_log_v4()

        # 初始阶段设置
        if self.enable_phase_management and self._phase_manager_v4:
            if self.not_null_agent_context:
                messages = await self.memory.gpts_memory.get_messages(
                    self.not_null_agent_context.conv_id
                )
                if len(messages) <= 3:  # 系统消息 + 前几条消息
                    self.set_phase("exploration", "任务开始")

        # 调用父类的 act 方法
        act_outs = await super().act(
            message=message,
            sender=sender,
            reviewer=reviewer,
            is_retry_chat=is_retry_chat,
            last_speaker_name=last_speaker_name,
            received_message=received_message,
            **kwargs,
        )

        # 处理每个 action 输出，记录到 WorkLog 和 Phase
        for act_out in act_outs:
            if act_out:
                tool_name = act_out.action or "unknown"

                # 记录到 WorkLog
                tool_args = {}
                # 尝试从 kwargs 中提取参数（如果有）
                if "params" in kwargs and isinstance(kwargs["params"], dict):
                    tool_args = kwargs["params"]

                await self._record_action_to_work_log(tool_name, tool_args, act_out)

                # 记录到 PhaseManager
                self.record_phase_action(tool_name, act_out.is_exe_success)

                # 如果是 terminate action 且启用了自动报告
                if self._is_terminate_action(act_out) and self.enable_auto_report:
                    self.set_phase("reporting", "任务完成，生成报告")

                    try:
                        report_content = await self.generate_report(
                            report_type=self.report_default_type,
                            report_format=self.report_default_format,
                            save_to_file=True,
                        )
                        logger.info("✅ Auto-generated report saved")
                    except Exception as e:
                        logger.warning(f"Failed to auto-generate report: {e}")

                    # 切换到完成阶段
                    self.set_phase("complete", "任务全部完成")

        return act_outs


# 导出
__all__ = ["ReActMasterAgentV4"]
