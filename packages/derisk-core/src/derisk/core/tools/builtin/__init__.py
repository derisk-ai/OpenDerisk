"""
Builtin Tools - Unified Tool Authorization System

This package provides built-in tools for:
- File system operations (read, write, edit, glob, grep)
- Shell command execution (bash)
- Network operations (webfetch, websearch)
- Code analysis (analyze)

Version: 2.0
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..base import ToolRegistry

# Import tools to trigger auto-registration
from .file_system import (
    read_file,
    write_file,
    edit_file,
    glob_search,
    grep_search,
)

from .shell import (
    bash_execute,
    detect_dangerous_command,
    DANGEROUS_PATTERNS,
    FORBIDDEN_COMMANDS,
)

from .network import (
    webfetch,
    websearch,
    is_sensitive_url,
    SENSITIVE_URL_PATTERNS,
)

from .code import (
    analyze_code,
    analyze_python_code,
    analyze_generic_code,
    CodeMetrics,
    PythonAnalyzer,
)


# All exported tools
BUILTIN_TOOLS = [
    # File system
    read_file,
    write_file,
    edit_file,
    glob_search,
    grep_search,
    # Shell
    bash_execute,
    # Network
    webfetch,
    websearch,
    # Code
    analyze_code,
]


def register_builtin_tools(registry: "ToolRegistry") -> None:
    """
    Register all builtin tools with the given registry.
    
    Note: Tools are auto-registered when imported if using the decorators.
    This function is provided for explicit registration with a custom registry.
    
    Args:
        registry: The ToolRegistry instance to register tools with
    """
    for tool in BUILTIN_TOOLS:
        if hasattr(tool, 'metadata'):
            # It's a tool instance
            registry.register(tool)


def get_builtin_tool_names() -> list:
    """Get list of builtin tool names."""
    return [tool.name if hasattr(tool, 'name') else str(tool) for tool in BUILTIN_TOOLS]


__all__ = [
    # File system tools
    "read_file",
    "write_file",
    "edit_file",
    "glob_search",
    "grep_search",
    # Shell tools
    "bash_execute",
    "detect_dangerous_command",
    "DANGEROUS_PATTERNS",
    "FORBIDDEN_COMMANDS",
    # Network tools
    "webfetch",
    "websearch",
    "is_sensitive_url",
    "SENSITIVE_URL_PATTERNS",
    # Code tools
    "analyze_code",
    "analyze_python_code",
    "analyze_generic_code",
    "CodeMetrics",
    "PythonAnalyzer",
    # Registration
    "register_builtin_tools",
    "get_builtin_tool_names",
    "BUILTIN_TOOLS",
]
