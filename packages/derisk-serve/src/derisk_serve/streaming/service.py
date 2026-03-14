"""
Streaming Configuration Service

Business logic for managing streaming tool configurations.
"""

import logging
from typing import Any, Dict, List, Optional

from derisk.component import SystemApp

logger = logging.getLogger(__name__)

_storage = None
_service: Optional["StreamingConfigService"] = None


class StreamingConfigService:
    """Service for managing streaming configurations"""

    def __init__(self, storage=None):
        self._storage = storage

    async def get_app_configs(self, app_code: str) -> Dict[str, Any]:
        """Get all streaming configs for an app"""
        if not self._storage:
            return {}

        from derisk.model.streaming.config_manager import (
            ToolStreamingConfig,
            ParamStreamingConfig,
        )
        from derisk.model.streaming.db_models import StreamingToolConfig

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

    async def get_tool_config(self, app_code: str, tool_name: str) -> Optional[Any]:
        """Get streaming config for a specific tool"""
        if not self._storage:
            return None

        from derisk.model.streaming.config_manager import (
            ToolStreamingConfig,
            ParamStreamingConfig,
        )
        from derisk.model.streaming.db_models import StreamingToolConfig

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
        self, app_code: str, tool_name: str, config: Any
    ) -> bool:
        """Save streaming config for a tool"""
        if not self._storage:
            logger.warning("Storage not available, skipping save")
            return False

        from derisk.model.streaming.db_models import StreamingToolConfig

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
        if not self._storage:
            return False

        from derisk.model.streaming.db_models import StreamingToolConfig

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
        from derisk.agent.tools import tool_registry

        tools = []

        try:
            all_tools = tool_registry.get_all_tools()

            for tool in all_tools:
                params = tool.parameters if hasattr(tool, "parameters") else {}
                properties = params.get("properties", {})

                parameters_list = []
                for param_name, param_info in properties.items():
                    parameters_list.append(
                        {
                            "name": param_name,
                            "type": param_info.get("type", "string"),
                            "description": param_info.get("description", ""),
                        }
                    )

                tools.append(
                    {
                        "tool_name": tool.name,
                        "tool_display_name": tool.metadata.display_name
                        if hasattr(tool, "metadata")
                        else tool.name,
                        "description": tool.metadata.description
                        if hasattr(tool, "metadata")
                        else "",
                        "parameters": parameters_list,
                        "has_streaming_config": False,
                    }
                )
        except Exception as e:
            logger.error(f"Failed to get tools from registry: {e}")

            if not tools:
                tools = self._get_default_tools()

        if app_code:
            configs = await self.get_app_configs(app_code)
            for tool in tools:
                tool["has_streaming_config"] = tool["tool_name"] in configs

        return tools

    def _get_default_tools(self) -> List[Dict]:
        """Get default tool list as fallback"""
        return [
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
                    {"name": "path", "type": "string", "description": "File path"},
                ],
                "has_streaming_config": False,
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
                "has_streaming_config": False,
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
                "has_streaming_config": False,
            },
            {
                "tool_name": "read",
                "tool_display_name": "Read File",
                "description": "Read file content",
                "parameters": [
                    {"name": "file_path", "type": "string", "description": "File path"},
                ],
                "has_streaming_config": False,
            },
        ]


def get_streaming_config_service() -> StreamingConfigService:
    """Get or create the streaming config service singleton"""
    global _service

    if _service is not None:
        return _service

    try:
        from derisk.storage.metadata.db_storage import SQLAlchemyStorage

        system_app = SystemApp.get_instance()
        storage = system_app.get_component(SQLAlchemyStorage)

        _service = StreamingConfigService(storage)
    except Exception as e:
        logger.warning(
            f"Failed to get SQLAlchemyStorage, using memory-only service: {e}"
        )
        _service = StreamingConfigService(None)

    return _service
