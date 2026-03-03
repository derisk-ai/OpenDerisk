"""
Core_v2 适配器 - 在现有服务中集成 Core_v2

架构说明：
===========

1. 统一配置模型 (UnifiedTeamContext):
   - agent_version: "v1" | "v2"  ← 选择架构版本
   - team_mode: "single_agent" | "multi_agent"  ← 工作模式
   - agent_name: 主Agent名称
     - v1: AgentManager 中预注册的 Agent
     - v2: V2 预定义模板 (simple_chat, planner, etc.)

2. V2 Agent 模板:
   - simple_chat: 简单对话Agent
   - planner: 规划执行Agent (PDCA)
   - code_assistant: 代码助手
   - data_analyst: 数据分析师
   - researcher: 研究助手
   - writer: 写作助手

3. API:
   - GET /api/agent/list?version=v2  获取V2可用Agent列表
   - POST /api/v2/chat  发送消息

使用示例：
=========

# 应用配置
{
    "app_code": "my_app",
    "agent_version": "v2",
    "team_mode": "single_agent",
    "team_context": {
        "agent_name": "planner",
        "tools": ["bash", "python"]
    }
}
"""
import logging
from typing import Optional, Dict, Any, List

from derisk.component import SystemApp, ComponentType, BaseComponent
from derisk._private.config import Config
from derisk.agent.core_v2.integration import (
    V2AgentRuntime,
    RuntimeConfig,
    V2AgentDispatcher,
    create_v2_agent,
)
from derisk.model.cluster import WorkerManagerFactory
from derisk.model import DefaultLLMClient

logger = logging.getLogger(__name__)
CFG = Config()


class CoreV2Component(BaseComponent):
    """Core_v2 组件"""
    
    name = "core_v2_runtime"
    
    def __init__(self, system_app: SystemApp):
        super().__init__(system_app)
        self.runtime: Optional[V2AgentRuntime] = None
        self.dispatcher: Optional[V2AgentDispatcher] = None
        self._started = False
        self._dynamic_agent_factory = None
    
    async def async_after_start(self):
        """组件启动后自动启动 Core_v2"""
        import sys
        print(f"[CoreV2Component] async_after_start called, id={id(self)}", file=sys.stderr, flush=True)
        logger.info("[CoreV2Component] async_after_start called, starting dispatcher...")
        await self.start()
        logger.info("[CoreV2Component] async_after_start completed")
    
    async def async_before_stop(self):
        """组件停止前自动停止 Core_v2"""
        logger.info("[CoreV2Component] async_before_stop called")
        await self.stop()
    
    def init_app(self, system_app: SystemApp):
        import sys
        print(f"[CoreV2Component] init_app called, id={id(self)}", file=sys.stderr, flush=True)
        self.system_app = system_app
        self._register_model_configs()
    
    def _register_model_configs(self):
        """注册全局模型配置到缓存"""
        from derisk.agent.util.llm.model_config_cache import (
            ModelConfigCache,
            parse_provider_configs,
        )
        
        global_agent_conf = self.system_app.config.get("agent.llm")
        if not global_agent_conf:
            agent_conf = self.system_app.config.get("agent")
            if isinstance(agent_conf, dict):
                global_agent_conf = agent_conf.get("llm")
        
        if global_agent_conf:
            model_configs = parse_provider_configs(global_agent_conf)
            if model_configs:
                ModelConfigCache.register_configs(model_configs)
                logger.info(f"[CoreV2Component] Registered {len(model_configs)} models to global cache")
    
    async def start(self):
        """启动 Core_v2"""
        if self._started:
            return

        gpts_memory = None
        try:
            from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
            gpts_memory = self.system_app.get_component(
                ComponentType.GPTS_MEMORY, GptsMemory
            )
        except Exception:
            logger.warning("GptsMemory not found")

        # 获取 LLM 客户端用于分层上下文管理
        llm_client = None
        try:
            worker_manager = self.system_app.get_component(
                ComponentType.WORKER_MANAGER, WorkerManagerFactory
            )
            if worker_manager:
                llm_client = DefaultLLMClient(
                    worker_manager=worker_manager.create(),
                    model_name=CFG.LLM_MODEL,
                )
                logger.info("[CoreV2Component] LLM client initialized for hierarchical context")
        except Exception as e:
            logger.warning(f"[CoreV2Component] Failed to initialize LLM client: {e}")

        # 获取 Conversation 存储（用于 ChatHistoryMessageEntity）
        conv_storage = None
        message_storage = None
        try:
            from derisk_serve.conversation.serve import Serve as ConversationServe
            conv_serve = ConversationServe.get_instance(self.system_app)
            if conv_serve:
                conv_storage = conv_serve.conv_storage
                message_storage = conv_serve.message_storage
                logger.info("[CoreV2Component] Conversation storage initialized")
        except Exception as e:
            logger.warning(f"[CoreV2Component] Failed to initialize conversation storage: {e}")

        self.runtime = V2AgentRuntime(
            config=RuntimeConfig(
                max_concurrent_sessions=100,
                session_timeout=3600,
                enable_streaming=True,
            ),
            gpts_memory=gpts_memory,
            enable_hierarchical_context=True,  # 启用分层上下文
            llm_client=llm_client,
            conv_storage=conv_storage,
            message_storage=message_storage,
        )
        
        self._register_agent_factories()
        
        self.dispatcher = V2AgentDispatcher(
            runtime=self.runtime,
            max_workers=10,
        )
        
        await self.dispatcher.start()
        self._started = True
        logger.info("Core_v2 component started")
    
    async def stop(self):
        """停止 Core_v2"""
        if self.dispatcher:
            await self.dispatcher.stop()
        self._started = False
        logger.info("Core_v2 component stopped")
    
    def _register_agent_factories(self):
        """
        注册 Agent 工厂
        
        支持两种方式:
        1. 预定义模板 (simple_chat, planner, etc.)
        2. 动态加载 (根据 app_code 从数据库加载配置)
        """
        
        def create_from_template(agent_name: str, context, **kwargs):
            """根据模板名称创建 Agent"""
            from derisk.agent.core.plan.unified_context import (
                V2_AGENT_TEMPLATES, 
                V2AgentTemplate
            )
            
            template = V2_AGENT_TEMPLATES.get(V2AgentTemplate(agent_name))
            if template:
                logger.info(f"[CoreV2Component] 使用模板创建 Agent: {agent_name}")
                
                # 新增：支持三种内置Agent
                if agent_name == "react_reasoning":
                    from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent
                    return ReActReasoningAgent.create(
                        name=agent_name,
                        **kwargs
                    )
                elif agent_name == "file_explorer":
                    from derisk.agent.core_v2.builtin_agents import FileExplorerAgent
                    return FileExplorerAgent.create(
                        name=agent_name,
                        **kwargs
                    )
                elif agent_name == "coding":
                    from derisk.agent.core_v2.builtin_agents import CodingAgent
                    return CodingAgent.create(
                        name=agent_name,
                        **kwargs
                    )
                
                # 原有模板
                return create_v2_agent(
                    name=agent_name,
                    mode=template.get("mode", "primary"),
                )
            
            return create_v2_agent(name=agent_name, mode="primary")
        
        async def dynamic_agent_factory(context, app_code: str = None, **kwargs):
            """
            动态 Agent 工厂
            
            优先级:
            1. 检查是否为预定义模板
            2. 从数据库加载应用配置
            3. 使用默认 Agent
            """
            from derisk.agent.core.plan.unified_context import V2AgentTemplate
            
            agent_name = app_code or context.agent_name
            logger.info(f"[CoreV2Component] 动态创建 Agent: {agent_name}")
            
            try:
                if agent_name in [t.value for t in V2AgentTemplate]:
                    return create_from_template(agent_name, context, **kwargs)
                
                from derisk_serve.building.app.config import SERVE_SERVICE_COMPONENT_NAME
                from derisk_serve.building.app.service.service import Service
                app_service = self.system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
                gpt_app = await app_service.app_detail(
                    agent_name, specify_config_code=None, building_mode=False
                )
                
                if gpt_app:
                    return await self._build_v2_agent_from_gpts_app(gpt_app, context, **kwargs)
                    
            except Exception as e:
                logger.exception(f"[CoreV2Component] 加载应用配置失败: {agent_name}")
            
            return create_v2_agent(name=agent_name or "default", mode="primary")
        
        async def fallback_factory(context, **kwargs):
            """兜底工厂 - 异步加载应用配置"""
            app_code = kwargs.get('app_code') or context.agent_name
            logger.info(f"[CoreV2Component] 使用兜底 Agent: {app_code}")
            
            from derisk.agent.core.plan.unified_context import V2AgentTemplate
            if app_code in [t.value for t in V2AgentTemplate]:
                return create_from_template(app_code, context, **kwargs)
            
            try:
                from derisk_serve.building.app.config import SERVE_SERVICE_COMPONENT_NAME
                from derisk_serve.building.app.service.service import Service
                app_service = self.system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
                gpt_app = await app_service.app_detail(
                    app_code, specify_config_code=None, building_mode=False
                )
                
                if gpt_app:
                    return await self._build_v2_agent_from_gpts_app(gpt_app, context, **kwargs)
            except Exception as e:
                logger.exception(f"[CoreV2Component] 加载应用配置失败: {app_code}")
            
            return create_v2_agent(name=app_code or "default", mode="primary")
        
        self.runtime.register_agent_factory("default", fallback_factory)
        self._dynamic_agent_factory = dynamic_agent_factory
        
        # 注册所有Agent模板工厂（包括新增的3种内置Agent）
        for template_name in ["simple_chat", "planner", "code_assistant", 
                              "data_analyst", "researcher", "writer",
                              "react_reasoning", "file_explorer", "coding"]:
            self.runtime.register_agent_factory(
                template_name,
                lambda ctx, name=template_name, **kw: create_from_template(name, ctx, **kw)
            )
        
        logger.info("[CoreV2Component] Agent 工厂已注册（包含3种新增内置Agent）")
    
    async def _build_v2_agent_from_gpts_app(self, gpt_app, context, **kwargs):
        """
        根据 GptsApp 配置构建 V2 Agent
        
        使用 UnifiedTeamContext 统一处理配置
        """
        from derisk.agent.core.plan.unified_context import UnifiedTeamContext
        from derisk.agent.core_v2.agent_info import PermissionRuleset
        
        app_code = gpt_app.app_code
        team_context = gpt_app.team_context
        
        logger.info(f"[CoreV2Component] _build_v2_agent_from_gpts_app 开始:")
        logger.info(f"  - app_code: {app_code}")
        logger.info(f"  - team_context 原始值: {team_context}")
        logger.info(f"  - team_context type: {type(team_context)}")
        if team_context:
            if hasattr(team_context, '__dict__'):
                logger.info(f"  - team_context.__dict__: {team_context.__dict__}")
        
        unified_ctx = None
        if team_context:
            if isinstance(team_context, UnifiedTeamContext):
                unified_ctx = team_context
                logger.info(f"  - team_context 是 UnifiedTeamContext")
            elif isinstance(team_context, dict):
                unified_ctx = UnifiedTeamContext.from_dict(team_context)
                logger.info(f"  - team_context 是 dict，转换后: {unified_ctx}")
            else:
                from derisk.agent.core.plan.base import SingleAgentContext
                from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
                
                if isinstance(team_context, SingleAgentContext):
                    unified_ctx = UnifiedTeamContext.from_legacy_single_agent(
                        team_context, 
                        agent_version=getattr(gpt_app, 'agent_version', 'v2')
                    )
                    logger.info(f"  - team_context 是 SingleAgentContext，转换后: {unified_ctx}")
                elif isinstance(team_context, AutoTeamContext):
                    unified_ctx = UnifiedTeamContext.from_legacy_auto_team(
                        team_context,
                        agent_version=getattr(gpt_app, 'agent_version', 'v2')
                    )
                    logger.info(f"  - team_context 是 AutoTeamContext，转换后: {unified_ctx}")
                else:
                    logger.warning(f"  - team_context 类型未知: {type(team_context)}")
        
        if not unified_ctx:
            logger.warning(f"[CoreV2Component] unified_ctx 为空，使用默认 simple_chat")
            unified_ctx = UnifiedTeamContext(
                agent_version=getattr(gpt_app, 'agent_version', 'v2'),
                team_mode="single_agent",
                agent_name="simple_chat",
            )
        
        logger.info(f"[CoreV2Component] 构建 V2 Agent:")
        logger.info(f"  - app_code: {app_code}")
        logger.info(f"  - agent_name: {unified_ctx.agent_name}")
        logger.info(f"  - team_mode: {unified_ctx.team_mode}")
        
        tools = await self._build_tools_from_resources(gpt_app.resources)
        resources = await self._build_resources_dict(gpt_app.resources)
        
        # 获取 V2 Agent 模板配置
        from derisk.agent.core.plan.unified_context import (
            V2AgentTemplate, 
            V2_AGENT_TEMPLATES, 
            get_v2_agent_template
        )
        
        agent_name = unified_ctx.agent_name
        template_config = get_v2_agent_template(agent_name)
        
        if template_config:
            mode = template_config.get("mode", "primary")
            template_tools = template_config.get("tools", [])
            logger.info(f"  - 使用模板: {agent_name}, mode={mode}, tools={template_tools}")
        else:
            mode = "planner" if unified_ctx.is_multi_agent() or bool(tools) else "primary"
            logger.info(f"  - 动态模式: mode={mode}")
        
        model_provider = await self._build_model_provider(gpt_app)
        
        # 新增：如果是内置Agent，使用对应的创建方法
        if agent_name == "react_reasoning":
            from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent
            logger.info(f"[CoreV2Component] 创建 ReActReasoningAgent")
            
            # 获取模型名称
            model_name = "gpt-4"
            if model_provider and hasattr(model_provider, 'strategy_context') and model_provider.strategy_context:
                if isinstance(model_provider.strategy_context, list) and len(model_provider.strategy_context) > 0:
                    model_name = model_provider.strategy_context[0]
                elif isinstance(model_provider.strategy_context, str):
                    model_name = model_provider.strategy_context
            
            agent = ReActReasoningAgent.create(
                name=agent_name,
                model=model_name,
                api_key=None,  # 不传api_key，让Agent使用默认配置
                max_steps=30,
                enable_doom_loop_detection=True,
                enable_output_truncation=True,
                enable_context_compaction=True,
                enable_history_pruning=True,
            )
            # 注意：不要覆盖agent.llm，内置Agent已经有完整的LLMAdapter实现
            # 如果需要使用model_provider的llm_client，应该通过其他方式注入
            logger.info(f"[CoreV2Component] ReActReasoningAgent创建完成，使用模型: {model_name}")
        elif agent_name == "file_explorer":
            from derisk.agent.core_v2.builtin_agents import FileExplorerAgent
            logger.info(f"[CoreV2Component] 创建 FileExplorerAgent")
            
            # 获取模型名称
            model_name = "gpt-4"
            if model_provider and hasattr(model_provider, 'strategy_context') and model_provider.strategy_context:
                if isinstance(model_provider.strategy_context, list) and len(model_provider.strategy_context) > 0:
                    model_name = model_provider.strategy_context[0]
                elif isinstance(model_provider.strategy_context, str):
                    model_name = model_provider.strategy_context
            
            agent = FileExplorerAgent.create(
                name=agent_name,
                model=model_name,
                api_key=None,
                project_path="./",
                enable_auto_exploration=True,
            )
            logger.info(f"[CoreV2Component] FileExplorerAgent创建完成，使用模型: {model_name}")
        elif agent_name == "coding":
            from derisk.agent.core_v2.builtin_agents import CodingAgent
            logger.info(f"[CoreV2Component] 创建 CodingAgent")
            
            # 获取模型名称
            model_name = "gpt-4"
            if model_provider and hasattr(model_provider, 'strategy_context') and model_provider.strategy_context:
                if isinstance(model_provider.strategy_context, list) and len(model_provider.strategy_context) > 0:
                    model_name = model_provider.strategy_context[0]
                elif isinstance(model_provider.strategy_context, str):
                    model_name = model_provider.strategy_context
            
            agent = CodingAgent.create(
                name=agent_name,
                model=model_name,
                api_key=None,
                workspace_path="./",
                enable_auto_exploration=True,
                enable_code_quality_check=True,
            )
            logger.info(f"[CoreV2Component] CodingAgent创建完成，使用模型: {model_name}")
        else:
            # 原有的通用创建逻辑
            agent = create_v2_agent(
                name=agent_name,
                mode=mode,
                tools=tools,
                resources=resources,
                model_provider=model_provider,
            )
        
        logger.info(f"[CoreV2Component] Agent 创建完成: {type(agent).__name__}")
        return agent
    
    async def _build_tools_from_resources(self, resources) -> Dict[str, Any]:
        """从资源列表构建工具字典"""
        tools = {}
        if not resources:
            return tools
        for resource in resources:
            if resource and getattr(resource, 'type', None) == "tool":
                tool_name = getattr(resource, 'name', None)
                if tool_name:
                    tools[tool_name] = resource
        return tools
    
    async def _build_resources_dict(self, resources) -> Dict[str, Any]:
        """构建资源字典"""
        result = {"knowledge": [], "skills": [], "tools": []}
        if not resources:
            return result
        for resource in resources:
            if not resource:
                continue
            res_type = getattr(resource, 'type', None)
            if res_type in result:
                result[res_type].append(resource)
        return result
    
    async def _build_model_provider(self, gpt_app) -> Optional[Any]:
        """
        根据 GptsApp 配置构建模型提供者
        
        参考 agent_chat.py 的实现，使用 LLMConfig 和 LLMStrategy 来选择模型
        """
        try:
            from derisk.model.cluster import WorkerManagerFactory
            from derisk.model import DefaultLLMClient
            from derisk.agent.util.llm.llm import LLMConfig, LLMStrategyType
            
            worker_manager = self.system_app.get_component(
                ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
            ).create()
            
            llm_client = DefaultLLMClient(worker_manager, auto_convert_message=True)
            
            llm_config_data = getattr(gpt_app, 'llm_config', None)
            
            if llm_config_data:
                llm_strategy = getattr(llm_config_data, 'llm_strategy', None)
                llm_strategy_value = getattr(llm_config_data, 'llm_strategy_value', None)
                llm_param = getattr(llm_config_data, 'llm_param', None)
                mist_keys = getattr(llm_config_data, 'mist_keys', None)
                
                strategy_type = LLMStrategyType(llm_strategy) if llm_strategy else LLMStrategyType.Default
                
                llm_config = LLMConfig(
                    llm_client=llm_client,
                    llm_strategy=strategy_type,
                    strategy_context=llm_strategy_value,
                    llm_param=llm_param or {},
                    mist_keys=mist_keys,
                )
                
                logger.info(f"[CoreV2Component] LLM provider 创建成功, strategy={strategy_type}, context={llm_strategy_value}")
                return llm_config
            else:
                llm_config = LLMConfig(
                    llm_client=llm_client,
                    llm_strategy=LLMStrategyType.Default,
                )
                logger.info(f"[CoreV2Component] LLM provider 创建成功 (默认配置)")
                return llm_config
            
        except Exception as e:
            logger.exception(f"[CoreV2Component] 创建 LLM provider 失败: {e}")
            return None
    
    async def get_or_create_agent(self, app_code: str, context=None):
        """获取或创建 Agent 实例"""
        if app_code in self.runtime._agents:
            return self.runtime._agents[app_code]
        
        if self._dynamic_agent_factory:
            from derisk.agent.core_v2.integration.runtime import SessionContext
            dummy_context = context or SessionContext(
                session_id="temp",
                conv_id="temp",
                agent_name=app_code,
            )
            agent = await self._dynamic_agent_factory(dummy_context, app_code=app_code)
            if agent:
                self.runtime._agents[app_code] = agent
            return agent
        return None


_core_v2: Optional[CoreV2Component] = None


def get_core_v2() -> CoreV2Component:
    """获取 Core_v2 组件"""
    global _core_v2
    import sys
    import traceback
    print(f"[get_core_v2] called, _core_v2 is None: {_core_v2 is None}, id={id(_core_v2) if _core_v2 else 'N/A'}", file=sys.stderr, flush=True)
    if _core_v2 is None:
        print("[get_core_v2] Stack trace:", file=sys.stderr, flush=True)
        traceback.print_stack(file=sys.stderr)
        _core_v2 = CoreV2Component(CFG.SYSTEM_APP)
        print(f"[get_core_v2] created new instance, id={id(_core_v2)}", file=sys.stderr, flush=True)
    return _core_v2
