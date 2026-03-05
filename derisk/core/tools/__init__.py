"""
Tools Module - Unified Tool Authorization System

This module provides the complete tool system:
- Metadata: Tool metadata definitions
- Base: ToolBase, ToolResult, ToolRegistry
- Decorators: Tool registration decorators
- Builtin: Built-in tools (file, shell, network, code)

Version: 2.0
"""

from .metadata import (
    ToolCategory,
    RiskLevel,
    RiskCategory,
    AuthorizationRequirement,
    ToolParameter,
    ToolMetadata,
)

from .base import (
    ToolResult,
    ToolBase,
    ToolRegistry,
    tool_registry,
)

from .decorators import (
    tool,
    shell_tool,
    file_read_tool,
    file_write_tool,
    network_tool,
    data_tool,
    agent_tool,
    interaction_tool,
)

from .builtin import register_builtin_tools

__all__ = [
    # Metadata
    "ToolCategory",
    "RiskLevel",
    "RiskCategory",
    "AuthorizationRequirement",
    "ToolParameter",
    "ToolMetadata",
    # Base
    "ToolResult",
    "ToolBase",
    "ToolRegistry",
    "tool_registry",
    # Decorators
    "tool",
    "shell_tool",
    "file_read_tool",
    "file_write_tool",
    "network_tool",
    "data_tool",
    "agent_tool",
    "interaction_tool",
    # Builtin
    "register_builtin_tools",
]
