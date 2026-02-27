import os
from dataclasses import dataclass, field
from typing import Optional

from derisk._private.config import Config
from derisk.configs.model_config import DATA_DIR
from derisk_serve.core import BaseServeConfig

APP_NAME = "skill"
SERVE_APP_NAME = "derisk_serve_skill"
SERVE_APP_NAME_HUMP = "Skill"
SERVER_APP_TABLE_NAME = "server_app_skill"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.skill"

CFG = Config()

# Default skill directories (use DATA_DIR/skill as default)
DEFAULT_PROJECT_SKILL_DIR = os.path.join(DATA_DIR, "skill")
DEFAULT_TEMP_GIT_DIR = os.path.join(DATA_DIR, "skill", ".git_cache")


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
        metadata={"help": "Project-local skill directory path"},
    )

    # Temporary directory for git operations
    temp_git_dir: Optional[str] = field(
        default=DEFAULT_TEMP_GIT_DIR,
        metadata={"help": "Temporary directory for git operations"},
    )

    # Sandbox skill directory (for syncing skills to sandbox)
    sandbox_skill_dir: Optional[str] = field(
        default=None, metadata={"help": "Sandbox skill directory path"}
    )

    # Default skill repository to load on startup
    default_skill_repo_url: Optional[str] = field(
        default="https://github.com/derisk-ai/derisk-skills.git",
        metadata={"help": "Default git repository URL for skills to load on startup"},
    )

    default_skill_repo_branch: Optional[str] = field(
        default="main",
        metadata={"help": "Default git branch for skill repository"},
    )

    def get_type_value(self):
        return self.__type__

    def get_project_skill_dir(self) -> str:
        """Get absolute path to project skill directory"""
        if self.project_skill_dir and os.path.isabs(self.project_skill_dir):
            return self.project_skill_dir
        # Use DATA_DIR/skill as the default skill directory
        return DEFAULT_PROJECT_SKILL_DIR

    def get_temp_git_dir(self) -> str:
        """Get absolute path to temp git directory"""
        if self.temp_git_dir and os.path.isabs(self.temp_git_dir):
            return self.temp_git_dir
        # Use DATA_DIR/skill/.git_cache as the default temp git directory
        return DEFAULT_TEMP_GIT_DIR

    def get_sandbox_skill_dir(self) -> Optional[str]:
        """Get sandbox skill directory"""
        if self.sandbox_skill_dir:
            return self.sandbox_skill_dir
        return None

    def get_default_skill_repo_url(self) -> Optional[str]:
        """Get default skill repository URL"""
        return self.default_skill_repo_url

    def get_default_skill_repo_branch(self) -> str:
        """Get default skill repository branch"""
        return self.default_skill_repo_branch or "main"
