"""L0 verbatim tools (RFC 004 §3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult
from derisk.knowledge.types import ExtractMode, Verbat

from derisk_ext.knowledge.tools.base import KnowledgeToolBase


_EXTRACT_MODE_VALUES = [m.value for m in ExtractMode]


class VerbatAddTool(KnowledgeToolBase):
    """Add an L0 verbatim (immutable raw source) to the space."""

    @classmethod
    def tool_name(cls) -> str:
        return "verbat_add"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Add a verbatim raw source (L0) to the knowledge space. "
            "Content is immutable after write; duplicates by content hash "
            "return the existing id. extract_mode must be one of: "
            + ", ".join(_EXTRACT_MODE_VALUES)
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Verbatim text"},
                "source_file": {
                    "type": "string",
                    "description": "Basename of the source file (no path)",
                },
                "extract_mode": {
                    "type": "string",
                    "enum": _EXTRACT_MODE_VALUES,
                    "description": "How this verbatim entered the space",
                },
                "source_path": {
                    "type": "string",
                    "description": "Optional full path (internal use)",
                },
            },
            "required": ["content", "source_file", "extract_mode"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            v = Verbat.create(
                space_id=vault.space_id,
                content=args["content"],
                source_file=args["source_file"],
                extract_mode=ExtractMode(args["extract_mode"]),
                source_path=args.get("source_path"),
            )
            vid = await vault.verbat_add(v)
            return self.ok({"verbat_id": vid})
        except Exception as e:
            return self.fail(str(e))


class VerbatSearchTool(KnowledgeToolBase):
    """Search L0 verbats by text + optional extract_mode filter."""

    @classmethod
    def tool_name(cls) -> str:
        return "verbat_search"

    @classmethod
    def tool_description(cls) -> str:
        return "Search L0 verbats by keyword. Optional extract_mode filter."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "extract_mode": {
                    "type": "string",
                    "enum": _EXTRACT_MODE_VALUES,
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            hits = await vault.verbat_search(
                args["query"],
                extract_mode=args.get("extract_mode"),
                limit=args.get("limit", 10),
            )
            return self.ok(
                [
                    {
                        "verbat_id": h.verbat_id,
                        "score": h.score,
                        "snippet": h.snippet,
                        "source_file": h.source_file,
                        "extract_mode": h.extract_mode.value
                        if hasattr(h.extract_mode, "value")
                        else h.extract_mode,
                    }
                    for h in hits
                ]
            )
        except Exception as e:
            return self.fail(str(e))


class VerbatGetTool(KnowledgeToolBase):
    """Fetch a single verbatim by id."""

    @classmethod
    def tool_name(cls) -> str:
        return "verbat_get"

    @classmethod
    def tool_description(cls) -> str:
        return "Fetch a single verbatim by id."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"verbat_id": {"type": "string"}},
            "required": ["verbat_id"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            v = await vault.verbat_get(args["verbat_id"])
            if v is None:
                return self.fail("not found", error_code="NOT_FOUND")
            return self.ok(
                {
                    "id": v.id,
                    "content": v.content,
                    "source_file": v.source_file,
                    "extract_mode": v.extract_mode.value,
                    "deprecated": v.deprecated,
                }
            )
        except Exception as e:
            return self.fail(str(e))


class VerbatListTool(KnowledgeToolBase):
    """List verbats with pagination."""

    @classmethod
    def tool_name(cls) -> str:
        return "verbat_list"

    @classmethod
    def tool_description(cls) -> str:
        return "List L0 verbats with pagination (limit/offset)."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "offset": {"type": "integer", "default": 0},
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            page = await vault.verbat_list(
                limit=args.get("limit", 20),
                offset=args.get("offset", 0),
            )
            return self.ok(
                [
                    {
                        "id": v.id,
                        "source_file": v.source_file,
                        "extract_mode": v.extract_mode.value,
                        "deprecated": v.deprecated,
                    }
                    for v in page
                ]
            )
        except Exception as e:
            return self.fail(str(e))
