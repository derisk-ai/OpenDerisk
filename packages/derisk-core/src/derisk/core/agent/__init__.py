"""
Agent Module - Unified Tool Authorization System

This module provides the agent system:
- Info: Agent configuration and templates
- Base: AgentBase abstract class and AgentState
- Production: ProductionAgent implementation
- Builtin: Built-in agent implementations

Version: 2.0
"""

from .info import (
    AgentMode,
    AgentCapability,
    ToolSelectionPolicy,
    AgentInfo,
    create_agent_from_template,
    get_agent_template,
    list_agent_templates,
    AGENT_TEMPLATES,
    PRIMARY_AGENT_TEMPLATE,
    PLAN_AGENT_TEMPLATE,
    SUBAGENT_TEMPLATE,
    EXPLORE_AGENT_TEMPLATE,
)

from .base import (
    AgentState,
    AgentBase,
)

from .production import (
    ProductionAgent,
    create_production_agent,
)

from .builtin import (
    PlanAgent,
    create_plan_agent,
    ExploreSubagent,
    CodeSubagent,
    create_explore_subagent,
)

__all__ = [
    # Info
    "AgentMode",
    "AgentCapability",
    "ToolSelectionPolicy",
    "AgentInfo",
    "create_agent_from_template",
    "get_agent_template",
    "list_agent_templates",
    "AGENT_TEMPLATES",
    "PRIMARY_AGENT_TEMPLATE",
    "PLAN_AGENT_TEMPLATE",
    "SUBAGENT_TEMPLATE",
    "EXPLORE_AGENT_TEMPLATE",
    # Base
    "AgentState",
    "AgentBase",
    # Production
    "ProductionAgent",
    "create_production_agent",
    # Builtin
    "PlanAgent",
    "create_plan_agent",
    "ExploreSubagent",
    "CodeSubagent",
    "create_explore_subagent",
]
