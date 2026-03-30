import logging
from functools import cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk.model.cluster import (
    WorkerManager,
    WorkerManagerFactory,
    WorkerStartupRequest,
)
from derisk.model.cluster.controller.controller import BaseModelController
from derisk.model.cluster.storage import ModelStorage
from derisk.model.parameter import WorkerType
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import ModelResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Add your API endpoints here

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance"""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


def get_worker_manager() -> WorkerManager:
    """Get the worker manager instance"""
    return WorkerManagerFactory.get_instance(global_system_app).create()


def get_model_controller() -> BaseModelController:
    """Get the model controller instance"""
    return BaseModelController.get_instance(global_system_app)


def get_model_storage() -> ModelStorage:
    """Get the model storage instance"""
    from ..serve import Serve as ModelServe

    model_serve = ModelServe.get_instance(global_system_app)
    # Persistent model storage
    model_storage = ModelStorage(model_serve.model_storage)
    return model_storage


get_bearer_token = HTTPBearer(auto_error=False)


@cache
def _parse_api_keys(api_keys: str) -> List[str]:
    """Parse the string api keys to a list

    Args:
        api_keys (str): The string api keys

    Returns:
        List[str]: The list of api keys
    """
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: Service = Depends(get_service),
) -> Optional[str]:
    """Check the api key

    If the api key is not set, allow all.

    Your can pass the token in you request header like this:

    .. code-block:: python

        import requests

        client_api_key = "your_api_key"
        headers = {"Authorization": "Bearer " + client_api_key}
        res = requests.get("http://test/hello", headers=headers)
        assert res.status_code == 200

    """
    if service.config.api_keys:
        api_keys = _parse_api_keys(service.config.api_keys)
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "message": "",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                },
            )
        return token
    else:
        # api_keys not set; allow all
        return None


@router.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


@router.get("/test_auth", dependencies=[Depends(check_api_key)])
async def test_auth():
    """Test auth endpoint"""
    return {"status": "ok"}


@router.get("/model-types")
async def model_params(worker_manager: WorkerManager = Depends(get_worker_manager)):
    try:
        params = []
        config_models_found = False

        # 1. Get models from system_app.config (JSON configuration) - PRIORITY
        system_app = SystemApp.get_instance() or global_system_app
        if system_app and system_app.config:
            # PRIORITY 1: Try app_config from configs dict (JSON config source)
            # This is the most reliable source as it's always updated via /api/v1/config/import
            app_config = system_app.config.configs.get("app_config")
            agent_llm_conf = None

            if app_config:
                agent_llm_attr = getattr(app_config, "agent_llm", None)
                if agent_llm_attr:
                    # Convert frontend format to backend format
                    agent_llm_dict = (
                        agent_llm_attr.model_dump(mode="json")
                        if hasattr(agent_llm_attr, "model_dump")
                        else dict(agent_llm_attr)
                    )
                    # Convert providers -> provider, models -> model
                    if "providers" in agent_llm_dict:
                        providers = agent_llm_dict.pop("providers")
                        if isinstance(providers, list):
                            converted = []
                            for p in providers:
                                if isinstance(p, dict):
                                    cp = dict(p)
                                    if "models" in cp:
                                        cp["model"] = cp.pop("models")
                                    converted.append(cp)
                            agent_llm_dict["provider"] = converted
                    agent_llm_conf = agent_llm_dict

            # PRIORITY 2: Try "agent.llm" direct key (fallback for TOML config)
            if not agent_llm_conf:
                agent_llm_conf = system_app.config.get("agent.llm")

            # PRIORITY 3: If not found, try "agent" -> "llm" (nested dict access)
            if not agent_llm_conf:
                agent_conf = system_app.config.get("agent")
                if isinstance(agent_conf, dict):
                    agent_llm_conf = agent_conf.get("llm")

            # PRIORITY 4: Check for flattened keys (fallback)
            if not agent_llm_conf:
                flattened = system_app.config.get_all_by_prefix("agent.llm.")
                if flattened:
                    agent_llm_conf = {}
                    prefix_len = len("agent.llm.")
                    for k, v in flattened.items():
                        agent_llm_conf[k[prefix_len:]] = v

            # Parse models from Multi-Provider List Structure [[agent.llm.provider]]
            if agent_llm_conf and isinstance(agent_llm_conf.get("provider"), list):
                providers = agent_llm_conf.get("provider")
                for p_conf in providers:
                    if isinstance(p_conf, dict) and "model" in p_conf:
                        p_models = p_conf.get("model")
                        p_name = p_conf.get("provider", "unknown")
                        if isinstance(p_models, list):
                            for m in p_models:
                                if isinstance(m, dict) and "name" in m:
                                    m_name = m.get("name")
                                    # Add model to params if not already present
                                    if not any(
                                        p.get("model") == m_name
                                        and p.get("provider") == p_name
                                        for p in params
                                    ):
                                        params.append(
                                            {
                                                "model": m_name,
                                                "provider": p_name,
                                                "worker_type": "llm",
                                                "host": f"proxy@{p_name}",
                                                "port": 0,
                                                "enabled": True,
                                            }
                                        )
                                    config_models_found = True

        # 2. Only get models from worker_manager if no config models found (fallback)
        if not config_models_found:
            workers = await worker_manager.supported_models()
            for worker in workers:
                for model in worker.models:
                    model_dict = model.__dict__
                    model_dict["host"] = worker.host
                    model_dict["port"] = worker.port
                    params.append(model_dict)

        return Result.succ(params)
    except Exception as e:
        return Result.failed(err_code="E000X", msg=f"model types failed {e}")


@router.get("/models")
async def model_list(controller: BaseModelController = Depends(get_model_controller)):
    try:
        responses = []
        managers = await controller.get_all_instances(
            model_name="WorkerManager@service", healthy_only=True
        )
        manager_map = dict(map(lambda manager: (manager.host, manager), managers))
        models = await controller.get_all_instances()
        for model in models:
            worker_name, worker_type = model.model_name.split("@")
            if worker_type in WorkerType.values():
                manager_host = model.host if manager_map.get(model.host) else ""
                manager_port = (
                    manager_map[model.host].port if manager_map.get(model.host) else -1
                )
                response = ModelResponse(
                    model_name=worker_name,
                    worker_type=worker_type,
                    host=model.host,
                    port=model.port,
                    manager_host=manager_host,
                    manager_port=manager_port,
                    healthy=model.healthy,
                    check_healthy=model.check_healthy,
                    last_heartbeat=model.str_last_heartbeat,
                    prompt_template=model.prompt_template,
                )
                responses.append(response)

        # Get system_app instance - prefer singleton instance for latest config
        system_app = SystemApp.get_instance() or global_system_app

        # Add the lightweight model from config if it exists
        if system_app and system_app.config:
            # PRIORITY 1: Try app_config from configs dict (JSON config source)
            # This is the most reliable source as it's always updated via /api/v1/config/import
            app_config = system_app.config.configs.get("app_config")
            agent_llm_conf = None

            if app_config:
                agent_llm_attr = getattr(app_config, "agent_llm", None)
                if agent_llm_attr:
                    # Convert frontend format to backend format
                    agent_llm_dict = (
                        agent_llm_attr.model_dump(mode="json")
                        if hasattr(agent_llm_attr, "model_dump")
                        else dict(agent_llm_attr)
                    )
                    # Convert providers -> provider, models -> model
                    if "providers" in agent_llm_dict:
                        providers = agent_llm_dict.pop("providers")
                        if isinstance(providers, list):
                            converted = []
                            for p in providers:
                                if isinstance(p, dict):
                                    cp = dict(p)
                                    if "models" in cp:
                                        cp["model"] = cp.pop("models")
                                    converted.append(cp)
                            agent_llm_dict["provider"] = converted
                    agent_llm_conf = agent_llm_dict

            # PRIORITY 2: Try "agent.llm" direct key (fallback for TOML config)
            if not agent_llm_conf:
                agent_llm_conf = system_app.config.get("agent.llm")

            # PRIORITY 3: If not found, try "agent" -> "llm" (nested dict access)
            if not agent_llm_conf:
                agent_conf = system_app.config.get("agent")
                if isinstance(agent_conf, dict):
                    agent_llm_conf = agent_conf.get("llm")

            # PRIORITY 4: Check for flattened keys (fallback)
            if not agent_llm_conf:
                flattened = system_app.config.get_all_by_prefix("agent.llm.")
                if flattened:
                    agent_llm_conf = {}
                    prefix_len = len("agent.llm.")
                    for k, v in flattened.items():
                        agent_llm_conf[k[prefix_len:]] = v

            # 5. Parse models from new Multi-Provider List Structure [[agent.llm.provider]]
            found_models = []

            if agent_llm_conf and isinstance(agent_llm_conf.get("provider"), list):
                providers = agent_llm_conf.get("provider")
                for p_conf in providers:
                    if isinstance(p_conf, dict) and "model" in p_conf:
                        p_models = p_conf.get("model")
                        p_name = p_conf.get("provider", "unknown")
                        if isinstance(p_models, list):
                            for m in p_models:
                                if isinstance(m, dict) and "name" in m:
                                    m_name = m.get("name")
                                    found_models.append((m_name, p_name))

            # 6. Parse models from legacy "models" list Structure (agent.llm.models)
            if (
                not found_models
                and agent_llm_conf
                and isinstance(agent_llm_conf.get("models"), list)
            ):
                models_list = agent_llm_conf.get("models")
                for m in models_list:
                    if isinstance(m, dict) and "model" in m:
                        found_models.append(
                            (m.get("model"), agent_llm_conf.get("provider", "system"))
                        )

            # 7. Parse single model from basic config
            elif not found_models and agent_llm_conf and agent_llm_conf.get("model"):
                found_models.append(
                    (
                        agent_llm_conf.get("model"),
                        agent_llm_conf.get("provider", "system"),
                    )
                )

            # Add all found models to response
            for m_name, p_name in found_models:
                responses.append(
                    ModelResponse(
                        model_name=str(m_name),
                        worker_type="llm",
                        host=f"proxy@{p_name}",  # Indicate it's a proxy model
                        port=0,
                        manager_host="system-config",
                        manager_port=0,
                        healthy=True,
                        check_healthy=True,
                        last_heartbeat="permanent",
                        prompt_template=None,
                    )
                )

        return Result.succ(responses)

    except Exception as e:
        logger.exception(f"model list error: {e}")
        return Result.failed(err_code="E000X", msg=f"model list error {e}")


@router.post("/models/stop")
async def model_stop(
    request: WorkerStartupRequest,
    worker_manager: WorkerManager = Depends(get_worker_manager),
):
    try:
        request.params = {}
        await worker_manager.model_shutdown(request)
        return Result.succ(True)
    except Exception as e:
        return Result.failed(err_code="E000X", msg=f"model stop failed {e}")


@router.post("/models")
async def create_model(
    request: WorkerStartupRequest,
    worker_manager: WorkerManager = Depends(get_worker_manager),
):
    """Create a model.

    Must provide the full information of the model, including the host, port,
    model name, worker type, and params.
    """
    try:
        await worker_manager.model_startup(request)
        return Result.succ(True)
    except Exception as e:
        logger.error(f"model start failed {e}")
        return Result.failed(err_code="E000X", msg=f"model start failed {e}")


@router.post("/models/start")
async def start_model(
    request: WorkerStartupRequest,
    worker_manager: WorkerManager = Depends(get_worker_manager),
    model_storage: ModelStorage = Depends(get_model_storage),
):
    """Start an existing model."""

    try:
        models = model_storage.query_models(
            request.model,
            worker_type=request.worker_type.value,
            user_name=request.user_name,
            sys_code=request.sys_code,
            host=request.host,
            port=request.port,
        )
        if not models:
            return Result.failed(err_code="E000X", msg="model not found")
        if len(models) > 1:
            return Result.failed(err_code="E000X", msg="multiple models found")
        await worker_manager.model_startup(models[0])
        return Result.succ(True)
    except Exception as e:
        logger.error(f"model start failed {e}")
        return Result.failed(err_code="E000X", msg=f"model start failed {e}")


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
