"""KnowledgeSpaceResource - mounts a VaultFS-backed space onto an Agent.

This is the link between an Agent and a knowledge space. It is purely a
mounting config — no retrieval logic lives here. Built-in tools
(see derisk_ext.knowledge.tools) operate on the VaultFS the resource
exposes.

Replaces the old RetrieverResource which coupled mounting to retrieval
(RFC 004 §2).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Callable, Optional, Type

from derisk.agent.resource.base import Resource, ResourceParameters, ResourceType

if TYPE_CHECKING:
    from derisk_ext.knowledge.vaultfs import VaultFS


@dataclasses.dataclass
class KnowledgeSpaceResourceParameters(ResourceParameters):
    """Mount parameters for a knowledge space."""

    space_slug: str = dataclasses.field(
        default="",
        metadata={"help": "Slug of the knowledge space to mount"},
    )


# Registry hook: set by derisk_app at startup so the resource can resolve
# a slug to a VaultFS instance without depending on app code directly.
# Signature: async def(slug: str) -> VaultFS
_VAULT_FACTORY: Optional[Callable[[str], Any]] = None


def set_vault_factory(factory: Callable[[str], Any]) -> None:
    """Register a factory that resolves space_slug -> VaultFS instance."""
    global _VAULT_FACTORY
    _VAULT_FACTORY = factory


def get_vault_factory() -> Optional[Callable[[str], Any]]:
    return _VAULT_FACTORY


class KnowledgeSpaceResource(Resource[KnowledgeSpaceResourceParameters]):
    """A knowledge space mounted onto an Agent.

    The resource itself is a thin handle: it holds the space slug and
    resolves it to a VaultFS instance via the registered factory. All
    operations (read, write, search, graph) are performed by built-in
    tools that look up the resource from the Agent context.
    """

    def __init__(
        self,
        name: str,
        space_slug: str = "",
        vault: Optional["VaultFS"] = None,
    ):
        self._name = name
        self._space_slug = space_slug
        self._vault = vault  # may be provided directly (tests) or resolved lazily

    # ----- Resource protocol -----
    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Knowledge space '{self._space_slug}' (L0 raw + L1 wiki + L2 graph)"

    @classmethod
    def type(cls) -> ResourceType:
        return ResourceType.Knowledge

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[ResourceParameters]:
        return KnowledgeSpaceResourceParameters

    @classmethod
    def from_resource(
        cls,
        resource_id: str,
        resource_params: KnowledgeSpaceResourceParameters,
        **kwargs,
    ) -> "KnowledgeSpaceResource":
        return cls(
            name=resource_id,
            space_slug=resource_params.space_slug,
        )

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ):
        """No prompt injection — knowledge is accessed via tools, not by RAG
        context assembly. Kept to satisfy the Resource protocol.
        """
        return "", None

    # ----- KnowledgeSpace-specific -----
    @property
    def space_slug(self) -> str:
        return self._space_slug

    async def get_vault(self) -> "VaultFS":
        """Resolve and return the VaultFS instance for this space.

        Resolution order:
        1. If a vault was provided to __init__, return it.
        2. Otherwise call the registered vault factory with space_slug.
        3. If no factory registered, raise RuntimeError.
        """
        if self._vault is not None:
            return self._vault

        factory = get_vault_factory()
        if factory is None:
            raise RuntimeError(
                "No vault factory registered. Call "
                "derisk_ext.knowledge.resource.set_vault_factory(...) at "
                "app startup, or pass vault= explicitly to the resource."
            )

        vault = factory(self._space_slug)
        # Factory may be sync or async
        if hasattr(vault, "__await__"):
            vault = await vault  # type: ignore[assignment]
        self._vault = vault
        return vault


__all__ = [
    "KnowledgeSpaceResource",
    "KnowledgeSpaceResourceParameters",
    "set_vault_factory",
    "get_vault_factory",
]
