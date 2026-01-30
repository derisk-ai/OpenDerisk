"""Stub module for reasoning agent ability type definitions.

This module provides minimal stub classes to support the reasoning
functionality that may have been refactored elsewhere. These stubs
allow existing imports to continue working while the codebase is being
reorganized.
"""
from typing import List, Type, Optional, Any

# Import resource types from derisk to build ability types
from derisk.agent.resource import FunctionTool, BaseTool
from derisk.agent.resource.agent_skills import AgentSkillResource
from derisk.agent.resource.workflow import WorkflowResource
from derisk.agent.resource.memory import MemoryResource
from derisk.agent.resource.base import Resource


def valid_ability_types() -> List[Type]:
    """Return a list of valid ability types.

    Returns:
        List of resource types that can be used as abilities in reasoning.
    """
    return [
        FunctionTool,
        AgentSkillResource,
        WorkflowResource,
        MemoryResource,
        BaseTool,
    ]


class Ability:
    """Represents a capability or ability that an agent can use.

    In the refactor, this was likely tracking different types of resources
    that agents can utilize during reasoning. This stub provides minimal
    compatibility for existing code.
    """

    name: str
    actual_type: Type
    resource: Resource

    def __init__(self, name: str, actual_type: Type, resource: Resource):
        """Initialize an Ability.

        Args:
            name: The display name of the ability
            actual_type: The actual Python type of the resource
            resource: The resource instance
        """
        self.name = name
        self.actual_type = actual_type
        self.resource = resource

    @classmethod
    def by(cls, resource: Resource) -> Optional["Ability"]:
        """Create an Ability from a Resource.

        Args:
            resource: The resource to wrap

        Returns:
            An Ability instance or None if the resource is not valid
        """
        if not resource:
            return None
        # Create ability from resource
        return Ability(
            name=getattr(resource, "name", str(type(resource).__name__)),
            actual_type=type(resource),
            resource=resource,
        )

    def to_dict(self) -> dict:
        """Convert ability to dictionary representation."""
        return {
            "name": self.name,
            "actual_type": str(self.actual_type),
        }