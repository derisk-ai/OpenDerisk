"""Base class for all knowledge tools.

Resolves the VaultFS instance for a given space_slug via the
KnowledgeSpaceResource's vault factory. Tools take `space_slug` as the
first parameter — the MCP/Agent layer validates that the slug matches
one of the Agent's mounted resources.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Optional

from derisk.agent.tools.base import ToolBase
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import ToolResult

from derisk_ext.knowledge.resource import get_vault_factory


class KnowledgeToolBase(ToolBase):
    """Common base: vault lookup + standard ok/fail helpers."""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.tool_name(),
            description=self.tool_description(),
        )

    @classmethod
    @abstractmethod
    def tool_name(cls) -> str:
        ...

    @classmethod
    @abstractmethod
    def tool_description(cls) -> str:
        ...

    def _define_parameters(self) -> Dict[str, Any]:
        # Subclasses override; common space_slug property injected here.
        params = self._define_own_parameters()
        props = params.setdefault("properties", {})
        if "space_slug" not in props:
            props["space_slug"] = {
                "type": "string",
                "description": "Slug of the knowledge space to operate on",
            }
        required = params.setdefault("required", [])
        if "space_slug" not in required:
            required.insert(0, "space_slug")
        return params

    def _define_own_parameters(self) -> Dict[str, Any]:
        """Subclass hook for parameters other than space_slug."""
        return {"type": "object", "properties": {}, "required": []}

    async def _get_vault(self, args: Dict[str, Any], context: Optional[ToolContext]):
        slug = args.get("space_slug")
        if not slug:
            raise ValueError("space_slug is required")

        factory = get_vault_factory()
        if factory is None:
            raise RuntimeError(
                "No vault factory registered. Call "
                "derisk_ext.knowledge.resource.set_vault_factory(...) "
                "at app startup."
            )

        # TODO: validate that `slug` matches one of the Agent's mounted
        # resources, once ToolContext exposes the resource_map. For now
        # the factory itself is authoritative.
        vault = factory(slug)
        if hasattr(vault, "__await__"):
            vault = await vault
        return vault

    def ok(self, output: Any) -> ToolResult:
        return ToolResult.ok(output=output, tool_name=self.name)

    def fail(self, error: str, error_code: str = "KNOWLEDGE_ERROR") -> ToolResult:
        return ToolResult.fail(error=error, tool_name=self.name, error_code=error_code)
