"""
ReActReasoningAgent - 长程任务推理Agent

完整迁移ReActMasterAgent的核心特性：
1. 末日循环检测
2. 上下文压缩
3. 输出截断
4. 历史修剪
5. 原生Function Call支持
6. 资源注入（skill、知识、自定义资源）
7. 沙箱环境支持
"""

from typing import AsyncIterator, Dict, Any, Optional, List
import logging
import json
import time

from .base_builtin_agent import BaseBuiltinAgent
from ..agent_info import AgentInfo
from ..llm_adapter import LLMAdapter, LLMConfig, LLMFactory
from ..tools_v2 import ToolRegistry, ToolResult
from ..sandbox_docker import SandboxManager
from .react_components import (
    DoomLoopDetector,
    OutputTruncator,
    ContextCompactor,
    HistoryPruner,
)

# 导入 PromptAssembler（通用 Prompt 组装模块）
from ...shared.prompt_assembly import (
    PromptAssembler,
    PromptAssemblyConfig,
    ResourceContext,
)

logger = logging.getLogger(__name__)


def _get_sandbox_system_info(sandbox_client) -> str:
    """Get system info description based on sandbox provider type."""
    provider = getattr(sandbox_client, "provider", lambda: "unknown")()

    if provider == "local":
        import platform

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


REACT_REASONING_SYSTEM_PROMPT = """你是一个遵循 ReAct (推理+行动) 范式的智能 AI 助手，用于解决复杂任务。

## 核心原则

1. **行动驱动**：每轮必须调用工具来推进任务，不要只是思考或总结
2. **持续探索**：工具返回结果后，必须继续调用新工具深入探索，直到完全解决问题
3. **系统性思维**：将复杂任务分解为可管理的步骤，逐步执行
4. **深度分析**：对工具返回的结果进行深入分析，发现新的线索和问题

## 工作流程

**重要：你必须持续调用工具，直到任务完全解决！**

1. **分析与规划**
   - 理解任务需求，制定详细执行计划
   - 根据任务性质选择最合适的工具

2. **执行与观察**（核心循环）
   - **必须**调用工具执行任务
   - 分析工具返回结果，提取关键信息
   - 如果结果不完整或有新发现，**必须**继续调用工具
   - 不要在第一个工具结果后就总结回答

3. **工具选择策略**（严格按优先级顺序选择工具）
   
   **优先级1（最高优先级） - 探索类工具**：
   - 查找特定内容、函数、变量、配置 → **必须优先用 `search`**（最高效）
   - 不确定目标位置或内容 → **先用 `search` 探索，而非 `list_files`**
   - `search` 找到结果后 → 用 `read` 深入阅读
   
   **优先级2 - 结构探索工具**：
   - 明确需要了解目录结构 → 用 `list_files`（仅在已知需要时使用）
   - **警告**：不要盲目使用 `list_files` 探索，使用 `search` 更高效
   
   **优先级3 - 操作工具**：
   - 已知文件路径需要阅读 → 用 `read` 读取
   - 需要执行命令 → 用 `bash`
   - 需要写入文件 → 用 `write`
   - 需要整理思路 → 用 `think`
   
   **默认行为**：遇到未知任务时，**先用 `search` 探索**，而不是逐个目录 `list_files`
   
   **禁止行为**：在探索不充分时直接回答

4. **完成判定**
   - 只有当你确信已经获得完整答案时才能停止
   - 如果还有不确定的地方，继续调用工具验证

## 可用工具

- `search`: 搜索文件内容（支持关键词和正则表达式，等同于 grep），适合查找特定代码、函数定义、配置项等
- `read`: 读取文件内容，适合阅读已知路径的文件
- `bash`: 执行shell命令，适合运行复杂命令或组合操作
- `write`: 写入文件
- `list_files`: 列出目录内容，适合了解项目结构
- `think`: 记录思考过程

当前Agent: {agent_name}
最大步骤: {max_steps}

{resource_prompt}
{sandbox_prompt}

## 立即行动

现在请调用工具开始执行任务！不要只是思考或总结。
"""


class ReActReasoningAgent(BaseBuiltinAgent):
    """
    ReAct推理Agent - 长程任务解决

    完整参考core架构的ReActMasterAgent实现，特性：
    1. 末日循环检测（DoomLoopDetector）
    2. 上下文压缩（ContextCompactor）
    3. 工具输出截断（OutputTruncator）
    4. 历史修剪（HistoryPruner）
    5. 原生Function Call支持
    6. 资源注入（skill、知识、自定义资源）
    7. 沙箱环境支持
    """

    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        resource: Optional[Any] = None,
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        enable_doom_loop_detection: bool = True,
        enable_output_truncation: bool = True,
        enable_context_compaction: bool = True,
        enable_history_pruning: bool = True,
        doom_loop_threshold: int = 3,
        max_output_lines: int = 2000,
        max_output_bytes: int = 50000,
        context_window: int = 128000,
        memory: Optional[Any] = None,
        use_persistent_memory: bool = False,
        enable_hierarchical_context: bool = True,
        hc_config: Optional[Any] = None,
        # New: compaction pipeline parameters
        enable_compaction_pipeline: bool = True,
        agent_file_system: Optional[Any] = None,
        work_log_storage: Optional[Any] = None,
        compaction_config: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            info=info,
            llm_adapter=llm_adapter,
            tool_registry=tool_registry,
            resource=resource,
            resource_map=resource_map,
            sandbox_manager=sandbox_manager,
            memory=memory,
            use_persistent_memory=use_persistent_memory,
            enable_hierarchical_context=enable_hierarchical_context,
            hc_config=hc_config,
            **kwargs,
        )

        self.enable_doom_loop_detection = enable_doom_loop_detection
        self.enable_output_truncation = enable_output_truncation
        # enable_context_compaction removed - Pipeline handles this
        # enable_history_pruning removed - Pipeline handles this

        self._doom_loop_detector = None
        self._output_truncator = None  # Kept as fallback
        # _context_compactor removed - replaced by UnifiedCompactionPipeline
        # _history_pruner removed - replaced by UnifiedCompactionPipeline
        self._resource_prompt_cache: Optional[str] = None
        self._sandbox_prompt_cache: Optional[str] = None

        # Compaction pipeline (lazy initialization)
        self._compaction_pipeline = None
        self._pipeline_initialized = False
        self._enable_compaction_pipeline = enable_compaction_pipeline
        self._compaction_config = compaction_config
        self._agent_file_system = agent_file_system
        self._work_log_storage = work_log_storage
        self._context_window = context_window
        self._max_output_lines = max_output_lines
        self._max_output_bytes = max_output_bytes

        if enable_doom_loop_detection:
            self._doom_loop_detector = DoomLoopDetector(threshold=doom_loop_threshold)

        # OutputTruncator kept as fallback for Layer 1 (Pipeline优先)
        if enable_output_truncation:
            self._output_truncator = OutputTruncator(
                max_lines=max_output_lines, max_bytes=max_output_bytes
            )

        # ContextCompactor removed in Phase 2 - replaced by UnifiedCompactionPipeline
        # HistoryPruner removed in Phase 2 - replaced by UnifiedCompactionPipeline

        # Initialize WorkLogStorage if not provided
        if self._work_log_storage is None and enable_compaction_pipeline:
            try:
                from ...core.memory.gpts.file_base import SimpleWorkLogStorage

                self._work_log_storage = SimpleWorkLogStorage()
            except Exception:
                pass

        # PromptAssembler 状态（通用 Prompt 组装器）
        self._prompt_assembler: Optional[PromptAssembler] = None

        logger.info(
            f"[ReActReasoningAgent] 初始化完成: "
            f"doom_loop={enable_doom_loop_detection}, "
            f"truncation={enable_output_truncation}, "
            f"compaction={enable_context_compaction}, "
            f"pruning={enable_history_pruning}, "
            f"compaction_pipeline={enable_compaction_pipeline}, "
            f"sandbox={sandbox_manager is not None}, "
            f"memory={'persistent' if use_persistent_memory else 'in-memory'}, "
            f"hierarchical_context={enable_hierarchical_context}"
        )

    def _get_default_tools(self) -> List[str]:
        """获取默认工具列表"""
        return ["bash", "read", "write", "search", "list_files"]

    def _get_prompt_assembler(self) -> PromptAssembler:
        """获取 Prompt 组装器（懒加载）"""
        if self._prompt_assembler is None:
            config = PromptAssemblyConfig(
                architecture="v2",
                language="zh",  # core_v2 默认使用中文
            )
            self._prompt_assembler = PromptAssembler(config)
        return self._prompt_assembler

    # ==================== Compaction Pipeline Support ====================

    async def _ensure_agent_file_system(self) -> Optional[Any]:
        """确保 AgentFileSystem 已初始化（懒加载）"""
        if self._agent_file_system:
            return self._agent_file_system

        try:
            from ...core.file_system.agent_file_system import AgentFileSystem

            session_id = self._session_id or self.info.name
            conv_id = getattr(self, "_conv_id", None) or session_id
            self._agent_file_system = AgentFileSystem(
                conv_id=conv_id,
                session_id=session_id,
            )
            await self._agent_file_system.sync_workspace()
            return self._agent_file_system
        except Exception as e:
            logger.warning(
                f"[ReActReasoningAgent] Failed to initialize AgentFileSystem: {e}"
            )
            return None

    async def _ensure_compaction_pipeline(self) -> Optional[Any]:
        """确保统一压缩管道已初始化（懒加载）"""
        if self._pipeline_initialized:
            return self._compaction_pipeline

        if not self._enable_compaction_pipeline:
            self._pipeline_initialized = True
            return None

        afs = await self._ensure_agent_file_system()
        if not afs:
            self._pipeline_initialized = True
            return None

        try:
            from derisk.agent.core.memory.compaction_pipeline import (
                UnifiedCompactionPipeline,
                HistoryCompactionConfig,
            )

            session_id = self._session_id or self.info.name
            conv_id = getattr(self, "_conv_id", None) or session_id

            config = self._compaction_config or HistoryCompactionConfig(
                context_window=self._context_window,
                max_output_lines=self._max_output_lines,
                max_output_bytes=self._max_output_bytes,
            )

            self._compaction_pipeline = UnifiedCompactionPipeline(
                conv_id=conv_id,
                session_id=session_id,
                agent_file_system=afs,
                work_log_storage=self._work_log_storage,
                llm_client=self.llm_client,
                config=config,
            )
            self._pipeline_initialized = True
            logger.info("[ReActReasoningAgent] UnifiedCompactionPipeline initialized")
            return self._compaction_pipeline
        except Exception as e:
            logger.warning(
                f"[ReActReasoningAgent] Failed to initialize compaction pipeline: {e}"
            )
            self._pipeline_initialized = True
            return None

    async def _inject_history_tools_if_needed(self) -> None:
        """在首次压缩完成后动态注入历史回顾工具。

        历史回顾工具只在 compaction 发生后才有意义（此时才有归档章节可供检索），
        因此不在 preload_resource() 中静态注入，而是由 think() 在检测到
        pipeline.has_compacted 后调用本方法。
        """
        # If already injected, skip
        if self.tools.get("read_history_chapter"):
            return

        pipeline = await self._ensure_compaction_pipeline()
        if not pipeline or not pipeline.has_compacted:
            return

        try:
            from derisk.agent.core.tools.history_tools import create_history_tools

            history_tools = create_history_tools(pipeline)
            for name, func_tool in history_tools.items():
                # Adapt v1 FunctionTool to v2 ToolBase via register_function
                self.tools.register_function(
                    name=name,
                    description=getattr(func_tool, "description", "")
                    or f"History tool: {name}",
                    func=getattr(func_tool, "func", None) or (lambda: "Not available"),
                    parameters=getattr(func_tool, "args", {}) or {},
                )

            logger.info(
                f"[ReActReasoningAgent] History recovery tools injected after first compaction: "
                f"{list(history_tools.keys())}"
            )
        except Exception as e:
            logger.warning(f"[ReActReasoningAgent] Failed to inject history tools: {e}")

    # ==================== End Compaction Pipeline Support ====================

    # ==================== Async Task Notification Support ====================

    async def _collect_async_task_notifications(self) -> str:
        """
        收集已完成的异步任务通知，用于注入到 LLM 上下文。

        在每轮 think() 中调用，将后台完成的任务结果以通知形式注入，
        使 LLM 能感知并利用这些结果。

        Returns:
            格式化的通知文本，如果没有通知则返回空字符串
        """
        async_task_manager = getattr(self, "_async_task_manager", None)
        if not async_task_manager:
            return ""

        try:
            completed = async_task_manager.get_completed_results(consume=True)
            if not completed:
                return ""

            return async_task_manager.format_notifications(completed)

        except Exception as e:
            logger.warning(
                f"[ReActReasoningAgent] Failed to collect async task notifications: {e}"
            )
            return ""

    # ==================== End Async Task Notification Support ====================

    async def preload_resource(self) -> None:
        """
        预加载资源并注入工具

        参考core架构的ReActMasterAgent.preload_resource实现：
        1. 调用父类的preload_resource（注入知识、Agent、沙箱工具）
        2. 注入skill相关工具
        3. 构建资源提示词和沙箱提示词

        NOTE: 历史回顾工具（read_history_chapter, search_history 等）不在此处注入。
        它们只在首次 compaction 完成后才动态注入，见 _inject_history_tools_if_needed()。
        """
        await super().preload_resource()

        await self._inject_skill_tools()

        self._resource_prompt_cache = await self._build_resource_prompt()
        self._sandbox_prompt_cache = await self._build_sandbox_prompt()

        logger.info(
            f"[ReActReasoningAgent] 资源预加载完成: "
            f"tools_count={len(self.tools.list_names())}, "
            f"resource_prompt_len={len(self._resource_prompt_cache or '')}"
        )

    async def _inject_skill_tools(self) -> None:
        """注入skill相关工具"""
        try:
            from ...resource.agent_skills import AgentSkillResource

            if self._check_have_resource(AgentSkillResource):
                logger.info("[ReActReasoningAgent] 检测到Skill资源，注入skill工具")
                try:
                    from ...expand.actions.skill_action import SkillAction

                    self._register_action_as_tool(SkillAction)
                except ImportError:
                    logger.debug("SkillAction未找到")
        except ImportError:
            logger.debug("AgentSkillResource模块未找到")

    async def _build_resource_prompt(self) -> str:
        """
        构建资源提示词

        参考core架构的register_variables实现，生成：
        1. available_agents - 可用Agent资源
        2. available_knowledges - 可用知识库
        3. available_skills - 可用技能
        4. other_resources - 其他资源
        """
        prompts = []

        try:
            available_agents = await self._get_available_agents_prompt()
            if available_agents:
                prompts.append(f"## 可用Agent资源\n{available_agents}")

            available_knowledges = await self._get_available_knowledges_prompt()
            if available_knowledges:
                prompts.append(f"## 可用知识库\n{available_knowledges}")

            available_skills = await self._get_available_skills_prompt()
            if available_skills:
                prompts.append(f"## 可用技能\n{available_skills}")

            other_resources = await self._get_other_resources_prompt()
            if other_resources:
                prompts.append(f"## 其他资源\n{other_resources}")

        except Exception as e:
            logger.warning(f"构建资源提示词时出错: {e}")

        return "\n\n".join(prompts) if prompts else ""

    async def _get_available_agents_prompt(self) -> str:
        """获取可用Agent资源的提示词"""
        try:
            from ...resource.app import AppResource

            prompts = []
            for k, v in self.resource_map.items():
                if v and isinstance(v[0], AppResource):
                    for item in v:
                        app_item: AppResource = item
                        prompts.append(
                            f"- <agent><code>{app_item.app_code}</code>"
                            f"<name>{app_item.app_name}</name>"
                            f"<description>{app_item.app_desc}</description></agent>"
                        )

            return "\n".join(prompts) if prompts else ""
        except ImportError:
            return ""

    async def _get_available_knowledges_prompt(self) -> str:
        """获取可用知识库的提示词"""
        try:
            from ...resource import RetrieverResource

            prompts = []
            for k, v in self.resource_map.items():
                if v and isinstance(v[0], RetrieverResource):
                    for item in v:
                        if hasattr(item, "knowledge_spaces") and item.knowledge_spaces:
                            for knowledge_space in item.knowledge_spaces:
                                prompts.append(
                                    f"- <knowledge><id>{knowledge_space.knowledge_id}</id>"
                                    f"<name>{knowledge_space.name}</name>"
                                    f"<description>{knowledge_space.desc}</description></knowledge>"
                                )

            return "\n".join(prompts) if prompts else ""
        except ImportError:
            return ""

    async def _get_available_skills_prompt(self) -> str:
        """获取可用技能的提示词"""
        try:
            from ...resource.agent_skills import AgentSkillResource

            prompts = []
            for k, v in self.resource_map.items():
                if v and isinstance(v[0], AgentSkillResource):
                    for item in v:
                        skill_item: AgentSkillResource = item
                        mode, branch = "release", "master"
                        debug_info = getattr(skill_item, "debug_info", None)
                        if debug_info and debug_info.get("is_debug"):
                            mode, branch = "debug", debug_info.get("branch")

                        skill_meta = skill_item.skill_meta(mode)
                        if not skill_meta:
                            continue

                        skill_path = (
                            skill_item._skill.parent_folder
                            if hasattr(skill_item, "_skill") and skill_item._skill
                            else skill_meta.path
                        )
                        prompts.append(
                            f"- <skill><name>{skill_meta.name}</name>"
                            f"<description>{skill_meta.description}</description>"
                            f"<path>{skill_path}</path>"
                            f"<branch>{branch}</branch></skill>"
                        )

            return "\n".join(prompts) if prompts else ""
        except ImportError:
            return ""

    async def _get_other_resources_prompt(self) -> str:
        """获取其他资源的提示词"""
        try:
            from ...resource import BaseTool, RetrieverResource
            from ...resource.agent_skills import AgentSkillResource
            from ...resource.app import AppResource
            from derisk_serve.agent.resource.tool.mcp import MCPToolPack

            excluded_types = (
                BaseTool,
                MCPToolPack,
                AppResource,
                AgentSkillResource,
                RetrieverResource,
            )

            prompts = []
            for k, v in self.resource_map.items():
                if v and not isinstance(v[0], excluded_types):
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

                            resource_name = item.name if hasattr(item, "name") else k
                            prompts.append(
                                f"- <{type_name}><name>{resource_name}</name></{type_name}>"
                            )
                        except Exception:
                            continue

            return "\n".join(prompts) if prompts else ""
        except ImportError:
            return ""

    async def _build_sandbox_prompt(self) -> str:
        """
        构建沙箱环境提示词

        兼容两种架构：
        1. core架构：SandboxManager有 client 和 initialized 属性
        2. core_v2架构：SandboxManager管理多个沙箱
        """
        if not self.sandbox_manager:
            return ""

        try:
            sandbox_client = None

            if hasattr(self.sandbox_manager, "client"):
                if hasattr(self.sandbox_manager, "initialized"):
                    if not self.sandbox_manager.initialized:
                        logger.warning("沙箱尚未准备完成!")
                sandbox_client = self.sandbox_manager.client
            elif hasattr(self.sandbox_manager, "get_sandbox"):
                sandbox_ids = self.sandbox_manager.list_sandboxes()
                if sandbox_ids:
                    sandbox_client = self.sandbox_manager.get_sandbox(sandbox_ids[0])

            if not sandbox_client:
                return "## 沙箱环境\n沙箱环境已启用，可在沙箱中执行代码。"

            try:
                from derisk.util.template_utils import render
            except ImportError:
                return "## 沙箱环境\n沙箱环境已启用，可在沙箱中执行代码。"

            try:
                from ...core.sandbox.prompt import (
                    AGENT_SKILL_SYSTEM_PROMPT,
                    SANDBOX_ENV_PROMPT,
                    SANDBOX_TOOL_BOUNDARIES,
                    sandbox_prompt,
                )
            except ImportError:
                return "## 沙箱环境\n沙箱环境已启用，可在沙箱中执行代码。"

            work_dir = getattr(sandbox_client, "work_dir", "/workspace")
            skill_dir = getattr(sandbox_client, "skill_dir", None)
            enable_skill = getattr(sandbox_client, "enable_skill", False)
            provider = getattr(sandbox_client, "provider", lambda: "unknown")()

            system_info = _get_sandbox_system_info(sandbox_client)

            env_param = {
                "sandbox": {
                    "work_dir": work_dir,
                    "skill_dir": skill_dir,
                    "system_info": system_info,
                }
            }
            skill_param = {"sandbox": {"agent_skill_dir": skill_dir}}

            param = {
                "sandbox": {
                    "tool_boundaries": render(SANDBOX_TOOL_BOUNDARIES, {}),
                    "execution_env": render(SANDBOX_ENV_PROMPT, env_param),
                    "agent_skill_system": render(AGENT_SKILL_SYSTEM_PROMPT, skill_param)
                    if enable_skill
                    else "",
                    "use_agent_skill": enable_skill,
                }
            }

            return render(sandbox_prompt, param)

        except Exception as e:
            logger.warning(f"构建沙箱提示词时出错: {e}")
            return ""

    def _build_system_prompt(self) -> str:
        """构建系统提示词（同步版本，保持向后兼容）"""
        resource_prompt = self._resource_prompt_cache or ""
        sandbox_prompt = self._sandbox_prompt_cache or ""

        return REACT_REASONING_SYSTEM_PROMPT.format(
            agent_name=self.info.name,
            max_steps=self.info.max_steps,
            resource_prompt=resource_prompt,
            sandbox_prompt=sandbox_prompt,
        )

    async def _build_system_prompt_with_assembler(self) -> str:
        """
        使用 PromptAssembler 构建系统提示词（异步版本）

        支持：
        1. 新旧模式兼容
        2. 分层组装（身份层 + 资源层 + 控制层）
        3. 资源注入
        """
        try:
            assembler = self._get_prompt_assembler()

            # 检查是否使用新模式
            # core_v2 默认不提供用户模板，所以这里使用 None 让 assembler 使用默认模板
            user_system_prompt = None  # core_v2 暂时不支持自定义模板

            # 构建资源上下文
            resource_ctx = ResourceContext.from_v2_agent(self)

            # 获取时间变量
            # core_v2 没有继承 ConversableAgent，所以没有 _vm 变量管理器
            # 直接生成时间值
            from datetime import datetime
            now_value = datetime.now().strftime("%Y-%m-%d")
            now_time_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 使用 PromptAssembler 组装
            system_prompt = await assembler.assemble_system_prompt(
                user_system_prompt=user_system_prompt,
                resource_context=resource_ctx,
                agent_name=self.info.name,
                max_steps=getattr(self.info, "max_steps", 20),
                language="zh",
                now=now_value,
                now_time=now_time_value,
            )

            logger.info("[ReActReasoningAgent] 使用 PromptAssembler 分层组装")
            return system_prompt

        except Exception as e:
            logger.warning(
                f"[ReActReasoningAgent] PromptAssembler 失败，使用传统方式: {e}"
            )
            return self._build_system_prompt()

    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """思考阶段 - 调用LLM生成思考内容（支持Function Calling）

        集成 UnifiedCompactionPipeline 四层压缩：
        - Layer 2: Pruning（修剪）
        - Layer 3: Compaction（压缩归档）
        - Layer 4: Multi-Turn History（跨轮次历史压缩）
        """
        # 先 yield 一个思考开始的标记
        yield f"[思考] 分析任务: {message[:100]}..."

        # 调用 LLM 生成思考内容
        if not self.llm_client:
            yield "错误: 未配置 LLM 客户端"
            return

        try:
            # Layer 2 + Layer 3: 在构建消息前执行压缩管道
            pipeline = await self._ensure_compaction_pipeline()
            if pipeline and self._messages:
                try:
                    # Layer 2: Pruning
                    prune_result = await pipeline.prune_history(self._messages)
                    self._messages = prune_result.messages
                    if prune_result.pruned_count > 0:
                        logger.info(
                            f"[ReActReasoningAgent] Pruned {prune_result.pruned_count} messages, "
                            f"saved ~{prune_result.tokens_saved} tokens"
                        )

                    # Layer 3: Compaction + Archival
                    compact_result = await pipeline.compact_if_needed(self._messages)
                    self._messages = compact_result.messages
                    if compact_result.compaction_triggered:
                        logger.info(
                            f"[ReActReasoningAgent] Compaction triggered: archived "
                            f"{compact_result.messages_archived} messages, "
                            f"saved ~{compact_result.tokens_saved} tokens"
                        )
                        # After first compaction, inject history tools
                        await self._inject_history_tools_if_needed()
                except Exception as e:
                    logger.warning(
                        f"[ReActReasoningAgent] Compaction pipeline failed, using raw messages: {e}"
                    )

            # Layer 4: 获取跨轮次历史压缩
            layer4_history = ""
            if pipeline:
                try:
                    layer4_history = await pipeline.get_layer4_history_for_prompt()
                    if layer4_history:
                        logger.info(
                            f"[ReActReasoningAgent] Layer 4: Retrieved {len(layer4_history)} chars of history"
                        )
                except Exception as e:
                    logger.debug(
                        f"[ReActReasoningAgent] Layer 4: Failed to get history: {e}"
                    )

            # 构建系统提示词（使用 PromptAssembler）
            system_prompt = await self._build_system_prompt_with_assembler()
            if layer4_history:
                system_prompt += f"\n\n## 历史对话记录\n\n{layer4_history}\n\n*注：以上为历史对话摘要。当前轮次的工具执行通过原生 Function Call 传递。*"

            # 构建消息列表
            from ..llm_adapter import LLMMessage

            messages = []

            if system_prompt:
                messages.append(LLMMessage(role="system", content=system_prompt))

            # 添加历史消息，正确处理 tool 角色和 tool_calls
            for msg in self._messages[-20:]:  # 增加历史消息数量
                if msg.role == "tool":
                    # 工具结果消息
                    messages.append(
                        LLMMessage(
                            role="tool",
                            content=msg.content,
                            tool_call_id=msg.metadata.get("tool_call_id", "unknown"),
                        )
                    )
                elif msg.role == "assistant" and msg.metadata.get("tool_calls"):
                    # 包含工具调用的助手消息
                    messages.append(
                        LLMMessage(
                            role="assistant",
                            content=msg.content or "",
                            tool_calls=msg.metadata.get("tool_calls"),
                        )
                    )
                else:
                    messages.append(LLMMessage(role=msg.role, content=msg.content))

            worklog_tool_messages = await self._get_worklog_tool_messages()
            if worklog_tool_messages:
                for tool_msg in worklog_tool_messages:
                    if tool_msg.get("role") == "assistant":
                        messages.append(
                            LLMMessage(
                                role="assistant",
                                content=tool_msg.get("content", ""),
                                tool_calls=tool_msg.get("tool_calls"),
                            )
                        )
                    elif tool_msg.get("role") == "tool":
                        messages.append(
                            LLMMessage(
                                role="tool",
                                content=tool_msg.get("content", ""),
                                tool_call_id=tool_msg.get("tool_call_id", ""),
                            )
                        )
                logger.info(
                    f"[ReActReasoningAgent] Injected {len(worklog_tool_messages)} worklog tool messages"
                )

            # 异步任务完成结果注入
            async_notification = await self._collect_async_task_notifications()
            if async_notification:
                messages.append(LLMMessage(role="user", content=async_notification))
                logger.info(
                    "[ReActReasoningAgent] Injected async task completion notifications"
                )

            # 构建工具定义
            tools = self._build_tool_definitions()

            logger.info(
                f"[ReActReasoningAgent] 调用 LLM: 消息数={len(messages)}, 工具数={len(tools)}, 当前步骤={self._current_step}"
            )

            # 设置 tool_choice 为 "auto" 鼓励模型使用工具
            call_kwargs = dict(kwargs)
            if tools:
                call_kwargs["tool_choice"] = "auto"

            # 直接使用 LLMAdapter 的 generate 方法
            response = await self.llm_client.generate(
                messages=messages, tools=tools if tools else None, **call_kwargs
            )

            # 存储 LLM 响应供 decide 方法使用
            self._last_llm_response = response

            # 输出思考内容
            if response.content:
                yield response.content

            # 如果有工具调用，输出工具调用信息
            if response.tool_calls:
                for tc in response.tool_calls:
                    yield f"\n[工具调用] {tc['function']['name']}"

        except Exception as e:
            logger.exception(f"[ReActReasoningAgent] think 阶段出错: {e}")
            yield f"[错误] 思考阶段异常: {str(e)}"

    async def decide(self, context: Dict[str, Any], **kwargs) -> "Decision":
        """决策阶段 - 检查LLM响应中的工具调用"""
        from ..enhanced_agent import Decision, DecisionType

        # 检查是否有 LLM 响应
        if hasattr(self, "_last_llm_response") and self._last_llm_response:
            response = self._last_llm_response

            # 检查是否有工具调用
            if response.tool_calls and len(response.tool_calls) > 0:
                tc = response.tool_calls[0]  # 取第一个工具调用
                import json

                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                logger.info(
                    f"[ReActReasoningAgent] 工具调用: {tc['function']['name']}, 参数: {args}"
                )
                return Decision(
                    type=DecisionType.TOOL_CALL,
                    content=response.content,
                    tool_name=tc["function"]["name"],
                    tool_args=args,
                    confidence=1.0,
                )

            # 如果有 function_call（旧格式）
            if response.function_call:
                import json

                try:
                    args = json.loads(response.function_call["arguments"])
                except json.JSONDecodeError:
                    args = {}

                logger.info(
                    f"[ReActReasoningAgent] 函数调用: {response.function_call['name']}"
                )
                return Decision(
                    type=DecisionType.TOOL_CALL,
                    content=response.content,
                    tool_name=response.function_call["name"],
                    tool_args=args,
                    confidence=1.0,
                )

            # 没有工具调用 - 检查是否过早结束
            content = response.content or ""

            # 记录警告
            if self._current_step < 3:
                logger.warning(
                    f"[ReActReasoningAgent] LLM 在第 {self._current_step} 步就返回了纯文本回答，"
                    f"可能需要更多探索。内容长度: {len(content)}"
                )

            # 返回响应
            logger.info(f"[ReActReasoningAgent] LLM 返回纯文本回答，任务可能已完成")
            return Decision(
                type=DecisionType.RESPONSE,
                content=content,
                confidence=0.9,
            )

        # 回退：使用父类的决策逻辑
        thinking = context.get("thinking", "")
        return Decision(
            type=DecisionType.RESPONSE,
            content=thinking,
            confidence=0.8,
        )

    async def act(self, decision: "Decision", **kwargs) -> "ActionResult":
        """执行工具 - 带截断和检测（集成 UnifiedCompactionPipeline Layer 1）

        Args:
            decision: 决策对象，包含 tool_name 和 tool_args

        Returns:
            ActionResult: 执行结果
        """
        from ..enhanced_agent import ActionResult

        tool_name = decision.tool_name
        tool_args = decision.tool_args or {}

        if self._doom_loop_detector:
            self._doom_loop_detector.record_call(tool_name, tool_args)

            check_result = self._doom_loop_detector.check_doom_loop()
            if check_result.is_doom_loop:
                logger.warning(f"[ReActAgent] 检测到末日循环: {check_result.message}")
                return ActionResult(
                    success=False,
                    output=f"[警告] {check_result.message}",
                    error="Doom loop detected",
                )

        # 执行工具
        result = await self.execute_tool(tool_name, tool_args)

        # Layer 1: 使用 UnifiedCompactionPipeline 截断（优先）
        # skill_read/skill_list 返回完整 Skill 内容，不截断
        # get_table_spec 返回结构化表 spec，截断会破坏格式；工具已限制最多 3 张表
        _SKIP_TRUNCATION_TOOLS = {"skill_read", "skill_list", "get_table_spec"}
        pipeline = await self._ensure_compaction_pipeline()
        if pipeline and result.output and tool_name not in _SKIP_TRUNCATION_TOOLS:
            try:
                tr = await pipeline.truncate_output(result.output, tool_name, tool_args)
                result.output = tr.content
                if tr.is_truncated:
                    result.metadata["truncated"] = True
                    result.metadata["file_key"] = tr.file_key
                    result.metadata["truncation_info"] = {
                        "original_size": tr.original_size,
                        "truncated_size": tr.truncated_size,
                    }
            except Exception as e:
                logger.warning(
                    f"[ReActReasoningAgent] Pipeline truncation failed, fallback to legacy: {e}"
                )
                # Fallback to legacy OutputTruncator
                if self._output_truncator and result.output:
                    truncation_result = self._output_truncator.truncate(
                        result.output, tool_name=tool_name
                    )
                    if truncation_result.is_truncated:
                        # truncation_result.content 已包含 suggestion，无需重复添加
                        result.output = truncation_result.content
                        result.metadata["truncated"] = True
                        result.metadata["truncation_info"] = {
                            "original_lines": truncation_result.original_lines,
                            "truncated_lines": truncation_result.truncated_lines,
                            "temp_file": truncation_result.temp_file_path,
                        }
        elif self._output_truncator and result.output and tool_name not in _SKIP_TRUNCATION_TOOLS:
            # Fallback: legacy OutputTruncator when pipeline not available
            truncation_result = self._output_truncator.truncate(
                result.output, tool_name=tool_name
            )

            if truncation_result.is_truncated:
                # truncation_result.content 已包含 suggestion，无需重复添加
                result.output = truncation_result.content
                result.metadata["truncated"] = True
                result.metadata["truncation_info"] = {
                    "original_lines": truncation_result.original_lines,
                    "truncated_lines": truncation_result.truncated_lines,
                    "temp_file": truncation_result.temp_file_path,
                }

        # Record to WorkLog
        if self._work_log_storage and pipeline:
            try:
                from derisk.agent.core.memory.gpts.file_base import WorkEntry

                entry = WorkEntry(
                    timestamp=time.time(),
                    tool=tool_name,
                    args=tool_args,
                    result=result.output[:500] if result.output else None,
                    full_result_archive=result.metadata.get("file_key"),
                    success=result.success,
                    step_index=self._current_step,
                )
                session_id = self._session_id or self.info.name
                conv_id = getattr(self, "_conv_id", None) or session_id
                await self._work_log_storage.append_work_entry(conv_id, entry)
            except Exception as e:
                logger.debug(
                    f"[ReActReasoningAgent] Failed to record WorkLog entry: {e}"
                )

        # 转换 ToolResult 为 ActionResult
        return ActionResult(
            success=result.success,
            output=result.output,
            error=result.error,
            metadata=result.metadata,
        )

    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """主执行循环"""
        async for chunk in super().run(message, stream):
            yield chunk

    @classmethod
    def create(
        cls,
        name: str = "react-reasoning-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        max_steps: int = 30,
        resource: Optional[Any] = None,
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        enable_doom_loop_detection: bool = True,
        enable_output_truncation: bool = True,
        enable_context_compaction: bool = True,
        enable_history_pruning: bool = True,
        memory: Optional[Any] = None,
        use_persistent_memory: bool = False,
        enable_hierarchical_context: bool = True,
        hc_config: Optional[Any] = None,
        **kwargs,
    ) -> "ReActReasoningAgent":
        """便捷创建方法 - 优先使用 ModelConfigCache 配置"""
        import os
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache

        if not api_key or not api_base:
            if ModelConfigCache.has_model(model):
                model_config = ModelConfigCache.get_config(model)
                if model_config:
                    api_key = api_key or model_config.get("api_key")
                    api_base = (
                        api_base
                        or model_config.get("base_url")
                        or model_config.get("api_base")
                    )
                    logger.info(
                        f"[ReActReasoningAgent] 从 ModelConfigCache 获取配置: model={model}, api_base={api_base}"
                    )

        if not api_key or not api_base:
            import os

            api_key = api_key or os.getenv("OPENAI_API_KEY")
            api_base = api_base or os.getenv("OPENAI_API_BASE")

        if not api_key:
            raise ValueError(
                f"需要提供 API Key，请配置 agent.llm.provider 或设置环境变量（model={model}）"
            )

        info = AgentInfo(name=name, max_steps=max_steps, **kwargs)

        llm_config = LLMConfig(model=model, api_key=api_key, api_base=api_base)

        llm_adapter = LLMFactory.create(llm_config)

        return cls(
            info=info,
            llm_adapter=llm_adapter,
            resource=resource,
            resource_map=resource_map,
            sandbox_manager=sandbox_manager,
            enable_doom_loop_detection=enable_doom_loop_detection,
            enable_output_truncation=enable_output_truncation,
            enable_context_compaction=enable_context_compaction,
            enable_history_pruning=enable_history_pruning,
            memory=memory,
            use_persistent_memory=use_persistent_memory,
            enable_hierarchical_context=enable_hierarchical_context,
            hc_config=hc_config,
            **kwargs,
        )

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "agent_name": self.info.name,
            "current_step": self._current_step,
            "max_steps": self.info.max_steps,
            "messages_count": len(self._messages),
            "resource_count": sum(len(v) for v in self.resource_map.values()),
            "has_sandbox": self.sandbox_manager is not None,
            "memory_type": "persistent" if self._use_persistent_memory else "in-memory",
            "hierarchical_context_enabled": self._enable_hierarchical_context,
        }

        if hasattr(self.memory, "get_stats"):
            stats["memory_stats"] = self.memory.get_stats()

        if self._context_load_result:
            stats["hierarchical_context_stats"] = self._context_load_result.stats

        if self._doom_loop_detector:
            stats["doom_loop"] = self._doom_loop_detector.get_statistics()

        if self._output_truncator:
            stats["truncation"] = {
                "max_lines": self._output_truncator.max_lines,
                "max_bytes": self._output_truncator.max_bytes,
            }

        # Compaction pipeline stats (removed legacy compactor/pruner stats)
        if self._compaction_pipeline:
            stats["compaction_pipeline"] = {
                "initialized": self._pipeline_initialized,
                "has_compacted": self._compaction_pipeline.has_compacted,
                "history_tools_injected": self.tools.get("read_history_chapter")
                is not None,
            }

        return stats
