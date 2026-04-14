"""
ReActMaster Agent - 最佳实践的 ReAct 范式 Agent 实现

核心特性：
1. "末日循环" (Doom Loop) 检测机制
2. 上下文压缩 (SessionCompaction)
3. 工具输出截断 (Truncate.output)
4. 历史记录修剪 (prune)
5. Kanban 任务规划（可选，通过 enable_kanban=True 启用）
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Callable, Awaitable

from derisk._private.pydantic import Field, PrivateAttr
from derisk.configs.model_config import DATA_DIR
import os
from derisk.agent import (
    ActionOutput,
    Agent,
    AgentMessage,
    ProfileConfig,
)
from derisk.agent.core.base_agent import ConversableAgent, ContextHelper
from derisk.agent.core.base_parser import SchemaType
from derisk.agent.core.role import AgentRunMode
from derisk.agent.core.schema import Status
from derisk.core.interface.message import ModelMessageRoleType
from derisk.agent.util.llm.llm_client import AgentLLMOut
from derisk.sandbox.base import SandboxBase
from derisk.util.template_utils import render
from derisk_serve.agent.resource.tool.mcp import MCPToolPack

from derisk.agent.expand.tool_agent.function_call_parser import (
    FunctionCallOutputParser,
    ReActOut,
)

# 导入核心组件
from .doom_loop_detector import (
    DoomLoopDetector,
    IntelligentDoomLoopDetector,
    DoomLoopCheckResult,
)

# SessionCompaction and HistoryPruner removed in Phase 2 - replaced by UnifiedCompactionPipeline
# 但 CompactionResult 仍在 compress_session 方法中使用
from .session_compaction import CompactionResult
from .truncation import Truncator, TruncationConfig

from .prompt_fc import (
    REACT_MASTER_FC_SYSTEM_TEMPLATE_CN,
    REACT_MASTER_FC_USER_TEMPLATE_CN,
    REACT_MASTER_FC_WRITE_MEMORY_TEMPLATE_CN,
    REACT_MASTER_FC_SYSTEM_TEMPLATE,
    REACT_MASTER_FC_USER_TEMPLATE,
    REACT_MASTER_FC_WRITE_MEMORY_TEMPLATE,
)
from ...core.file_system.agent_file_system import AgentFileSystem

# 新增模块导入
from .work_log import WorkLogManager, create_work_log_manager
from .history_message_builder import (
    HistoryMessageBuilder,
    create_history_message_builder,
    CompressionConfig,
    BuildResult,
)
from .phase_manager import PhaseManager, TaskPhase, create_phase_manager
from .report_generator import ReportGenerator, ReportType, ReportFormat
from .kanban_manager import (
    KanbanManager,
    create_kanban_manager,
    validate_deliverable_schema,
)
from derisk.agent.core.memory.gpts.system_event import (
    SystemEventManager,
    SystemEventType,
)
from ...resource import BaseTool, RetrieverResource, FunctionTool, ToolPack
from ...resource.agent_skills import AgentSkillResource
from ...resource.app import AppResource
from ..actions.agent_action import AgentStart
from ..actions.knowledge_action import KnowledgeSearch
from ..actions.tool_action import ToolAction
from ...core.action.blank_action import BlankAction

# 导入 read_file 工具使其注册到 system_tool_dict
from ...core.tools.read_file_tool import read_file  # noqa: F401

# 导入 PromptAssembler（通用 Prompt 组装模块）
from ...shared.prompt_assembly import (
    PromptAssembler,
    PromptAssemblyConfig,
    ResourceContext,
    create_prompt_assembler,
)

logger = logging.getLogger(__name__)


def _get_sandbox_system_info(sandbox_client: SandboxBase) -> str:
    """Get system info description based on sandbox provider type."""
    provider = getattr(sandbox_client, "provider", lambda: "unknown")()

    if provider == "local":
        import platform
        import os

        system = platform.system()
        if system == "Darwin":
            return f"macOS ({platform.processor()}), 本地沙箱环境，路径映射到项目目录"
        elif system == "Linux":
            return f"Linux ({platform.processor()}), 本地沙箱环境，路径映射到项目目录"
        elif system == "Windows":
            return f"Windows, 本地沙箱环境，路径映射到项目目录"
        else:
            return f"{system}, 本地沙箱环境，路径映射到项目目录"
    else:
        return "Ubuntu 24.04 linux/amd64（已联网），用户：ubuntu（拥有免密 sudo 权限）"


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
    max_retry_count: int = 300
    run_mode: AgentRunMode = AgentRunMode.LOOP

    profile: ProfileConfig = Field(
        default_factory=lambda: ProfileConfig(
            name="BAIZE",
            role="BAIZE",
            goal="白泽，一个遵循最佳ReAct推理范式实践的Agent，通过系统化推理和工具使用高效解决复杂任务。",
            system_prompt_template=None,
            user_prompt_template=None,
            write_memory_template=REACT_MASTER_FC_WRITE_MEMORY_TEMPLATE_CN,
            # 别名配置：用于历史数据兼容
            aliases=["ReActMasterV2", "ReActMaster"],
        )
    )

    agent_parser: FunctionCallOutputParser = Field(
        default_factory=lambda: FunctionCallOutputParser(extract_scratch_pad=False)
    )
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

    # Prompt 组装模式配置
    use_layered_prompt_assembly: bool = False
    force_layered_assembly: bool = False

    # Message List 历史模式（原生格式 vs 文本注入）
    use_message_list_history: bool = True
    message_list_history_max_tokens: int = 30000

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

    # Kanban 配置 (从 PDCAAgent 合并)
    enable_kanban: bool = False  # 启用 Kanban 任务规划模式
    kanban_exploration_limit: int = 2  # 探索阶段最大轮次
    kanban_auto_stage_transition: bool = True  # 自动阶段转换

    # 内部状态
    _ctx: ContextHelper[dict] = PrivateAttr(default_factory=lambda: ContextHelper(dict))
    _doom_loop_detector: Optional[DoomLoopDetector] = PrivateAttr(default=None)
    # _session_compaction removed - replaced by UnifiedCompactionPipeline
    # _history_pruner removed - replaced by UnifiedCompactionPipeline
    _truncator: Optional[Truncator] = PrivateAttr(default=None)  # Kept as fallback
    _agent_file_system: Optional[AgentFileSystem] = PrivateAttr(default=None)
    _tool_call_count: int = PrivateAttr(default=0)
    _compaction_count: int = PrivateAttr(default=0)
    _prune_count: int = PrivateAttr(default=0)

    # 工具失败追踪：记录每个工具的连续失败次数
    _tool_failure_counts: Dict[str, int] = PrivateAttr(default_factory=lambda: {})
    _max_tool_failure_count: int = PrivateAttr(default=3)  # 同一工具最大失败次数

    # Kanban 内部状态
    _kanban_manager: Optional[KanbanManager] = PrivateAttr(default=None)
    _kanban_initialized: bool = PrivateAttr(default=False)

    # PromptAssembler 状态（通用 Prompt 组装器）
    _prompt_assembler: Optional[PromptAssembler] = PrivateAttr(default=None)

    # AsyncTaskManager 异步任务管理器（在 preload_resource 中按需初始化）
    _async_task_manager: Optional[Any] = PrivateAttr(default=None)

    # SystemEventManager 系统事件管理器（用于 VIS 渲染）
    _system_event_manager: Optional[SystemEventManager] = PrivateAttr(default=None)

    # HistoryMessageBuilder 历史消息构建器（统一三层压缩）
    _history_message_builder: Optional[Any] = PrivateAttr(default=None)
    _history_builder_initialized: bool = PrivateAttr(default=False)
    _last_budget_event_data: Optional[Dict] = PrivateAttr(default=None)
    _budget_event_min_change_ratio: float = PrivateAttr(default=0.05)

    available_system_tools: Dict[str, FunctionTool] = Field(
        default_factory=dict, description="available system tools"
    )
    enable_function_call: bool = True

    def __init__(self, **kwargs):
        """Initialize ReActMaster Agent."""
        super().__init__(**kwargs)
        self._init_actions([AgentStart, KnowledgeSearch, ToolAction])
        self._initialize_components()

        # 初始化交互能力
        self._interaction_extension = None

        # Skill 内容追踪：skill_name -> content（用于 compaction 后重新注入）
        self._invoked_skills: Dict[str, str] = {}

    async def preload_resource(self) -> None:
        """Preload resources and inject system tools.

        工具注入现在通过统一工具框架进行：
        1. base_agent.system_tool_injection() 从 tool_manager 获取绑定工具
        2. 工具绑定配置来自编辑页面保存的 resource_tool
        3. 无配置时使用默认工具
        """
        await super().preload_resource()
        await self.system_tool_injection()
        await self.sandbox_tool_injection()

        # 初始化 SystemEventManager
        await self._ensure_system_event_manager()

        # NOTE: read_file, todowrite, todoread 等工具现在通过统一工具框架注入
        # 不再在此处直接注入，见 base_agent.system_tool_injection()

        # NOTE: 历史回顾工具（read_history_chapter, search_history 等）不在此处注入。
        # 它们只在首次 compaction 完成后才动态注入，见 _inject_history_tools_if_needed()。

        # 注入异步任务工具（当检测到多 Agent 场景时）
        await self._inject_async_task_tools()

    async def _inject_async_task_tools(self) -> None:
        """
        注入异步任务工具到 available_system_tools。

        条件：存在 AppResource（表示有可委派的子 Agent）且有 agents 属性。
        创建 AsyncTaskManager 并注册 4 个 FunctionTool 包装。
        """
        try:
            # 检查是否有子 Agent 可委派
            if not hasattr(self, "agents") or not self.agents:
                return

            # 检查 resource_map 是否有 AppResource
            has_app_resource = False
            for k, v in (self.resource_map or {}).items():
                if v and isinstance(v[0], AppResource):
                    has_app_resource = True
                    break

            if not has_app_resource:
                return

            from ...core_v2.async_task_manager import AsyncTaskManager, AsyncTaskSpec
            from ...core_v2.subagent_manager import SubagentManager as V2SubagentManager

            # 创建一个轻量级 SubagentManager 适配器，包装 core v1 的 agent delegation
            class CoreV1SubagentAdapter:
                """适配 Core V1 的 agent delegation 为 SubagentManager.delegate 接口"""

                def __init__(self, master_agent):
                    self._master = master_agent

                async def delegate(
                    self,
                    subagent_name: str,
                    task: str,
                    parent_session_id: str = "",
                    context: Optional[Dict] = None,
                    sync: bool = True,
                    **kwargs,
                ):
                    """通过 Core V1 的 send/receive 机制委派任务"""
                    from derisk.agent import AgentMessage

                    # 找到目标子 Agent
                    recipient = next(
                        (
                            agent
                            for agent in self._master.agents
                            if agent.name == subagent_name
                            or getattr(agent, "agent_context", None)
                            and getattr(agent.agent_context, "agent_app_code", None)
                            == subagent_name
                        ),
                        None,
                    )

                    if not recipient:
                        # 返回失败结果
                        result = type(
                            "SubagentResult",
                            (),
                            {
                                "success": False,
                                "output": None,
                                "error": f"子 Agent '{subagent_name}' 不存在",
                                "artifacts": {},
                            },
                        )()
                        return result

                    # 构建消息
                    message = AgentMessage.init_new(
                        content=task,
                        context=context or {},
                        show_message=False,
                        observation=task,
                        current_goal=task,
                    )

                    try:
                        answer = await self._master.send(
                            message=message,
                            recipient=recipient,
                            request_reply=True,
                            request_sender_reply=False,
                        )

                        result = type(
                            "SubagentResult",
                            (),
                            {
                                "success": True,
                                "output": answer.content if answer else "",
                                "error": None,
                                "artifacts": {},
                            },
                        )()
                        return result
                    except Exception as e:
                        result = type(
                            "SubagentResult",
                            (),
                            {
                                "success": False,
                                "output": None,
                                "error": str(e),
                                "artifacts": {},
                            },
                        )()
                        return result

            # 创建适配器和 AsyncTaskManager
            adapter = CoreV1SubagentAdapter(self)
            session_id = (
                getattr(self.agent_context, "conv_id", "") if self.agent_context else ""
            )

            self._async_task_manager = AsyncTaskManager(
                subagent_manager=adapter,
                max_concurrent=5,
                parent_session_id=session_id,
            )

            # 获取可用子 Agent 名称列表
            agent_names = []
            for agent in self.agents:
                name = agent.name or getattr(
                    getattr(agent, "agent_context", None), "agent_app_code", None
                )
                if name:
                    agent_names.append(name)

            # 创建 FunctionTool 包装
            atm = self._async_task_manager

            async def _spawn_agent_task(
                agent_name: str, task: str, timeout: int = 300, depend_on: str = ""
            ) -> str:
                spec = AsyncTaskSpec(
                    agent_name=agent_name,
                    task_description=task,
                    timeout=timeout,
                    depend_on=[d.strip() for d in depend_on.split(",") if d.strip()]
                    if depend_on
                    else [],
                )
                task_id = await atm.spawn(spec)
                deps_info = f"\n依赖: {spec.depend_on}" if spec.depend_on else ""
                return (
                    f"任务已提交到后台执行。\n"
                    f"- Task ID: {task_id}\n"
                    f"- Agent: {agent_name}\n"
                    f"- 描述: {task[:100]}\n"
                    f"- 超时: {timeout}s{deps_info}\n\n"
                    f"你可以继续其他工作，稍后用 check_tasks 查看状态或 wait_tasks 获取结果。"
                )

            async def _check_tasks(task_ids: str = "") -> str:
                ids = (
                    [t.strip() for t in task_ids.split(",") if t.strip()]
                    if task_ids
                    else None
                )
                return atm.format_status_table(ids)

            async def _wait_tasks(task_ids: str = "", timeout: int = 60) -> str:
                ids = (
                    [t.strip() for t in task_ids.split(",") if t.strip()]
                    if task_ids
                    else []
                )
                if ids:
                    results = await atm.wait_all(ids, timeout=timeout)
                else:
                    results = await atm.wait_any(timeout=timeout)
                if not results:
                    return "等待超时，暂无任务完成。你可以继续其他工作后再检查。"
                return atm.format_results(results)

            async def _cancel_task(task_id: str) -> str:
                success = await atm.cancel(task_id)
                return (
                    f"任务 {task_id} 已取消。"
                    if success
                    else f"无法取消任务 {task_id}（任务可能已完成或不存在）。"
                )

            # 注册为 FunctionTool
            spawn_tool = FunctionTool(
                name="spawn_agent_task",
                func=_spawn_agent_task,
                description=(
                    "启动一个后台 Agent 异步任务。任务在后台执行，你可以继续其他工作。"
                    f"可用 Agent: {', '.join(agent_names)}"
                ),
                args={
                    "agent_name": ToolParameter(
                        name="agent_name",
                        type="string",
                        required=True,
                        description=f"目标子 Agent 名称。可选: {', '.join(agent_names)}",
                    ),
                    "task": ToolParameter(
                        name="task",
                        type="string",
                        required=True,
                        description="任务描述，请提供清晰具体的说明。",
                    ),
                    "timeout": ToolParameter(
                        name="timeout",
                        type="integer",
                        required=False,
                        description="超时秒数（默认300）",
                        default=300,
                    ),
                    "depend_on": ToolParameter(
                        name="depend_on",
                        type="string",
                        required=False,
                        description="依赖的 task_id 列表，逗号分隔（可选）。这些任务完成后才开始。",
                        default="",
                    ),
                },
            )

            check_tool = FunctionTool(
                name="check_tasks",
                func=_check_tasks,
                description="查看后台任务的当前状态，不阻塞。",
                args={
                    "task_ids": ToolParameter(
                        name="task_ids",
                        type="string",
                        required=False,
                        description="要查询的 task_id 列表，逗号分隔。为空则查询全部。",
                        default="",
                    ),
                },
            )

            wait_tool = FunctionTool(
                name="wait_tasks",
                func=_wait_tasks,
                description="等待后台任务完成并获取结果。指定 task_ids 等待全部完成，为空则等待任意一个完成。",
                args={
                    "task_ids": ToolParameter(
                        name="task_ids",
                        type="string",
                        required=False,
                        description="等待的 task_id 列表，逗号分隔。为空则等待任意一个完成。",
                        default="",
                    ),
                    "timeout": ToolParameter(
                        name="timeout",
                        type="integer",
                        required=False,
                        description="最大等待秒数（默认60）",
                        default=60,
                    ),
                },
            )

            cancel_tool = FunctionTool(
                name="cancel_task",
                func=_cancel_task,
                description="取消一个正在执行或等待中的后台任务。",
                args={
                    "task_id": ToolParameter(
                        name="task_id",
                        type="string",
                        required=True,
                        description="要取消的任务 ID",
                    ),
                },
            )

            self.available_system_tools["spawn_agent_task"] = spawn_tool
            self.available_system_tools["check_tasks"] = check_tool
            self.available_system_tools["wait_tasks"] = wait_tool
            self.available_system_tools["cancel_task"] = cancel_tool

            logger.info(
                f"[ReActMasterAgent] 异步任务工具已注入，可用子 Agent: {agent_names}"
            )

        except ImportError as e:
            logger.debug(f"[ReActMasterAgent] 异步任务模块未找到: {e}")
        except Exception as e:
            logger.warning(f"[ReActMasterAgent] 注入异步任务工具失败: {e}")

    async def _collect_async_task_notifications(self) -> Optional[str]:
        """
        收集已完成的异步任务通知。

        在 thinking() 中调用，将后台完成的任务结果注入到 LLM 上下文。

        Returns:
            格式化的通知文本，没有通知则返回 None
        """
        if not self._async_task_manager:
            return None

        try:
            completed = self._async_task_manager.get_completed_results(consume=True)
            if not completed:
                return None

            notification = self._async_task_manager.format_notifications(completed)
            return notification if notification else None

        except Exception as e:
            logger.warning(f"[ReActMasterAgent] 收集异步任务通知失败: {e}")
            return None

    async def load_resource(self, question: str, is_retry_chat: bool = False):
        """Load agent bind resource."""
        self.function_calling_context = await self.function_calling_params()
        return None, None

    async def function_calling_params(self):
        from derisk.agent.resource import ToolPack

        def _tool_to_function(tool) -> Dict:
            # 新框架 ToolBase: 使用 to_openai_tool() 方法
            if hasattr(tool, "to_openai_tool"):
                return tool.to_openai_tool()

            # 旧框架 BaseTool: 使用 args 属性
            properties = {}
            required_list = []
            for key, value in tool.args.items():
                properties[key] = {
                    "type": value.type,
                    "description": value.description,
                }
                if value.required:
                    required_list.append(key)
            parameters_dict = {
                "type": "object",
                "properties": properties,
                "required": required_list,
            }

            function = {}
            function["name"] = tool.name
            function["description"] = tool.description
            function["parameters"] = parameters_dict
            return {"type": "function", "function": function}

        functions = []

        # Log available_system_tools
        logger.info(
            f"function_calling_params: available_system_tools count={len(self.available_system_tools)}"
        )
        for k, v in self.available_system_tools.items():
            functions.append(_tool_to_function(v))

        # Log tool_packs
        tool_packs = ToolPack.from_resource(self.resource)
        logger.info(f"function_calling_params: tool_packs={tool_packs}")
        if tool_packs:
            tool_pack = tool_packs[0]
            for tool in tool_pack.sub_resources:
                tool_item: BaseTool = tool
                functions.append(_tool_to_function(tool_item))

        system_tool_count = len(self.available_system_tools)
        resource_tool_count = len(functions) - system_tool_count
        logger.info(
            f"function_calling_params: total={len(functions)} "
            f"(system={system_tool_count}, resource={resource_tool_count})"
        )

        if system_tool_count == 0 and resource_tool_count > 0:
            logger.warning(
                "function_calling_params: system tools are EMPTY! "
                "Only resource tools available. Check preload_resource() was called."
            )
        elif system_tool_count > 0 and resource_tool_count == 0:
            logger.warning(
                "function_calling_params: resource tools are EMPTY! "
                "Only system tools available. Check resource binding."
            )

        if functions:
            return {
                "tool_choice": "auto",
                "tools": functions,
                "parallel_tool_calls": True,
            }
        else:
            logger.warning("function_calling_params: No functions available!")
            return None

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

        # SessionCompaction and HistoryPruner have been replaced by UnifiedCompactionPipeline.
        # Initialization removed in Phase 2 cleanup.

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

        # 8. 初始化 Kanban 管理器（延迟初始化）
        if self.enable_kanban:
            self._kanban_manager = None
            self._kanban_initialized = False
            logger.info(
                f"Kanban enabled (exploration_limit={self.kanban_exploration_limit})"
            )
        else:
            self._kanban_manager = None
            self._kanban_initialized = False

        # 9. 初始化交互能力
        self._interaction_extension = None
        logger.info("Interaction extension enabled (will initialize on demand)")

        # 10. 初始化统一压缩管道（延迟初始化，需要 conv_id）
        self._compaction_pipeline = None
        self._pipeline_initialized = False

    def _get_interaction_extension(self):
        """获取交互扩展（懒加载）"""
        if self._interaction_extension is None:
            from .interaction_extension import create_interaction_extension

            self._interaction_extension = create_interaction_extension(self)
        return self._interaction_extension

    def _get_prompt_assembler(self) -> PromptAssembler:
        """获取 Prompt 组装器（懒加载）- 使用 Agent 级别的模板目录"""
        if self._prompt_assembler is None:
            from pathlib import Path

            # 获取 Agent 级别的 prompts 目录
            agent_prompts_dir = Path(__file__).parent / "prompts"

            config = PromptAssemblyConfig(
                architecture="v1",
                language=getattr(self.profile, "language", "zh")
                if hasattr(self, "profile")
                else "zh",
            )
            self._prompt_assembler = PromptAssembler(config)

            # 设置 Agent 级别的模板目录
            self._prompt_assembler.registry.set_agent_prompts_dir(agent_prompts_dir)
            self._prompt_assembler.registry.initialize(agent_prompts_dir)

            logger.info(
                f"PromptAssembler initialized with agent prompts: {agent_prompts_dir}"
            )

        return self._prompt_assembler

    @property
    def interaction(self):
        """交互能力访问入口"""
        return self._get_interaction_extension()

    async def _ask_user_permission(self, message: str, context: Dict = None) -> bool:
        """
        请求用户权限回调

        Args:
            message: 确认消息
            context: 上下文信息

        Returns:
            bool: 是否允许继续
        """
        try:
            extension = self._get_interaction_extension()

            tool_name = context.get("tool_name", "unknown") if context else "unknown"
            tool_args = context.get("tool_args", {}) if context else {}

            authorized = await extension.request_tool_authorization(
                tool_name=tool_name,
                tool_args=tool_args,
                reason=message,
            )

            if authorized:
                logger.info(f"User authorized: {tool_name}")
            else:
                logger.warning(f"User denied: {tool_name}")

            return authorized

        except Exception as e:
            logger.warning(f"Interaction failed, falling back to default: {e}")

            if self.memory and self.memory.gpts_memory and self.not_null_agent_context:
                await self.memory.gpts_memory.push_message(
                    conv_id=self.not_null_agent_context.conv_id,
                    stream_msg={
                        "type": "permission_request",
                        "message": message,
                        "context": context or {},
                    },
                )

            return False

    async def ask_user(
        self,
        question: str,
        title: str = "需要您的输入",
        default: str = None,
        options: List[str] = None,
    ) -> str:
        """
        主动向用户提问

        Args:
            question: 问题内容
            title: 标题
            default: 默认值
            options: 选项列表

        Returns:
            str: 用户回答
        """
        extension = self._get_interaction_extension()
        return await extension.ask_user(
            question=question,
            title=title,
            default=default,
            options=options,
        )

    async def choose_plan(
        self, plans: List[Dict[str, Any]], title: str = "请选择执行方案"
    ) -> str:
        """
        让用户选择执行方案

        Args:
            plans: 方案列表
            title: 标题

        Returns:
            str: 选择的方案ID
        """
        extension = self._get_interaction_extension()
        return await extension.choose_plan(plans=plans, title=title)

    async def confirm_action(self, message: str, title: str = "确认操作") -> bool:
        """
        请求用户确认

        Args:
            message: 确认消息
            title: 标题

        Returns:
            bool: 是否确认
        """
        extension = self._get_interaction_extension()
        return await extension.confirm_action(message=message, title=title)

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

            # 获取 sandbox 客户端
            sandbox = None
            if self.sandbox_manager and self.sandbox_manager.client:
                sandbox = self.sandbox_manager.client

            # 创建AgentFileSystem实例（V3 集成在默认版本中）
            self._agent_file_system = AgentFileSystem(
                conv_id=conv_id,
                session_id=session_id,
                metadata_storage=self.memory.gpts_memory if self.memory else None,
                file_storage_client=file_storage_client,
                sandbox=sandbox,
            )

            # 同步工作区（恢复文件）
            await self._agent_file_system.sync_workspace()

            # 注入 AgentFileSystem 到 sandbox 客户端
            if sandbox:
                sandbox.agent_file_system = self._agent_file_system
                logger.info("Injected AgentFileSystem into Sandbox client")

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

    async def _ensure_compaction_pipeline(self):
        """确保统一压缩管道已初始化（懒加载）"""
        if self._pipeline_initialized:
            return self._compaction_pipeline

        afs = await self._ensure_agent_file_system()
        if not afs:
            self._pipeline_initialized = True
            return None

        try:
            from derisk.agent.core.memory.compaction_pipeline import (
                UnifiedCompactionPipeline,
                HistoryCompactionConfig,
            )

            ctx = self.not_null_agent_context
            self._compaction_pipeline = UnifiedCompactionPipeline(
                conv_id=ctx.conv_id,
                session_id=ctx.conv_session_id or ctx.conv_id,
                agent_file_system=afs,
                work_log_storage=self.memory.gpts_memory if self.memory else None,
                llm_client=self._get_llm_client(),
                config=HistoryCompactionConfig(
                    context_window=self.context_window,
                    compaction_threshold_ratio=self.compaction_threshold_ratio,
                    prune_protect_tokens=self.prune_protect_tokens,
                    max_output_lines=(
                        self._truncator_max_lines
                        if hasattr(self, "_truncator_max_lines")
                        else 2000
                    ),
                    max_output_bytes=(
                        self._truncator_max_bytes
                        if hasattr(self, "_truncator_max_bytes")
                        else 50 * 1024
                    ),
                ),
            )
            self._pipeline_initialized = True
            logger.info("UnifiedCompactionPipeline initialized")
            return self._compaction_pipeline
        except Exception as e:
            logger.warning(f"Failed to initialize compaction pipeline: {e}")
            self._pipeline_initialized = True
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

    async def _inject_history_tools_if_needed(self):
        """在首次压缩完成后动态注入历史回顾工具。

        历史回顾工具只在 compaction 发生后才有意义（此时才有归档章节可供检索），
        因此不在 preload_resource() 中静态注入，而是由 load_thinking_messages()
        在检测到 pipeline.has_compacted 后调用本方法。
        """
        # 如果已经注入过，跳过
        if "read_history_chapter" in self.available_system_tools:
            return

        pipeline = await self._ensure_compaction_pipeline()
        if not pipeline or not pipeline.has_compacted:
            return

        try:
            from derisk.agent.core.tools.history_tools import create_history_tools

            history_tools = create_history_tools(pipeline)
            for name, tool in history_tools.items():
                self.available_system_tools[name] = tool

            # 刷新 function_calling_context 以使 LLM 能看到新工具
            self.function_calling_context = await self.function_calling_params()
            logger.info(
                f"History recovery tools injected after first compaction: "
                f"{list(history_tools.keys())}"
            )
        except Exception as e:
            logger.warning(f"Failed to inject history tools: {e}")

    # _check_and_compact_context removed in Phase 2 - replaced by UnifiedCompactionPipeline
    # _prune_history removed in Phase 2 - replaced by UnifiedCompactionPipeline

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

        # 3. 截断输出（使用统一压缩管道 Layer 1 或回退到旧逻辑）
        if result.content and self.enable_output_truncation:
            pipeline = await self._ensure_compaction_pipeline()
            if pipeline:
                tr = await pipeline.truncate_output(result.content, tool_name, args)
                result.content = tr.content
            elif self._truncator:
                tr_result = self._truncator.truncate(
                    result.content, tool_name=tool_name
                )
                result.content = tr_result.content

        return result

    async def load_thinking_messages(
        self,
        received_message: AgentMessage,
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Tuple[List[AgentMessage], Optional[Dict], Optional[str], Optional[str]]:
        """
        加载思考消息，包含四层上下文压缩

        改造：使用 PromptAssembler 分层组装 prompt，替代旧的模板变量替换

        四层架构：
        - Layer 1: 工具输出截断
        - Layer 2: 历史修剪
        - Layer 3: 上下文压缩
        - Layer 4: 跨轮次对话历史压缩

        Returns:
            Tuple: (消息列表, 上下文, 系统提示, 用户提示)
        """
        # Layer 4: 跨轮次历史管理
        user_question = received_message.content if received_message else ""

        # 开始/复用对话轮次，获取历史记录
        memory_content = None
        history_messages: List[Dict[str, Any]] = []

        try:
            pipeline = await self._ensure_compaction_pipeline()
            if pipeline:
                await pipeline.start_conversation_round(
                    user_question=user_question,
                    user_context=received_message.context if received_message else None,
                )

                if self.use_message_list_history:
                    history_messages = (
                        await pipeline.get_layer4_history_as_message_list(
                            max_tokens=self.message_list_history_max_tokens,
                        )
                    )
                else:
                    memory_content = await pipeline.get_layer4_history_for_prompt()
                    if memory_content:
                        logger.info(
                            f"[HistoryMessageBuilder] Text mode: {len(memory_content)} chars"
                        )
        except Exception as e:
            logger.warning(f"Layer 4: Failed to get history: {e}")

        # 获取基础消息列表（从基类获取消息组装逻辑，但我们会重新构建 prompt）
        (
            messages,
            context,
            _,  # 忽略基类的 system_prompt
            _,  # 忽略基类的 user_prompt
        ) = await super().load_thinking_messages(
            received_message, sender, rely_messages, **kwargs
        )

        if not messages:
            return messages, context, "", ""

        # 尝试使用统一压缩管道（Layer 2 + Layer 3）
        pipeline = await self._ensure_compaction_pipeline()
        if pipeline:
            # Layer 2: 历史修剪
            prune_result = await pipeline.prune_history(messages)
            messages = prune_result.messages
            if prune_result.pruned_count > 0:
                self._prune_count += 1
                logger.info(
                    f"Pipeline pruning: removed {prune_result.pruned_count} entries, "
                    f"saved ~{prune_result.tokens_saved} tokens"
                )

            # Layer 3: 上下文压缩 + 章节归档
            compact_result = await pipeline.compact_if_needed(messages)
            messages = compact_result.messages
            if compact_result.compaction_triggered:
                self._compaction_count += 1
                logger.info(
                    f"Pipeline compaction: archived {compact_result.messages_archived} messages, "
                    f"saved ~{compact_result.tokens_saved} tokens"
                )
                # 首次压缩完成后动态注入历史回顾工具
                if pipeline.has_compacted:
                    await self._inject_history_tools_if_needed()

                # 压缩后重新注入已调用的 Skill 内容，防止 Skill 指令丢失
                # 淘汰策略：保留第 1 个 + 最后 2 个的完整内容，中间的只保留名称摘要
                if self._invoked_skills:
                    skill_items = list(self._invoked_skills.items())
                    total = len(skill_items)
                    # _MAX_FULL_SKILLS: first 1 + last 2 = 3 slots for full content
                    _MAX_FULL_SKILLS = 3

                    if total <= _MAX_FULL_SKILLS:
                        # 少于等于 3 个，全部完整注入
                        full_inject = skill_items
                        evicted_names = []
                    else:
                        # 保留第 1 个 + 最后 2 个，中间的被淘汰
                        keep_first = skill_items[:1]
                        keep_last = skill_items[-2:]
                        evicted = skill_items[1:-2]
                        full_inject = keep_first + keep_last
                        evicted_names = [name for name, _ in evicted]

                    # 注入完整 skill 内容
                    for sk_name, sk_content in full_inject:
                        truncated = sk_content[:100_000] if len(sk_content) > 100_000 else sk_content
                        skill_msg = {
                            "role": "system",
                            "content": f'<skill-content name="{sk_name}">\n{truncated}\n</skill-content>',
                            "context": {"is_skill_content": True, "is_critical": True},
                        }
                        messages.append(skill_msg)

                    # 注入被淘汰 skill 的名称摘要（供 Agent 知道曾加载过哪些 skill）
                    if evicted_names:
                        summary_msg = {
                            "role": "system",
                            "content": (
                                f"<evicted-skills>\n"
                                f"The following {len(evicted_names)} skill(s) were previously loaded but their "
                                f"content was evicted to save context space. Use skill_read to reload if needed:\n"
                                + "\n".join(f"- {name}" for name in evicted_names)
                                + "\n</evicted-skills>"
                            ),
                            "context": {"is_skill_content": True},
                        }
                        messages.append(summary_msg)

                    logger.info(
                        f"Re-injected {len(full_inject)} skill(s) after compaction"
                        + (f", evicted {len(evicted_names)}" if evicted_names else "")
                    )

        else:
            # 降级到传统的修剪 + 压缩
            messages = await self._prune_history(messages)
            messages = await self._check_and_compact_context(messages)

        # 确保AgentFileSystem已初始化（用于文件管理）
        await self._ensure_agent_file_system()

        # ========== 使用 PromptAssembler 分层组装 Prompt ==========
        # 配置说明：
        # - force_layered_assembly=True: 强制使用分层组装，忽略旧模式检测
        # - use_layered_prompt_assembly=True: 默认使用分层组装
        # - 默认=False: 按旧模式检测决定（包含流程标记→旧模式，否则→分层组装）
        system_prompt = ""
        user_prompt = ""

        try:
            assembler = self._get_prompt_assembler()
            resource_ctx = ResourceContext.from_v1_agent(self)
            logger.info(
                f"ReActMasterAgent: sandbox_manager={getattr(self, 'sandbox_manager', None) is not None}, "
                f"resource_ctx.sandbox_manager={resource_ctx.sandbox_manager is not None}"
            )

            # 获取用户配置的身份内容
            user_identity = None
            user_prompt_prefix = None

            if hasattr(self, "profile"):
                user_identity = getattr(self.profile, "system_prompt_template", None)
                user_prompt_prefix = getattr(self.profile, "user_prompt_template", None)

            # 判断是否使用分层组装
            use_layered = False

            if self.force_layered_assembly:
                # 强制使用分层组装
                use_layered = True
                logger.info(
                    "PromptAssembler: force_layered_assembly=True，强制分层组装"
                )
            elif self.use_layered_prompt_assembly:
                # 用户配置启用分层组装
                use_layered = True
                logger.info(
                    "PromptAssembler: use_layered_prompt_assembly=True，使用分层组装"
                )
            elif user_identity and assembler._is_legacy_mode(user_identity):
                # 旧模式兼容：检测到流程控制标记，直接渲染完整模板
                use_layered = False
                logger.info("PromptAssembler: 检测到旧模式标记，使用兼容渲染")
            else:
                # 默认：对新内容使用分层组装
                use_layered = True

            # 构建模板变量
            template_vars = getattr(self.profile, "template_vars", None) or {}
            # 从 agent_context 获取用户信息和对话时间
            ctx = self.agent_context

            # 从 Agent 注册的变量管理器获取时间变量
            # now: 当前日期 (YYYY-MM-DD)
            # now_time: 当前时间 (YYYY-MM-DD HH:MM:SS)
            # conv_start_time: 对话开始时间
            now_value = ""
            now_time_value = ""
            try:
                now_value = await self._vm.get_value("now", instance=self)
                now_time_value = await self._vm.get_value("now_time", instance=self)
            except Exception as e:
                logger.warning(f"Failed to get time variables from _vm: {e}")

            base_vars = {
                "role": getattr(self.profile, "role", "")
                if hasattr(self, "profile")
                else "",
                "name": getattr(self.profile, "name", "")
                if hasattr(self, "profile")
                else "",
                "goal": getattr(self.profile, "goal", "")
                if hasattr(self, "profile")
                else "",
                "language": getattr(self.profile, "language", "zh")
                if hasattr(self, "profile")
                else "zh",
                "user_name": getattr(ctx, "user_name", "") if ctx else "",
                "user_id": getattr(ctx, "user_id", "") if ctx else "",
                "conv_start_time": getattr(ctx, "conv_start_time", "") if ctx else "",
                "now": now_value,
                "now_time": now_time_value,
            }
            render_vars = {**base_vars, **template_vars}

            # 根据 mode 选择组装方式
            if use_layered:
                # 新模式：分层组装
                # - 身份层：用户输入的 system_prompt_template（或默认身份模板）
                # - 资源层：通过 ResourceInjector 动态注入
                # - 控制层：从 prompts/ 目录加载（workflow/exceptions/delivery）
                system_prompt = await assembler.assemble_system_prompt(
                    user_system_prompt=user_identity,
                    resource_context=resource_ctx,
                    **render_vars,
                )
                logger.info("PromptAssembler: 分层组装完成（身份层 + 资源层 + 控制层）")
            else:
                # 旧模式兼容：直接渲染完整模板
                system_prompt = await assembler.assemble_system_prompt(
                    user_system_prompt=user_identity,
                    resource_context=resource_ctx,
                    **render_vars,
                )
                logger.info("PromptAssembler: 旧模式兼容渲染完成")

            user_prompt = await assembler.assemble_user_prompt(
                user_prompt_prefix=user_prompt_prefix,
                memory_content=None
                if self.use_message_list_history
                else memory_content,
                question=user_question,
                **render_vars,
            )

        except Exception as e:
            logger.warning(f"PromptAssembler: 组装失败，回退到默认 prompt: {e}")
            import traceback

            traceback.print_exc()
            try:
                from derisk.util.template_utils import render

                system_prompt = render(
                    REACT_MASTER_FC_SYSTEM_TEMPLATE_CN,
                    {
                        "agent_name": getattr(self.profile, "name", "Assistant")
                        if hasattr(self, "profile")
                        else "Assistant",
                        "max_steps": "20",
                        "resource_prompt": "",
                        "sandbox_prompt": "",
                        "sandbox": {"enable": False, "prompt": ""},
                        "available_agents": "",
                        "available_knowledges": "",
                        "available_skills": "",
                    },
                )
            except Exception as render_error:
                logger.error(f"回退渲染也失败: {render_error}")
                system_prompt = "你是一个 AI 助手，请帮助用户完成任务。"
            user_prompt = user_question

        filtered_messages = [
            msg
            for msg in messages
            if not (hasattr(msg, "role") and msg.role == ModelMessageRoleType.SYSTEM)
            and not (isinstance(msg, dict) and msg.get("role") == "system")
        ]

        if filtered_messages:
            last_idx = len(filtered_messages) - 1
            last_msg = filtered_messages[last_idx]
            is_human = (
                hasattr(last_msg, "role")
                and last_msg.role == ModelMessageRoleType.HUMAN
            ) or (isinstance(last_msg, dict) and last_msg.get("role") == "human")
            if is_human:
                filtered_messages.pop()

        if system_prompt:
            from derisk.agent.core.types import AgentMessage

            filtered_messages.insert(
                0,
                AgentMessage(
                    content=system_prompt,
                    role=ModelMessageRoleType.SYSTEM,
                ),
            )

        # Message List 模式：插入历史消息到消息列表
        if self.use_message_list_history and history_messages:
            from derisk.agent.core.types import AgentMessage

            for hist_msg in history_messages:
                filtered_messages.append(
                    AgentMessage(
                        content=hist_msg.get("content", ""),
                        role=hist_msg.get("role", "user"),
                        context=hist_msg,
                    )
                )
            logger.info(
                f"[HistoryMessageBuilder] Injected {len(history_messages)} history messages"
            )

        if user_prompt:
            from derisk.agent.core.types import AgentMessage

            filtered_messages.append(
                AgentMessage(
                    content=user_prompt,
                    role=ModelMessageRoleType.HUMAN,
                    context=received_message.context if received_message else None,
                    content_types=received_message.content_types
                    if received_message
                    else None,
                ),
            )

        return filtered_messages, context, system_prompt, user_prompt

    async def _get_worklog_tool_messages(
        self, max_entries: int = 30
    ) -> List[Dict[str, Any]]:
        """
        将 WorkLog 历史转换为原生 Function Call 格式的工具消息列表。

        重写基类方法，从 compaction_pipeline 获取历史工具调用记录。

        核心设计：压缩后的条目使用摘要替代原始内容，保证上下文管理有效。
        - 历史 WorkLog 压缩后，用摘要替代原始结果
        - 当前轮次保持原生 Function Call 模式

        遵循 OpenAI Function Call 协议：
        [
            {"role": "assistant", "content": "", "tool_calls": [...]},
            {"role": "tool", "tool_call_id": "...", "content": "..."},
            ...
        ]

        Args:
            max_entries: 最大获取的 WorkEntry 数量

        Returns:
            符合原生 Function Call 格式的消息列表
        """
        pipeline = await self._ensure_compaction_pipeline()
        if not pipeline:
            return []

        try:
            # 使用压缩摘要，保证上下文连续性
            tool_messages = await pipeline.get_tool_messages_from_worklog(
                max_entries=max_entries,
                use_compressed_summary=True,  # 默认值，显式声明
            )
            if tool_messages:
                logger.info(
                    f"Converted WorkLog to {len(tool_messages)} tool messages for LLM"
                )
            return tool_messages
        except Exception as e:
            logger.warning(f"Failed to get worklog tool messages: {e}")
            return []

    @staticmethod
    def _extract_text_from_content(content) -> str:
        """从 LLM 消息的 content 字段提取纯文本。"""
        if not content:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    obj = item.get("object", {})
                    if isinstance(obj, dict):
                        text_parts.append(obj.get("data", ""))
                elif hasattr(item, "object"):
                    obj = getattr(item, "object", None)
                    if obj and hasattr(obj, "data"):
                        text_parts.append(getattr(obj, "data", ""))
            return "\n".join(filter(None, text_parts))
        return str(content)

    def _estimate_context_tokens(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """估算实际上下文窗口的 token 使用情况"""
        CHARS_PER_TOKEN = 4
        message_tokens = 0
        tool_tokens = 0

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                msg_chars = len(content)
            else:
                msg_chars = len(str(content))

            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                msg_chars += len(json.dumps(tool_calls))

            msg_token_estimate = max(1, msg_chars // CHARS_PER_TOKEN)
            message_tokens += msg_token_estimate

        if tools:
            tools_json = json.dumps(tools)
            tool_chars = len(tools_json)
            tool_tokens = max(1, tool_chars // CHARS_PER_TOKEN)

        return {
            "total_tokens": message_tokens + tool_tokens,
            "message_tokens": message_tokens,
            "tool_tokens": tool_tokens,
        }

    async def thinking(
        self,
        messages: List[AgentMessage],
        reply_message_id: str,
        sender: Optional[Agent] = None,
        prompt: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        reply_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> Optional[AgentLLMOut]:
        """重写 thinking 方法 - 使用 Message List 模式注入历史对话。

        核心改动：
        1. 将用户消息记录到 WorkLog
        2. 通过 HistoryMessageBuilder 从 WorkLog + GptsMessage 统一构建消息列表
        3. 不使用 base_agent 的 tool_messages 机制，改由 builder 统一管理
        4. 确保工具列表每轮刷新
        """
        from datetime import datetime
        from derisk.agent.core.base_agent import _new_system_message

        # ========== 确保核心组件已初始化 ==========
        await self._ensure_work_log_manager()
        await self._ensure_history_message_builder()

        # ========== 获取基本上下文 ==========
        conv_id = "default"
        session_id = "default"
        if self.not_null_agent_context:
            conv_id = self.not_null_agent_context.conv_id or "default"
            session_id = self.not_null_agent_context.conv_session_id or conv_id

        # ========== 提取当前用户消息 ==========
        current_user_content = None
        if received_message and received_message.content:
            current_user_content = self._extract_text_from_content(
                received_message.content
            )

        # ========== 记录用户消息到 WorkLog ==========
        # 仅在首次调用时录入（current_retry_counter == 0）
        if current_user_content and self._work_log_manager and self.current_retry_counter == 0:
            try:
                await self._work_log_manager.record_user_message(
                    user_content=current_user_content,
                    conv_id=conv_id,
                )
            except Exception as e:
                logger.warning(f"Failed to record user message to work_log: {e}")

        # ========== 确保工具列表每轮刷新 ==========
        if self.current_retry_counter > 0:
            try:
                self.function_calling_context = await self.function_calling_params()
                logger.info(
                    f"[ToolRefresh] Refreshed function_calling_context on retry {self.current_retry_counter}"
                )
            except Exception as e:
                logger.warning(f"Failed to refresh function_calling_context: {e}")

        # ========== 计算上下文预算 ==========
        context_window = await self.get_agent_llm_context_length()
        history_budget = int(context_window * 0.85)

        logger.info(
            f"[ContextBudget] context_window={context_window}, "
            f"history_budget={history_budget}"
        )

        # ========== 通过 HistoryMessageBuilder 统一构建消息 ==========
        all_conversation_messages = []
        history_layer_tokens = {"hot": 0, "warm": 0, "cold": 0}
        build_result: Optional[BuildResult] = None

        if self._history_message_builder:
            try:
                build_result = await self._history_message_builder.build_messages_with_result(
                    current_conv_id=conv_id,
                    session_id=session_id,
                    context_window=history_budget,
                    include_current_conversation=True,
                )
                all_conversation_messages = build_result.messages
                history_layer_tokens = build_result.layer_tokens

                logger.info(
                    f"[HistoryMessageBuilder] Built {len(all_conversation_messages)} total messages, "
                    f"layer_tokens={history_layer_tokens}"
                )
            except Exception as e:
                logger.error(f"[CRITICAL] Failed to build messages: {e}", exc_info=True)

        # ========== Fallback: 若 builder 不可用，使用 base_agent 的 tool_messages ==========
        if not all_conversation_messages:
            logger.info("[Fallback] HistoryMessageBuilder unavailable, using base tool_messages")

            # 异步任务完成通知注入
            async_notification = await self._collect_async_task_notifications()
            if async_notification:
                notification_msg = {"role": "user", "content": async_notification}
                tool_msgs = kwargs.get("tool_messages") or []
                tool_msgs.append(notification_msg)
                kwargs["tool_messages"] = tool_msgs

            if self._system_event_manager:
                self._system_event_manager.add_event(
                    event_type=SystemEventType.LLM_THINKING,
                    title="LLM 思考",
                    description=f"Agent: {self.name}",
                )

            return await super().thinking(
                messages,
                reply_message_id,
                sender,
                prompt=prompt,
                received_message=received_message,
                reply_message=reply_message,
                **kwargs,
            )

        # ========== 注入 user_prompt 到最后一条 HUMAN 消息 ==========
        user_prompt = getattr(reply_message, "user_prompt", None) if reply_message else None
        if user_prompt and user_prompt.strip() and all_conversation_messages:
            for i in range(len(all_conversation_messages) - 1, -1, -1):
                role = all_conversation_messages[i].get("role", "")
                if role in ("human", "user"):
                    original_content = all_conversation_messages[i].get("content", "")
                    if isinstance(original_content, list):
                        new_content = [{"type": "text", "text": user_prompt}]
                        new_content.extend(
                            part for part in original_content if part.get("type") != "text"
                        )
                        all_conversation_messages[i] = {
                            **all_conversation_messages[i],
                            "content": new_content,
                        }
                    else:
                        all_conversation_messages[i] = {
                            **all_conversation_messages[i],
                            "content": user_prompt,
                        }
                    logger.info(
                        f"[UserPromptInjection] Replaced last human message (index={i})"
                    )
                    break

        # ========== 异步任务通知注入 ==========
        async_notification = await self._collect_async_task_notifications()
        if async_notification:
            all_conversation_messages.append(
                {"role": "user", "content": async_notification}
            )
            logger.info("[ReActMasterAgent] 注入异步任务完成通知到消息列表")

        # ========== 构建最终 LLM 消息列表 ==========
        llm_messages = []

        # 1. System message
        # prompt 参数优先；若无，从 reply_message.system_prompt 获取（load_thinking_messages 设置）；
        # 再无，从 messages 参数中提取第一个 system 消息
        system_prompt_text = prompt
        if not system_prompt_text and reply_message:
            system_prompt_text = getattr(reply_message, "system_prompt", None)
        if not system_prompt_text and messages:
            for m in messages:
                m_role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
                if m_role and str(m_role).lower() in ("system", ModelMessageRoleType.SYSTEM):
                    m_content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
                    if m_content:
                        system_prompt_text = str(m_content)
                    break
        if system_prompt_text:
            llm_messages.extend(_new_system_message(system_prompt_text))

        # 2. 所有对话消息（历史 + 当前）
        if all_conversation_messages:
            llm_messages.extend(all_conversation_messages)

        logger.info(
            f"[MSG_DEBUG] Final llm_messages: count={len(llm_messages)}, "
            f"roles={[m.get('role') for m in llm_messages[:10]]}"
        )

        # ========== 记录 LLM 思考事件 ==========
        if self._system_event_manager:
            self._system_event_manager.add_event(
                event_type=SystemEventType.LLM_THINKING,
                title="LLM 思考",
                description=f"Agent: {self.name}",
            )

        # ========== 调用 LLM ==========
        if not self.llm_client:
            raise ValueError("LLM client is not initialized!")

        last_model = None
        last_err = None
        retry_count = 0
        start_time: datetime = datetime.now()
        MAX_ATTEMPTS = 3

        while retry_count < MAX_ATTEMPTS:
            llm_model = None
            llm_context = None
            try:
                llm_model, llm_context = await self.select_llm_model(last_model)

                # 统计上下文使用
                tools_for_context = None
                if self.function_calling_context and "tools" in self.function_calling_context:
                    tools_for_context = self.function_calling_context.get("tools")

                context_stats = self._estimate_context_tokens(
                    llm_messages, tools_for_context
                )
                logger.info(
                    f"[ContextWindow] Total tokens: {context_stats['total_tokens']}, "
                    f"messages: {context_stats['message_tokens']}, "
                    f"tools: {context_stats['tool_tokens']}, "
                    f"history_layers: {history_layer_tokens}"
                )

                prev_thinking = ""
                prev_content = ""
                agent_llm_out = None
                thinking_chunk_count = 0
                content_chunk_count = 0
                import time as time_mod
                start_ms = int(time_mod.time() * 1000)

                async for output in self.llm_client.create(
                    context=llm_messages[-1].pop("context", None) if llm_messages else None,
                    messages=llm_messages,
                    llm_model=llm_model,
                    mist_keys=self.mist_keys,
                    max_new_tokens=self.not_null_agent_context.max_new_tokens,
                    temperature=self.not_null_agent_context.temperature,
                    llm_context=llm_context,
                    verbose=self.not_null_agent_context.verbose,
                    trace_id=self.not_null_agent_context.trace_id,
                    rpc_id=self.not_null_agent_context.rpc_id,
                    function_calling_context=self.function_calling_context,
                    staff_no=self.not_null_agent_context.staff_no,
                ):
                    agent_llm_out = output
                    current_thinking = output.thinking_content
                    current_content = output.content

                    if self.not_null_agent_context.incremental:
                        res_thinking = current_thinking[len(prev_thinking):]
                        res_content = current_content[len(prev_content):]
                        prev_thinking = current_thinking
                        temp_prev_content = current_content
                    else:
                        res_thinking = (
                            current_thinking.strip().replace("\\n", "\n")
                            if current_thinking
                            else current_thinking
                        )
                        res_content = (
                            current_content.strip().replace("\\n", "\n")
                            if current_content
                            else current_content
                        )
                        prev_thinking = res_thinking
                        temp_prev_content = res_content

                    if len(prev_thinking) > 0 and len(temp_prev_content) <= 0:
                        thinking_chunk_count += 1
                    if len(prev_content) > 0:
                        content_chunk_count += 1
                    is_first_chunk = thinking_chunk_count == 1
                    is_first_content = content_chunk_count == 1

                    await self.listen_thinking_stream(
                        output,
                        reply_message_id,
                        start_time=start_time,
                        cu_thinking_incr=res_thinking,
                        cu_content_incr=res_content,
                        is_first_chunk=is_first_chunk,
                        is_first_content=is_first_content,
                        received_message=received_message,
                        reply_message=reply_message,
                        sender=sender,
                        prev_content=prev_content,
                    )

                    prev_content = temp_prev_content

                if agent_llm_out is None:
                    raise Exception(f"Model {llm_model} returned empty response")

                logger.info(
                    f"[LLM_RESPONSE] model={llm_model}, "
                    f"content_length={len(agent_llm_out.content) if agent_llm_out.content else 0}"
                )

                # ========== 应用 BuildResult 清理 ==========
                if build_result and self.memory and hasattr(self.memory, "gpts_memory"):
                    try:
                        cleanup_hints = build_result.get_cache_cleanup_hints()
                        if cleanup_hints.get("can_evict_message_ids") or cleanup_hints.get("can_evict_entry_message_ids"):
                            cleanup_stats = await self.memory.gpts_memory.apply_build_result_cleanup(
                                conv_id, cleanup_hints
                            )
                            if self._work_log_manager:
                                evictable = set(cleanup_hints.get("can_evict_entry_message_ids", []))
                                self._work_log_manager.trim_work_log(evictable)
                            logger.info(f"[Cleanup] Applied: {cleanup_stats}")
                    except Exception as cleanup_err:
                        logger.warning(f"[Cleanup] Failed to apply build result cleanup: {cleanup_err}")

                return agent_llm_out

            except Exception as e:
                last_model = llm_model
                last_err = str(e)
                retry_count += 1
                logger.warning(
                    f"[LLM Retry] Attempt {retry_count}/{MAX_ATTEMPTS}, "
                    f"model {llm_model} failed: {str(e)[:200]}"
                )

        raise Exception(
            f"Failed to get response from LLM after {MAX_ATTEMPTS} attempts. "
            f"Last error: {last_err}"
        )

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
            filtered_kwargs["agent_file_system"] = afs
            filtered_kwargs["max_output_bytes"] = (
                self._truncator_max_bytes
                if hasattr(self, "_truncator_max_bytes")
                else 5 * 1024
            )
            filtered_kwargs["max_output_lines"] = (
                self._truncator_max_lines
                if hasattr(self, "_truncator_max_lines")
                else 50
            )

            tasks = []
            batch_init_action_reports = []
            has_blank_action = False

            for real_action in real_actions:
                if isinstance(real_action, BlankAction):
                    has_blank_action = True
                    logger.warning(
                        "⚠️ No tool call returned by LLM, will inject system reminder"
                    )

                # 预检查：获取工具名称并检查是否被禁止
                tool_name_to_check = None
                if hasattr(real_action, "action_input") and hasattr(
                    real_action.action_input, "tool_name"
                ):
                    tool_name_to_check = real_action.action_input.tool_name
                elif hasattr(real_action, "name"):
                    tool_name_to_check = real_action.name

                if tool_name_to_check and self._is_tool_blocked(tool_name_to_check):
                    logger.warning(
                        f"🚫 Tool '{tool_name_to_check}' is blocked due to consecutive failures. Skipping execution."
                    )
                    # 直接创建失败结果，跳过执行
                    blocked_output = ActionOutput(
                        content=f"工具 [{tool_name_to_check}] 连续失败超过 {self._max_tool_failure_count} 次，已终止执行。请尝试使用其他工具或修改参数后重试。",
                        name=real_action.name
                        if hasattr(real_action, "name")
                        else tool_name_to_check,
                        action=tool_name_to_check,
                        action_name=tool_name_to_check,
                        is_exe_success=False,
                        state=Status.FAILED.value,
                        have_retry=False,
                        view=f"❌ **工具执行被阻止**\n\n工具 `{tool_name_to_check}` 已连续失败多次，系统已自动终止该工具的执行。\n\n请尝试使用其他工具或修改参数后重试。",
                    )
                    act_outs.append(blocked_output)
                    continue

                if hasattr(real_action, "prepare_init_msg"):
                    init_report = await real_action.prepare_init_msg(
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
                    if init_report:
                        batch_init_action_reports.append(init_report)

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
                    skip_init_push=True,
                    **filtered_kwargs,
                )
                tasks.append((real_action, task))

            if batch_init_action_reports:
                await self.memory.gpts_memory.push_message(
                    conv_id=self.not_null_agent_context.conv_id,
                    stream_msg={
                        "uid": message.message_id,
                        "type": "all",
                        "sender": self.name or self.role,
                        "sender_role": self.role,
                        "message_id": message.message_id,
                        "avatar": self.avatar,
                        "goal_id": message.goal_id,
                        "conv_id": self.not_null_agent_context.conv_id,
                        "conv_session_uid": self.not_null_agent_context.conv_session_id,
                        "app_code": self.not_null_agent_context.gpts_app_code,
                        "start_time": None,
                        "action_report": batch_init_action_reports,
                    },
                )

            # 并行执行所有任务
            results = await asyncio.gather(
                *[task for _, task in tasks], return_exceptions=True
            )

            # 处理执行结果
            for (real_action, _), result in zip(tasks, results):
                # 获取工具名称（用于失败追踪）
                tool_name_for_tracking = None

                if isinstance(result, Exception):
                    logger.exception(f"Action execution failed: {result}")
                    # 从 action 中提取工具名称
                    tool_name_for_tracking = getattr(real_action, "action_input", None)
                    if tool_name_for_tracking and hasattr(
                        tool_name_for_tracking, "tool_name"
                    ):
                        tool_name_for_tracking = tool_name_for_tracking.tool_name
                    else:
                        tool_name_for_tracking = real_action.name

                    # 检查工具失败次数
                    should_stop = self._check_and_record_tool_failure(
                        tool_name_for_tracking
                    )

                    # 创建完整的失败 ActionOutput
                    failed_output = ActionOutput(
                        content=f"工具执行失败: {str(result)}",
                        name=real_action.name,
                        action=tool_name_for_tracking,
                        action_name=tool_name_for_tracking,
                        is_exe_success=False,
                        state=Status.FAILED.value,
                        have_retry=not should_stop,
                    )

                    if should_stop:
                        failed_output.content = f"工具 [{tool_name_for_tracking}] 连续失败超过 {self._max_tool_failure_count} 次，已终止执行。错误: {str(result)}"
                        failed_output.view = f"❌ **工具执行失败**\n\n工具 `{tool_name_for_tracking}` 已连续失败多次，系统已自动终止该工具的执行。\n\n**错误信息**: {str(result)}\n\n请尝试使用其他工具或修改参数后重试。"

                    act_outs.append(failed_output)

                    # 失败也要记录到 WorkLog（确保消息列表中有对应的 tool result）
                    if isinstance(real_action, (FunctionTool, ToolAction)):
                        tc_id_fail = getattr(real_action, "action_uid", None)
                        await self._record_action_to_work_log(
                            tool_name_for_tracking, {}, failed_output,
                            tool_call_id=tc_id_fail,
                        )
                else:
                    if result:
                        # 提取工具信息
                        tool_name = result.action or real_action.name
                        tool_args = {}

                        # 从 action 中获取参数
                        if hasattr(real_action, "execute_params"):
                            tool_args = getattr(real_action, "execute_params", {})

                        logger.info(
                            f"🎯 Tool executed: {tool_name}, success={result.is_exe_success if hasattr(result, 'is_exe_success') else 'unknown'}"
                        )

                        # 追踪 Skill 内容（用于 compaction 后重新注入）
                        if tool_name == "skill_read" and result.is_exe_success and result.content:
                            skill_name = tool_args.get("skill_name", "")
                            if skill_name:
                                self._invoked_skills[skill_name] = result.content
                                logger.info(f"📚 Tracked invoked skill: {skill_name}")

                        # 记录系统事件
                        if self._system_event_manager:
                            event_type = (
                                SystemEventType.ACTION_COMPLETE
                                if result.is_exe_success
                                else SystemEventType.ACTION_FAILED
                            )
                            self._system_event_manager.add_event(
                                event_type=event_type,
                                title=f"{tool_name} {'完成' if result.is_exe_success else '失败'}",
                            )

                        # 记录到 PhaseManager
                        self.record_phase_action(tool_name, result.is_exe_success)

                        # 工具执行成功或失败时，重置该工具的连续失败计数
                        if result.is_exe_success:
                            self._reset_tool_failure_count(tool_name)
                        else:
                            # 工具执行失败（非异常），也记录失败次数
                            should_stop = self._check_and_record_tool_failure(tool_name)
                            if should_stop:
                                result.content = f"工具 [{tool_name}] 连续失败超过 {self._max_tool_failure_count} 次，已终止执行。\n\n{result.content or ''}"
                                result.view = f"❌ **工具执行失败**\n\n工具 `{tool_name}` 已连续失败多次，系统已自动终止该工具的执行。\n\n{result.view or result.content or ''}"

                        # ========== 集成：记录到 WorkLog ==========
                        # 重要：只有真正的工具调用才应该记录到 WorkLog
                        # 真正的工具包括两类：
                        # 1. FunctionTool 的 Action 子类：AgentStart, KnowledgeSearch 等
                        # 2. ToolAction 的子类：执行外部工具的基础 Action
                        # BlankAction 不是工具，它只是 LLM 返回纯文本时的占位 Action
                        # 记录非工具会导致生成假的 tool_calls 消息，引发 OpenAI API 错误
                        if isinstance(real_action, (FunctionTool, ToolAction)):
                            # WAITING 状态区分两种场景：
                            # 1. 工具授权 WAITING：工具尚未执行，等待用户授权 → 不记录 work_log
                            # 2. ask_user WAITING：工具已执行（问题已推送给用户），等待用户回复 → 需要记录
                            is_waiting = getattr(result, "state", None) == Status.WAITING.value
                            is_ask_user = getattr(result, "ask_user", False)
                            if is_waiting and not is_ask_user:
                                logger.info(
                                    f"📝 Skipping WorkLog for {tool_name} (WAITING for authorization)"
                                )
                            else:
                                tc_id = getattr(real_action, "action_uid", None) or getattr(result, "action_id", None)
                                assistant_content = message.content if message else None
                                await self._record_action_to_work_log(
                                    tool_name, tool_args, result,
                                    tool_call_id=tc_id,
                                    assistant_content=assistant_content,
                                )
                        else:
                            logger.info(
                                f"📝 Skipping WorkLog record for {real_action.__class__.__name__} (not a tool)"
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
                            if self.report_auto_generate:
                                try:
                                    report_content = await self.generate_report(
                                        report_type=self.report_default_type,
                                        report_format=self.report_default_format,
                                        save_to_file=True,
                                    )
                                    if report_content:
                                        if result.extra is None:
                                            result.extra = {}
                                        result.extra["report"] = report_content
                                        if result.view:
                                            result.view += f"\n\n---\n## 📋 Task Report\n\n{report_content[:2000]}"
                                        else:
                                            result.view = f"## 📋 Task Report\n\n{report_content[:2000]}"
                                        logger.info(
                                            f"Auto-generated report attached to result"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to auto-generate report: {e}"
                                    )

                            # 切换到完成阶段
                            self.set_phase("complete", "任务全部完成")

                            # Layer 4: 完成当前对话轮次
                            try:
                                pipeline = await self._ensure_compaction_pipeline()
                                if pipeline:
                                    ai_response = result.view or result.content or ""
                                    await pipeline.complete_conversation_round(
                                        ai_response=ai_response,
                                        ai_thinking=result.content or "",
                                    )
                                    logger.info("Layer 4: Completed conversation round")
                            except Exception as e:
                                logger.warning(
                                    f"Layer 4: Failed to complete conversation round: {e}"
                                )

                        act_outs.append(result)
                    else:
                        logger.warning(
                            f"⚠️ Tool execution returned None/empty result for action: {real_action.name}"
                        )

                await self.push_context_event(
                    EventType.AfterAction,
                    ActionPayload(action_output=result),
                    await self.task_id_by_received_message(received_message),
                )

            # 只在BlankAction不终止时才注入提醒（避免简单对话进入死循环）
            if has_blank_action and act_outs:
                # 检查BlankAction是否应该终止（terminate=True表示应该结束任务）
                blank_action_output = act_outs[0]
                if not blank_action_output.terminate:
                    await self._inject_no_tool_call_reminder(
                        blank_action_output, message.message_id
                    )

        return act_outs

    async def _inject_no_tool_call_reminder(
        self, action_output: ActionOutput, message_id: str
    ):
        """
        当没有工具调用时，注入系统提醒消息，引导继续推进任务

        Args:
            action_output: 当前执行的 ActionOutput
            message_id: 关联的消息ID
        """
        from derisk.agent.core.memory.gpts.agent_system_message import (
            AgentSystemMessage,
            AgentPhase,
            SystemMessageType,
        )

        if not self.not_null_agent_context:
            return

        reminder_content = """【系统提醒】你没有调用任何工具来推进任务。

请遵循以下原则继续执行：
1. **必须使用工具**：调用合适的工具来完成任务，不能只输出文本
2. **循环只能通过 terminate 工具结束**：如果你想结束任务，请调用 terminate 工具
3. **推进任务**：根据当前任务目标，选择下一步操作

可用工具包括：
- 信息获取：read_file, search, grep 等
- 任务执行：调用相关工具执行具体操作
- 任务结束：terminate（仅在任务完成时使用）

请立即调用工具继续执行任务！"""

        try:
            system_message = AgentSystemMessage.build(
                agent_context=self.agent_context,
                agent=self,
                type=SystemMessageType.STATUS,
                phase=AgentPhase.ACTION_RUN,
                content=reminder_content,
                final_status=Status.RUNNING,
                reply_message_id=message_id,
            )

            if self.memory and self.memory.gpts_memory:
                await self.memory.gpts_memory.append_system_message(system_message)
                logger.info(
                    "✅ Injected no-tool-call reminder to guide task continuation"
                )
        except Exception as e:
            logger.warning(f"Failed to inject no-tool-call reminder: {e}")

    async def _attach_delivery_files(
        self, action_out: "ActionOutput"
    ) -> "ActionOutput":
        """为 action 附加交付文件.

        从AgentFileSystem收集所有结论文件和交付物文件，
        附加到ActionOutput的output_files字段中。
        """
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

    def _check_and_record_tool_failure(self, tool_name: str) -> bool:
        """
        记录工具失败并检查是否应停止执行

        Args:
            tool_name: 工具名称

        Returns:
            bool: 是否应该停止执行该工具（失败次数超过阈值）
        """
        if not tool_name:
            return False

        # 增加失败计数
        self._tool_failure_counts[tool_name] = (
            self._tool_failure_counts.get(tool_name, 0) + 1
        )
        failure_count = self._tool_failure_counts[tool_name]

        logger.warning(
            f"⚠️ Tool '{tool_name}' failed ({failure_count}/{self._max_tool_failure_count} consecutive failures)"
        )

        # 检查是否超过阈值
        if failure_count >= self._max_tool_failure_count:
            logger.error(
                f"🚫 Tool '{tool_name}' has failed {failure_count} times consecutively. "
                f"Blocking further execution of this tool."
            )
            return True

        return False

    def _is_tool_blocked(self, tool_name: str) -> bool:
        """
        检查工具是否已被禁止执行（失败次数超过阈值）

        Args:
            tool_name: 工具名称

        Returns:
            bool: 是否已被禁止
        """
        if not tool_name:
            return False
        failure_count = self._tool_failure_counts.get(tool_name, 0)
        return failure_count >= self._max_tool_failure_count

    def _reset_tool_failure_count(self, tool_name: str = None):
        """
        重置工具失败计数

        Args:
            tool_name: 工具名称，如果为 None 则重置所有工具
        """
        if tool_name:
            self._tool_failure_counts[tool_name] = 0
        else:
            self._tool_failure_counts.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取 Agent 运行统计信息"""
        stats = {
            "tool_call_count": self._tool_call_count,
            "compaction_count": self._compaction_count,
            "prune_count": self._prune_count,
            "tool_failure_counts": dict(self._tool_failure_counts),
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
        self._tool_failure_counts.clear()

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

            # Sandbox mode: skill_dir comes from the sandbox client
            # (e.g. /mnt/derisk/skills set in [sandbox].skill_dir of the toml).
            # Local mode: default to DATA_DIR/skill (pilot/data/skill).
            sandbox_skill_dir: Optional[str] = None
            sandbox_enabled = False
            if instance and getattr(instance, "sandbox_manager", None):
                sb_client = getattr(instance.sandbox_manager, "client", None)
                if sb_client:
                    sandbox_skill_dir = getattr(sb_client, "skill_dir", None)
                    sandbox_enabled = True

            local_skill_dir = os.path.join(DATA_DIR, "skill")
            logger.info(
                f"var_skills: sandbox_enabled={sandbox_enabled}, "
                f"sandbox_skill_dir={sandbox_skill_dir!r}, "
                f"local_skill_dir={local_skill_dir!r}"
            )

            prompts = ""
            # Add sandbox environment info if sandbox is enabled
            if sandbox_enabled and sandbox_skill_dir:
                prompts += (
                    "以下技能存储在沙箱环境中，路径为沙箱内的绝对路径。\n"
                    f"技能目录：{sandbox_skill_dir}\n"
                    "使用方式：使用 `skill_read` 工具加载技能的 SKILL.md 指令，使用 `skill_exec` 执行技能目录中的脚本。\n\n"
                )

            for k, v in self.resource_map.items():
                if isinstance(v[0], AgentSkillResource):
                    for item in v:
                        skill_item: AgentSkillResource = item  # type:ignore
                        mode, branch = "release", "master"
                        debug_info = getattr(skill_item, "debug_info", None)
                        if debug_info and debug_info.get("is_debug"):
                            mode, branch = "debug", debug_info.get("branch")
                        skill_meta = skill_item.skill_meta(mode)
                        if not skill_meta:
                            continue

                        # skill_code is the UUID (DeriskSkillResource) or dir name.
                        skill_code = getattr(
                            skill_item, "_skill_code", None
                        ) or getattr(skill_item, "skill_code", None)
                        if not skill_code and skill_meta.path:
                            skill_code = os.path.basename(skill_meta.path)

                        # Determine skill path based on sandbox mode
                        # If sandbox is enabled, use sandbox_skill_dir + skill_code (absolute path in sandbox)
                        # If sandbox is disabled, use local_skill_dir + skill_code (absolute path locally)
                        if sandbox_enabled and sandbox_skill_dir and skill_code:
                            skill_path = os.path.join(sandbox_skill_dir, skill_code)
                        elif skill_code:
                            skill_path = os.path.join(local_skill_dir, skill_code)
                        else:
                            skill_path = skill_meta.path

                        prompts += (
                            f"- <skill>"
                            f"<name>{skill_meta.name}</name>"
                            f"<description>{skill_meta.description}</description>"
                            f"<path>{skill_path}</path>"
                            f"<branch>{branch}</branch>"
                            f"<load_command>skill_read(skill_name=\"{skill_code}\")</load_command>"
                            f"\n</skill>\n"
                        )

            return prompts

        @self._vm.register("other_resources", "其他资源")
        async def var_other_resources(instance):
            logger.info("注入其他资源")

            excluded_types = (
                BaseTool,
                MCPToolPack,
                AppResource,
                AgentSkillResource,
                RetrieverResource,
            )

            prompts = ""
            for k, v in self.resource_map.items():
                if not isinstance(v[0], excluded_types):
                    for item in v:
                        try:
                            resource_type = item.type()
                            if isinstance(resource_type, str):
                                type_name = resource_type
                            else:
                                type_name = (
                                    resource_type.value
                                    if hasattr(resource_type, "value")
                                    else str(resource_type)
                                )

                            resource_prompt, _ = await item.get_prompt(
                                lang=instance.agent_context.language
                                if instance.agent_context
                                else "en"
                            )
                            if resource_prompt:
                                resource_name = (
                                    item.name if hasattr(item, "name") else k
                                )
                                prompts += f"- <{type_name}><name>{resource_name}</name><prompt>{resource_prompt}</prompt>\n</{type_name}>\n"
                        except Exception as e:
                            logger.warning(
                                f"Failed to get prompt for resource {k}: {e}"
                            )
                            continue
            return prompts

        @self._vm.register("sandbox", "沙箱配置")
        async def var_sandbox(instance):
            logger.info("注入沙箱配置信息，如果存在沙箱客户端即默认使用沙箱")
            if instance and instance.sandbox_manager:
                if instance.sandbox_manager.initialized == False:
                    logger.warning(
                        f"沙箱尚未准备完成!({instance.sandbox_manager.client.provider}-{instance.sandbox_manager.client.sandbox_id})"
                    )
                sandbox_client: SandboxBase = instance.sandbox_manager.client

                from derisk.agent.core.sandbox.prompt import (
                    AGENT_SKILL_SYSTEM_PROMPT,
                    SANDBOX_ENV_PROMPT,
                    SANDBOX_TOOL_BOUNDARIES,
                    sandbox_prompt,
                )

                env_param = {
                    "sandbox": {
                        "work_dir": sandbox_client.work_dir,
                        "skill_dir": sandbox_client.skill_dir,
                        "system_info": _get_sandbox_system_info(sandbox_client),
                    }
                }
                skill_param = {"sandbox": {"agent_skill_dir": sandbox_client.skill_dir}}

                param = {
                    "sandbox": {
                        "tool_boundaries": render(SANDBOX_TOOL_BOUNDARIES, {}),
                        "execution_env": render(SANDBOX_ENV_PROMPT, env_param),
                        "agent_skill_system": render(
                            AGENT_SKILL_SYSTEM_PROMPT, skill_param
                        )
                        if sandbox_client.enable_skill
                        else "",
                        "use_agent_skill": sandbox_client.enable_skill,
                    }
                }

                return {
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

        @self._vm.register("memory", "工作日志")
        async def var_memory(instance):
            """获取Layer 4压缩的历史对话记录作为 memory 变量

            四层架构设计：
            - Layer 1-3: 处理当前轮次的工具输出（截断、修剪、压缩）
            - Layer 4: 处理跨轮次对话历史的压缩

            memory 变量现在包含：
            - 历史轮次的压缩摘要（用户提问 + WorkLog摘要 + 答案摘要）
            - 不包含当前轮次的详细工具执行（通过原生Function Call传递）

            这种设计避免了重复：
            - 历史轮次：通过 memory 变量以摘要形式提供
            - 当前轮次：通过原生 tool messages 直接传递
            """
            logger.info("var_memory: fetching Layer 4 compressed history...")
            return await instance._get_layer4_history_for_memory()

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
            logger.info(
                f"var_work_log: fetched work log, entries={len(instance._work_log_manager.work_log)}"
            )
            return context

        logger.info(f"register_variables end {self.role}")

    async def _get_work_log_context_for_memory(self) -> str:
        """获取工具执行记录(WorkLog)上下文，用于整合到 memory 变量"""
        if not self.enable_work_log:
            return ""

        try:
            await self._ensure_work_log_manager()
            if not self._work_log_manager or not self._work_log_initialized:
                return ""

            await self._work_log_manager.initialize()
            context = await self._work_log_manager.get_context_for_prompt(
                max_entries=50
            )
            logger.info(
                f"_get_work_log_context_for_memory: entries={len(self._work_log_manager.work_log)}"
            )
            return context
        except Exception as e:
            logger.warning(f"Failed to get work log context: {e}")
            return ""

    async def _get_layer4_history_for_memory(self) -> str:
        """获取 Layer 4 压缩的跨轮次对话历史

        四层架构中的 Layer 4：处理多轮对话历史的压缩
        - 返回历史轮次的压缩摘要
        - 当前轮次的工具执行通过原生 Function Call 传递
        """
        try:
            pipeline = await self._ensure_compaction_pipeline()
            if not pipeline:
                logger.debug(
                    "Layer 4: Pipeline not available, falling back to work log"
                )
                return await self._get_work_log_context_for_memory()

            # 获取 Layer 4 压缩的历史记录
            history = await pipeline.get_layer4_history_for_prompt()
            if history:
                logger.info(
                    f"Layer 4: Retrieved compressed history ({len(history)} chars)"
                )
                return history
            else:
                logger.debug("Layer 4: No compressed history available")
                return ""
        except Exception as e:
            logger.warning(f"Layer 4: Failed to get compressed history: {e}")
            # 降级到 WorkLog
            return await self._get_work_log_context_for_memory()

    async def _ensure_work_log_manager(self):
        """确保 WorkLog 管理器已初始化

        存储策略：
        1. 优先使用 self.memory.gpts_memory 作为 WorkLogStorage（推荐）
        2. 回退使用 AgentFileSystem（向后兼容）
        """
        if not self.enable_work_log:
            logger.debug("_ensure_work_log_manager: work_log is disabled")
            return

        # 添加锁保护防止并发初始化
        if not hasattr(self, "_work_log_initialization_lock"):
            self._work_log_initialization_lock = asyncio.Lock()

        async with self._work_log_initialization_lock:
            # 双重检查
            if self._work_log_manager and self._work_log_initialized:
                logger.info(
                    "WorkLogManager already initialized, skipping re-initialization"
                )
                return

            logger.info("Initializing WorkLogManager...")

            conv_id = "default"
            session_id = "default"

            if self.not_null_agent_context:
                conv_id = self.not_null_agent_context.conv_id or "default"
                session_id = self.not_null_agent_context.conv_session_id or conv_id

            logger.info(
                f"WorkLogManager session info: conv_id={conv_id}, session_id={session_id}"
            )

            # 优先使用 gpts_memory 作为 WorkLogStorage
            work_log_storage = None
            afs = None
            if (
                self.memory
                and hasattr(self.memory, "gpts_memory")
                and self.memory.gpts_memory
            ):
                # GptsMemory 实现了 WorkLogStorage 接口
                work_log_storage = self.memory.gpts_memory  # type: ignore[assignment]
                logger.info("Using gpts_memory as WorkLogStorage (recommended)")

            # 回退到 AgentFileSystem
            if not work_log_storage:
                afs = await self._ensure_agent_file_system()
                if afs:
                    logger.info("Using AgentFileSystem for WorkLog (fallback mode)")

            self._work_log_manager = await create_work_log_manager(
                agent_id=self.name,
                session_id=session_id,
                agent_file_system=afs,
                work_log_storage=work_log_storage,
                context_window_tokens=self.work_log_context_window,
                compression_threshold_ratio=self.work_log_compression_ratio,
            )

            self._work_log_initialized = True
            logger.info(
                f"WorkLogManager initialized: agent_id={self.name}, session_id={session_id}, "
                f"storage_mode={self._work_log_manager.storage_mode}"
            )

            await self._work_log_manager.initialize()
            logger.info(
                f"WorkLogManager loaded: {len(self._work_log_manager.work_log)} entries"
            )

    async def _ensure_history_message_builder(self):
        """确保 HistoryMessageBuilder 已初始化。

        依赖 WorkLogManager 已初始化。
        """
        if self._history_builder_initialized and self._history_message_builder:
            return

        if not hasattr(self, "_history_builder_init_lock"):
            self._history_builder_init_lock = asyncio.Lock()

        async with self._history_builder_init_lock:
            if self._history_builder_initialized and self._history_message_builder:
                return

            # 确保 WorkLogManager 先初始化
            await self._ensure_work_log_manager()

            gpts_memory_ref = (
                self.memory.gpts_memory if self.memory else None
            )

            # 初始化 SessionHistoryManager（如果启用）
            session_history_manager = getattr(self, "_session_history_manager", None)
            if (
                getattr(self, "enable_session_history", False)
                and not session_history_manager
                and self.agent_context
            ):
                try:
                    from derisk.agent.core.memory.session_history import (
                        SessionHistoryManager,
                        SessionHistoryManagerConfig,
                    )

                    session_history_manager = SessionHistoryManager(
                        session_id=self.agent_context.conv_session_id,
                        gpts_memory=gpts_memory_ref,
                        config=SessionHistoryManagerConfig(
                            hot_ratio=0.45,
                            warm_ratio=0.25,
                            cold_ratio=0.10,
                        ),
                        work_log_manager=self._work_log_manager,
                    )
                    await session_history_manager.load_session_history()
                    self._session_history_manager = session_history_manager
                    logger.info(
                        f"SessionHistoryManager initialized: "
                        f"hot={len(session_history_manager.hot_conversations)}"
                    )
                except Exception as e:
                    logger.error(f"Failed to init SessionHistoryManager: {e}")

            # 创建 HistoryMessageBuilder
            try:
                config = CompressionConfig()
                llm_client = None
                if hasattr(self, "llm_client"):
                    llm_client = self.llm_client

                self._history_message_builder = await create_history_message_builder(
                    session_history_manager=session_history_manager,
                    work_log_manager=self._work_log_manager,
                    config=config,
                    llm_client=llm_client,
                    system_event_manager=self._system_event_manager,
                    gpts_memory=gpts_memory_ref,
                )
                self._history_builder_initialized = True
                logger.info("HistoryMessageBuilder initialized successfully")
            except Exception as e:
                logger.error(f"Failed to init HistoryMessageBuilder: {e}", exc_info=True)

    async def _ensure_system_event_manager(self):
        """确保 SystemEventManager 已初始化并设置到 GptsMemory"""
        if self._system_event_manager:
            return

        conv_id = "default"
        if self.not_null_agent_context:
            conv_id = self.not_null_agent_context.conv_id or "default"

        self._system_event_manager = SystemEventManager(conv_id=conv_id)

        # 记录初始化事件
        self._system_event_manager.add_event(
            event_type=SystemEventType.AGENT_BUILD_START,
            title="初始化 Agent 环境",
            description=f"Agent: {self.name}",
        )
        self._system_event_manager.add_event(
            event_type=SystemEventType.ENVIRONMENT_READY,
            title="运行环境就绪",
        )

        # 设置到 GptsMemory
        if (
            self.memory
            and hasattr(self.memory, "gpts_memory")
            and self.memory.gpts_memory
        ):
            await self.memory.gpts_memory.init(
                conv_id=conv_id,
                event_manager=self._system_event_manager,
            )
            logger.info(
                f"[ReActMasterAgent] SystemEventManager 已设置: conv_id={conv_id[:8]}"
            )

    async def _record_action_to_work_log(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]],
        action_output: ActionOutput,
        tool_call_id: Optional[str] = None,
        assistant_content: Optional[str] = None,
    ):
        """记录操作到 WorkLog

        Args:
            tool_name: 工具名称
            args: 工具参数
            action_output: 工具执行结果
            tool_call_id: LLM 返回的 tool_call id（用于与消息列表中的 tool_calls 关联）
            assistant_content: LLM 生成的 assistant 消息内容
        """
        if not self.enable_work_log:
            return

        await self._ensure_work_log_manager()

        if not self._work_log_manager:
            logger.warning(
                "Failed to initialize WorkLogManager, skipping work log recording"
            )
            return

        tags = []
        if not action_output.is_exe_success:
            tags.append("error")
        if action_output.content and len(action_output.content) > 10000:
            tags.append("large_output")

        # 获取当前 conv_id
        conv_id = None
        if self.not_null_agent_context:
            conv_id = self.not_null_agent_context.conv_id

        try:
            entry = await self._work_log_manager.record_action(
                tool_name=tool_name,
                args=args if args is not None else {},
                action_output=action_output,
                tags=tags,
                tool_call_id=tool_call_id,
                assistant_content=assistant_content,
                conv_id=conv_id,
            )
            logger.info(
                f"Recorded work log: tool={tool_name}, tool_call_id={tool_call_id}, "
                f"conv_id={conv_id}, success={action_output.is_exe_success}, "
                f"total_entries={len(self._work_log_manager.work_log)}"
            )
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

    async def _ensure_kanban_manager(self) -> Optional[KanbanManager]:
        """
        确保 Kanban 管理器已初始化（懒加载）

        Returns:
            KanbanManager 实例或 None
        """
        if not self.enable_kanban:
            return None

        if self._kanban_manager is not None and self._kanban_initialized:
            return self._kanban_manager

        if not self.not_null_agent_context:
            return None

        try:
            conv_id = self.not_null_agent_context.conv_id or "default"
            session_id = self.not_null_agent_context.conv_session_id or conv_id

            afs = await self._ensure_agent_file_system()

            kanban_storage = None
            if (
                self.memory
                and hasattr(self.memory, "gpts_memory")
                and self.memory.gpts_memory
            ):
                kanban_storage = self.memory.gpts_memory

            self._kanban_manager = await create_kanban_manager(
                agent_id=self.name,
                session_id=session_id,
                agent_file_system=afs,
                kanban_storage=kanban_storage,
                exploration_limit=self.kanban_exploration_limit,
            )

            self._kanban_initialized = True
            logger.info(
                f"KanbanManager initialized: agent_id={self.name}, session_id={session_id}, "
                f"storage_mode={self._kanban_manager.storage_mode}"
            )
            return self._kanban_manager

        except Exception as e:
            logger.warning(f"Failed to initialize KanbanManager: {e}")
            return None

    async def create_kanban(
        self, mission: str, stages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        创建看板

        Args:
            mission: 任务描述
            stages: 阶段列表，每个阶段包含:
                - stage_id: 阶段ID
                - description: 阶段描述
                - deliverable_type: 交付物类型
                - deliverable_schema: 交付物 Schema（可选）
                - depends_on: 依赖的阶段ID列表（可选）

        Returns:
            操作结果
        """
        if not self.enable_kanban:
            return {
                "status": "error",
                "message": "Kanban is not enabled. Set enable_kanban=True",
            }

        await self._ensure_kanban_manager()

        if not self._kanban_manager:
            return {"status": "error", "message": "Failed to initialize KanbanManager"}

        result = await self._kanban_manager.create_kanban(mission, stages)

        if result.get("status") == "success":
            self.set_phase("planning", "Kanban created, starting planning phase")

        return result

    async def submit_deliverable(
        self,
        stage_id: str,
        deliverable: Dict[str, Any],
        reflection: str = "",
    ) -> Dict[str, Any]:
        """
        提交当前阶段的交付物

        Args:
            stage_id: 阶段ID
            deliverable: 交付物数据
            reflection: 自我评估

        Returns:
            操作结果
        """
        if not self.enable_kanban or not self._kanban_manager:
            return {"status": "error", "message": "Kanban is not available"}

        result = await self._kanban_manager.submit_deliverable(
            stage_id, deliverable, reflection
        )

        if result.get("status") == "success":
            if result.get("all_completed"):
                self.set_phase("complete", "All stages completed")
            elif result.get("next_stage"):
                self.set_phase(
                    "execution", f"Moving to stage: {result['next_stage']['stage_id']}"
                )

        return result

    async def read_deliverable(self, stage_id: str) -> Dict[str, Any]:
        """
        读取指定阶段的交付物

        Args:
            stage_id: 阶段ID

        Returns:
            交付物内容
        """
        if not self.enable_kanban or not self._kanban_manager:
            return {"status": "error", "message": "Kanban is not available"}

        return await self._kanban_manager.read_deliverable(stage_id)

    async def get_kanban_status(self) -> str:
        """
        获取看板状态（用于 Prompt 注入）

        Returns:
            看板状态的 Markdown 文本
        """
        if not self.enable_kanban:
            return ""

        await self._ensure_kanban_manager()

        if not self._kanban_manager:
            return ""

        return await self._kanban_manager.get_kanban_status()

    async def get_current_stage_detail(self) -> str:
        """
        获取当前阶段详情（用于 Prompt 注入）

        Returns:
            当前阶段详情的 Markdown 文本
        """
        if not self.enable_kanban:
            return ""

        await self._ensure_kanban_manager()

        if not self._kanban_manager:
            return ""

        return await self._kanban_manager.get_current_stage_detail()

    def is_exploration_limit_reached(self) -> bool:
        """
        检查是否达到探索限制

        Returns:
            True 如果达到限制
        """
        if not self.enable_kanban or not self._kanban_manager:
            return False

        return self._kanban_manager.is_exploration_limit_reached()


# 导入需要的东西
from derisk.context.event import ActionPayload, EventType

# 导出
__all__ = [
    "ReActMasterAgent",
    "DoomLoopDetector",
    "SessionCompaction",
    "HistoryPruner",
    "KanbanManager",
    "validate_deliverable_schema",
]
