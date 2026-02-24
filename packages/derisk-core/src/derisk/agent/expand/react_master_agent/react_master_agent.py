"""
ReActMaster Agent - 最佳实践的 ReAct 范式 Agent 实现

核心特性：
1. "末日循环" (Doom Loop) 检测机制
2. 上下文压缩 (SessionCompaction)
3. 工具输出截断 (Truncate.output)
4. 历史记录修剪 (prune)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Callable, Awaitable

from derisk._private.pydantic import Field, PrivateAttr
from derisk.agent import (
    ActionOutput,
    Agent,
    AgentMessage,
    ProfileConfig,
)
from derisk.agent.core.base_agent import ConversableAgent, ContextHelper
from derisk.agent.core.base_parser import SchemaType
from derisk.agent.core.role import AgentRunMode
from derisk.agent.core.schema import Status, DynamicParam, DynamicParamType
from derisk.sandbox.base import SandboxBase
from derisk.util.template_utils import render
from derisk_serve.agent.resource.tool.mcp import MCPToolPack

from ..react_agent.react_parser import ReActOutputParser, ReActOut

# 导入核心组件
from .doom_loop_detector import (
    DoomLoopDetector,
    IntelligentDoomLoopDetector,
    DoomLoopCheckResult,
)
from .session_compaction import SessionCompaction, CompactionResult
from .prune import HistoryPruner
from .truncation import Truncator, TruncationConfig
from .prompt import (
    REACT_MASTER_SYSTEM_TEMPLATE,
    REACT_MASTER_USER_TEMPLATE,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE,
    REACT_MASTER_SYSTEM_TEMPLATE_CN,
    REACT_MASTER_USER_TEMPLATE_CN,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE_CN,
    DOOM_LOOP_WARNING_PROMPT_CN,
    TOOL_TRUNCATION_REMINDER_CN,
    COMPACTION_NOTIFICATION_CN,
    PRUNE_NOTIFICATION_CN,
    REACT_PARSE_ERROR_PROMPT_CN,
)
from ...core.file_system.agent_file_system import AgentFileSystem

# 新增模块导入
from .work_log import WorkLogManager, create_work_log_manager
from .phase_manager import PhaseManager, TaskPhase, create_phase_manager
from .report_generator import ReportGenerator, ReportType, ReportFormat
from ...resource import BaseTool, RetrieverResource, FunctionTool
from ...resource.agent_skills import AgentSkillResource
from ...resource.app import AppResource
from ..actions.agent_action import AgentStart
from ..actions.knowledge_action import KnowledgeSearch
from ..actions.terminate_action import Terminate
from ..actions.tool_action import ToolAction
# 导入 read_file 工具使其注册到 system_tool_dict
from ...core.tools.read_file_tool import read_file  # noqa: F401

logger = logging.getLogger(__name__)


class ReActMasterParser(ReActOutputParser):
    """
    ReActMaster 专用的输出解析器

    在基础 ReAct 解析器之上，增加了对特殊标签和格式的支持。
    """

    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.XML

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def parse(self, llm_out: Any) -> ReActOut:
        """
        解析 LLM 输出，包含增强的错误处理
        """
        try:
            return super().parse(llm_out)
        except Exception as e:
            logger.error(f"Failed to parse ReAct output: {e}")
            # 返回一个包含错误信息的 ReActOut
            return ReActOut(
                thought=f"Error parsing output: {str(e)}",
                scratch_pad="",
                steps=[],
                is_terminal=False,
            )


class ReActMasterAgent(ConversableAgent):
    """
    ReActMaster Agent - 最佳实践的 ReAct 范式 Agent

    这是基于 ReAct (Reasoning + Acting) 范式的智能 Agent 实现，具备以下特性：

    1. **末日循环检测 (Doom Loop Detection)**
       - 监控工具调用模式
       - 检测连续重复调用
       - 请求用户确认防止无限循环

    2. **上下文压缩 (Session Compaction)**
       - 自动检测上下文溢出
       - 使用 LLM 生成对话摘要
       - 保留关键信息，减少 Token 消耗

    3. **工具输出截断 (Tool Output Truncation)**
       - 限制大型输出（默认 2000 行 / 50KB）
       - 保存完整输出到临时文件
       - 提供智能提示指导后续处理

    4. **历史记录修剪 (History Pruning)**
       - 定期清理旧的工具输出
       - 保留关键消息
       - 管理上下文窗口使用
    """

    # 基础配置
    max_retry_count: int = 25
    run_mode: AgentRunMode = AgentRunMode.LOOP

    profile: ProfileConfig = Field(
        default_factory=lambda: ProfileConfig(
            name="ReActMasterV2",
            role="ReActMasterV2",
            goal="一个遵循最佳实践的 ReAct 代理，通过系统化推理和工具使用高效解决复杂任务。",
            system_prompt_template=REACT_MASTER_SYSTEM_TEMPLATE_CN,
            user_prompt_template=REACT_MASTER_USER_TEMPLATE_CN,
            write_memory_template=REACT_MASTER_WRITE_MEMORY_TEMPLATE_CN,
        )
    )

    agent_parser: ReActMasterParser = Field(default_factory=ReActMasterParser)
    function_calling: bool = True

    # 组件配置
    enable_doom_loop_detection: bool = True
    doom_loop_threshold: int = 3
    enable_session_compaction: bool = True
    context_window: int = 128000
    compaction_threshold_ratio: float = 0.8
    enable_output_truncation: bool = True
    enable_history_pruning: bool = True
    prune_protect_tokens: int = 4000

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
    report_auto_generate: bool = False  # 默认不自动生成，可在任务结束时手动调用
    report_default_type: str = "detailed"
    report_default_format: str = "markdown"

    # 动态变量
    dynamic_variables: List[DynamicParam] = [
        DynamicParam(
            key="memory_history",
            name="MEMORY_HISTORY_ARG_SUPPLIER",
            type=DynamicParamType.CUSTOM.value,
        ),
    ]

    # 内部状态
    _ctx: ContextHelper[dict] = PrivateAttr(default_factory=lambda: ContextHelper(dict))
    _doom_loop_detector: Optional[DoomLoopDetector] = PrivateAttr(default=None)
    _session_compaction: Optional[SessionCompaction] = PrivateAttr(default=None)
    _history_pruner: Optional[HistoryPruner] = PrivateAttr(default=None)
    _truncator: Optional[Truncator] = PrivateAttr(default=None)
    _agent_file_system: Optional[AgentFileSystem] = PrivateAttr(default=None)
    _tool_call_count: int = PrivateAttr(default=0)
    _compaction_count: int = PrivateAttr(default=0)
    _prune_count: int = PrivateAttr(default=0)

    available_system_tools: Dict[str, FunctionTool] = Field(
        default_factory=dict, description="available system tools"
    )
    # FunctionCall函数和action的绑定
    enable_function_call: bool = False

    def __init__(self, **kwargs):
        """Initialize ReActMaster Agent."""
        super().__init__(**kwargs)
        self._init_actions([AgentStart, KnowledgeSearch, Terminate, ToolAction])
        self._initialize_components()

    async def preload_resource(self) -> None:
        """Preload resources and inject system tools."""
        await super().preload_resource()
        await self.system_tool_injection()
        await self.sandbox_tool_injection()
        
        # 注入 read_file 工具
        from ...core.system_tool_registry import system_tool_dict
        if "read_file" in system_tool_dict:
            self.available_system_tools["read_file"] = system_tool_dict["read_file"]
            logger.info("read_file 工具已注入")

    def _initialize_components(self):
        """初始化核心组件"""
        # 1. 初始化 Doom Loop 检测器
        if self.enable_doom_loop_detection:
            self._doom_loop_detector = IntelligentDoomLoopDetector(
                threshold=self.doom_loop_threshold,
                permission_callback=self._ask_user_permission,
            )
            logger.info(
                f"DoomLoopDetector initialized with threshold={self.doom_loop_threshold}"
            )

        # 2. 初始化上下文压缩器
        if self.enable_session_compaction:
            self._session_compaction = SessionCompaction(
                context_window=self.context_window,
                threshold_ratio=self.compaction_threshold_ratio,
            )
            logger.info(
                f"SessionCompaction initialized with window={self.context_window}"
            )

        # 3. 初始化历史修剪器
        if self.enable_history_pruning:
            self._history_pruner = HistoryPruner(
                prune_protect=self.prune_protect_tokens,
            )
            logger.info(
                f"HistoryPruner initialized with protect={self.prune_protect_tokens}"
            )

        # 4. 初始化 AgentFileSystem 和输出截断器
        if self.enable_output_truncation:
            # 创建截断器（AgentFileSystem 将在需要时异步初始化）
            self._truncator = Truncator(
                max_lines=self._truncator_max_lines
                if hasattr(self, "_truncator_max_lines")
                else TruncationConfig.DEFAULT_MAX_LINES,
                max_bytes=self._truncator_max_bytes
                if hasattr(self, "_truncator_max_bytes")
                else TruncationConfig.DEFAULT_MAX_BYTES,
            )
            self._agent_file_system = None
            logger.info(
                "Truncator initialized (AgentFileSystem will be initialized on demand)"
            )

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
            logger.info(
                f"PhaseManager initialized (auto_detection={self.phase_auto_detection})"
            )
        else:
            self._phase_manager = None

        # 7. 准备报告生成器（延迟初始化）
        if self.enable_auto_report:
            self._report_generator = None
            logger.info("ReportGenerator enabled (will initialize on demand)")
        else:
            self._report_generator = None

    async def _ask_user_permission(self, message: str, context: Dict = None) -> bool:
        """
        请求用户权限回调

        Args:
            message: 提示消息
            context: 上下文信息

        Returns:
            bool: 是否允许继续
        """
        # 这里可以集成 PermissionNext.ask 或其他权限系统
        # 简化实现：通过输出消息请求用户确认

        if self.memory and self.memory.gpts_memory and self.not_null_agent_context:
            await self.memory.gpts_memory.push_message(
                conv_id=self.not_null_agent_context.conv_id,
                stream_msg={
                    "type": "permission_request",
                    "message": message,
                    "context": context or {},
                },
            )

        # 默认返回 False（阻止），实际应用中应该等待用户输入
        logger.warning(
            f"Permission requested but auto-denied (no actual permission system): {message[:100]}..."
        )
        return False

    async def _ensure_agent_file_system(self) -> Optional[Any]:
        """
        确保AgentFileSystem已初始化（懒加载）

        Returns:
            AgentFileSystem实例或None
        """
        if self._agent_file_system is not None:
            return self._agent_file_system

        if not self.not_null_agent_context:
            return None

        try:
            conv_id = self.not_null_agent_context.conv_id or "default"
            session_id = self.not_null_agent_context.conv_session_id or conv_id

            # 尝试获取 FileStorageClient
            file_storage_client = None
            try:
                from derisk.core.interface.file import FileStorageClient
                from derisk._private.config import Config

                CFG = Config()
                system_app = CFG.SYSTEM_APP
                if system_app:
                    file_storage_client = FileStorageClient.get_instance(system_app)
            except Exception:
                pass  # FileStorageClient 不可用

            # 创建AgentFileSystem实例（V3 集成在默认版本中）
            self._agent_file_system = AgentFileSystem(
                conv_id=conv_id,
                session_id=session_id,
                metadata_storage=self.memory.gpts_memory if self.memory else None,
                file_storage_client=file_storage_client,
            )

            # 同步工作区（恢复文件）
            await self._agent_file_system.sync_workspace()

            # 更新截断器的AFS引用
            if self._truncator:
                self._truncator.agent_file_system = self._agent_file_system

            logger.info(
                f"AgentFileSystem initialized with conv_id={conv_id}, "
                f"session_id={session_id}, storage_type={self._agent_file_system.get_storage_type()}"
            )
            return self._agent_file_system

        except Exception as e:
            logger.warning(
                f"Failed to initialize AgentFileSystem: {e}, using legacy mode"
            )
            return None

    def _get_llm_client(self) -> Optional[Any]:
        """获取 LLM 客户端"""
        if (
            hasattr(self, "llm_config")
            and self.llm_config
            and self.llm_config.llm_client
        ):
            return self.llm_config.llm_client
        return None

    async def _check_and_compact_context(
        self,
        messages: List[AgentMessage],
    ) -> List[AgentMessage]:
        """
        检查并压缩上下文

        Args:
            messages: 当前消息列表

        Returns:
            List[AgentMessage]: 处理后的消息列表
        """
        if not self.enable_session_compaction or not self._session_compaction:
            return messages

        # 设置 LLM 客户端（如果可用）
        llm_client = self._get_llm_client()
        if llm_client and not self._session_compaction.llm_client:
            self._session_compaction.set_llm_client(llm_client)

        # 执行压缩
        result = await self._session_compaction.compact(messages, force=False)

        if result.success and result.messages_removed > 0:
            self._compaction_count += 1
            logger.info(
                f"Session compaction #{self._compaction_count}: "
                f"removed {result.messages_removed} messages, "
                f"saved ~{result.tokens_saved} tokens"
            )
            return result.compacted_messages

        return messages

    async def _prune_history(
        self,
        messages: List[AgentMessage],
    ) -> List[AgentMessage]:
        """
        修剪历史记录

        Args:
            messages: 当前消息列表

        Returns:
            List[AgentMessage]: 处理后的消息列表
        """
        if not self.enable_history_pruning or not self._history_pruner:
            return messages

        result = self._history_pruner.prune(messages)

        if result.success and result.removed_count > 0:
            self._prune_count += 1
            logger.info(
                f"History pruning #{self._prune_count}: "
                f"marked {result.removed_count} messages as compacted, "
                f"saved ~{result.tokens_saved} tokens"
            )

        return result.pruned_messages

    async def _check_doom_loop(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> bool:
        """
        检查是否存在末日循环

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            bool: 是否允许继续执行
        """
        if not self.enable_doom_loop_detection or not self._doom_loop_detector:
            return True

        # 记录工具调用
        self._doom_loop_detector.record_call(tool_name, args)

        # 检查是否触发 Doom Loop
        result: DoomLoopCheckResult = self._doom_loop_detector.check_doom_loop(
            tool_name, args, auto_record=False
        )

        if result.is_doom_loop:
            logger.warning(
                f"Doom loop detected for {tool_name}: {result.consecutive_count} consecutive calls"
            )

            # 通过权限系统请求确认
            allowed = await self._doom_loop_detector.check_and_ask_permission(
                tool_name, args
            )

            if not allowed:
                logger.info(f"Doom loop blocked for {tool_name}")
                return False

        return True

    async def _run_single_tool_with_protection(
        self,
        tool_name: str,
        args: Dict[str, Any],
        execution_func: Callable[..., Awaitable[ActionOutput]],
        **execution_kwargs,
    ) -> ActionOutput:
        """
        执行单个工具，包含完整的保护机制

        Args:
            tool_name: 工具名称
            args: 工具参数
            execution_func: 实际执行工具的功能函数
            **execution_kwargs: 传递给执行函数的额外参数

        Returns:
            ActionOutput: 工具执行结果
        """
        self._tool_call_count += 1

        # 1. 检查 Doom Loop
        allowed = await self._check_doom_loop(tool_name, args)
        if not allowed:
            return ActionOutput(
                action_id=f"doom_loop_blocked_{self._tool_call_count}",
                name="ToolExecution",
                action=tool_name,
                is_exe_success=False,
                content=f"Tool execution blocked due to detected doom loop pattern (tool: {tool_name})",
                state=Status.BLOCKED.value,
            )

        # 2. 执行工具
        try:
            result: ActionOutput = await execution_func(**execution_kwargs)
        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return ActionOutput(
                action_id=f"error_{self._tool_call_count}",
                name="ToolExecution",
                action=tool_name,
                is_exe_success=False,
                content=f"Tool execution failed: {str(e)}",
                state=Status.FAILED.value,
            )

        # 3. 截断输出（如果启用且是工具输出）
        if result.content and self.enable_output_truncation:
            result.content = self._truncate_tool_output(result.content, tool_name)

        return result

    async def load_thinking_messages(
        self,
        received_message: AgentMessage,
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Tuple[List[AgentMessage], Optional[Dict], Optional[str], Optional[str]]:
        """
        加载思考消息，包含上下文压缩和历史修剪

        Returns:
            Tuple: (消息列表, 上下文, 系统提示, 用户提示)
        """
        # 获取基础消息列表
        (
            messages,
            context,
            system_prompt,
            user_prompt,
        ) = await super().load_thinking_messages(
            received_message, sender, rely_messages, **kwargs
        )

        if not messages:
            return messages, context, system_prompt, user_prompt

        # 1. 执行历史修剪
        messages = await self._prune_history(messages)

        # 2. 执行上下文压缩
        messages = await self._check_and_compact_context(messages)

        # 3. 确保AgentFileSystem已初始化（用于文件管理）
        await self._ensure_agent_file_system()

        return messages, context, system_prompt, user_prompt

    async def act(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> List[ActionOutput]:
        """
        执行动作，包含完整保护机制
        """
        if not message:
            raise ValueError("The message content is empty!")

        act_outs: List[ActionOutput] = []

        # 阶段 1：解析所有可能的 action
        real_actions = self.agent_parser.parse_actions(
            llm_out=kwargs.get("agent_llm_out"), action_cls_list=self.actions, **kwargs
        )

        # 阶段 2：并行执行所有解析出的 action
        if real_actions:
            explicit_keys = [
                "ai_message",
                "resource",
                "rely_action_out",
                "render_protocol",
                "message_id",
                "sender",
                "agent",
                "received_message",
                "agent_context",
                "memory",
            ]

            filtered_kwargs = {
                k: v for k, v in kwargs.items() if k not in explicit_keys
            }
            
            # 传入 AgentFileSystem 和截断配置用于大结果归档
            afs = await self._ensure_agent_file_system()
            filtered_kwargs['agent_file_system'] = afs
            filtered_kwargs['max_output_bytes'] = self._truncator_max_bytes if hasattr(self, '_truncator_max_bytes') else 5 * 1024
            filtered_kwargs['max_output_lines'] = self._truncator_max_lines if hasattr(self, '_truncator_max_lines') else 50

            tasks = []
            for real_action in real_actions:
                task = real_action.run(
                    ai_message=message.content if message.content else "",
                    resource=self.resource,
                    resource_map=self.resource_map,
                    render_protocol=await self.memory.gpts_memory.async_vis_converter(
                        self.not_null_agent_context.conv_id
                    ),
                    message_id=message.message_id,
                    current_message=message,
                    sender=sender,
                    agent=self,
                    received_message=received_message,
                    agent_context=self.agent_context,
                    memory=self.memory,
                    **filtered_kwargs,
                )
                tasks.append((real_action, task))

            # 并行执行所有任务
            results = await asyncio.gather(
                *[task for _, task in tasks], return_exceptions=True
            )

            # 处理执行结果
            for (real_action, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    logger.exception(f"Action execution failed: {result}")
                    act_outs.append(
                        ActionOutput(
                            content=str(result),
                            name=real_action.name,
                            is_exe_success=False,
                        )
                    )
                else:
                    if result:
                        # 提取工具信息
                        tool_name = result.action or real_action.name
                        tool_args = {}

                        # 从 action 中获取参数
                        if hasattr(real_action, "execute_params"):
                            tool_args = getattr(real_action, "execute_params", {})

                        logger.info(f"🎯 Tool executed: {tool_name}, success={result.is_exe_success if hasattr(result, 'is_exe_success') else 'unknown'}")

                        # 记录到 PhaseManager
                        self.record_phase_action(tool_name, result.is_exe_success)

                        # ========== 集成：记录到 WorkLog ==========
                        logger.info(f"📝 Calling _record_action_to_work_log for {tool_name}...")
                        await self._record_action_to_work_log(
                            tool_name, tool_args, result
                        )

                        # ========== 集成：判断是否需要自动生成报告 ==========
                        # 如果是 terminate action 且启用了自动报告
                        if (
                            self._is_terminate_action(result)
                            and self.report_auto_generate
                        ):
                            self.set_phase("reporting", "任务完成，生成报告")

# 如果是terminate action，附加交付文件
                        if isinstance(result, ActionOutput) and result.terminate:
                            result = await self._attach_delivery_files(result)

                            # ========== 集成：自动生成报告 ==========
                            try:
                                report_content = await self.generate_report(
                                    report_type=self.report_default_type,
                                    report_format=self.report_default_format,
                                    save_to_file=True,
                                )
                                logger.info(f"Auto-generated report saved")
                            except Exception as e:
                                logger.warning(f"Failed to auto-generate report: {e}")

                            # 切换到完成阶段
                            self.set_phase("complete", "任务全部完成")

                        act_outs.append(result)
                    else:
                        logger.warning(f"⚠️ Tool execution returned None/empty result for action: {real_action.name}")

                await self.push_context_event(
                    EventType.AfterAction,
                    ActionPayload(action_output=result),
                    await self.task_id_by_received_message(received_message),
                )

        return act_outs

    async def _attach_delivery_files(
        self, action_out: "ActionOutput"
    ) -> "ActionOutput":
        """为terminate action附加交付文件.

        从AgentFileSystem收集所有结论文件和交付物文件，
        附加到ActionOutput的output_files字段中。
        """
        from derisk.agent.expand.actions.terminate_action import Terminate

        if action_out.name != Terminate.name:
            return action_out

        try:
            # 确保AgentFileSystem已初始化
            afs = await self._ensure_agent_file_system()
            if not afs:
                logger.warning("AgentFileSystem not available, skip file collection")
                return action_out

            # 收集交付文件
            delivery_files = await afs.collect_delivery_files()

            if delivery_files:
                # 附加到ActionOutput
                action_out.output_files = delivery_files
                logger.info(f"Attached {len(delivery_files)} files to terminate action")

        except Exception as e:
            logger.error(f"Failed to attach delivery files: {e}")

        return action_out

    def get_stats(self) -> Dict[str, Any]:
        """获取 Agent 运行统计信息"""
        stats = {
            "tool_call_count": self._tool_call_count,
            "compaction_count": self._compaction_count,
            "prune_count": self._prune_count,
        }

        if self._doom_loop_detector:
            stats["doom_loop"] = self._doom_loop_detector.get_stats()

        if self._session_compaction:
            stats["compaction"] = self._session_compaction.get_stats()

        if self._history_pruner:
            stats["prune"] = self._history_pruner.get_stats()

        return stats

    def reset_stats(self):
        """重置统计信息"""
        self._tool_call_count = 0
        self._compaction_count = 0
        self._prune_count = 0

        if self._doom_loop_detector:
            self._doom_loop_detector.reset()

        if self._session_compaction:
            self._session_compaction.clear_history()

        if self._history_pruner:
            self._history_pruner._prune_history.clear()

    async def save_conclusion_file(
        self,
        content: Any,
        file_name: str,
        extension: str = "md",
        task_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        保存结论文件并自动推送d-attach组件到前端

        Args:
            content: 文件内容
            file_name: 文件名
            extension: 文件扩展名
            task_id: 关联任务ID

        Returns:
            文件元数据字典，失败返回None
        """
        afs = await self._ensure_agent_file_system()
        if not afs:
            logger.warning("AgentFileSystem not available, cannot save conclusion file")
            return None

        try:
            from derisk.agent.core.memory.gpts import AgentFileMetadata

            file_metadata = await afs.save_conclusion(
                data=content,
                file_name=file_name,
                extension=extension,
                created_by=self.name,
                task_id=task_id,
            )
            logger.info(f"Saved conclusion file: {file_name}")
            return file_metadata.to_attach_content()
        except Exception as e:
            logger.error(f"Failed to save conclusion file: {e}")
            return None

    async def get_agent_files(
        self,
        file_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取当前Agent的所有文件

        Args:
            file_type: 文件类型过滤

        Returns:
            文件信息列表
        """
        afs = await self._ensure_agent_file_system()
        if not afs:
            return []

        try:
            files = await afs.list_files(file_type=file_type)
            return files
        except Exception as e:
            logger.error(f"Failed to list agent files: {e}")
            return []

    async def push_all_conclusions(self):
        """推送所有结论文件到前端"""
        afs = await self._ensure_agent_file_system()
        if not afs:
            return

        try:
            await afs.push_conclusion_files()
            logger.info("Pushed all conclusion files")
        except Exception as e:
            logger.error(f"Failed to push conclusion files: {e}")

    async def sync_file_workspace(self):
        """同步文件工作区（用于会话恢复）"""
        afs = await self._ensure_agent_file_system()
        if not afs:
            return

        try:
            await afs.sync_workspace()
            logger.info("File workspace synced")
        except Exception as e:
            logger.error(f"Failed to sync file workspace: {e}")

    async def compress_session(self, force: bool = False) -> Optional[CompactionResult]:
        """
        手动触发会话压缩

        Args:
            force: 是否强制压缩

        Returns:
            Optional[CompactionResult]: 压缩结果
        """
        if not self._session_compaction:
            return None

        # 获取当前消息
        if self.not_null_agent_context:
            messages = await self.memory.gpts_memory.get_messages(
                self.not_null_agent_context.conv_id
            )

            # 设置 LLM 客户端
            llm_client = self._get_llm_client()
            if llm_client:
                self._session_compaction.set_llm_client(llm_client)

            result = await self._session_compaction.compact(
                [item.to_agent_message() for item in messages], force=force
            )

            if result.success and result.messages_removed > 0:
                # 更新内存中的消息
                # 注意：这里需要考虑如何安全地替换消息
                logger.info(
                    f"Manual compression: removed {result.messages_removed} messages"
                )

            return result

        return None

    def record_phase_action(self, tool_name: str, success: bool):
        """记录到阶段管理器（在工具执行后调用）"""
        if (
            self.enable_phase_management
            and hasattr(self, "_phase_manager")
            and self._phase_manager
        ):
            self._phase_manager.record_action(tool_name, success)

    def register_variables(self):
        """子类通过重写此方法注册变量"""
        logger.info(f"register_variables {self.role}")
        super().register_variables()

        @self._vm.register("available_agents", "可用Agents资源")
        async def var_available_agents(instance):
            logger.info("注入agent资源")
            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], AppResource):
                    for item in v:
                        app_item: AppResource = item  # type:ignore
                        prompts += f"- <agent><code>{app_item.app_code}</code><name>{app_item.app_name}</name><description>{app_item.app_desc}</description>\n</agent>\n"
            return prompts

        @self._vm.register("available_knowledges", "可用知识库")
        async def var_available_knowledges(instance):
            logger.info("注入knowledges资源")

            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], RetrieverResource):
                    for item in v:
                        if hasattr(item, "knowledge_spaces") and item.knowledge_spaces:
                            for i, knowledge_space in enumerate(item.knowledge_spaces):
                                prompts += f"- <knowledge><id>{knowledge_space.knowledge_id}</id><name>{knowledge_space.name}</name><description>{knowledge_space.desc}</description></knowledge>\n"

                        else:
                            logger.error(f"当前知识资源无法使用!{k}")
            return prompts

        @self._vm.register("available_skills", "可用技能")
        async def var_skills(instance):
            logger.info("注入技能资源")

            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], AgentSkillResource):
                    for item in v:
                        skill_item: AgentSkillResource = item  # type:ignore
                        mode, branch = "release", "master"
                        debug_info = getattr(skill_item, "debug_info", None)
                        if debug_info and debug_info.get("is_debug"):
                            mode, branch = "debug", debug_info.get("branch")
                        prompts += (
                            f"- <skill>"
                            f"<name>{skill_item.skill_meta(mode).name}</name>"
                            f"<description>{skill_item.skill_meta(mode).description}</description>"
                            f"<path>{skill_item.skill_meta(mode).path}</path>"
                            f"<branch>{branch}</branch>"
                            f"\n</skill>\n"
                        )
            return prompts

        @self._vm.register("system_tools", "系统工具")
        async def var_system_tools(instance):
            result = ""
            if self.available_system_tools:
                logger.info("注入系统工具")
                tool_prompts = ""
                for k, v in self.available_system_tools.items():
                    t_prompt, _ = await v.get_prompt(
                        lang=instance.agent_context.language
                    )
                    tool_prompts += f"- <tool>{t_prompt}</tool>\n"
                return tool_prompts

            return None

        @self._vm.register("custom_tools", "自定义工具")
        async def var_custom_tools(instance):
            logger.info("注入自定义工具")
            tool_prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], BaseTool):
                    for item in v:
                        t_prompt, _ = await item.get_prompt(
                            lang=instance.agent_context.language
                        )
                        tool_prompts += f"- <tool>{t_prompt}</tool>\n"
                ## 临时兼容MCP 因为异步加载
                elif isinstance(v[0], MCPToolPack):
                    for mcp in v:
                        if mcp and mcp.sub_resources:
                            for item in mcp.sub_resources:
                                t_prompt, _ = await item.get_prompt(
                                    lang=instance.agent_context.language
                                )
                                tool_prompts += f"- <tool>{t_prompt}</tool>\n"
            return tool_prompts

        @self._vm.register("sandbox", "沙箱配置")
        async def var_sandbox(instance):
            logger.info("注入沙箱配置信息，如果存在沙箱客户端即默认使用沙箱")
            if instance and instance.sandbox_manager:
                if instance.sandbox_manager.initialized == False:
                    logger.warning(
                        f"沙箱尚未准备完成!({instance.sandbox_manager.client.provider}-{instance.sandbox_manager.client.sandbox_id})"
                    )
                sandbox_client: SandboxBase = instance.sandbox_manager.client

                from derisk.agent.core.sandbox.prompt import sandbox_prompt
                from derisk.agent.core.sandbox.sandbox_tool_registry import (
                    sandbox_tool_dict,
                )
                from derisk.agent.core.sandbox.tools.browser_tool import BROWSER_TOOLS

                sandbox_tool_prompts = []
                browser_tool_prompts = []
                for k, v in sandbox_tool_dict.items():
                    prompt, _ = await v.get_prompt(lang=instance.agent_context.language)
                    if k in BROWSER_TOOLS:
                        browser_tool_prompts.append(f"- <tool>{prompt}</tool>")
                    else:
                        sandbox_tool_prompts.append(f"- <tool>{prompt}</tool>")

                param = {
                    "sandbox": {
                        "work_dir": sandbox_client.work_dir,
                        "use_agent_skill": sandbox_client.enable_skill,
                        "agent_skill_dir": sandbox_client.skill_dir,
                    }
                }

                return {
                    "tools": "\n".join([item for item in sandbox_tool_prompts]),
                    # "browser_tools": "\n".join([item for item in browser_tool_prompts]),
                    "enable": True if sandbox_client else False,
                    "prompt": render(sandbox_prompt, param),
                }
            else:
                return {"enable": False, "prompt": ""}

        @self._vm.register("input", "用户输入")
        def var_input(received_message):
            if received_message:
                return received_message.content
            return ""

        @self._vm.register("work_log", "工作日志")
        async def var_work_log(instance):
            logger.info("var_work_log: fetching work log...")
            if not instance.enable_work_log:
                logger.info("var_work_log: work_log is disabled")
                return ""

            await instance._ensure_work_log_manager()
            if not instance._work_log_manager or not instance._work_log_initialized:
                logger.warning("var_work_log: WorkLogManager not initialized")
                return ""

            await instance._work_log_manager.initialize()
            context = await instance._work_log_manager.get_context_for_prompt(
                max_entries=50
            )
            logger.info(f"var_work_log: fetched work log, entries={len(instance._work_log_manager.work_log)}")
            return context

        logger.info(f"register_variables end {self.role}")

    async def _ensure_work_log_manager(self):
        """确保 WorkLog 管理器已初始化"""
        if not self.enable_work_log:
            logger.debug("_ensure_work_log_manager: work_log is disabled")
            return

        # 添加锁保护防止并发初始化
        if not hasattr(self, '_work_log_initialization_lock'):
            self._work_log_initialization_lock = asyncio.Lock()

        async with self._work_log_initialization_lock:
            # 双重检查
            if self._work_log_manager and self._work_log_initialized:
                logger.info("WorkLogManager already initialized, skipping re-initialization")
                return

            logger.info("Initializing WorkLogManager...")

            conv_id = "default"
            session_id = "default"

            if self.not_null_agent_context:
                conv_id = self.not_null_agent_context.conv_id or "default"
                session_id = self.not_null_agent_context.conv_session_id or conv_id

            logger.info(f"WorkLogManager session info: conv_id={conv_id}, session_id={session_id}")

            afs = await self._ensure_agent_file_system()
            if not afs:
                logger.warning("AgentFileSystem not available, WorkLogManager will not initialize")
                return

            self._work_log_manager = await create_work_log_manager(
                agent_id=self.name,
                session_id=session_id,
                agent_file_system=afs,
                context_window_tokens=self.work_log_context_window,
                compression_threshold_ratio=self.work_log_compression_ratio,
            )

            self._work_log_initialized = True
            logger.info(f"WorkLogManager initialized: agent_id={self.name}, session_id={session_id}")

            await self._work_log_manager.initialize()
            logger.info(f"WorkLogManager loaded: {len(self._work_log_manager.work_log)} entries")

    async def _record_action_to_work_log(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]],
        action_output: ActionOutput,
    ):
        """记录操作到 WorkLog"""
        logger.info(f"_record_action_to_work_log: start, tool={tool_name}, enable_work_log={self.enable_work_log}")
        
        if not self.enable_work_log:
            logger.info("_record_action_to_work_log: work_log disabled, returning")
            return

        # 确保工作日志管理器已初始化
        logger.info("_record_action_to_work_log: calling _ensure_work_log_manager...")
        await self._ensure_work_log_manager()
        logger.info(f"_record_action_to_work_log: _ensure_work_log_manager done, manager={self._work_log_manager is not None}, initialized={self._work_log_initialized}")

        if not self._work_log_manager:
            logger.warning("Failed to initialize WorkLogManager, skipping work log recording")
            return

        tags = []
        if not action_output.is_exe_success:
            tags.append("error")
        if action_output.content and len(action_output.content) > 10000:
            tags.append("large_output")

        try:
            logger.info(f"_record_action_to_work_log: calling record_action for {tool_name}...")
            entry = await self._work_log_manager.record_action(
                tool_name=tool_name,
                args=args if args is not None else {},
                action_output=action_output,
                tags=tags,
            )
            logger.info(f"✅ Recorded work log: tool={tool_name}, success={action_output.is_exe_success}, "
                       f"total_entries={len(self._work_log_manager.work_log)}")
        except Exception as e:
            logger.exception(f"Failed to record work log for {tool_name}: {e}")

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

    def set_phase(self, phase: str, reason: str = ""):
        """手动设置阶段"""
        if self.enable_phase_management and self._phase_manager:
            phase_enum = TaskPhase(phase.lower())
            self._phase_manager.set_phase(phase_enum, reason)
            logger.info(f"Phase set to {phase}: {reason}")
        else:
            logger.warning("PhaseManager is not enabled")

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
            logger.warning(
                "ReportGenerator is not enabled. Set enable_auto_report=True"
            )
            return ""

        await self._ensure_work_log_manager()

        if not self._work_log_manager or not self._work_log_initialized:
            logger.warning("WorkLog must be initialized for report generation")
            return ""

        report_generator = ReportGenerator(
            work_log_manager=self._work_log_manager,
            agent_id=self.name,
            task_id=self.not_null_agent_context.conv_id
            if self.not_null_agent_context
            else "unknown",
            llm_client=None,
        )

        try:
            report_type_enum = ReportType(report_type.lower())
        except ValueError:
            report_type_enum = ReportType.DETAILED

        try:
            report_format_enum = ReportFormat(report_format.lower())
        except ValueError:
            report_format_enum = ReportFormat.MARKDOWN

        report = await report_generator.generate_report(
            report_type=report_type_enum,
            report_format=report_format_enum,
        )

        if report_format_enum == ReportFormat.MARKDOWN:
            content = report.to_markdown()
        elif report_format_enum == ReportFormat.HTML:
            content = report.to_html()
        elif report_format_enum == ReportFormat.JSON:
            content = report.to_json()
        else:
            content = report.to_plain_text()

        if save_to_file:
            await self._save_report_to_file(content, report_format_enum)

        logger.info(f"Report generated: {report_type}/{report_format}")
        return content

    async def _save_report_to_file(
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

        logger.info(f"Report saved: {report_key}")


# 导入需要的东西
from derisk.context.event import ActionPayload, EventType

# 导出
__all__ = [
    "ReActMasterAgent",
    "ReActMasterParser",
    "DoomLoopDetector",
    "SessionCompaction",
    "HistoryPruner",
    "Truncator",
]
