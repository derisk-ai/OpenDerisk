"""
Streaming Configuration Loader

Loads and manages configuration for streaming parameters.
Supports YAML configuration files with sensible defaults.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set

import yaml

from .chunk_strategies import ChunkStrategy

logger = logging.getLogger(__name__)


@dataclass
class ParamStreamingConfig:
    """Configuration for a single parameter's streaming behavior"""

    name: str
    threshold: int = 256  # Characters
    strategy: ChunkStrategy = ChunkStrategy.ADAPTIVE
    chunk_size: int = 100
    chunk_by_line: bool = True
    renderer: str = "default"  # Frontend renderer hint


@dataclass
class ToolStreamingConfig:
    """Configuration for a tool's streaming behavior"""

    tool_name: str
    streaming_params: Dict[str, ParamStreamingConfig] = field(default_factory=dict)


@dataclass
class GlobalStreamingConfig:
    """Global streaming configuration"""

    default_threshold: int = 256
    default_strategy: ChunkStrategy = ChunkStrategy.ADAPTIVE
    default_chunk_size: int = 100
    default_chunk_by_line: bool = True
    max_chunk_size: int = 4096
    enable_compression: bool = False
    enable_checksum: bool = True


class StreamingConfigLoader:
    """
    Loader for streaming configuration.

    Loads from YAML file with fallback to defaults.
    Configuration can be hot-reloaded for dynamic updates.

    Configuration file format (streaming-tools.yaml):
    ```yaml
    streaming_tools:
      write:
        streaming_params:
          - name: content
            threshold: 1024
            strategy: semantic
            renderer: code

      edit:
        streaming_params:
          - name: newString
            threshold: 512
            strategy: line_based
            renderer: code
          - name: oldString
            threshold: 512
            strategy: line_based
            renderer: code

    global:
      default_threshold: 256
      default_strategy: adaptive
      max_chunk_size: 4096
      enable_checksum: true
    ```

    Usage:
        loader = StreamingConfigLoader()

        # Check if a param should be streamed
        if loader.should_stream('write', 'content', value):
            # Stream it

        # Get chunk strategy
        strategy = loader.get_chunk_strategy('write', 'content')
    """

    DEFAULT_CONFIG_PATH = "config/streaming-tools.yaml"

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config loader.

        Args:
            config_path: Path to configuration file (optional)
        """
        self.config_path = Path(config_path or self.DEFAULT_CONFIG_PATH)

        # Configuration storage
        self._global_config = GlobalStreamingConfig()
        self._tool_configs: Dict[str, ToolStreamingConfig] = {}

        # Load configuration
        self._load()

    def _load(self) -> None:
        """Load configuration from file"""
        if not self.config_path.exists():
            logger.info(
                f"[StreamingConfigLoader] Config file not found: {self.config_path}"
            )
            self._load_defaults()
            return

        try:
            with open(self.config_path, "r") as f:
                config_data = yaml.safe_load(f)

            if config_data:
                self._parse_config(config_data)
                logger.info(
                    f"[StreamingConfigLoader] Loaded config from: {self.config_path}"
                )
            else:
                self._load_defaults()

        except Exception as e:
            logger.error(f"[StreamingConfigLoader] Error loading config: {e}")
            self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default configuration"""
        self._global_config = GlobalStreamingConfig()

        # Default tool configurations
        default_tools = {
            "write": {
                "content": ParamStreamingConfig(
                    name="content",
                    threshold=1024,
                    strategy=ChunkStrategy.SEMANTIC,
                    renderer="code",
                )
            },
            "edit": {
                "newString": ParamStreamingConfig(
                    name="newString",
                    threshold=512,
                    strategy=ChunkStrategy.LINE_BASED,
                    renderer="code",
                ),
                "oldString": ParamStreamingConfig(
                    name="oldString",
                    threshold=512,
                    strategy=ChunkStrategy.LINE_BASED,
                    renderer="code",
                ),
            },
            "bash": {
                "command": ParamStreamingConfig(
                    name="command",
                    threshold=256,
                    strategy=ChunkStrategy.FIXED_SIZE,
                    chunk_size=256,
                    renderer="code",
                )
            },
            "execute_code": {
                "code": ParamStreamingConfig(
                    name="code",
                    threshold=512,
                    strategy=ChunkStrategy.SEMANTIC,
                    renderer="code",
                )
            },
        }

        for tool_name, params in default_tools.items():
            self._tool_configs[tool_name] = ToolStreamingConfig(
                tool_name=tool_name, streaming_params=params
            )

    def _parse_config(self, config_data: Dict[str, Any]) -> None:
        """Parse configuration from loaded data"""
        # Parse global config
        global_data = config_data.get("global", {})
        self._global_config = GlobalStreamingConfig(
            default_threshold=global_data.get("default_threshold", 256),
            default_strategy=ChunkStrategy(
                global_data.get("default_strategy", "adaptive")
            ),
            default_chunk_size=global_data.get("default_chunk_size", 100),
            default_chunk_by_line=global_data.get("default_chunk_by_line", True),
            max_chunk_size=global_data.get("max_chunk_size", 4096),
            enable_compression=global_data.get("enable_compression", False),
            enable_checksum=global_data.get("enable_checksum", True),
        )

        # Parse tool configs
        tools_data = config_data.get("streaming_tools", {})
        for tool_name, tool_data in tools_data.items():
            params_data = tool_data.get("streaming_params", [])

            streaming_params = {}
            for param_data in params_data:
                param_name = param_data.get("name")
                if param_name:
                    streaming_params[param_name] = ParamStreamingConfig(
                        name=param_name,
                        threshold=param_data.get(
                            "threshold", self._global_config.default_threshold
                        ),
                        strategy=ChunkStrategy(
                            param_data.get(
                                "strategy", self._global_config.default_strategy.value
                            )
                        ),
                        chunk_size=param_data.get(
                            "chunk_size", self._global_config.default_chunk_size
                        ),
                        chunk_by_line=param_data.get(
                            "chunk_by_line", self._global_config.default_chunk_by_line
                        ),
                        renderer=param_data.get("renderer", "default"),
                    )

            self._tool_configs[tool_name] = ToolStreamingConfig(
                tool_name=tool_name, streaming_params=streaming_params
            )

    def reload(self) -> None:
        """Reload configuration from file"""
        self._load()

    def should_stream(self, tool_name: str, param_name: str, value: Any) -> bool:
        """
        Determine if a parameter should be streamed.

        Args:
            tool_name: Name of the tool
            param_name: Name of the parameter
            value: The parameter value

        Returns:
            True if the parameter should be streamed
        """
        # Get tool config
        tool_config = self._tool_configs.get(tool_name)
        if not tool_config:
            return False

        # Get param config
        param_config = tool_config.streaming_params.get(param_name)
        if not param_config:
            return False

        # Check value type
        if not isinstance(value, str):
            return False

        # Check threshold
        return len(value) >= param_config.threshold

    def get_param_config(
        self, tool_name: str, param_name: str
    ) -> Optional[ParamStreamingConfig]:
        """
        Get configuration for a specific parameter.

        Args:
            tool_name: Name of the tool
            param_name: Name of the parameter

        Returns:
            Parameter configuration or None
        """
        tool_config = self._tool_configs.get(tool_name)
        if tool_config:
            return tool_config.streaming_params.get(param_name)
        return None

    def get_chunk_strategy(self, tool_name: str, param_name: str) -> ChunkStrategy:
        """
        Get the chunk strategy for a parameter.

        Args:
            tool_name: Name of the tool
            param_name: Name of the parameter

        Returns:
            Chunk strategy to use
        """
        param_config = self.get_param_config(tool_name, param_name)
        if param_config:
            return param_config.strategy
        return self._global_config.default_strategy

    def get_renderer(self, tool_name: str, param_name: str) -> str:
        """
        Get the renderer hint for a parameter.

        Args:
            tool_name: Name of the tool
            param_name: Name of the parameter

        Returns:
            Renderer name hint
        """
        param_config = self.get_param_config(tool_name, param_name)
        if param_config:
            return param_config.renderer
        return "default"

    def get_streaming_params(self, tool_name: str) -> Set[str]:
        """
        Get all streaming parameters for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Set of parameter names that should be streamed
        """
        tool_config = self._tool_configs.get(tool_name)
        if tool_config:
            return set(tool_config.streaming_params.keys())
        return set()

    def get_global_config(self) -> GlobalStreamingConfig:
        """Get the global configuration"""
        return self._global_config

    def get_all_streaming_params(self) -> Dict[str, Set[str]]:
        """
        Get all streaming parameters grouped by tool.

        Returns:
            Dict mapping tool names to sets of streaming parameter names
        """
        result = {}
        for tool_name, tool_config in self._tool_configs.items():
            result[tool_name] = set(tool_config.streaming_params.keys())
        return result


# Global config loader instance
_config_loader: Optional[StreamingConfigLoader] = None


def get_config_loader() -> StreamingConfigLoader:
    """Get the global config loader instance"""
    global _config_loader
    if _config_loader is None:
        _config_loader = StreamingConfigLoader()
    return _config_loader


def set_config_loader(loader: StreamingConfigLoader) -> None:
    """Set the global config loader instance"""
    global _config_loader
    _config_loader = loader
