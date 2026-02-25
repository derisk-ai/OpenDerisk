import os
from dataclasses import dataclass, field
from typing import Optional

from derisk.configs.model_config import DATA_DIR
from derisk_serve.core import BaseServeConfig

APP_NAME = "mcp"
SERVE_APP_NAME = "derisk_serve_mcp"
SERVE_APP_NAME_HUMP = "derisk_serve_Mcp"
SERVE_CONFIG_KEY_PREFIX = "derisk_serve.mcp."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_mcp"

# Default MCP directories (use DATA_DIR/mcp, consistent with skill using DATA_DIR/skill)
DEFAULT_MCP_DIR = os.path.join(DATA_DIR, "mcp")
DEFAULT_MCP_GIT_CACHE_DIR = os.path.join(DATA_DIR, "mcp", ".git_cache")

# Default remote repository for MCP server configurations
DEFAULT_MCP_REPO_URL = "https://github.com/derisk-ai/derisk-mcps"
DEFAULT_MCP_REPO_BRANCH = "main"

# Subdirectory inside the repo that contains MCP server JSON config files
DEFAULT_MCP_SERVERS_SUBDIR = "servers"


@dataclass
class ServeConfig(BaseServeConfig):
    """Parameters for the serve command"""

    __type__ = APP_NAME

    # Git repository URL containing default MCP server configurations.
    # Set to empty string to disable automatic syncing from remote repo.
    default_mcp_repo_url: Optional[str] = field(
        default=DEFAULT_MCP_REPO_URL,
        metadata={"help": "Git repo URL for default MCP server configs"},
    )

    # Git branch to use when cloning the MCP config repo.
    default_mcp_repo_branch: str = field(
        default=DEFAULT_MCP_REPO_BRANCH,
        metadata={"help": "Git branch for the MCP config repo"},
    )

    # Local directory where MCP JSON config files are stored.
    # The repo's servers/ content is copied here after cloning.
    # Defaults to pilot/data/mcp, consistent with skill at pilot/data/skill.
    default_mcp_dir: Optional[str] = field(
        default=DEFAULT_MCP_DIR,
        metadata={"help": "Local MCP data directory path"},
    )

    # Temporary directory for git clone operations.
    # Follows the same .git_cache pattern as the skill module.
    default_mcp_git_cache_dir: Optional[str] = field(
        default=DEFAULT_MCP_GIT_CACHE_DIR,
        metadata={"help": "Temporary directory for git operations"},
    )

    # Subdirectory inside the repo containing JSON config files.
    default_mcp_servers_subdir: str = field(
        default=DEFAULT_MCP_SERVERS_SUBDIR,
        metadata={"help": "Subdirectory in repo containing MCP server configs"},
    )

    # Whether to overwrite existing DB records when syncing default MCPs.
    # When False (default), only new MCPs are inserted; existing ones are skipped.
    default_mcp_overwrite: bool = field(
        default=False,
        metadata={"help": "Whether to overwrite existing MCP records during sync"},
    )

    def get_mcp_dir(self) -> str:
        """Get absolute path to MCP data directory"""
        if self.default_mcp_dir and os.path.isabs(self.default_mcp_dir):
            return self.default_mcp_dir
        return DEFAULT_MCP_DIR

    def get_mcp_git_cache_dir(self) -> str:
        """Get absolute path to MCP git cache directory"""
        if self.default_mcp_git_cache_dir and os.path.isabs(
            self.default_mcp_git_cache_dir
        ):
            return self.default_mcp_git_cache_dir
        return DEFAULT_MCP_GIT_CACHE_DIR
