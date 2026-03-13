"""
Streaming Configuration Service

Business logic for managing streaming tool configurations.
"""

import logging
from typing import Any, Dict, List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata.db_storage import SQLAlchemyStorage

from derisk.model.streaming.config_manager import (
    StreamingConfigManager,
    ToolStreamingConfig,
    ParamStreamingConfig,
)
from derisk.model.streaming.db_models import (
    StreamingToolConfig,
    StreamingToolConfigInput,
    StreamingToolConfigResponse,
    AvailableToolResponse,
    StreamingConfigListResponse,
)

logger = logging.getLogger(__name__)

_storage: Optional[SQLAlchemyStorage] = None
_service: Optional["StreamingConfigService"] = None


class StreamingConfigService:
    """Service for managing streaming configurations"""

    def __init__(self, storage: SQLAlchemyStorage):
        self._storage = storage

    async def get_app_configs(self, app_code: str) -> Dict[str, ToolStreamingConfig]:
        """Get all streaming configs for an app"""
        with self._storage.session() as session:
            configs = (
                session.query(StreamingToolConfig)
                .filter(StreamingToolConfig.app_code == app_code)
                .all()
            )

            result = {}
            for config in configs:
                tool_config = ToolStreamingConfig(
                    tool_name=config.tool_name,
                    app_code=config.app_code,
                    param_configs={
                        name: ParamStreamingConfig.from_dict(data)
                        for name, data in (config.param_configs or {}).items()
                    },
                    global_threshold=config.global_threshold or 256,
                    global_strategy=config.global_strategy or "adaptive",
                    global_renderer=config.global_renderer or "default",
                    enabled=config.enabled,
                    priority=config.priority or 0,
                )
                result[config.tool_name] = tool_config

            return result

    async def get_tool_config(
        self, app_code: str, tool_name: str
    ) -> Optional[ToolStreamingConfig]:
        """Get streaming config for a specific tool"""
        with self._storage.session() as session:
            config = (
                session.query(StreamingToolConfig)
                .filter(
                    StreamingToolConfig.app_code == app_code,
                    StreamingToolConfig.tool_name == tool_name,
                )
                .first()
            )

            if not config:
                return None

            return ToolStreamingConfig(
                tool_name=config.tool_name,
                app_code=config.app_code,
                param_configs={
                    name: ParamStreamingConfig.from_dict(data)
                    for name, data in (config.param_configs or {}).items()
                },
                global_threshold=config.global_threshold or 256,
                global_strategy=config.global_strategy or "adaptive",
                global_renderer=config.global_renderer or "default",
                enabled=config.enabled,
                priority=config.priority or 0,
            )

    async def save_tool_config(
        self, app_code: str, tool_name: str, config: ToolStreamingConfig
    ) -> bool:
        """Save streaming config for a tool"""
        with self._storage.session() as session:
            existing = (
                session.query(StreamingToolConfig)
                .filter(
                    StreamingToolConfig.app_code == app_code,
                    StreamingToolConfig.tool_name == tool_name,
                )
                .first()
            )

            param_configs_dict = {
                name: pc.to_dict() for name, pc in config.param_configs.items()
            }

            if existing:
                existing.param_configs = param_configs_dict
                existing.global_threshold = config.global_threshold
                existing.global_strategy = config.global_strategy.value
                existing.global_renderer = config.global_renderer
                existing.enabled = config.enabled
                existing.priority = config.priority
            else:
                new_config = StreamingToolConfig(
                    app_code=app_code,
                    tool_name=tool_name,
                    param_configs=param_configs_dict,
                    global_threshold=config.global_threshold,
                    global_strategy=config.global_strategy.value,
                    global_renderer=config.global_renderer,
                    enabled=config.enabled,
                    priority=config.priority,
                )
                session.add(new_config)

            session.commit()
            return True

    async def delete_tool_config(self, app_code: str, tool_name: str) -> bool:
        """Delete streaming config for a tool"""
        with self._storage.session() as session:
            deleted = (
                session.query(StreamingToolConfig)
                .filter(
                    StreamingToolConfig.app_code == app_code,
                    StreamingToolConfig.tool_name == tool_name,
                )
                .delete()
            )
            session.commit()
            return deleted > 0

    async def get_available_tools(self, app_code: Optional[str] = None) -> List[Dict]:
        """Get list of available tools with their parameters"""
        tools = []

        default_tools = [
            {
                "tool_name": "write",
                "tool_display_name": "Write Tool",
                "description": "Create or overwrite files",
                "parameters": [
                    {
                        "name": "content",
                        "type": "string",
                        "description": "File content",
                    },
                    {"name": "file_path", "type": "string", "description": "File path"},
                ],
            },
            {
                "tool_name": "edit",
                "tool_display_name": "Edit Tool",
                "description": "Edit file content",
                "parameters": [
                    {
                        "name": "newString",
                        "type": "string",
                        "description": "New content",
                    },
                    {
                        "name": "oldString",
                        "type": "string",
                        "description": "Old content",
                    },
                ],
            },
            {
                "tool_name": "bash",
                "tool_display_name": "Bash Tool",
                "description": "Execute commands",
                "parameters": [
                    {
                        "name": "command",
                        "type": "string",
                        "description": "Command content",
                    },
                ],
            },
            {
                "tool_name": "execute_code",
                "tool_display_name": "Execute Code",
                "description": "Execute code",
                "parameters": [
                    {"name": "code", "type": "string", "description": "Code content"},
                ],
            },
        ]

        if app_code:
            configs = await self.get_app_configs(app_code)
            for tool in default_tools:
                tool["has_streaming_config"] = tool["tool_name"] in configs
                tools.append(tool)
        else:
            for tool in default_tools:
                tool["has_streaming_config"] = False
                tools.append(tool)

        return tools


def get_streaming_config_service() -> StreamingConfigService:
    """Get or create the streaming config service singleton"""
    global _service, _storage

    if _service is not None:
        return _service

    system_app = SystemApp.get_instance()
    _storage = system_app.get_component(SQLAlchemyStorage)

    if _storage is None:
        raise RuntimeError("SQLAlchemyStorage not found in SystemApp")

    _service = StreamingConfigService(_storage)
    return _service
