"""
Streaming Configuration API Endpoints

REST API for managing tool streaming configurations.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from derisk.model.streaming.db_models import (
    StreamingToolConfigInput,
    StreamingToolConfigResponse,
    AvailableToolResponse,
    StreamingConfigListResponse,
    ParamConfigInput,
)
from derisk.model.streaming.config_manager import (
    ToolStreamingConfig,
    ParamStreamingConfig,
    ChunkStrategy,
)

from .service import get_streaming_config_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/streaming-config", tags=["streaming-config"])


@router.get("/apps/{app_code}", response_model=StreamingConfigListResponse)
async def get_app_configs(app_code: str):
    """
    Get all streaming configurations for an application.

    Args:
        app_code: Application code

    Returns:
        List of streaming tool configurations
    """
    try:
        service = get_streaming_config_service()
        configs = await service.get_app_configs(app_code)

        config_responses = [
            StreamingToolConfigResponse(
                id=0,
                app_code=cfg.app_code,
                tool_name=cfg.tool_name,
                param_configs=[pc.to_dict() for pc in cfg.param_configs.values()],
                global_threshold=cfg.global_threshold,
                global_strategy=cfg.global_strategy.value,
                global_renderer=cfg.global_renderer,
                enabled=cfg.enabled,
                priority=cfg.priority,
                created_at=None,
                updated_at=None,
            )
            for cfg in configs.values()
        ]

        return StreamingConfigListResponse(
            app_code=app_code,
            configs=config_responses,
            total=len(config_responses),
        )
    except Exception as e:
        logger.error(f"Failed to get app configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/apps/{app_code}/tools/{tool_name}")
async def get_tool_config(app_code: str, tool_name: str):
    """
    Get streaming configuration for a specific tool.

    Args:
        app_code: Application code
        tool_name: Tool name

    Returns:
        Tool streaming configuration
    """
    try:
        service = get_streaming_config_service()
        config = await service.get_tool_config(app_code, tool_name)

        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")

        return {
            "success": True,
            "config": {
                "tool_name": config.tool_name,
                "app_code": config.app_code,
                "param_configs": [pc.to_dict() for pc in config.param_configs.values()],
                "global_threshold": config.global_threshold,
                "global_strategy": config.global_strategy.value,
                "global_renderer": config.global_renderer,
                "enabled": config.enabled,
                "priority": config.priority,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tool config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/apps/{app_code}/tools/{tool_name}")
async def save_tool_config(
    app_code: str,
    tool_name: str,
    config_input: StreamingToolConfigInput,
):
    """
    Save streaming configuration for a tool.

    Args:
        app_code: Application code
        tool_name: Tool name
        config_input: Configuration input

    Returns:
        Saved configuration
    """
    try:
        logger.info(
            f"[StreamingConfig] Saving config for app={app_code}, tool={tool_name}"
        )
        service = get_streaming_config_service()

        param_configs = {}
        for pc in config_input.param_configs:
            param_configs[pc.param_name] = ParamStreamingConfig(
                param_name=pc.param_name,
                threshold=pc.threshold,
                strategy=ChunkStrategy(pc.strategy),
                chunk_size=pc.chunk_size,
                chunk_by_line=pc.chunk_by_line,
                renderer=pc.renderer,
                enabled=pc.enabled,
                description=pc.description,
            )

        config = ToolStreamingConfig(
            tool_name=tool_name,
            app_code=app_code,
            param_configs=param_configs,
            global_threshold=config_input.global_threshold or 256,
            global_strategy=ChunkStrategy(config_input.global_strategy or "adaptive"),
            global_renderer=config_input.global_renderer or "default",
            enabled=config_input.enabled,
            priority=config_input.priority or 0,
        )

        success = await service.save_tool_config(app_code, tool_name, config)

        if not success:
            logger.error(
                f"[StreamingConfig] Failed to save config: storage not available"
            )
            return {
                "success": False,
                "error": "Storage not available. Please check database configuration.",
                "config": None,
            }

        logger.info(f"[StreamingConfig] Config saved successfully for tool={tool_name}")
        return {
            "success": True,
            "config": {
                "tool_name": config.tool_name,
                "app_code": config.app_code,
                "param_configs": [pc.to_dict() for pc in config.param_configs.values()],
                "global_threshold": config.global_threshold,
                "global_strategy": config.global_strategy.value,
                "global_renderer": config.global_renderer,
                "enabled": config.enabled,
                "priority": config.priority,
            },
        }
    except Exception as e:
        logger.error(f"Failed to save tool config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/apps/{app_code}/tools/{tool_name}")
async def delete_tool_config(app_code: str, tool_name: str):
    """
    Delete streaming configuration for a tool.

    Args:
        app_code: Application code
        tool_name: Tool name

    Returns:
        Deletion result
    """
    try:
        service = get_streaming_config_service()
        success = await service.delete_tool_config(app_code, tool_name)

        if not success:
            raise HTTPException(status_code=404, detail="Configuration not found")

        return {"success": True, "message": f"Configuration for {tool_name} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete tool config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/available")
async def get_available_tools(
    app_code: Optional[str] = Query(
        None, description="Application code to check config status"
    ),
):
    """
    Get list of available tools with their parameters.

    Args:
        app_code: Optional application code to check if tools have streaming configs

    Returns:
        List of available tools
    """
    try:
        service = get_streaming_config_service()
        tools = await service.get_available_tools(app_code)

        return {"tools": tools, "total": len(tools)}
    except Exception as e:
        logger.error(f"Failed to get available tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))
