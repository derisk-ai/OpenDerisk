"""
Derisk Core Module - Unified Tool Authorization System

This package provides the core components for the unified tool authorization system:
- Tools: Tool definitions, registry, and decorators
- Authorization: Permission rules, risk assessment, and authorization engine
- Interaction: User interaction protocol and gateway
- Agent: Agent base class and implementations

Version: 2.0

Usage:
    from derisk.core.tools import ToolRegistry, tool
    from derisk.core.authorization import AuthorizationEngine, AuthorizationConfig
    from derisk.core.interaction import InteractionGateway
    from derisk.core.agent import AgentInfo

Example:
    # Register a custom tool
    @tool(
        name="my_tool",
        description="My custom tool",
        category="utility",
    )
    async def my_tool(param: str) -> str:
        return f"Result: {param}"
    
    # Create an agent with authorization
    info = AgentInfo(
        name="my_agent",
        authorization={"mode": "strict"},
    )
"""

__version__ = "2.0.0"

# Submodules will be available as:
# - derisk.core.tools
# - derisk.core.authorization
# - derisk.core.interaction
# - derisk.core.agent
