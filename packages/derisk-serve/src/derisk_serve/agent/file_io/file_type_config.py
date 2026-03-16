"""File Type Configuration for OpenDeRisk

Supports dynamic configuration of file processing modes:
- MODEL_DIRECT: Direct model consumption (multimodal messages)
- SANDBOX_TOOL: Sandbox tool consumption

Configuration priority:
1. Environment variable FILE_TYPE_CONFIG (JSON format)
2. Configuration file file_type_config.yaml
3. Default configuration
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

logger = logging.getLogger(__name__)


class FileProcessMode(Enum):
    """File processing mode"""

    MODEL_DIRECT = "model_direct"  # Direct model consumption (multimodal messages)
    SANDBOX_TOOL = "sandbox_tool"  # Sandbox tool consumption


@dataclass
class FileTypeRule:
    """File type rule"""

    extensions: Set[str]  # File extension set, e.g. {".jpg", ".png"}
    mime_types: Set[str]  # MIME type set, e.g. {"image/jpeg", "image/png"}
    mode: FileProcessMode  # Processing mode
    description: str = ""  # Rule description


@dataclass
class FileTypeConfig:
    """File type configuration"""

    # Model direct consumption file types (multimodal)
    model_direct_rules: List[FileTypeRule] = field(default_factory=list)
    # Sandbox tool consumption file types
    sandbox_tool_rules: List[FileTypeRule] = field(default_factory=list)
    # Default processing mode
    default_mode: FileProcessMode = FileProcessMode.SANDBOX_TOOL
    # Enable configuration hot reload
    enable_hot_reload: bool = False

    def get_process_mode(
        self, file_name: str, mime_type: Optional[str] = None
    ) -> FileProcessMode:
        """Get processing mode based on file name and MIME type

        Args:
            file_name: File name
            mime_type: MIME type (optional)

        Returns:
            File processing mode
        """
        # Get file extension
        ext = self._get_extension(file_name)

        # Check model direct rules first (higher priority)
        for rule in self.model_direct_rules:
            if ext in rule.extensions:
                return FileProcessMode.MODEL_DIRECT
            if mime_type and mime_type in rule.mime_types:
                return FileProcessMode.MODEL_DIRECT

        # Check sandbox tool rules
        for rule in self.sandbox_tool_rules:
            if ext in rule.extensions:
                return FileProcessMode.SANDBOX_TOOL
            if mime_type and mime_type in rule.mime_types:
                return FileProcessMode.SANDBOX_TOOL

        # Return default mode
        return self.default_mode

    def _get_extension(self, file_name: str) -> str:
        """Get file extension (lowercase)"""
        if not file_name:
            return ""
        parts = file_name.rsplit(".", 1)
        if len(parts) == 2:
            return f".{parts[1].lower()}"
        return ""

    def is_model_direct(self, file_name: str, mime_type: Optional[str] = None) -> bool:
        """Check if file should be processed by model directly"""
        return (
            self.get_process_mode(file_name, mime_type) == FileProcessMode.MODEL_DIRECT
        )

    def is_sandbox_tool(self, file_name: str, mime_type: Optional[str] = None) -> bool:
        """Check if file should be processed by sandbox tool"""
        return (
            self.get_process_mode(file_name, mime_type) == FileProcessMode.SANDBOX_TOOL
        )


# Default configuration
DEFAULT_CONFIG = FileTypeConfig(
    model_direct_rules=[
        # Image types - Model direct consumption
        FileTypeRule(
            extensions={".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"},
            mime_types={
                "image/jpeg",
                "image/png",
                "image/gif",
                "image/webp",
                "image/bmp",
                "image/svg+xml",
            },
            mode=FileProcessMode.MODEL_DIRECT,
            description="Image files (model direct consumption)",
        ),
    ],
    sandbox_tool_rules=[
        # Document types - Sandbox tool consumption
        FileTypeRule(
            extensions={".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"},
            mime_types={
                "application/pdf",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
            mode=FileProcessMode.SANDBOX_TOOL,
            description="Document files (sandbox tool consumption)",
        ),
        # Code files - Sandbox tool consumption
        FileTypeRule(
            extensions={
                ".py",
                ".js",
                ".ts",
                ".java",
                ".go",
                ".rs",
                ".cpp",
                ".c",
                ".h",
                ".json",
                ".yaml",
                ".yml",
                ".xml",
                ".sql",
            },
            mime_types={"text/x-python", "application/javascript", "text/javascript"},
            mode=FileProcessMode.SANDBOX_TOOL,
            description="Code files (sandbox tool consumption)",
        ),
        # Data files - Sandbox tool consumption
        FileTypeRule(
            extensions={".csv", ".txt", ".log", ".md", ".json", ".parquet"},
            mime_types={"text/csv", "text/plain", "text/markdown"},
            mode=FileProcessMode.SANDBOX_TOOL,
            description="Data files (sandbox tool consumption)",
        ),
        # Archive files - Sandbox tool consumption
        FileTypeRule(
            extensions={".zip", ".tar", ".gz", ".rar", ".7z"},
            mime_types={"application/zip", "application/x-tar", "application/gzip"},
            mode=FileProcessMode.SANDBOX_TOOL,
            description="Archive files (sandbox tool consumption)",
        ),
    ],
    default_mode=FileProcessMode.SANDBOX_TOOL,
)


class FileTypeConfigManager:
    """File type configuration manager"""

    _instance: Optional["FileTypeConfigManager"] = None
    _config: Optional[FileTypeConfig] = None
    _config_path: Optional[Path] = None
    _last_modified: float = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "FileTypeConfigManager":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_config(self) -> FileTypeConfig:
        """Get current configuration (supports hot reload)"""
        if self._config is None:
            self._load_config()
        elif self._config.enable_hot_reload and self._config_path:
            # Check if configuration file has been updated
            if self._config_path.exists():
                current_modified = self._config_path.stat().st_mtime
                if current_modified > self._last_modified:
                    logger.info("[FileTypeConfig] Config file changed, reloading...")
                    self._load_config()
        return self._config

    def _load_config(self) -> None:
        """Load configuration"""
        # Priority 1: Environment variable
        env_config = os.getenv("FILE_TYPE_CONFIG")
        if env_config:
            try:
                config_dict = json.loads(env_config)
                self._config = self._parse_config_dict(config_dict)
                logger.info("[FileTypeConfig] Loaded config from environment variable")
                return
            except Exception as e:
                logger.warning(f"[FileTypeConfig] Failed to parse env config: {e}")

        # Priority 2: Configuration file
        config_paths = [
            Path("config/file_type_config.yaml"),
            Path("file_type_config.yaml"),
            Path(__file__).parent / "file_type_config.yaml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    self._config = self._load_yaml_config(config_path)
                    self._config_path = config_path
                    self._last_modified = config_path.stat().st_mtime
                    logger.info(f"[FileTypeConfig] Loaded config from {config_path}")
                    return
                except Exception as e:
                    logger.warning(
                        f"[FileTypeConfig] Failed to load {config_path}: {e}"
                    )

        # Priority 3: Default configuration
        self._config = DEFAULT_CONFIG
        logger.info("[FileTypeConfig] Using default config")

    def _load_yaml_config(self, config_path: Path) -> FileTypeConfig:
        """Load YAML configuration file"""
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
        return self._parse_config_dict(config_dict)

    def _parse_config_dict(self, config_dict: dict) -> FileTypeConfig:
        """Parse configuration dictionary"""
        model_direct_rules = []
        for rule_dict in config_dict.get("model_direct_rules", []):
            model_direct_rules.append(
                FileTypeRule(
                    extensions=set(rule_dict.get("extensions", [])),
                    mime_types=set(rule_dict.get("mime_types", [])),
                    mode=FileProcessMode.MODEL_DIRECT,
                    description=rule_dict.get("description", ""),
                )
            )

        sandbox_tool_rules = []
        for rule_dict in config_dict.get("sandbox_tool_rules", []):
            sandbox_tool_rules.append(
                FileTypeRule(
                    extensions=set(rule_dict.get("extensions", [])),
                    mime_types=set(rule_dict.get("mime_types", [])),
                    mode=FileProcessMode.SANDBOX_TOOL,
                    description=rule_dict.get("description", ""),
                )
            )

        default_mode_str = config_dict.get("default_mode", "sandbox_tool")
        default_mode = FileProcessMode.SANDBOX_TOOL
        if default_mode_str == "model_direct":
            default_mode = FileProcessMode.MODEL_DIRECT

        return FileTypeConfig(
            model_direct_rules=model_direct_rules,
            sandbox_tool_rules=sandbox_tool_rules,
            default_mode=default_mode,
            enable_hot_reload=config_dict.get("enable_hot_reload", False),
        )

    def reload_config(self) -> None:
        """Force reload configuration"""
        self._config = None
        self._load_config()

    def add_model_direct_type(
        self, extension: str, mime_type: Optional[str] = None
    ) -> None:
        """Dynamically add model direct consumption type"""
        config = self.get_config()
        ext = extension if extension.startswith(".") else f".{extension}"

        # Find or create rule
        for rule in config.model_direct_rules:
            if ext not in rule.extensions:
                rule.extensions.add(ext)
                logger.info(
                    f"[FileTypeConfig] Added extension {ext} to model_direct rules"
                )
                return

        # Create new rule
        new_rule = FileTypeRule(
            extensions={ext},
            mime_types={mime_type} if mime_type else set(),
            mode=FileProcessMode.MODEL_DIRECT,
            description=f"Dynamically added: {ext}",
        )
        config.model_direct_rules.append(new_rule)
        logger.info(f"[FileTypeConfig] Created new rule for {ext}")

    def add_sandbox_tool_type(
        self, extension: str, mime_type: Optional[str] = None
    ) -> None:
        """Dynamically add sandbox tool consumption type"""
        config = self.get_config()
        ext = extension if extension.startswith(".") else f".{extension}"

        for rule in config.sandbox_tool_rules:
            if ext not in rule.extensions:
                rule.extensions.add(ext)
                logger.info(
                    f"[FileTypeConfig] Added extension {ext} to sandbox_tool rules"
                )
                return

        new_rule = FileTypeRule(
            extensions={ext},
            mime_types={mime_type} if mime_type else set(),
            mode=FileProcessMode.SANDBOX_TOOL,
            description=f"Dynamically added: {ext}",
        )
        config.sandbox_tool_rules.append(new_rule)
        logger.info(f"[FileTypeConfig] Created new rule for {ext}")


def get_file_process_mode(
    file_name: str, mime_type: Optional[str] = None
) -> FileProcessMode:
    """Convenience function: get file processing mode"""
    manager = FileTypeConfigManager.get_instance()
    config = manager.get_config()
    return config.get_process_mode(file_name, mime_type)


def is_model_direct_file(file_name: str, mime_type: Optional[str] = None) -> bool:
    """Convenience function: check if file should be processed by model directly"""
    return get_file_process_mode(file_name, mime_type) == FileProcessMode.MODEL_DIRECT


def is_sandbox_tool_file(file_name: str, mime_type: Optional[str] = None) -> bool:
    """Convenience function: check if file should be processed by sandbox tool"""
    return get_file_process_mode(file_name, mime_type) == FileProcessMode.SANDBOX_TOOL
