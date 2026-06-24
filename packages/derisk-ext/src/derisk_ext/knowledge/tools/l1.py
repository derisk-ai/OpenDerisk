"""L1 document tools (RFC 004 §3)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult

from derisk_ext.knowledge.tools.base import KnowledgeToolBase


class DocCreateTool(KnowledgeToolBase):
    """Create a new L1 markdown document under wiki/."""

    @classmethod
    def tool_name(cls) -> str:
        return "doc_create"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Create a new L1 markdown page at the given path under wiki/. "
            "The content must include YAML frontmatter with at least type "
            "and title. The type must be declared in schema.md Page Types."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to wiki/, e.g. 'concepts/attention.md'",
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown including frontmatter fence",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            doc_id = await vault.doc_create(path=args["path"], content=args["content"])
            return self.ok({"doc_id": doc_id})
        except Exception as e:
            return self.fail(str(e))


class DocReadTool(KnowledgeToolBase):
    """Read a single L1 document by path."""

    @classmethod
    def tool_name(cls) -> str:
        return "doc_read"

    @classmethod
    def tool_description(cls) -> str:
        return "Read a single L1 document by path under wiki/."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            doc = await vault.doc_read(args["path"])
            if doc is None:
                return self.fail("not found", error_code="NOT_FOUND")
            return self.ok(
                {
                    "id": doc.id,
                    "path": doc.path,
                    "type": doc.type,
                    "title": doc.title,
                    "frontmatter": doc.frontmatter,
                    "content": doc.content,
                    "version": doc.version,
                }
            )
        except Exception as e:
            return self.fail(str(e))


class DocEditTool(KnowledgeToolBase):
    """Edit an existing L1 document. Bumps version."""

    @classmethod
    def tool_name(cls) -> str:
        return "doc_edit"

    @classmethod
    def tool_description(cls) -> str:
        return "Replace an L1 document's content. Version auto-increments."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            await vault.doc_edit(path=args["path"], content=args["content"])
            return self.ok({"path": args["path"]})
        except Exception as e:
            return self.fail(str(e))


class DocSearchTool(KnowledgeToolBase):
    """Search L1 documents by keyword (FTS5)."""

    @classmethod
    def tool_name(cls) -> str:
        return "doc_search"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Search L1 wiki documents. mode='documents' = FTS (keyword); "
            "mode='semantic' = vector recall (cosine similarity, requires "
            "embedder configured); mode='hybrid' = FTS + vector via "
            "reciprocal rank fusion (best default for conceptual queries); "
            "mode='references' = backlink lookup via L2 edges."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {
                    "type": "string",
                    "default": "documents",
                    "enum": ["documents", "semantic", "hybrid", "references"],
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
            hits = await vault.doc_search(
                args["query"],
                mode=args.get("mode", "documents"),
                limit=args.get("limit", 10),
            )
            return self.ok(
                [
                    {
                        "document_id": h.document_id,
                        "path": h.path,
                        "title": h.title,
                        "type": h.type,
                        "score": h.score,
                        "snippet": h.snippet,
                    }
                    for h in hits
                ]
            )
        except Exception as e:
            return self.fail(str(e))


class DocListTool(KnowledgeToolBase):
    """List L1 documents with pagination."""

    @classmethod
    def tool_name(cls) -> str:
        return "doc_list"

    @classmethod
    def tool_description(cls) -> str:
        return "List L1 documents with pagination (limit/offset)."

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
            metas = await vault.doc_list(
                limit=args.get("limit", 20),
                offset=args.get("offset", 0),
            )
            return self.ok(
                [
                    {
                        "id": m.id,
                        "path": m.path,
                        "type": m.type,
                        "title": m.title,
                        "status": m.status,
                    }
                    for m in metas
                ]
            )
        except Exception as e:
            return self.fail(str(e))


class DocAppendLogTool(KnowledgeToolBase):
    """Append a timestamped entry to log.md."""

    @classmethod
    def tool_name(cls) -> str:
        return "doc_append_log"

    @classmethod
    def tool_description(cls) -> str:
        return "Append a markdown entry to log.md (protected file)."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"entry": {"type": "string"}},
            "required": ["entry"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            await vault.doc_append_log(args["entry"])
            return self.ok({"ok": True})
        except Exception as e:
            return self.fail(str(e))
