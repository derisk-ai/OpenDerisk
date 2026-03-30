"""
BaseBuiltinAgent - 内置Agent基类

为所有内置Agent提供通用功能：
- 工具管理（统一到ToolRegistry）
- 配置加载
- 默认行为
- 资源注入（参考core架构的ConversableAgent）
- 沙箱环境支持
- 统一压缩管道支持（UnifiedCompactionPipeline三层压缩）

工具分层：
1. 内置工具（_setup_default_tools）：bash, read, write, grep, glob, think 等
2. 交互工具（_setup_default_tools）：question, confirm, notify 等
3. 资源工具（preload_resource）：根据绑定的资源动态注入
   - AppResource -> Agent调用工具
   - RetrieverResource -> 知识检索工具
   - AgentSkillResource -> Skill工具
   - SandboxManager -> 沙箱工具
"""

from typing import AsyncIterator, Dict, Any, Optional, List, Type
from collections import defaultdict
import logging
import json
import asyncio

from ..agent_base import AgentBase, AgentInfo, AgentContext
from ..tools_v2 import (
    ToolRegistry,
    ToolResult,
    register_builtin_tools,
    register_interaction_tools,
)
from ..llm_adapter import LLMAdapter, LLMConfig, LLMFactory
from ..production_agent import ProductionAgent
from ..sandbox_docker import SandboxManager
from ...tools.runtime_loader import AgentRuntimeToolLoader

logger = logging.getLogger(__name__)


class BaseBuiltinAgent(ProductionAgent):
    """
    内置Agent基类

    继承ProductionAgent，提供：
    1. 默认工具集管理（统一到ToolRegistry）
    2. 配置驱动的工具加载
    3. 原生Function Call支持
    4. 场景特定的默认行为
    5. 资源注入能力（参考core架构）
    6. 沙箱环境支持
    7. 统一压缩管道支持（三层压缩：Layer1截断、Layer2剪枝、Layer3压缩归档）

    工具管理策略：
    - 所有工具统一注册到 self.tools (ToolRegistry)
    - _setup_default_tools(): 注册基础工具和交互工具
    - preload_resource(): 根据资源绑定动态注入工具

    子类需要实现：
    - _get_default_tools(): 返回默认工具列表
    - _build_system_prompt(): 构建系统提示词
    """

    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        default_tools: Optional[List[str]] = None,
        resource: Optional[Any] = None,
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        memory: Optional[Any] = None,
        use_persistent_memory: bool = False,
        gpts_memory: Optional[Any] = None,
        conv_id: Optional[str] = None,
        session_id: Optional[str] = None,
        # UnifiedCompactionPipeline 配置参数
        enable_compaction_pipeline: bool = True,
        agent_file_system: Optional[Any] = None,
        work_log_storage: Optional[Any] = None,
        compaction_config: Optional[Any] = None,
        context_window: int = 128000,
        max_output_lines: int = 2000,
        max_output_bytes: int = 50000,
        # 工具运行时加载器配置
        app_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        use_runtime_tool_loader: bool = True,
        **kwargs,
    ):
        super().__init__(
            info=info,
            llm_adapter=llm_adapter,
            tool_registry=tool_registry,
            memory=memory,
            use_persistent_memory=use_persistent_memory,
            gpts_memory=gpts_memory,
            conv_id=conv_id,
            session_id=session_id,
            **kwargs,
        )

        self.resource = resource
        self.resource_map = resource_map or defaultdict(list)
        self.sandbox_manager = sandbox_manager

        # 初始化工具运行时加载器
        self._app_id = app_id or info.name
        self._agent_name = agent_name or info.name
        self._use_runtime_tool_loader = use_runtime_tool_loader
        self._tool_loader: Optional[AgentRuntimeToolLoader] = None

        if use_runtime_tool_loader:
            self._tool_loader = AgentRuntimeToolLoader(
                app_id=self._app_id,
                agent_name=self._agent_name,
                default_tools=default_tools or self._get_default_tools(),
            )
            logger.info(
                f"[{self.__class__.__name__}] 已初始化工具运行时加载器: "
                f"app_id={self._app_id}, agent_name={self._agent_name}"
            )

        self.default_tools = default_tools or self._get_default_tools()
        self._setup_default_tools()

        # UnifiedCompactionPipeline 相关属性
        self._enable_compaction_pipeline = enable_compaction_pipeline
        self._compaction_pipeline = None
        self._pipeline_initialized = False
        self._agent_file_system = agent_file_system
        self._work_log_storage = work_log_storage
        self._compaction_config = compaction_config
        self._context_window = context_window
        self._max_output_lines = max_output_lines
        self._max_output_bytes = max_output_bytes

        # 初始化 WorkLogStorage（如果启用 Pipeline 但未提供）
        if self._work_log_storage is None and enable_compaction_pipeline:
            try:
                from ...core.memory.gpts.file_base import SimpleWorkLogStorage

                self._work_log_storage = SimpleWorkLogStorage()
            except Exception:
                pass

        logger.info(
            f"[{self.__class__.__name__}] 初始化完成: "
            f"compaction_pipeline={enable_compaction_pipeline}"
        )

    def _get_default_tools(self) -> List[str]:
        """获取默认工具列表 - 子类实现"""
        return ["bash", "read", "write"]

    def _setup_default_tools(self):
        """设置默认工具"""
        # 如果使用运行时加载器，工具会在运行时被动态加载
        if self._use_runtime_tool_loader and self._tool_loader:
            logger.info(
                f"[{self.__class__.__name__}] 使用运行时工具加载器，工具将在运行时动态加载"
            )
            # 仍然注册基础工具到注册表，但实际可用的工具由运行时加载器控制
            if len(self.tools.list_all()) == 0:
                register_builtin_tools(self.tools)
                register_interaction_tools(self.tools)
        else:
            # 传统模式：直接注册所有工具
            if len(self.tools.list_all()) == 0:
                register_builtin_tools(self.tools)
                register_interaction_tools(self.tools)

            logger.info(
                f"[{self.__class__.__name__}] 已注册默认工具: {len(self.tools.list_names())} 个"
            )

    async def _load_runtime_tools(self) -> List[Dict[str, Any]]:
        """
        加载运行时工具定义

        根据 Agent 配置返回实际可用的工具定义列表

        Returns:
            工具定义列表（OpenAI Function Calling格式）
        """
        if self._use_runtime_tool_loader and self._tool_loader:
            tool_data = await self._tool_loader.load_tools(format_type="openai")
            schemas = tool_data.get("schemas", [])

            logger.info(
                f"[{self.__class__.__name__}] 运行时加载工具: "
                f"数量={len(schemas)}, 工具列表={[s.get('function', {}).get('name') for s in schemas]}"
            )
            return schemas
        else:
            # 传统模式：返回所有注册的工具
            return self._build_tool_definitions()

    def _build_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        构建工具定义（Function Call格式）

        Returns:
            List[Dict]: OpenAI Function Calling格式的工具定义
        """
        tools = []

        # 获取所有注册的工具名称
        all_tool_names = self.tools.list_names()

        for tool_name in all_tool_names:
            tool = self.tools.get(tool_name)
            if tool:
                tools.append(self._tool_to_function(tool))

        # 记录日志：工具数量和名称列表
        tool_names_in_defs = [
            t.get("function", {}).get("name", "unknown") for t in tools
        ]
        logger.info(
            f"[{self.__class__.__name__}] 构建工具定义: 数量={len(tools)}, 工具列表={tool_names_in_defs}"
        )

        return tools

    def _tool_to_function(self, tool: Any) -> Dict[str, Any]:
        """
        将工具转换为 Function Call 格式

        Args:
            tool: 工具实例

        Returns:
            Dict: Function 定义
        """
        metadata = tool.metadata

        return {
            "type": "function",
            "function": {
                "name": metadata.name,
                "description": metadata.description,
                "parameters": tool.parameters,
            },
        }

    def _build_system_prompt(self) -> str:
        """构建系统提示词 - 子类实现"""
        return f"你是一个专业的AI助手。当前Agent: {self.info.name}"

    def _check_have_resource(self, resource_type: Type) -> bool:
        """
        检查是否有某种类型的资源

        Args:
            resource_type: 资源类型

        Returns:
            bool: 是否有该类型资源
        """
        for resources in self.resource_map.values():
            if not resources:
                continue
            first = resources[0]
            if isinstance(first, resource_type):
                if len(resources) == 1 and getattr(first, "is_empty", False):
                    return False
                else:
                    return True
        return False

    async def preload_resource(self) -> None:
        """
        预加载资源并注入工具

        参考core架构的ConversableAgent.preload_resource实现

        根据绑定的资源动态注入工具到 ToolRegistry：
        1. AppResource -> Agent调用工具
        2. RetrieverResource -> 知识检索工具
        3. AgentSkillResource -> Skill工具
        4. SandboxManager -> 沙箱工具
        """
        await self._inject_resource_tools()
        logger.info(
            f"[{self.__class__.__name__}] 资源预加载完成，工具数量: {len(self.tools.list_names())}"
        )

    async def _inject_resource_tools(self) -> None:
        """
        根据绑定的资源注入工具到 ToolRegistry
        """
        await self._inject_knowledge_tools()
        await self._inject_agent_tools()
        await self._inject_sandbox_tools()
        await self._inject_async_task_tools()

    async def _inject_async_task_tools(self) -> None:
        """
        注入异步任务工具（当检测到多 Agent 场景时）

        条件：存在 AppResource（表示有子 Agent 可委派）
        功能：注册 spawn_agent_task, check_tasks, wait_tasks, cancel_task 4 个工具
        """
        try:
            from ...resource.app import AppResource

            if not self._check_have_resource(AppResource):
                return

            # 需要 SubagentManager 支持
            subagent_manager = getattr(self, "_subagent_manager", None)
            if not subagent_manager:
                logger.debug(
                    f"[{self.__class__.__name__}] AppResource 存在但无 SubagentManager，跳过异步任务工具注入"
                )
                return

            from ..async_task_manager import AsyncTaskManager
            from ...tools.builtin.async_task import register_async_task_tools

            session_id = getattr(self, "_session_id", "") or ""
            async_task_manager = AsyncTaskManager(
                subagent_manager=subagent_manager,
                max_concurrent=5,
                parent_session_id=session_id,
            )

            # 保存到实例上，供 ReActReasoningAgent 访问
            self._async_task_manager = async_task_manager

            register_async_task_tools(
                registry=self.tools,
                async_task_manager=async_task_manager,
            )

            logger.info(
                f"[{self.__class__.__name__}] 检测到多 Agent 场景，已注入异步任务工具"
            )

        except ImportError as e:
            logger.debug(f"异步任务工具模块未找到: {e}")
        except Exception as e:
            logger.warning(f"注入异步任务工具失败: {e}")

    async def _inject_knowledge_tools(self) -> None:
        """注入知识检索工具"""
        try:
            from ...resource import RetrieverResource

            if self._check_have_resource(RetrieverResource):
                logger.info(f"[{self.__class__.__name__}] 检测到知识资源，注入检索工具")
                try:
                    from ...expand.actions.knowledge_action import KnowledgeSearch

                    self._register_action_as_tool(KnowledgeSearch)
                except ImportError:
                    logger.debug("KnowledgeSearch action未找到")

        except ImportError:
            logger.debug("RetrieverResource模块未找到")

    async def _inject_agent_tools(self) -> None:
        """注入Agent调用工具"""
        try:
            from ...resource.app import AppResource

            if self._check_have_resource(AppResource):
                logger.info(
                    f"[{self.__class__.__name__}] 检测到Agent资源，注入Agent调用工具"
                )
                try:
                    from ...expand.actions.agent_action import AgentStart

                    self._register_action_as_tool(AgentStart)
                except ImportError:
                    logger.debug("AgentStart action未找到")

        except ImportError:
            logger.debug("AppResource模块未找到")

    async def _inject_sandbox_tools(self) -> None:
        """注入沙箱工具"""
        if self.sandbox_manager:
            logger.info(f"[{self.__class__.__name__}] 检测到沙箱环境，注入沙箱工具")
            try:
                from ...core.sandbox.sandbox_tool_registry import sandbox_tool_dict

                count = 0
                for tool_name, tool in sandbox_tool_dict.items():
                    tool_adapter = self._adapt_core_function_tool(tool)
                    if tool_adapter:
                        self.tools.register(tool_adapter)
                        count += 1
                logger.info(f"[{self.__class__.__name__}] 已注入 {count} 个沙箱工具")
            except ImportError:
                logger.debug("沙箱工具注册表未找到")

    def _adapt_core_function_tool(self, core_tool: Any) -> Optional[Any]:
        """
        将 core 架构的 FunctionTool 适配为 core_v2 的 ToolBase

        Args:
            core_tool: core架构的FunctionTool实例

        Returns:
            ToolBase适配后的工具实例，失败返回None
        """
        try:
            from ..tools_v2 import ToolBase, ToolMetadata, ToolResult

            class CoreFunctionToolAdapter(ToolBase):
                """Core FunctionTool 适配器"""

                def __init__(self, func_tool: Any):
                    self._func_tool = func_tool
                    super().__init__()

                def _define_metadata(self) -> ToolMetadata:
                    return ToolMetadata(
                        name=getattr(self._func_tool, "name", "unknown"),
                        description=getattr(self._func_tool, "description", "")
                        or f"工具: {getattr(self._func_tool, 'name', 'unknown')}",
                        parameters=getattr(self._func_tool, "args", {}) or {},
                        requires_permission=getattr(self._func_tool, "ask_user", False),
                        dangerous=False,
                        category="sandbox",
                        version="1.0.0",
                    )

                async def execute(
                    self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None
                ) -> ToolResult:
                    try:
                        if hasattr(self._func_tool, "async_execute"):
                            result = await self._func_tool.async_execute(**args)
                        elif hasattr(self._func_tool, "execute"):
                            result = self._func_tool.execute(**args)
                            if asyncio.iscoroutine(result):
                                result = await result
                        else:
                            return ToolResult(
                                success=False,
                                output="",
                                error=f"Tool {self.metadata.name} has no execute method",
                            )

                        if isinstance(result, ToolResult):
                            return result

                        return ToolResult(
                            success=True,
                            output=str(result) if result else "",
                            metadata={"raw_result": result},
                        )
                    except Exception as e:
                        logger.warning(f"沙箱工具执行失败 {self.metadata.name}: {e}")
                        return ToolResult(success=False, output="", error=str(e))

            return CoreFunctionToolAdapter(core_tool)

        except Exception as e:
            logger.warning(f"适配core工具失败: {e}")
            return None

    def _register_action_as_tool(self, action_cls: Type) -> None:
        """
        将 Action 转换并注册为工具

        Args:
            action_cls: Action类
        """
        try:
            from ..tools_v2 import ActionToolAdapter

            tool = ActionToolAdapter(action_cls())
            self.tools.register(tool)
            logger.info(f"[{self.__class__.__name__}] 已注册工具: {tool.metadata.name}")
        except Exception as e:
            logger.warning(f"注册工具失败 {action_cls.__name__}: {e}")

    async def execute_tool(
        self, tool_name: str, tool_args: Dict[str, Any], **kwargs
    ) -> "ToolResult":
        """
        执行工具

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            **kwargs: 其他参数

        Returns:
            ToolResult: 工具执行结果
        """
        from ..tools_v2 import ToolResult

        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False, output="", error=f"工具不存在: {tool_name}"
            )

        try:
            context = dict(kwargs)
            if self.sandbox_manager is not None:
                context["sandbox_manager"] = self.sandbox_manager
            result = await tool.execute(tool_args, context)
            return result
        except Exception as e:
            logger.exception(f"[{self.__class__.__name__}] 工具执行异常: {tool_name}")
            return ToolResult(success=False, output="", error=str(e))

    @classmethod
    def create(
        cls,
        name: str = "builtin-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        max_steps: int = 20,
        **kwargs,
    ) -> "BaseBuiltinAgent":
        """
        便捷创建方法

        Args:
            name: Agent名称
            model: 模型名称
            api_key: API密钥
            max_steps: 最大步数
            **kwargs: 其他参数

        Returns:
            BaseBuiltinAgent: Agent实例
        """
        import os

        api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("需要提供OpenAI API Key")

        info = AgentInfo(name=name, max_steps=max_steps, **kwargs)

        llm_config = LLMConfig(model=model, api_key=api_key)

        llm_adapter = LLMFactory.create(llm_config)

        return cls(info, llm_adapter, **kwargs)

    async def _ensure_agent_file_system(self) -> Optional[Any]:
        """确保 AgentFileSystem 已初始化（懒加载）"""
        if self._agent_file_system:
            return self._agent_file_system

        try:
            from ...core.file_system.agent_file_system import AgentFileSystem

            session_id = getattr(self, "_session_id", None) or self.info.name
            conv_id = getattr(self, "_conv_id", None) or session_id
            self._agent_file_system = AgentFileSystem(
                conv_id=conv_id,
                session_id=session_id,
            )
            await self._agent_file_system.sync_workspace()
            return self._agent_file_system
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] Failed to initialize AgentFileSystem: {e}"
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
            from ...core.memory.compaction_pipeline import (
                UnifiedCompactionPipeline,
                HistoryCompactionConfig,
            )

            session_id = getattr(self, "_session_id", None) or self.info.name
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
                llm_client=self.llm_client if hasattr(self, "llm_client") else None,
                config=config,
            )
            self._pipeline_initialized = True
            logger.info(
                f"[{self.__class__.__name__}] UnifiedCompactionPipeline initialized with Layer 4 support"
            )
            return self._compaction_pipeline
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] Failed to initialize compaction pipeline: {e}"
            )
            self._pipeline_initialized = True
            return None

    async def _inject_history_tools_if_needed(self) -> None:
        """在首次压缩完成后动态注入历史回顾工具"""
        try:
            from ...core.tools.history_tools import create_history_tools

            pipeline = await self._ensure_compaction_pipeline()
            if not pipeline or not pipeline.has_compacted:
                return

            if hasattr(self, "tools") and self.tools.get("read_history_chapter"):
                return

            history_tools = create_history_tools(pipeline)
            for name, func_tool in history_tools.items():
                if hasattr(self, "tools") and not self.tools.get(name):
                    try:
                        from ...core.base_tool import FunctionTool

                        if isinstance(func_tool, FunctionTool):
                            self.tools.register_function(
                                name=name,
                                description=getattr(
                                    func_tool, "description", f"History tool: {name}"
                                ),
                                func=getattr(
                                    func_tool, "func", lambda: "Not available"
                                ),
                                parameters=getattr(func_tool, "args", {}),
                            )
                    except Exception as e:
                        logger.debug(f"Failed to register history tool {name}: {e}")

            logger.info(f"[{self.__class__.__name__}] History recovery tools injected")
        except Exception as e:
            logger.debug(
                f"[{self.__class__.__name__}] Failed to inject history tools: {e}"
            )

    # ==================== WorkLog Tool Messages Conversion ====================

    async def _get_worklog_tool_messages(
        self, max_entries: int = 30
    ) -> List[Dict[str, Any]]:
        """
        将 WorkLog 历史转换为原生 Function Call 格式的工具消息列表。

        重写此方法以支持原生 Function Call 模式下的历史工具调用记录传递。

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
            logger.debug(
                f"[{self.__class__.__name__}] No compaction pipeline, returning empty tool messages"
            )
            return []

        try:
            # 使用压缩摘要，保证上下文连续性
            tool_messages = await pipeline.get_tool_messages_from_worklog(
                max_entries=max_entries,
                use_compressed_summary=True,
            )
            if tool_messages:
                logger.info(
                    f"[{self.__class__.__name__}] Converted WorkLog to {len(tool_messages)} tool messages for LLM"
                )
            return tool_messages
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] Failed to get worklog tool messages: {e}"
            )
            return []

    # ==================== Layer 4: Multi-Turn History ====================

    async def start_conversation_round(
        self, user_question: str, user_context: Optional[Dict] = None
    ) -> Optional[Any]:
        """Start a new conversation round (Layer 4)."""
        try:
            pipeline = await self._ensure_compaction_pipeline()
            if pipeline:
                return await pipeline.start_conversation_round(
                    user_question, user_context
                )
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] Layer 4: Failed to start round: {e}"
            )
        return None

    async def complete_conversation_round(
        self, ai_response: str, ai_thinking: str = ""
    ):
        """Complete current conversation round (Layer 4)."""
        try:
            pipeline = await self._ensure_compaction_pipeline()
            if pipeline:
                await pipeline.complete_conversation_round(ai_response, ai_thinking)
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] Layer 4: Failed to complete round: {e}"
            )

    async def get_layer4_history_for_prompt(
        self, max_rounds: Optional[int] = None
    ) -> str:
        """Get Layer 4 compressed history for prompt injection."""
        try:
            pipeline = await self._ensure_compaction_pipeline()
            if pipeline:
                return await pipeline.get_layer4_history_for_prompt(max_rounds)
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] Layer 4: Failed to get history: {e}"
            )
        return ""
