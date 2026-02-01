import os
from dataclasses import dataclass, field
from typing import Optional

from derisk._private.config import Config
from derisk_serve.core import BaseServeConfig

APP_NAME = "skill"
SERVE_APP_NAME = "derisk_serve_skill"
SERVE_APP_NAME_HUMP = "Skill"
SERVER_APP_TABLE_NAME = "server_app_skill"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.skill"

CFG = Config()

# Default skill directories
DEFAULT_PROJECT_SKILL_DIR = "data/skills"
DEFAULT_TEMP_GIT_DIR = "data/skills/.git_cache"


@dataclass
class ServeConfig(BaseServeConfig):
    """Serve configuration for skill"""

    __type__ = SERVE_APP_NAME

    api_keys: Optional[str] = field(
        default=None, metadata={"help": "API keys for the serve"}
    )

    # Project-local skill directory where skills are stored
    project_skill_dir: Optional[str] = field(
        default=DEFAULT_PROJECT_SKILL_DIR,
        metadata={"help": "Project-local skill directory path"}
    )

    # Temporary directory for git operations
    temp_git_dir: Optional[str] = field(
        default=DEFAULT_TEMP_GIT_DIR,
        metadata={"help": "Temporary directory for git operations"}
    )

    # Sandbox skill directory (for syncing skills to sandbox)
    sandbox_skill_dir: Optional[str] = field(
        default=None,
        metadata={"help": "Sandbox skill directory path"}
    )

    def get_type_value(self):
        return self.__type__

    def get_project_skill_dir(self) -> str:
        """Get absolute path to project skill directory"""
        if self.project_skill_dir and os.path.isabs(self.project_skill_dir):
            return self.project_skill_dir
        # Use CONFIG_ROOT if available, otherwise current working directory
        root = getattr(CFG, 'CONFIG_ROOT', os.getcwd())
        return os.path.join(root, self.project_skill_dir or DEFAULT_PROJECT_SKILL_DIR)

    def get_temp_git_dir(self) -> str:
        """Get absolute path to temp git directory"""
        if self.temp_git_dir and os.path.isabs(self.temp_git_dir):
            return self.temp_git_dir
        root = getattr(CFG, 'CONFIG_ROOT', os.getcwd())
        return os.path.join(root, self.temp_git_dir or DEFAULT_TEMP_GIT_DIR)

    def get_sandbox_skill_dir(self) -> Optional[str]:
        """Get sandbox skill directory"""
        if self.sandbox_skill_dir:
            return self.sandbox_skill_dir
        # Try to get from sandbox config
        try:
            from derisk_serve.core.config import GPTsAppConfig
            app_config = CFG.get(GPTsAppConfig, default=None)
            if app_config and hasattr(app_config, 'sandbox') and app_config.sandbox:
                sandbox_skill_dir = app_config.sandbox.skill_dir
                if sandbox_skill_dir:
                    return sandbox_skill_dir
        except Exception:
            pass
        return None
