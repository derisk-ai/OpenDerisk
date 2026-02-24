"""
Register local sandbox provider

This module provides the LocalSandbox class which uses the improved
implementation with proper security isolation, Playwright browser support,
and full SandboxBase interface compliance.
"""
import logging
from typing import Optional, Dict, Any, List

# Import the improved implementation
from derisk_ext.sandbox.local.improved_provider import (
    ImprovedLocalSandbox as LocalSandbox,
    LocalSandboxConfig,
    get_local_sandbox_config_from_toml,
    create_local_sandbox_from_toml,
    create_development_sandbox,
    create_strict_sandbox,
    create_browser_sandbox,
)

# Re-export original runtime for backward compatibility
from derisk_ext.sandbox.local.runtime import LocalSandboxRuntime, SessionConfig

logger = logging.getLogger(__name__)


# Re-export everything for backward compatibility
__all__ = [
    "LocalSandbox",
    "LocalSandboxRuntime",
    "SessionConfig",
    "LocalSandboxConfig",
    "get_local_sandbox_config_from_toml",
    "create_local_sandbox_from_toml",
    "create_development_sandbox",
    "create_strict_sandbox",
    "create_browser_sandbox",
]


# Backward compatibility helpers
async def create_local_sandbox(
    user_id: str,
    agent: str,
    **kwargs
) -> LocalSandbox:
    """
    Create a local sandbox instance.

    This is a backward-compatible wrapper around ImprovedLocalSandbox.create().

    Args:
        user_id: User ID
        agent: Agent identifier
        **kwargs: Additional arguments including:
            - work_dir: Working directory (default: /workspace)
            - timeout: Execution timeout in seconds (default: 300)
            - allow_network: Whether to allow network access (default: True)
            - use_sandbox_exec: Whether to use sandbox-exec on macOS (default: auto-detect)
            - enable_browser: Whether to enable browser capabilities (default: True)
            - max_memory: Maximum memory in bytes (default: 256MB)
            - max_cpus: Maximum CPU count (default: 1)
            - metadata: Optional metadata dictionary

    Returns:
        LocalSandbox instance
    """
    return await LocalSandbox.create(user_id, agent, **kwargs)


def parse_sandbox_config(config_dict: Dict[str, Any]) -> LocalSandboxConfig:
    """
    Parse sandbox configuration from a dictionary.

    Args:
        config_dict: Configuration dictionary

    Returns:
        LocalSandboxConfig instance
    """
    return LocalSandboxConfig.from_dict(config_dict)