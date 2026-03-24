"""配置管理 API"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from derisk_serve.utils.auth import UserRequest, get_user_from_headers

router = APIRouter(prefix="/config", tags=["Config"])

logger = logging.getLogger(__name__)


class ConfigUpdateRequest(BaseModel):
    updates: Dict[str, Any]


class AgentConfigRequest(BaseModel):
    name: str
    description: Optional[str] = None
    max_steps: Optional[int] = 200
    permission: Optional[Dict[str, Any]] = None
    tools: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    color: Optional[str] = None


class SandboxConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    image: Optional[str] = None
    memory_limit: Optional[str] = None
    timeout: Optional[int] = None
    type: Optional[str] = None
    work_dir: Optional[str] = None


class FileBackendRequest(BaseModel):
    type: str = "local"
    storage_path: Optional[str] = None
    endpoint: Optional[str] = None
    region: Optional[str] = None
    access_key_ref: Optional[str] = None
    access_secret_ref: Optional[str] = None
    bucket: Optional[str] = None


class FileServiceRequest(BaseModel):
    enabled: Optional[bool] = None
    default_backend: Optional[str] = None
    backends: Optional[List[FileBackendRequest]] = None


class SecretRequest(BaseModel):
    name: str
    value: str
    description: Optional[str] = None


class LLMKeyRequest(BaseModel):
    provider: str
    api_key: str


class LLMKeyStatus(BaseModel):
    provider: str
    description: str
    is_configured: bool


class FeaturePluginUpdateRequest(BaseModel):
    plugin_id: str
    enabled: Optional[bool] = None
    settings: Optional[Dict[str, Any]] = None


_config_manager = None


def _user_has_app_admin_role(user: UserRequest) -> bool:
    """True if this principal maps to a DB user with role=admin (User Management)."""
    for raw in (user.user_no, user.user_id):
        if raw is None or raw == "":
            continue
        try:
            uid = int(str(raw).strip())
        except ValueError:
            continue
        try:
            from derisk_app.auth.user_service import UserService

            row = UserService().get_user(uid)
            if row and (row.get("role") or "").strip() == "admin":
                return True
        except Exception:
            logger.debug("feature_plugins admin check: get_user failed for uid=%s", uid, exc_info=True)
    return False


def _ensure_can_write_feature_plugins(user: UserRequest) -> None:
    """When OAuth2 is on and admin_users is non-empty, restrict writes to admins.

    Allows either:
    - login in oauth2.admin_users (initial OAuth bootstrap list), or
    - user id with role=admin in the ``user`` table (User Management 管理员).
    """
    manager = get_config_manager()
    config = manager.get()
    oauth2 = getattr(config, "oauth2", None)
    if oauth2 is None or not oauth2.enabled or not oauth2.admin_users:
        return
    if _user_has_app_admin_role(user):
        return
    login = (
        user.user_name
        or user.email
        or user.real_name
        or user.user_id
        or ""
    )
    if login not in oauth2.admin_users:
        raise HTTPException(
            status_code=403,
            detail="Only users listed in oauth2.admin_users may update feature plugins",
        )


def get_config_manager():
    global _config_manager
    if _config_manager is None:
        from derisk_core.config import ConfigManager

        _config_manager = ConfigManager
    return _config_manager


def save_config_with_error_handling(manager, config_name: str = "配置") -> bool:
    try:
        manager.save()
        logger.info(f"{config_name}已保存到文件: {manager.get_config_path()}")
        return True
    except Exception as e:
        logger.warning(f"保存{config_name}到文件失败: {e}")
        return False


@router.get("/current")
async def get_current_config():
    try:
        manager = get_config_manager()
        config = manager.get()
        return JSONResponse(
            content={
                "success": True,
                "data": config.model_dump(mode="json"),
                "config_path": manager.get_config_path(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path")
async def get_config_path():
    """获取当前配置文件路径"""
    manager = get_config_manager()
    path = manager.get_config_path()
    return JSONResponse(
        content={
            "success": True,
            "data": {
                "config_path": path,
                "default_path": manager.get_default_config_path(),
            },
        }
    )


@router.get("/schema")
async def get_config_schema():
    """获取配置 Schema（用于前端表单生成）"""
    from derisk_core.config import AppConfig, AgentConfig, ModelConfig, SandboxConfig

    schema = {
        "app": AppConfig.model_json_schema(),
        "agent": AgentConfig.model_json_schema(),
        "model": ModelConfig.model_json_schema(),
        "sandbox": SandboxConfig.model_json_schema(),
    }

    return JSONResponse(content={"success": True, "data": schema})


@router.get("/model")
async def get_model_config():
    """获取模型配置"""
    manager = get_config_manager()
    config = manager.get()
    return JSONResponse(
        content={"success": True, "data": config.default_model.model_dump()}
    )


@router.post("/model")
async def update_model_config(request: Dict[str, Any]):
    """更新模型配置"""
    try:
        manager = get_config_manager()
        config = manager.get()

        for key, value in request.items():
            if hasattr(config.default_model, key):
                setattr(config.default_model, key, value)

        saved = save_config_with_error_handling(manager, "模型配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "模型配置已更新" + ("并保存" if saved else "（保存失败）"),
                "data": config.default_model.model_dump(),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents")
async def list_agents():
    """列出所有 Agent 配置"""
    manager = get_config_manager()
    config = manager.get()

    agents = []
    for name, agent in config.agents.items():
        agents.append(
            {
                "name": agent.name,
                "description": agent.description,
                "max_steps": agent.max_steps,
                "color": agent.color,
                "tools": agent.tools,
                "system_prompt": agent.system_prompt,
                "permission": agent.permission.model_dump()
                if agent.permission
                else None,
            }
        )

    return JSONResponse(content={"success": True, "data": agents})


@router.get("/agents/{agent_name}")
async def get_agent_config(agent_name: str):
    """获取指定 Agent 配置"""
    manager = get_config_manager()
    config = manager.get()

    if agent_name not in config.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    agent = config.agents[agent_name]
    return JSONResponse(content={"success": True, "data": agent.model_dump()})


@router.post("/agents")
async def create_agent(request: AgentConfigRequest):
    """创建新 Agent"""
    try:
        manager = get_config_manager()
        config = manager.get()

        from derisk_core.config import AgentConfig, PermissionConfig

        agent = AgentConfig(
            name=request.name,
            description=request.description or "",
            max_steps=request.max_steps or 200,
            permission=PermissionConfig(**request.permission)
            if request.permission
            else PermissionConfig(),
            tools=request.tools or [],
            system_prompt=request.system_prompt,
            color=request.color or "#4A90E2",
        )

        config.agents[request.name] = agent

        saved = save_config_with_error_handling(manager, "Agent配置")

        return JSONResponse(
            content={
                "success": True,
                "message": f"Agent '{request.name}' created"
                + ("并保存" if saved else "（保存失败）"),
                "data": agent.model_dump(),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/agents/{agent_name}")
async def update_agent(agent_name: str, request: Dict[str, Any]):
    """更新 Agent 配置"""
    try:
        manager = get_config_manager()
        config = manager.get()

        if agent_name not in config.agents:
            raise HTTPException(
                status_code=404, detail=f"Agent '{agent_name}' not found"
            )

        agent = config.agents[agent_name]

        for key, value in request.items():
            if hasattr(agent, key):
                setattr(agent, key, value)

        saved = save_config_with_error_handling(manager, "Agent配置")

        return JSONResponse(
            content={
                "success": True,
                "message": f"Agent '{agent_name}' updated"
                + ("并保存" if saved else "（保存失败）"),
                "data": agent.model_dump(),
                "saved_to_file": saved,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """删除 Agent"""
    try:
        manager = get_config_manager()
        config = manager.get()

        if agent_name not in config.agents:
            raise HTTPException(
                status_code=404, detail=f"Agent '{agent_name}' not found"
            )

        if agent_name == "primary":
            raise HTTPException(status_code=400, detail="Cannot delete primary agent")

        del config.agents[agent_name]

        saved = save_config_with_error_handling(manager, "Agent配置")

        return JSONResponse(
            content={
                "success": True,
                "message": f"Agent '{agent_name}' deleted"
                + ("并保存" if saved else "（保存失败）"),
                "saved_to_file": saved,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sandbox")
async def get_sandbox_config():
    """获取沙箱配置"""
    manager = get_config_manager()
    config = manager.get()
    return JSONResponse(content={"success": True, "data": config.sandbox.model_dump()})


@router.post("/sandbox")
async def update_sandbox_config(request: SandboxConfigRequest):
    """更新沙箱配置"""
    try:
        manager = get_config_manager()
        config = manager.get()

        if request.enabled is not None:
            config.sandbox.enabled = request.enabled
        if request.image:
            config.sandbox.image = request.image
        if request.memory_limit:
            config.sandbox.memory_limit = request.memory_limit
        if request.timeout:
            config.sandbox.timeout = request.timeout

        saved = save_config_with_error_handling(manager, "沙箱配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "沙箱配置已更新" + ("并保存" if saved else "（保存失败）"),
                "data": config.sandbox.model_dump(),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate")
async def validate_config():
    """验证当前配置"""
    try:
        manager = get_config_manager()
        config = manager.get()

        from derisk_core.config import ConfigValidator

        warnings = ConfigValidator.validate(config)

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "valid": len([w for w in warnings if w[0] == "error"]) == 0,
                    "warnings": [{"level": w[0], "message": w[1]} for w in warnings],
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_config():
    """重新加载配置（从文件重新读取）"""
    try:
        manager = get_config_manager()
        config = manager.reload()

        return JSONResponse(
            content={
                "success": True,
                "message": "配置已从文件重新加载",
                "data": config.model_dump(mode="json"),
                "config_path": manager.get_config_path(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_config():
    """手动保存当前配置到文件"""
    try:
        manager = get_config_manager()
        manager.save()

        return JSONResponse(
            content={
                "success": True,
                "message": "配置已保存到文件",
                "config_path": manager.get_config_path(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oauth2")
async def get_oauth2_config():
    """获取 OAuth2 配置"""
    manager = get_config_manager()
    config = manager.get()
    oauth2 = getattr(config, "oauth2", None)
    if oauth2 is None:
        return JSONResponse(
            content={"success": True, "data": {"enabled": False, "providers": []}}
        )
    return JSONResponse(
        content={"success": True, "data": oauth2.model_dump(mode="json")}
    )


@router.post("/oauth2")
async def update_oauth2_config(oauth2_data: Dict[str, Any]):
    """更新 OAuth2 配置并保存到文件"""
    try:
        from derisk_core.config import AppConfig, OAuth2Config

        manager = get_config_manager()
        config = manager.get()
        config_dict = config.model_dump(mode="json")
        config_dict["oauth2"] = oauth2_data
        config = AppConfig(**config_dict)
        manager._config = config

        saved = save_config_with_error_handling(manager, "OAuth2配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "OAuth2 配置已更新"
                + ("并保存" if saved else "（保存失败）"),
                "data": config.oauth2.model_dump(mode="json"),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/feature-plugins/catalog")
async def get_feature_plugins_catalog():
    """Builtin plugin catalog merged with current enabled/settings from derisk.json."""
    from derisk_app.feature_plugins.catalog import merge_catalog_with_state

    manager = get_config_manager()
    config = manager.get()
    raw = getattr(config, "feature_plugins", None) or {}
    normalized: Dict[str, Any] = {}
    for k, v in raw.items():
        if hasattr(v, "model_dump"):
            normalized[k] = v.model_dump(mode="json")
        elif isinstance(v, dict):
            normalized[k] = v
    items = merge_catalog_with_state(normalized)
    return JSONResponse(content={"success": True, "data": {"items": items}})


@router.get("/feature-plugins")
async def get_feature_plugins_state():
    manager = get_config_manager()
    config = manager.get()
    fp = getattr(config, "feature_plugins", None) or {}
    out = {
        k: v.model_dump(mode="json") if hasattr(v, "model_dump") else dict(v)
        for k, v in fp.items()
    }
    return JSONResponse(content={"success": True, "data": out})


@router.post("/feature-plugins")
async def update_feature_plugins(
    body: FeaturePluginUpdateRequest,
    user: UserRequest = Depends(get_user_from_headers),
):
    from derisk_app.feature_plugins.catalog import is_known_plugin
    from derisk_core.config import AppConfig, FeaturePluginEntry

    _ensure_can_write_feature_plugins(user)
    if not is_known_plugin(body.plugin_id):
        raise HTTPException(status_code=400, detail=f"Unknown plugin_id: {body.plugin_id}")

    manager = get_config_manager()
    config = manager.get()
    config_dict = config.model_dump(mode="json")
    fp = dict(config_dict.get("feature_plugins") or {})
    cur = fp.get(body.plugin_id) or {}
    entry = FeaturePluginEntry(**cur) if cur else FeaturePluginEntry()
    new_enabled = body.enabled if body.enabled is not None else entry.enabled
    new_settings = body.settings if body.settings is not None else entry.settings
    entry = FeaturePluginEntry(enabled=new_enabled, settings=new_settings)
    fp[body.plugin_id] = entry.model_dump(mode="json")
    config_dict["feature_plugins"] = fp
    new_cfg = AppConfig(**config_dict)
    manager._config = new_cfg
    saved = save_config_with_error_handling(manager, "Feature plugins")
    return JSONResponse(
        content={
            "success": True,
            "message": "功能插件配置已更新" + ("并保存" if saved else "（保存失败）"),
            "data": entry.model_dump(mode="json"),
            "saved_to_file": saved,
        }
    )


@router.post("/import")
async def import_config(config_data: Dict[str, Any]):
    """导入配置并保存到文件"""
    try:
        from derisk_core.config import AppConfig

        config = AppConfig(**config_data)

        manager = get_config_manager()
        manager._config = config

        saved = save_config_with_error_handling(manager, "配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "配置已导入" + ("并保存" if saved else "（保存失败）"),
                "data": config.model_dump(mode="json"),
                "saved_to_file": saved,
                "config_path": manager.get_config_path(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reset")
async def reset_config():
    """重置为默认配置"""
    try:
        from derisk_core.config import AppConfig

        manager = get_config_manager()
        config = AppConfig()
        manager._config = config

        saved = save_config_with_error_handling(manager, "默认配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "配置已重置为默认值",
                "data": config.model_dump(mode="json"),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_config_status():
    """获取配置状态信息"""
    manager = get_config_manager()
    config_path = manager.get_config_path()

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "config_path": config_path,
                "default_config_path": manager.get_default_config_path(),
                "config_type": "json",
                "hot_reload_capable": True,
                "requires_restart_for": [
                    "OAuth2 provider changes (需要重启生效)",
                    "Sandbox configuration changes (需要重启生效)",
                    "Model provider changes (需要重启生效)",
                    "Builtin feature plugins enable/disable (需要重启生效)",
                ],
                "instant_effect": [
                    "Agent configuration (立即生效)",
                    "Permission rules (立即生效)",
                ],
            },
        }
    )


@router.get("/system/reload-info")
async def get_reload_info():
    manager = get_config_manager()

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "json_config": {
                    "path": manager.get_config_path(),
                    "reloadable": True,
                    "description": "应用配置（Agent、权限、OAuth2等）可通过 /api/config/reload 热重载",
                },
                "toml_config": {
                    "description": "服务基础设施配置（数据库、模型服务、Workers等）修改后需要重启服务",
                    "restart_command": "重启服务以应用TOML配置更改",
                },
                "note": "JSON配置修改后自动保存到文件，调用 /api/config/reload 可从文件重新加载",
            },
        }
    )


@router.get("/file-service")
async def get_file_service_config():
    manager = get_config_manager()
    config = manager.get()
    return JSONResponse(
        content={
            "success": True,
            "data": config.file_service.model_dump(),
        }
    )


@router.post("/file-service")
async def update_file_service_config(request: FileServiceRequest):
    try:
        manager = get_config_manager()
        config = manager.get()

        if request.enabled is not None:
            config.file_service.enabled = request.enabled
        if request.default_backend:
            config.file_service.default_backend = request.default_backend
        if request.backends:
            from derisk_core.config import FileBackendConfig

            config.file_service.backends = [
                FileBackendConfig(**b.model_dump()) for b in request.backends
            ]

        saved = save_config_with_error_handling(manager, "文件服务配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "文件服务配置已更新"
                + ("并保存" if saved else "（保存失败）"),
                "data": config.file_service.model_dump(),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/secrets")
async def list_secrets():
    from derisk_core.config.encryption import list_secrets as get_secrets_status

    secrets_status = get_secrets_status()

    default_secrets = {
        "master_encrypt_key": "主加密密钥，用于加密其他敏感数据",
        "openai_api_key": "OpenAI API Key (系统设置 - LLM)",
        "dashscope_api_key": "阿里云 DashScope API Key (系统设置 - LLM)",
        "alibaba_api_key": "阿里云 API Key (系统设置 - LLM)",
        "anthropic_api_key": "Anthropic API Key (系统设置 - LLM)",
        "claude_api_key": "Claude API Key (系统设置 - LLM)",
        "llm_api_key": "通用 LLM API Key (系统设置 - LLM)",
        "oss_access_key_id": "阿里云 OSS Access Key ID",
        "oss_access_key_secret": "阿里云 OSS Access Key Secret",
        "db_password": "数据库密码",
    }

    secrets_list = []
    for name, description in default_secrets.items():
        secrets_list.append(
            {
                "name": name,
                "description": description,
                "has_value": secrets_status.get(name, False),
            }
        )

    for name, has_value in secrets_status.items():
        if name not in default_secrets:
            secrets_list.append(
                {
                    "name": name,
                    "description": "",
                    "has_value": has_value,
                }
            )

    return JSONResponse(
        content={
            "success": True,
            "data": secrets_list,
        }
    )


@router.get("/secrets/{secret_name}")
async def get_secret_info(secret_name: str):
    from derisk_core.config.encryption import get_secret as get_secret_value

    value = get_secret_value(secret_name)

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "name": secret_name,
                "has_value": bool(value),
            },
        }
    )


@router.post("/secrets")
async def set_secret(request: SecretRequest):
    from derisk_core.config.encryption import set_secret as save_secret_value

    try:
        success = save_secret_value(request.name, request.value)

        if success:
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"密钥 '{request.name}' 已加密存储",
                }
            )
        else:
            raise HTTPException(status_code=500, detail="保存密钥失败")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/secrets/{secret_name}")
async def delete_secret(secret_name: str):
    from derisk_core.config.encryption import delete_secret as delete_secret_value

    try:
        success = delete_secret_value(secret_name)

        return JSONResponse(
            content={
                "success": True,
                "message": f"密钥 '{secret_name}' 已删除",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/export")
async def export_config_safe():
    from derisk_core.config.encryption import mask_secrets_in_json

    manager = get_config_manager()
    config = manager.get()
    config_dict = config.model_dump(mode="json", exclude_none=True)

    masked_config = mask_secrets_in_json(config_dict)
    masked_config.pop("secrets", None)

    return JSONResponse(
        content={
            "success": True,
            "data": masked_config,
            "config_path": manager.get_config_path(),
            "note": "密钥值已替换为引用格式，secrets 部分已移除",
        }
    )


@router.get("/llm-keys")
async def list_llm_keys():
    """获取 LLM Key 配置状态列表

    只返回是否已配置的状态，不返回实际的 key 值
    """
    from derisk_core.config.encryption import list_secrets as get_secrets_status

    secrets_status = get_secrets_status()

    # 定义支持的 LLM Provider 及其默认描述（简化为最常用的两个）
    llm_providers = {
        "openai": "OpenAI API Key (GPT 系列模型)",
        "alibaba": "阿里云 DashScope API Key (通义千问/Qwen/DeepSeek 等)",
    }

    # 定义各个 provider 对应的 secrets key 名称
    provider_secret_keys = {
        "openai": ["openai_api_key"],
        "alibaba": ["dashscope_api_key"],
    }

    llm_keys = []
    for provider, description in llm_providers.items():
        secret_keys = provider_secret_keys.get(provider, [])
        # 检查该 provider 是否有任意一个对应的 secret key 已配置
        is_configured = any(
            secrets_status.get(key, False) for key in secret_keys
        )

        llm_keys.append({
            "provider": provider,
            "description": description,
            "is_configured": is_configured,
        })

    return JSONResponse(
        content={
            "success": True,
            "data": llm_keys,
            "note": "只返回配置状态，不返回实际的 key 值",
        }
    )


@router.post("/llm-keys")
async def set_llm_key(request: LLMKeyRequest):
    """设置 LLM API Key

    将 API Key 加密存储到 secrets 中，配置后立即生效
    """
    from derisk_core.config.encryption import set_secret
    import logging

    logger = logging.getLogger(__name__)

    try:
        # 根据 provider 确定存储的 key 名称（简化为只支持 openai 和 alibaba）
        provider = request.provider.lower()

        secret_key_mapping = {
            "openai": "openai_api_key",
            "alibaba": "dashscope_api_key",
        }

        if provider not in secret_key_mapping:
            raise HTTPException(status_code=400, detail=f"不支持的 provider: {provider}")

        secret_name = secret_key_mapping.get(provider)

        # 清理 API Key（去除前后空格）
        api_key = request.api_key.strip() if request.api_key else ""

        if not api_key:
            raise HTTPException(status_code=400, detail="API Key 不能为空")

        # 记录调试信息（隐藏部分 key）
        key_preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        logger.info(f"Saving API key for provider={provider}, secret_name={secret_name}, key_preview={key_preview}, key_length={len(api_key)}")

        # 加密存储 API Key
        success = set_secret(secret_name, api_key)

        if success:
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"{provider} API Key 已加密存储",
                    "provider": provider,
                    "secret_name": secret_name,
                    "note": "配置已生效，新的请求将使用此 API Key",
                }
            )
        else:
            raise HTTPException(status_code=500, detail="保存 API Key 失败")
    except Exception as e:
        logger.error(f"Failed to save LLM key: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/llm-keys/{provider}")
async def delete_llm_key(provider: str):
    """删除 LLM API Key 配置

    删除后，系统将回退到使用配置文件中的 API Key
    """
    from derisk_core.config.encryption import delete_secret

    try:
        provider = provider.lower()

        secret_key_mapping = {
            "openai": "openai_api_key",
            "alibaba": "dashscope_api_key",
        }

        if provider not in secret_key_mapping:
            raise HTTPException(status_code=400, detail=f"不支持的 provider: {provider}")

        secret_name = secret_key_mapping.get(provider)

        success = delete_secret(secret_name)

        if success:
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"{provider} API Key 已删除",
                    "note": "已删除系统设置中的 API Key，将回退到使用配置文件中的配置",
                }
            )
        else:
            raise HTTPException(status_code=500, detail="删除 API Key 失败")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/system")
async def get_system_config():
    manager = get_config_manager()
    config = manager.get()
    return JSONResponse(
        content={
            "success": True,
            "data": config.system.model_dump(),
        }
    )


@router.post("/system")
async def update_system_config(request: Dict[str, Any]):
    try:
        manager = get_config_manager()
        config = manager.get()

        for key, value in request.items():
            if hasattr(config.system, key):
                setattr(config.system, key, value)

        saved = save_config_with_error_handling(manager, "系统配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "系统配置已更新" + ("并保存" if saved else "（保存失败）"),
                "data": config.system.model_dump(),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/web")
async def get_web_config():
    manager = get_config_manager()
    config = manager.get()
    return JSONResponse(
        content={
            "success": True,
            "data": config.web.model_dump(),
        }
    )


@router.post("/web")
async def update_web_config(request: Dict[str, Any]):
    try:
        manager = get_config_manager()
        config = manager.get()

        for key, value in request.items():
            if hasattr(config.web, key):
                setattr(config.web, key, value)

        saved = save_config_with_error_handling(manager, "Web服务配置")

        return JSONResponse(
            content={
                "success": True,
                "message": "Web服务配置已更新"
                + ("并保存" if saved else "（保存失败）"),
                "data": config.web.model_dump(),
                "saved_to_file": saved,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
