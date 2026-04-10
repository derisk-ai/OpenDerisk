import logging
import os
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles


class WebSocketAwareStaticFiles(StaticFiles):
    """StaticFiles that gracefully handles WebSocket connections."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            # WebSocket connections should not reach static files
            # Let them fall through to 404 or other handlers
            await send({"type": "websocket.close", "code": 1000})
            return
        await super().__call__(scope, receive, send)


from derisk._version import version
from derisk.component import SystemApp
from derisk.configs.model_config import (
    STATIC_MESSAGE_IMG_PATH,
)
from derisk.util.fastapi import create_app as create_fastapi_app, replace_router
from derisk.util.i18n_utils import _
from derisk.util.i18n_utils import set_default_language
from derisk.util.tracer import initialize_tracer
from derisk_app.base import (
    _create_model_start_listener,
    _migration_db_storage,
    server_init,
)
from derisk_app.config import (
    ApplicationConfig,
    ServiceConfig,
    ServiceWebParameters,
    SystemParameters,
)
from derisk_serve.core import add_exception_handler

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_ROOT_PATH = os.path.dirname(os.path.dirname(ROOT_PATH)) + "/configs"
logger = logging.getLogger(__name__)


def scan_configs():
    from derisk.model import scan_model_providers
    from derisk_app.initialization.serve_initialization import scan_serve_configs
    from derisk_ext.storage import scan_storage_configs
    from derisk_serve.datasource.manages.connector_manager import ConnectorManager

    ConnectorManager.pkg_import()
    # Register all model providers
    scan_model_providers()
    # Register all serve configs
    scan_serve_configs()
    # Register all storage configs
    scan_storage_configs()


def load_config(config_file: str = None) -> ApplicationConfig:
    from derisk.configs.model_config import ROOT_PATH as DERISK_ROOT_PATH
    from derisk_ext.datasource.rdbms.conn_sqlite import SQLiteConnectorParameters
    from derisk.model.parameter import (
        ModelWorkerParameters,
        ModelServiceConfig,
    )
    from derisk.storage.cache.manager import ModelCacheParameters
    from derisk.util.tracer import TracerParameters
    from derisk.util.logger import LoggingParameters

    # 支持环境变量覆盖配置文件
    env_config = os.environ.get("DERISK_CONFIG_FILE")
    if env_config and not config_file:
        config_file = env_config

    if config_file is None:
        config_file = os.path.join(DERISK_ROOT_PATH, "configs", "derisk-minimal.toml")
    elif not os.path.isabs(config_file):
        config_file = os.path.join(DERISK_ROOT_PATH, config_file)

    from derisk.util.configure import ConfigurationManager

    if not os.path.exists(config_file):
        logger.info(
            f"Starting with zero configuration (no TOML file needed). "
            f"Configure models and settings through the web UI at http://localhost:7777"
        )

        # 支持环境变量覆盖端口和主机
        env_port = os.environ.get("DERISK_WEB_PORT")
        env_host = os.environ.get("DERISK_WEB_HOST")

        sys_config = SystemParameters()
        set_default_language(sys_config.language)
        scan_configs()

        app_config = ApplicationConfig(
            system=SystemParameters(),
            service=ServiceConfig(
                web=ServiceWebParameters(
                    host=env_host or "0.0.0.0",
                    port=int(env_port) if env_port else 7777,
                    database=SQLiteConnectorParameters(
                        path="pilot/meta_data/derisk.db",
                        check_same_thread=False,
                    ),
                    model_storage="database",
                    model_cache=ModelCacheParameters(
                        enable_model_cache=True,
                        storage_type="memory",
                        max_memory_mb=256,
                    ),
                ),
                model=ModelServiceConfig(
                    worker=ModelWorkerParameters(host="127.0.0.1", port=8001),
                ),
            ),
            trace=TracerParameters(),
            log=LoggingParameters(),
        )

        logger.info(
            f"Service ready. Open http://localhost:{app_config.service.web.port} to configure."
        )
        return app_config

    logger.info(f"Loading configuration from: {config_file}")
    cfg = ConfigurationManager.from_file(config_file)
    sys_config = cfg.parse_config(SystemParameters, prefix="system")
    set_default_language(sys_config.language)

    scan_configs()

    app_config = cfg.parse_config(ApplicationConfig, hook_section="hooks")

    # 支持环境变量覆盖端口和主机（即使有配置文件）
    env_port = os.environ.get("DERISK_WEB_PORT")
    env_host = os.environ.get("DERISK_WEB_HOST")
    if env_port:
        app_config.service.web.port = int(env_port)
    if env_host:
        app_config.service.web.host = env_host

    return app_config


def mount_routers(app: FastAPI, param: Optional[ApplicationConfig] = None):
    """Lazy import to avoid high time cost"""
    from derisk_app.knowledge.api import router as knowledge_router
    from derisk_app.openapi.api_v1.api_v1 import router as api_v1
    from derisk_app.openapi.api_v1.feedback.api_fb_v1 import router as api_fb_v1
    from derisk_app.openapi.api_v2.api_v2 import router as api_v2

    app.include_router(api_v1, prefix="/api", tags=["Chat"])
    app.include_router(api_v2, prefix="/api", tags=["ChatV2"])
    app.include_router(api_fb_v1, prefix="/api", tags=["FeedBack"])
    app.include_router(knowledge_router, tags=["Knowledge"])

    from derisk_serve.agent.app.recommend_question.controller import (
        router as recommend_question_v1,
    )

    app.include_router(recommend_question_v1, prefix="/api", tags=["RecommendQuestion"])

    from derisk_serve.agent.app.controller import router as agent_app_router

    app.include_router(agent_app_router, prefix="/api", tags=["Agent App"])

    # Tool Management API routes
    from derisk_app.openapi.api_v1.tool_management_api import (
        router as tool_management_router,
    )

    app.include_router(tool_management_router, prefix="/api", tags=["Tool Management"])

    # Core_v2 Agent API routes - V1/V2 共存
    from derisk_serve.agent.core_v2_api import router as core_v2_router
    from derisk_serve.agent.agent_selection_api import router as agent_selection_router

    app.include_router(core_v2_router, tags=["Core_v2 Agent"])
    app.include_router(agent_selection_router, tags=["Agent Selection"])
    logger.info("[Core_v2] API routes registered at /api/v2")

    # Monitoring Dashboard API routes
    from derisk.agent.core_v2.monitoring_dashboard import create_dashboard_routes

    app.include_router(create_dashboard_routes(), prefix="/api/v1", tags=["Monitoring"])
    logger.info("[Monitoring] Dashboard API routes registered at /api/v1/monitoring")

    # Streaming Configuration API routes
    from derisk_serve.streaming.api import router as streaming_config_router

    app.include_router(streaming_config_router, tags=["Streaming Config"])
    logger.info("[Streaming] Config API routes registered at /api/v1/streaming-config")

    from derisk_app.feature_plugins.bootstrap import (
        register_enabled_feature_plugin_routers,
    )

    register_enabled_feature_plugin_routers(app)


def mount_static_files(app: FastAPI, param: ApplicationConfig):
    if param.service.web.new_web_ui:
        static_file_path = os.path.join(ROOT_PATH, "src", "derisk_app/static/web")
    else:
        static_file_path = os.path.join(ROOT_PATH, "src", "derisk_app/static/old_web")

    os.makedirs(STATIC_MESSAGE_IMG_PATH, exist_ok=True)
    app.mount(
        "/images",
        WebSocketAwareStaticFiles(directory=STATIC_MESSAGE_IMG_PATH, html=True),
        name="static2",
    )
    app.mount(
        "/",
        WebSocketAwareStaticFiles(directory=static_file_path, html=True),
        name="static",
    )

    app.mount(
        "/swagger_static",
        WebSocketAwareStaticFiles(directory=static_file_path),
        name="swagger_static",
    )


def _sync_oauth2_config_from_db():
    """Sync OAuth2 config from database to runtime config on startup.

    This ensures that after deployment/restart, the OAuth2 configuration
    stored in database (which survives redeployment) is loaded into
    the in-memory config used by the application.
    """
    try:
        from derisk_app.config_storage.oauth2_db_storage import get_oauth2_db_storage
        from derisk_core.config import ConfigManager, OAuth2Config

        db_storage = get_oauth2_db_storage()
        # Load with actual secrets for runtime use
        db_oauth2 = db_storage.load_with_secrets()

        if db_oauth2 is not None:
            # Update the runtime config with database values
            cfg = ConfigManager.get()
            oauth2_config = OAuth2Config(
                enabled=db_oauth2.get("enabled", False),
                providers=db_oauth2.get("providers", []),
                admin_users=db_oauth2.get("admin_users", []),
            )
            cfg.oauth2 = oauth2_config
            logger.info(
                "OAuth2 config loaded from database (secrets loaded for runtime)"
            )
        else:
            logger.info("No OAuth2 config in database, using file config")
    except Exception as e:
        logger.warning(f"Failed to sync OAuth2 from database: {e}")


def _sync_app_config_to_system_app():
    """Sync JSON config (agent_llm, default_model, etc.) to system_app.config on startup.

    This ensures that after restart, the LLM configuration saved in derisk.json
    is properly loaded into system_app.config and ModelConfigCache, making models
    available immediately without needing manual refresh.
    """
    try:
        from derisk_core.config import ConfigManager
        from derisk.agent.util.llm.model_config_cache import (
            ModelConfigCache,
            parse_provider_configs,
        )

        cfg = ConfigManager.get()

        agent_llm_conf = getattr(cfg, "agent_llm", None)
        if not agent_llm_conf:
            logger.info("No agent_llm config in derisk.json")
            return

        from derisk.component import SystemApp

        system_app = SystemApp.get_instance()
        if not system_app:
            logger.warning("SystemApp not available, cannot sync app config")
            return

        from derisk_app.openapi.api_v1.config_api import (
            _convert_agent_llm_to_system_format,
        )

        agent_llm_dict = _convert_agent_llm_to_system_format(agent_llm_conf)

        system_app.config.set("agent.llm", agent_llm_dict, overwrite=True)

        model_configs = parse_provider_configs(agent_llm_dict)
        if model_configs:
            ModelConfigCache.register_configs(model_configs)

        model_count = 0
        for p in agent_llm_dict.get("provider", []):
            if isinstance(p, dict):
                model_count += len(p.get("model", []))

        logger.info(
            f"App config synced: {len(agent_llm_dict.get('provider', []))} providers, "
            f"{model_count} models registered to ModelConfigCache"
        )

        default_model = getattr(cfg, "default_model", None)
        if default_model:
            default_model_dict = default_model.model_dump(mode="json")
            system_app.config.set("agent.default_model", default_model_dict, overwrite=True)
            if default_model.model_id:
                system_app.config.set("agent.default_llm", default_model.model_id, overwrite=True)
            logger.info(f"Default model synced: {default_model.model_id}")

    except Exception as e:
        logger.warning(f"Failed to sync app config to system_app: {e}")


def initialize_app(param: ApplicationConfig, app: FastAPI, system_app: SystemApp):
    """Initialize app
    If you use gunicorn as a process manager, initialize_app can be invoke in
    `on_starting` hook.
    Args:
        param:WebWerverParameters
        args:List[str]
    """

    # import after param is initialized, accelerate --help speed
    from derisk.model.cluster import initialize_worker_manager_in_client

    web_config = param.service.web
    print(param)

    server_init(param, system_app)
    mount_routers(app, param)
    model_start_listener = _create_model_start_listener(system_app)

    # Migration db storage, so you db models must be imported before this
    # Import cron module to register CronJobEntity before create_all
    from derisk_serve.cron.models.models import CronJobEntity  # noqa: F401

    _migration_db_storage(
        param.service.web.database, web_config.disable_alembic_upgrade
    )

    _sync_oauth2_config_from_db()

    _sync_app_config_to_system_app()

    from derisk_app.component_configs import initialize_components

    initialize_components(
        param,
        system_app,
    )
    system_app.on_init()

    # After init, when the database is ready
    system_app.after_init()

    binding_port = web_config.port
    binding_host = web_config.host
    if not web_config.light:
        from derisk.model.cluster.storage import ModelStorage
        from derisk_serve.model.serve import Serve as ModelServe

        logger.info(
            "Model Unified Deployment Mode, run all services in the same process"
        )
        model_serve = ModelServe.get_instance(system_app)
        # Persistent model storage
        model_storage = ModelStorage(model_serve.model_storage)
        initialize_worker_manager_in_client(
            worker_params=param.service.model.worker,
            models_config=param.models,
            app=app,
            binding_port=binding_port,
            binding_host=binding_host,
            start_listener=model_start_listener,
            system_app=system_app,
            model_storage=model_storage,
        )

    else:
        # MODEL_SERVER is controller address now
        controller_addr = web_config.controller_addr
        param.models.llms = []
        param.models.rerankers = []
        param.models.embeddings = []
        initialize_worker_manager_in_client(
            worker_params=param.service.model.worker,
            models_config=param.models,
            app=app,
            run_locally=False,
            controller_addr=controller_addr,
            binding_port=binding_port,
            binding_host=binding_host,
            start_listener=model_start_listener,
            system_app=system_app,
        )

    mount_static_files(app, param)

    # Initialize Core_v2 Agent Runtime
    from derisk_serve.agent.core_v2_adapter import get_core_v2

    core_v2 = get_core_v2()
    system_app.register_instance(core_v2)
    logger.info("[Core_v2] Runtime component registered")

    # Before start, after on_init
    system_app.before_start()
    return param


class AppCreator:
    config_file: str = None

    @classmethod
    def create(cls):
        pid = os.getpid()
        logger.info(f"{cls.__name__} [pid:{pid}]开始启动")
        try:
            app = create_fastapi_app(
                title=_("DERISK Open API"),
                description=_("DERISK Open API"),
                version=version,
                openapi_tags=[],
            )
            # Use custom router to support priority
            replace_router(app)

            # https://github.com/encode/starlette/issues/617
            cors_app = CORSMiddleware(
                app=app,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                allow_headers=["*"],
            )

            add_exception_handler(app)

            @app.get("/doc", include_in_schema=False)
            async def custom_swagger_ui_html():
                return get_swagger_ui_html(
                    openapi_url=app.openapi_url,
                    title="Custom Swagger UI",
                    swagger_js_url="/swagger_static/swagger-ui-bundle.js",
                    swagger_css_url="/swagger_static/swagger-ui.css",
                )

            config: ApplicationConfig = load_config(cls.config_file)
            system_app = SystemApp(app)
            system_app.config.configs["app_config"] = config
            if hasattr(config, "agent"):
                system_app.config.set("agent", config.agent)

            initialize_app(param=config, app=app, system_app=system_app)
            initialize_tracer(
                system_app=system_app, tracer_parameters=config.service.web.trace
            )
            logger.info(f"{cls.__name__} [pid:{pid}]启动成功")
        except BaseException as e:
            logger.exception(f"{cls.__name__} [pid:{pid}]启动失败: {repr(e)}")
            raise
        return cors_app

    def __init__(self, config_file=None):
        self.config = load_config(config_file or self.config_file)

    def app(self):
        return f"{self.__class__.__module__}:{self.__class__.__name__}.create"

    def workers(self):
        return self.config.system.workers


class DevAppCreator(AppCreator):
    config_file: str = CONFIG_ROOT_PATH + "/derisk-dev.toml"


class ProdAppCreator(AppCreator):
    config_file: str = CONFIG_ROOT_PATH + "/derisk-prod.toml"


class PreAppCreator(AppCreator):
    config_file: str = CONFIG_ROOT_PATH + "/derisk-prepub.toml"


class GrayAppCreator(AppCreator):
    config_file: str = CONFIG_ROOT_PATH + "/derisk-gray.toml"


class TestAppCreator(AppCreator):
    config_file: str = CONFIG_ROOT_PATH + "/derisk-test.toml"


class CustomAppCreator(AppCreator):
    def __init__(self, config_file=None):
        super().__init__(config_file)
        if config_file:
            # Dynamically set the class attribute so that the create class method can get the correct configuration file
            CustomAppCreator.config_file = config_file

    def app(self):
        return self.create

    def workers(self):
        return None  # Custom config does not support multi-process mode
