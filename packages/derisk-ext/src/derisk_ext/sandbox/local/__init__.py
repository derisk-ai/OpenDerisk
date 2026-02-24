"""
Expose local sandbox

Local sandbox implementation with proper security isolation:
- macOS: Uses sandbox-exec for process isolation
- Linux: Uses resource limits and path restrictions
- Windows: Basic isolation (full sandboxing not yet available)

Features:
- Secure file operations within sandbox directory
- Real browser automation via Playwright
- Shell command execution with timeouts
- Resource limit enforcement
- Optional network access control
"""

from derisk_ext.sandbox.local.provider import (
    LocalSandbox,
    LocalSandboxRuntime,
    SessionConfig,
    LocalSandboxConfig,
    get_local_sandbox_config_from_toml,
    create_local_sandbox_from_toml,
    create_development_sandbox,
    create_strict_sandbox,
    create_browser_sandbox,
    parse_sandbox_config,
)

from derisk_ext.sandbox.local.improved_runtime import (
    ImprovedLocalSandboxRuntime,
    ImprovedLocalSandboxSession,
    get_platform,
)

from derisk_ext.sandbox.local.runtime import (
    LocalSandboxRuntime as OldLocalSandboxRuntime,
)

from derisk_ext.sandbox.local.shell_client import LocalShellClient
from derisk_ext.sandbox.local.file_client import LocalFileClient
from derisk_ext.sandbox.local.macos_sandbox import (
    MacOSSandboxWrapper,
    MacOSSandboxProfile,
    SandboxProfileConfig,
    create_sandbox_wrapper,
    SandboxProfileConfig as MacOSSandboxProfileConfig,
    SandboxProfileConfig as SandboxConfig,
)
from derisk_ext.sandbox.local.playwright_browser_client import (
    PlaywrightBrowserClient,
    BrowserConfig,
    is_playwright_available,
)

# Re-export original browser client for fallback
from derisk_ext.sandbox.local.browser_client import LocalBrowserClient

__all__ = [
    # Main provider
    "LocalSandbox",
    "LocalSandboxConfig",
    "LocalSandboxRuntime",
    "SessionConfig",
    # Improved runtime
    "ImprovedLocalSandboxRuntime",
    "ImprovedLocalSandboxSession",
    "get_platform",
    # (Deprecated) Original runtime for backward compatibility
    "OldLocalSandboxRuntime",
    # Clients
    "LocalShellClient",
    "LocalFileClient",
    "LocalBrowserClient",
    "PlaywrightBrowserClient",
    # macOS sandbox integration
    "MacOSSandboxWrapper",
    "MacOSSandboxProfile",
    "MacOSSandboxProfileConfig",
    "SandboxConfig",
    "create_sandbox_wrapper",
    # Browser config
    "BrowserConfig",
    "is_playwright_available",
    # Configuration helpers
    "get_local_sandbox_config_from_toml",
    "create_local_sandbox_from_toml",
    "parse_sandbox_config",
    # Predefined templates
    "create_development_sandbox",
    "create_strict_sandbox",
    "create_browser_sandbox",
]


def __dir__():
    """Return a sorted list of public names."""
    return sorted(__all__)