"""Admin tools: reindex and embedder identity (RFC 004 §3)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult

from derisk_ext.knowledge.tools.base import KnowledgeToolBase


class ReindexTool(KnowledgeToolBase):
    """Rebuild derived indexes (chunks / L2 / all)."""

    @classmethod
    def tool_name(cls) -> str:
        return "reindex"

    @classmethod
    def tool_description(cls) -> str:
        return "Rebuild derived indexes. layer: 'chunks' | 'L2' | 'all'."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": ["chunks", "L2", "all"],
                    "default": "L2",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            report = await vault.reindex(layer=args.get("layer", "L2"))
            return self.ok(
                {
                    "layer": report.layer,
                    "verbats_processed": report.verbats_processed,
                    "documents_processed": report.documents_processed,
                    "chunks_built": report.chunks_built,
                    "edges_built": report.edges_built,
                    "duration_seconds": report.duration_seconds,
                    "errors": report.errors,
                }
            )
        except Exception as e:
            return self.fail(str(e))


class SetEmbedderIdentityTool(KnowledgeToolBase):
    """Lock or swap the embedder identity for a space."""

    @classmethod
    def tool_name(cls) -> str:
        return "set_embedder_identity"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Persist the embedder identity (model_name + dimension) for the "
            "space. Use force_swap=true to override a mismatched identity."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model_name": {"type": "string"},
                "dimension": {"type": "integer"},
                "force_swap": {"type": "boolean", "default": False},
            },
            "required": ["model_name", "dimension"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            await vault.set_embedder_identity(
                model_name=args["model_name"],
                dimension=args["dimension"],
                force_swap=args.get("force_swap", False),
            )
            ident = await vault.get_embedder_identity()
            return self.ok(
                {
                    "model_name": ident.model_name,
                    "dimension": ident.dimension,
                    "state": ident.state.value
                    if hasattr(ident.state, "value")
                    else ident.state,
                }
            )
        except Exception as e:
            return self.fail(str(e))
