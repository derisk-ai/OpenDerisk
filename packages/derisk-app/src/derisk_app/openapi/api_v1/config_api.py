"""配置管理 API"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
from pathlib import Path

router = APIRouter(prefix="/config", tags=["Config"])

# 配置模型
class ConfigUpdateRequest(BaseModel):
    updates: Dict[str, Any]

class AgentConfigRequest(BaseModel):
    name: str
    description: Optional[str] = None
    max_steps: Optional[int] = 200
    permission: Optional[Dict[str, Any]] = None

class SandboxConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    image: Optional[str] = None
    memory_limit: Optional[str] = None
    timeout: Optional[int] = None

# 全局配置管理器
_config_manager = None

def get_config_manager():
    global _config_manager
    if _config_manager is None:
        from derisk_core.config import ConfigManager
        _config_manager = ConfigManager
    return _config_manager

@router.get("/current")
async def get_current_config():
    """获取当前完整配置"""
    try:
        manager = get_config_manager()
        config = manager.get()
        return JSONResponse(content={
            "success": True,
            "data": config.model_dump(mode="json")
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/schema")
async def get_config_schema():
    """获取配置 Schema（用于前端表单生成）"""
    from derisk_core.config import AppConfig, AgentConfig, ModelConfig, SandboxConfig
    
    schema = {
        "app": AppConfig.model_json_schema(),
        "agent": AgentConfig.model_json_schema(),
        "model": ModelConfig.model_json_schema(),
        "sandbox": SandboxConfig.model_json_schema()
    }
    
    return JSONResponse(content={
        "success": True,
        "data": schema
    })

@router.get("/model")
async def get_model_config():
    """获取模型配置"""
    manager = get_config_manager()
    config = manager.get()
    return JSONResponse(content={
        "success": True,
        "data": config.default_model.model_dump()
    })

@router.post("/model")
async def update_model_config(request: Dict[str, Any]):
    """更新模型配置"""
    try:
        manager = get_config_manager()
        config = manager.get()
        
        # 更新模型配置
        for key, value in request.items():
            if hasattr(config.default_model, key):
                setattr(config.default_model, key, value)
        
        return JSONResponse(content={
            "success": True,
            "message": "模型配置已更新",
            "data": config.default_model.model_dump()
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/agents")
async def list_agents():
    """列出所有 Agent 配置"""
    manager = get_config_manager()
    config = manager.get()
    
    agents = []
    for name, agent in config.agents.items():
        agents.append({
            "name": agent.name,
            "description": agent.description,
            "max_steps": agent.max_steps,
            "color": agent.color,
            "permission": agent.permission.model_dump() if agent.permission else None
        })
    
    return JSONResponse(content={
        "success": True,
        "data": agents
    })

@router.get("/agents/{agent_name}")
async def get_agent_config(agent_name: str):
    """获取指定 Agent 配置"""
    manager = get_config_manager()
    config = manager.get()
    
    if agent_name not in config.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    agent = config.agents[agent_name]
    return JSONResponse(content={
        "success": True,
        "data": agent.model_dump()
    })

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
            permission=PermissionConfig(**request.permission) if request.permission else PermissionConfig()
        )
        
        config.agents[request.name] = agent
        
        return JSONResponse(content={
            "success": True,
            "message": f"Agent '{request.name}' created",
            "data": agent.model_dump()
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/agents/{agent_name}")
async def update_agent(agent_name: str, request: Dict[str, Any]):
    """更新 Agent 配置"""
    try:
        manager = get_config_manager()
        config = manager.get()
        
        if agent_name not in config.agents:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        
        agent = config.agents[agent_name]
        
        for key, value in request.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Agent '{agent_name}' updated",
            "data": agent.model_dump()
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """删除 Agent"""
    try:
        manager = get_config_manager()
        config = manager.get()
        
        if agent_name not in config.agents:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        
        if agent_name == "primary":
            raise HTTPException(status_code=400, detail="Cannot delete primary agent")
        
        del config.agents[agent_name]
        
        return JSONResponse(content={
            "success": True,
            "message": f"Agent '{agent_name}' deleted"
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/sandbox")
async def get_sandbox_config():
    """获取沙箱配置"""
    manager = get_config_manager()
    config = manager.get()
    return JSONResponse(content={
        "success": True,
        "data": config.sandbox.model_dump()
    })

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
        
        return JSONResponse(content={
            "success": True,
            "message": "沙箱配置已更新",
            "data": config.sandbox.model_dump()
        })
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
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "valid": len([w for w in warnings if w[0] == "error"]) == 0,
                "warnings": [{"level": w[0], "message": w[1]} for w in warnings]
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reload")
async def reload_config():
    """重新加载配置"""
    try:
        manager = get_config_manager()
        config = manager.reload()
        
        return JSONResponse(content={
            "success": True,
            "message": "配置已重新加载",
            "data": config.model_dump(mode="json")
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_config():
    """导出配置为 JSON"""
    manager = get_config_manager()
    config = manager.get()
    
    return JSONResponse(
        content={
            "success": True,
            "data": config.model_dump(mode="json", exclude_none=True)
        }
    )

@router.get("/oauth2")
async def get_oauth2_config():
    """获取 OAuth2 配置"""
    manager = get_config_manager()
    config = manager.get()
    oauth2 = getattr(config, "oauth2", None)
    if oauth2 is None:
        return JSONResponse(content={
            "success": True,
            "data": {"enabled": False, "providers": []}
        })
    return JSONResponse(content={
        "success": True,
        "data": oauth2.model_dump(mode="json")
    })


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

        # 保存到配置文件
        try:
            manager.save()
        except Exception as save_err:
            # 保存失败但仍然返回成功（内存中已更新）
            import logging
            logging.getLogger(__name__).warning(f"Failed to save config to file: {save_err}")

        return JSONResponse(content={
            "success": True,
            "message": "OAuth2 配置已更新",
            "data": config.oauth2.model_dump(mode="json")
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import")
async def import_config(config_data: Dict[str, Any]):
    """导入配置"""
    try:
        from derisk_core.config import AppConfig
        
        config = AppConfig(**config_data)
        
        manager = get_config_manager()
        manager._config = config
        
        return JSONResponse(content={
            "success": True,
            "message": "配置已导入",
            "data": config.model_dump(mode="json")
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))