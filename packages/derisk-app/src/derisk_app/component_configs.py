import logging
import os
from typing import Optional
from derisk.agent.resource.agent_skills import AgentSkillResource
from derisk.agent.resource.workflow import WorkflowResource
from derisk.component import SystemApp
from derisk.configs.model_config import MODEL_DISK_CACHE_DIR, resolve_root_path
from derisk.util.executor_utils import DefaultExecutorFactory
from derisk.vis.vis_manage import initialize_vis_convert
from derisk_app.config import ApplicationConfig, ServiceWebParameters
from derisk_serve.agent.resource.knowledge_pack import KnowledgePackSearchResource
from derisk_serve.agent.resource.tool.local_tool import LocalToolPack
from derisk_serve.agent.resource.tool.mcp import MCPSSEToolPack
from derisk_serve.agent.resource.tool.mcp_collect import MCPCollectSSEToolPack
from derisk_serve.agent.resource.derisk_skill import DeriskSkillResource

from derisk_serve.rag.storage_manager import StorageManager

logger = logging.getLogger(__name__)


def initialize_components(
    param: ApplicationConfig,
    system_app: SystemApp,
):
    from derisk.model.cluster.controller.controller import controller
    from derisk_app.initialization.embedding_component import (
        _initialize_embedding_model,
        _initialize_rerank_model,
    )
    from derisk_app.initialization.scheduler import DefaultScheduler
    from derisk_app.initialization.serve_initialization import register_serve_apps
    from derisk_serve.datasource.manages.connector_manager import ConnectorManager
    from derisk.sandbox import initialize_sandbox_adapter
    from derisk_serve.agent.agents.controller import multi_agents

    # Initialize Oracle thick mode at startup (for Oracle 11g support)
    _initialize_oracle_thick_mode(param)

    web_config = param.service.web
    default_embedding_name = param.models.default_embedding
    default_rerank_name = param.models.default_reranker
    system_app.register(
        DefaultExecutorFactory, max_workers=web_config.default_thread_pool_size
    )
    system_app.register(DefaultScheduler)
    system_app.register_instance(controller)
    system_app.register(ConnectorManager)
    system_app.register(StorageManager)

    system_app.register_instance(multi_agents)
    if default_embedding_name:
        _initialize_embedding_model(system_app, default_embedding_name)
    if default_rerank_name:
        _initialize_rerank_model(system_app, default_rerank_name)
    _initialize_model_cache(system_app, web_config)
    _initialize_awel(system_app, web_config.awel_dirs)
    # Initialize resource manager of agent
    _initialize_resource_manager(system_app)
    _initialize_agent(system_app)

    initialize_sandbox_adapter(system_app)
    _initialize_openapi(system_app)
    # Register serve apps
    register_serve_apps(system_app, param, web_config.host, web_config.port)
    _initialize_operators()
    _initialize_code_server(system_app)
    _initialize_local_tool(system_app)
    _initialize_mcp_cache()
    _initialize_context(system_app)
    _initialize_perfermance(system_app)


def _initialize_model_cache(system_app: SystemApp, web_config: ServiceWebParameters):
    from derisk.storage.cache import initialize_cache

    if not web_config.model_cache or not web_config.model_cache.enable_model_cache:
        logger.info("Model cache is not enable")
        return
    storage_type = web_config.model_cache.storage_type or "memory"
    max_memory_mb = web_config.model_cache.max_memory_mb or 256
    if web_config.model_cache.persist_dir:
        persist_dir = web_config.model_cache.persist_dir
    else:
        persist_dir = f"{MODEL_DISK_CACHE_DIR}_{web_config.port}"
    persist_dir = resolve_root_path(persist_dir)
    initialize_cache(system_app, storage_type, max_memory_mb, persist_dir)


def _initialize_awel(system_app: SystemApp, awel_dirs: Optional[str] = None):
    from derisk.configs.model_config import _DAG_DEFINITION_DIR
    from derisk.core.awel import initialize_awel

    # Add default dag definition dir
    dag_dirs = [_DAG_DEFINITION_DIR]
    if awel_dirs:
        dag_dirs += awel_dirs.strip().split(",")
    dag_dirs = [x.strip() for x in dag_dirs]
    initialize_awel(system_app, dag_dirs)


def _initialize_agent(system_app: SystemApp):
    from derisk.agent import initialize_agent

    initialize_agent(system_app)

    ## init agent vis convert
    initialize_vis_convert(system_app)


def _initialize_resource_manager(system_app: SystemApp):
    from derisk.agent.expand.resources.derisk_tool import list_derisk_support_models
    from derisk.agent.resource.base import ResourceType
    from derisk.agent.resource.manage import get_resource_manager, initialize_resource, _SYSTEM_APP as check_system_app
    from derisk_serve.agent.resource.app import GptAppResource
    from derisk_serve.agent.resource.datasource import DatasourceResource
    from derisk_serve.agent.resource.knowledge import KnowledgeSpaceRetrieverResource

    from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
    from derisk.agent.resource.memory import MemoryResource
    from derisk.agent.expand.resources.fetch_tool import fetch

    logger.info(
        f"[ResourceInit] _initialize_resource_manager called, "
        f"system_app_id={id(system_app)}, "
        f"_SYSTEM_APP_before={id(check_system_app) if check_system_app else 'None'}"
    )

    initialize_resource(system_app)
    rm = get_resource_manager(system_app)
    logger.info(
        f"[ResourceInit] ResourceManager instance created, "
        f"system_app_id={id(system_app)}, rm_id={id(rm)}"
    )
    rm.register_resource(
        DatasourceResource, resource_type_alias="datasource"
    )
    logger.info(
        f"[ResourceInit] DatasourceResource registered with alias='datasource', "
        f"type_to_resources_keys={list(rm._type_to_resources.keys())}"
    )
    rm.register_resource(KnowledgeSpaceRetrieverResource)
    rm.register_resource(GptAppResource)
    rm.register_resource(resource_instance=fetch)
    rm.register_resource(resource_instance=list_derisk_support_models)
    # Register mcp tool
    rm.register_resource(MCPSSEToolPack, resource_type=ResourceType.Tool)
    rm.register_resource(MCPCollectSSEToolPack, resource_type=ResourceType.Tool)
    rm.register_resource(LocalToolPack, resource_type=ResourceType.Tool)
    rm.register_resource(AgentSkillResource)
    rm.register_resource(DeriskSkillResource)
    rm.register_resource(ReasoningEngineResource)
    rm.register_resource(KnowledgePackSearchResource)
    rm.register_resource(MemoryResource)
    rm.register_resource(WorkflowResource)

    # Register openderisk tool
    # Register Excel File to DB tools
    from derisk_ext.agent.agents.open_ta.tools.xls_analysis import get_data_introduction
    from derisk_ext.agent.agents.open_ta.tools.xls_analysis import run_sql_with_file

    rm.register_resource(resource_instance=get_data_introduction)
    rm.register_resource(resource_instance=run_sql_with_file)

    # Register Flamegraph analysis tools
    from derisk_ext.agent.agents.open_ta.tools.flamegraph_cpu_analyzer import (
        flamegraph_overview,
    )
    from derisk_ext.agent.agents.open_ta.tools.flamegraph_cpu_analyzer import (
        flamegraph_drill_down,
    )

    rm.register_resource(resource_instance=flamegraph_overview)
    rm.register_resource(resource_instance=flamegraph_drill_down)

    # Register OpenRCA scene resource
    from derisk_ext.agent.agents.open_rca.resource.open_rca_resource import (
        OpenRcaSceneResource,
    )

    rm.register_resource(OpenRcaSceneResource)

    # Final summary of all registered types
    logger.info(
        f"[ResourceInit] All resources registered, "
        f"final_type_to_resources_keys={list(rm._type_to_resources.keys())}, "
        f"rm_id={id(rm)}, system_app_id={id(system_app)}"
    )

    # Register mock tool 在页面上注册工具
    # from derisk_ext.agent.agents.smartTestUI.tool.image_find_static_bug_tools import find_image_bugs
    # from derisk_ext.agent.agents.smartTestUI.tool.test_analysis_tools import generate_analysis_tool
    # from derisk_ext.agent.agents.smartTestUI.tool.tvp_cypress_code_tools import tvp_cypress_code
    # from derisk_ext.agent.agents.smartTestUI.tool.tvp_run_task_tools import tvp_execute_case
    # from derisk_ext.agent.agents.smartTestUI.tool.tvp_url_tools import tvp_main_screenshot, tvp_multi_screenshot
    # from derisk_ext.agent.agents.smartTestUI.tool.ding_information_tools import ding_send_text
    # from derisk_ext.agent.agents.smartTestUI.tool.image_analysis_tools import analysis_image
    # rm.register_resource(resource_instance=find_image_bugs)
    # rm.register_resource(resource_instance=tvp_main_screenshot)
    # rm.register_resource(resource_instance=tvp_multi_screenshot)
    # rm.register_resource(resource_instance=analysis_image)
    # rm.register_resource(resource_instance=generate_analysis_tool)
    # rm.register_resource(resource_instance=tvp_cypress_code)
    # rm.register_resource(resource_instance=tvp_execute_case)
    # rm.register_resource(resource_instance=ding_send_text)
    # Register risk punish tool
    # from derisk_ext.agent.agents.smartTestUI.tool.risk_punish_tools import create_dima_link
    # rm.register_resource(resource_instance=create_dima_link)

    # Register scene generate tool
    # from derisk_ext.agent.agents.smartTestFlux.tool.flux_scene_generate_tools import query_interface_description
    # from derisk_ext.agent.agents.smartTestFlux.tool.flux_scene_generate_tools import select_important_feature_key
    # from derisk_ext.agent.agents.smartTestFlux.tool.flux_scene_generate_tools import select_important_feature_key_value_list
    # from derisk_ext.agent.agents.smartTestFlux.tool.flux_scene_generate_tools import pair_feature
    # rm.register_resource(resource_instance=query_interface_description)
    # rm.register_resource(resource_instance=select_important_feature_key)
    # rm.register_resource(resource_instance=select_important_feature_key_value_list)
    # rm.register_resource(resource_instance=pair_feature)


def _initialize_oracle_thick_mode(param: ApplicationConfig = None):
    """Initialize Oracle thick mode at server startup.

    This must be called BEFORE any Oracle connection is made.
    For Oracle 11g and earlier, thick mode is required because
    python-oracledb thin mode doesn't support these versions.

    Configuration via System Config Management (数据源配置):
    - oracle_enable_thick_mode: 启用 thick mode（默认 False）
    - oracle_instant_client_path: Instant Client 路径（可选）

    Or via environment variable:
    - ORACLE_ENABLE_THICK_MODE=true: Enable thick mode
    - ORACLE_INSTANT_CLIENT_HOME: Path to Instant Client

    IMPORTANT: Once thick mode is initialized, ALL subsequent Oracle connections
    in this process will use thick mode automatically. No need to configure each connection.

    For multi-worker deployments: Each worker process initializes thick mode independently.
    The global state is per-process, so all workers will have thick mode enabled.
    """
    # Get datasource config from derisk.json (managed by System Config Management)
    from derisk_core.config import ConfigManager

    logger.info("[OracleInit] Starting Oracle thick mode initialization check...")

    try:
        manager = ConfigManager
        config = manager.get()
        logger.info(f"[OracleInit] ConfigManager.get() returned config, type={type(config)}")
        datasource_config = getattr(config, 'datasource', None)
        logger.info(f"[OracleInit] datasource_config={datasource_config}, type={type(datasource_config)}")
        if datasource_config:
            logger.info(
                f"[OracleInit] DatasourceConfig attributes: "
                f"oracle_enable_thick_mode={getattr(datasource_config, 'oracle_enable_thick_mode', 'NOT_FOUND')}, "
                f"oracle_instant_client_path={getattr(datasource_config, 'oracle_instant_client_path', 'NOT_FOUND')}"
            )
    except Exception as e:
        logger.warning(f"[OracleInit] Failed to read config: {e}")
        datasource_config = None

    # Default values
    enable_thick_mode = False
    instant_client_path = None

    # Read from datasource config
    if datasource_config:
        enable_thick_mode = getattr(datasource_config, 'oracle_enable_thick_mode', False)
        instant_client_path = getattr(datasource_config, 'oracle_instant_client_path', None)

    # Also check environment variable as override
    env_enable = os.environ.get('ORACLE_ENABLE_THICK_MODE', '').lower() in ('true', '1', 'yes')
    if env_enable:
        enable_thick_mode = True
        logger.info("[OracleInit] Environment variable ORACLE_ENABLE_THICK_MODE=true detected")

    # Environment variable for instant client path
    env_client_path = os.environ.get('ORACLE_INSTANT_CLIENT_HOME')
    if env_client_path:
        instant_client_path = env_client_path
        logger.info(f"[OracleInit] Environment variable ORACLE_INSTANT_CLIENT_HOME={env_client_path} detected")

    logger.info(
        f"[OracleInit] Final thick mode decision: enable_thick_mode={enable_thick_mode}, "
        f"instant_client_path={instant_client_path}"
    )

    if not enable_thick_mode:
        logger.info(
            "[OracleInit] Thick mode disabled. "
            "Enable via System Config Management (数据源配置 -> oracle_enable_thick_mode) "
            "or set ORACLE_ENABLE_THICK_MODE=true for Oracle 11g support."
        )
        return

    try:
        from derisk_ext.datasource.rdbms.conn_oracle import _init_thick_mode

        logger.info("[OracleInit] Initializing Oracle thick mode at startup...")
        success = _init_thick_mode(instant_client_path)
        if success:
            logger.info(
                "[OracleInit] Oracle thick mode initialized successfully. "
                "All Oracle connections in this process will use thick mode."
            )
        else:
            logger.warning(
                "[OracleInit] Oracle thick mode initialization failed. "
                "Please install Oracle Instant Client and set oracle_instant_client_path "
                "in System Config Management or ORACLE_INSTANT_CLIENT_HOME environment variable."
            )
    except ImportError:
        logger.debug("[OracleInit] derisk_ext not available, skipping Oracle thick mode init")
    except Exception as e:
        logger.warning(f"[OracleInit] Failed to initialize Oracle thick mode: {e}")


def _initialize_openapi(system_app: SystemApp):
    pass


def _initialize_operators():
    from derisk_app.operators.code import CodeMapOperator  # noqa: F401
    from derisk_app.operators.converter import StringToInteger  # noqa: F401

    from derisk_app.operators.llm import (  # noqa: F401
        HOLLMOperator,
        HOStreamingLLMOperator,
    )
    from derisk_app.operators.rag import HOKnowledgeOperator  # noqa: F401
    from derisk_serve.agent.resource.datasource import DatasourceResource  # noqa: F401


def _initialize_code_server(system_app: SystemApp):
    from derisk.util.code.server import initialize_code_server

    initialize_code_server(system_app)


def _initialize_local_tool(system_app: SystemApp):
    from derisk_serve.agent.resource.func_registry import central_registry
    # central_registry.set_system_app(system_app)


def _initialize_mcp_cache():
    logger.info("未支持")


def _initialize_context(system_app: SystemApp):
    from derisk.context.operator import OperatorManager

    OperatorManager.operator_scan()


def _initialize_perfermance(system_app: SystemApp):
    from derisk.perf.profiler import PerformanceProfiler

    system_app.register(component=PerformanceProfiler)
