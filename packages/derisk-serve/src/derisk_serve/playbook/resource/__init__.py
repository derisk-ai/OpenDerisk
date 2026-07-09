"""Playbook resource module.

This module provides PlaybookResource, a ResourceProtocol implementation
that treats playbooks as composite resources containing:
- Independent text content (workflow, role definition, constraints, etc.)
- Sub-resource references (skills, datasources, mcp, knowledge, etc.)
- Built-in playbook tools (get_playbook_info, get_playbook_skills, etc.)
"""
from .playbook_resource import (
    PlaybookConfig,
    PlaybookResource,
    PlaybookTextContent,
    build_playbook_tools,
    create_playbook_resource,
)

__all__ = [
    "PlaybookConfig",
    "PlaybookResource",
    "PlaybookTextContent",
    "build_playbook_tools",
    "create_playbook_resource",
]