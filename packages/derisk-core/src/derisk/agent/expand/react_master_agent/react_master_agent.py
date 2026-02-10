"""
ReActMaster Agent - 最佳实践的 ReAct 范式 Agent 实现

核心特性：
1. "末日循环" (Doom Loop) 检测机制
2. 上下文压缩 (SessionCompaction)
3. 工具输出截断 (Truncate.output)
4. 历史记录修剪 (prune)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type, Union, Callable, Awaitable

from derisk._private.pydantic import Field, PrivateAttr
from derisk.agent import (
    ActionOutput,
    Agent,
    AgentMessage,
    ProfileConfig,
    Resource,
    ResourceType,
    BlankAction,
)
from derisk.agent.core.action.base import Action, ToolCall
from derisk.agent.core.base_agent import ConversableAgent, ContextHelper
from derisk.agent.core.base_parser import AgentParser, SchemaType
from derisk.agent.core.role import AgentRunMode
from derisk.agent.core.schema import Status, DynamicParam, DynamicParamType

from ..react_agent.react_parser import ReActOutputParser, ReActOut

# 导入核心组件
from .doom_loop_detector import (
    DoomLoopDetector,
    IntelligentDoomLoopDetector,
    DoomLoopCheckResult,
)
from .session_compaction import SessionCompaction, CompactionResult
from .prune import HistoryPruner, PruneResult
from .truncation import Truncator, TruncationResult, TruncationConfig
from .prompt import (
    REACT_MASTER_SYSTEM_TEMPLATE,
    REACT_MASTER_USER_TEMPLATE,
    REACT_MASTER_WRITE_MEMORY_TEMPLATE,
)

# AgentFileSystem 导入
try:
    from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem
    AGENT_FILESYSTEM_AVAILABLE = True
except ImportError:
    AGENT_FILESYSTEM_AVAILABLE = False
    AgentFileSystem = None

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
            goal="A best-practice ReAct agent that efficiently solves complex tasks through systematic reasoning and tool usage.",
            system_prompt_template=REACT_MASTER_SYSTEM_TEMPLATE,
            user_prompt_template=REACT_MASTER_USER_TEMPLATE,
            write_memory_template=REACT_MASTER_WRITE_MEMORY_TEMPLATE,
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

    # 动态变量
    dynamic_variables: List[DynamicParam] = [
        DynamicParam(
            key="memory_history",
            name="Memory History",
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

    def __init__(self, **kwargs):
        """Initialize ReActMaster Agent."""
        super().__init__(**kwargs)
        self._initialize_components()

    def _initialize_components(self):
        """初始化核心组件"""
        # 1. 初始化 Doom Loop 检测器
        if self.enable_doom_loop_detection:
            self._doom_loop_detector = IntelligentDoomLoopDetector(
                threshold=self.doom_loop_threshold,
                permission_callback=self._ask_user_permission,
            )
            logger.info(f"DoomLoopDetector initialized with threshold={self.doom_loop_threshold}")

        # 2. 初始化上下文压缩器
        if self.enable_session_compaction:
            self._session_compaction = SessionCompaction(
                context_window=self.context_window,
                threshold_ratio=self.compaction_threshold_ratio,
            )
            logger.info(f"SessionCompaction initialized with window={self.context_window}")

        # 3. 初始化历史修剪器
        if self.enable_history_pruning:
            self._history_pruner = HistoryPruner(
                prune_protect=self.prune_protect_tokens,
            )
            logger.info(f"HistoryPruner initialized with protect={self.prune_protect_tokens}")

        # 4. 初始化 AgentFileSystem 和输出截断器
        if self.enable_output_truncation:
            # 创建截断器（AgentFileSystem 将在需要时异步初始化）
            self._truncator = Truncator(
                max_lines=self._truncator_max_lines if hasattr(self, '_truncator_max_lines') else TruncationConfig.DEFAULT_MAX_LINES,
                max_bytes=self._truncator_max_bytes if hasattr(self, '_truncator_max_bytes') else TruncationConfig.DEFAULT_MAX_BYTES,
            )
            self._agent_file_system = None
            logger.info("Truncator initialized (AgentFileSystem will be initialized on demand)")

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
        logger.warning(f"Permission requested but auto-denied (no actual permission system): {message[:100]}...")
        return False

    async def _ensure_agent_file_system(self) -> Optional[Any]:
        """
        确保AgentFileSystem已初始化（懒加载）

        Returns:
            AgentFileSystem实例或None
        """
        if self._agent_file_system is not None:
            return self._agent_file_system

        if not AGENT_FILESYSTEM_AVAILABLE:
            return None

        if not self.not_null_agent_context:
            return None

        try:
            from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem

            conv_id = self.not_null_agent_context.conv_id or "default"
            session_id = self.not_null_agent_context.conv_session_id or conv_id

            # 创建AgentFileSystem实例
            self._agent_file_system = AgentFileSystem(
                conv_id=conv_id,
                session_id=session_id,
                gpts_memory=self.memory.gpts_memory if self.memory else None,
            )

            # 同步工作区（恢复文件）
            await self._agent_file_system.sync_workspace()

            # 更新截断器的AFS引用
            if self._truncator:
                self._truncator.agent_file_system = self._agent_file_system

            logger.info(f"AgentFileSystem initialized with conv_id={conv_id}, session_id={session_id}")
            return self._agent_file_system

        except Exception as e:
            logger.warning(f"Failed to initialize AgentFileSystem: {e}, using legacy mode")
            return None

    def _get_llm_client(self) -> Optional[Any]:
        """获取 LLM 客户端"""
        if hasattr(self, 'llm_config') and self.llm_config and self.llm_config.llm_client:
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

    def _truncate_tool_output(
        self,
        content: str,
        tool_name: str,
    ) -> str:
        """
        截断工具输出

        Args:
            content: 原始输出内容
            tool_name: 工具名称

        Returns:
            str: 处理后的输出内容
        """
        if not self.enable_output_truncation or not self._truncator:
            return content

        result = self._truncator.truncate(content, tool_name)

        if result.is_truncated:
            logger.info(
                f"Output truncated for {tool_name}: "
                f"{result.original_lines}->{result.truncated_lines} lines, "
                f"{result.original_bytes}->{result.truncated_bytes} bytes"
            )

        return result.content

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
            logger.warning(f"Doom loop detected for {tool_name}: {result.consecutive_count} consecutive calls")

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

    async def _load_thinking_messages(
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
        messages, context, system_prompt, user_prompt = await super()._load_thinking_messages(
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
            llm_out=kwargs.get("agent_llm_out"),
            action_cls_list=self.actions,
            **kwargs
        )

        # 阶段 2：并行执行所有解析出的 action
        if real_actions:
            explicit_keys = [
                'ai_message', 'resource', 'rely_action_out', 'render_protocol',
                'message_id', 'sender', 'agent', 'received_message', 'agent_context', "memory"
            ]

            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in explicit_keys}

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
            results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

            # 处理执行结果
            for (real_action, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    logger.exception(f"Action execution failed: {result}")
                    act_outs.append(ActionOutput(
                        content=str(result),
                        name=real_action.name,
                        is_exe_success=False
                    ))
                else:
                    if result:
                        # 对工具执行结果应用输出截断
                        if isinstance(result, ActionOutput) and result.content:
                            tool_name = result.action or real_action.name
                            result.content = self._truncate_tool_output(result.content, tool_name)

                        # 如果是terminate action，附加交付文件
                        if isinstance(result, ActionOutput) and result.terminate:
                            result = await self._attach_delivery_files(result)

                        act_outs.append(result)

                await self.push_context_event(
                    EventType.AfterAction,
                    ActionPayload(action_output=result),
                    await self.task_id_by_received_message(received_message)
                )

        return act_outs

    async def _attach_delivery_files(self, action_out: "ActionOutput") -> "ActionOutput":
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

            result = await self._session_compaction.compact(messages, force=force)

            if result.success and result.messages_removed > 0:
                # 更新内存中的消息
                # 注意：这里需要考虑如何安全地替换消息
                logger.info(f"Manual compression: removed {result.messages_removed} messages")

            return result

        return None


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
