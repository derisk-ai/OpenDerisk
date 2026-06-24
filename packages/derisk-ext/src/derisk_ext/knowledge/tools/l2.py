"""L2 graph tools (RFC 004 §3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult
from derisk.knowledge.types import Edge, new_edge_id

from derisk_ext.knowledge.tools.base import KnowledgeToolBase


class EdgeAddTool(KnowledgeToolBase):
    """Add an L2 edge. Predicate must be declared in schema.md."""

    @classmethod
    def tool_name(cls) -> str:
        return "edge_add"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Add a directed edge (subject, predicate, object) to the L2 graph. "
            "predicate must be declared in schema.md Relation Types."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "source_document_id": {"type": "string"},
                "source_verbat_id": {"type": "string"},
                "weight": {"type": "number", "default": 1.0},
            },
            "required": ["subject", "predicate", "object"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            e = Edge(
                id=new_edge_id(),
                space_id=vault.space_id,
                subject=args["subject"],
                predicate=args["predicate"],
                object=args["object"],
                source_document_id=args.get("source_document_id"),
                source_verbat_id=args.get("source_verbat_id"),
                weight=args.get("weight", 1.0),
            )
            eid = await vault.edge_add(e)
            return self.ok({"edge_id": eid})
        except Exception as e:
            return self.fail(str(e))


class EdgeInvalidateTool(KnowledgeToolBase):
    """Set valid_to on an edge, keeping history."""

    @classmethod
    def tool_name(cls) -> str:
        return "edge_invalidate"

    @classmethod
    def tool_description(cls) -> str:
        return "Invalidate an edge (set valid_to). The edge remains in history."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"edge_id": {"type": "string"}},
            "required": ["edge_id"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            await vault.edge_invalidate(args["edge_id"])
            return self.ok({"ok": True})
        except Exception as e:
            return self.fail(str(e))


class GraphQueryTool(KnowledgeToolBase):
    """Single-hop graph query by entity."""

    @classmethod
    def tool_name(cls) -> str:
        return "graph_query"

    @classmethod
    def tool_description(cls) -> str:
        return "Query the L2 graph by entity. Returns adjacent nodes and edges."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "predicate": {"type": "string"},
                "include_invalid": {"type": "boolean", "default": False},
            },
            "required": ["entity"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            sub = await vault.graph_query(
                entity=args["entity"],
                predicate=args.get("predicate"),
                include_invalid=args.get("include_invalid", False),
            )
            return self.ok(_subgraph_to_dict(sub))
        except Exception as e:
            return self.fail(str(e))


class GraphTraverseTool(KnowledgeToolBase):
    """Multi-hop BFS/DFS traversal."""

    @classmethod
    def tool_name(cls) -> str:
        return "graph_traverse"

    @classmethod
    def tool_description(cls) -> str:
        return "Traverse the L2 graph from an entity, up to `hop` hops."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "hop": {"type": "integer", "default": 1},
                "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs"},
            },
            "required": ["entity"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            sub = await vault.graph_traverse(
                entity=args["entity"],
                hop=args.get("hop", 1),
                mode=args.get("mode", "bfs"),
            )
            return self.ok(_subgraph_to_dict(sub))
        except Exception as e:
            return self.fail(str(e))


class GraphBacklinksTool(KnowledgeToolBase):
    """Reverse lookup: who links to `entity`."""

    @classmethod
    def tool_name(cls) -> str:
        return "graph_backlinks"

    @classmethod
    def tool_description(cls) -> str:
        return "Return all edges whose object is the given entity."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"entity": {"type": "string"}},
            "required": ["entity"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            edges = await vault.graph_backlinks(args["entity"])
            return self.ok({"edges": [_edge_to_dict(e) for e in edges]})
        except Exception as e:
            return self.fail(str(e))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _edge_to_dict(e) -> dict:
    return {
        "id": e.id,
        "subject": e.subject,
        "predicate": e.predicate,
        "object": e.object,
        "valid_from": e.valid_from.isoformat() if e.valid_from else None,
        "valid_to": e.valid_to.isoformat() if e.valid_to else None,
        "source_document_id": e.source_document_id,
        "source_verbat_id": e.source_verbat_id,
        "weight": e.weight,
    }


def _subgraph_to_dict(sub) -> dict:
    return {
        "nodes": sub.nodes,
        "edges": [_edge_to_dict(e) for e in sub.edges],
        "root": sub.root,
    }
