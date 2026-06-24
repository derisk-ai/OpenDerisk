"""Space-level tools: schema.md and lint (RFC 004 §3)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult

from derisk_ext.knowledge.tools.base import KnowledgeToolBase


class SchemaReadTool(KnowledgeToolBase):
    """Read the raw schema.md content of a space."""

    @classmethod
    def tool_name(cls) -> str:
        return "schema_read"

    @classmethod
    def tool_description(cls) -> str:
        return "Read the raw schema.md content of the space. Use this before adding new page types or relation types."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            raw = await vault.read_schema_md()
            return self.ok({"schema_md": raw})
        except Exception as e:
            return self.fail(str(e))


class SchemaWriteTool(KnowledgeToolBase):
    """Replace schema.md content. Caller is responsible for triggering reindex."""

    @classmethod
    def tool_name(cls) -> str:
        return "schema_write"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Replace schema.md content. Editing schema.md immediately affects "
            "future doc_create / edge_add validation."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            await vault.write_schema_md(args["content"])
            return self.ok({"ok": True})
        except Exception as e:
            return self.fail(str(e))


class LintRunTool(KnowledgeToolBase):
    """Run lint checks per schema.md ## Lint Rules."""

    @classmethod
    def tool_name(cls) -> str:
        return "lint_run"

    @classmethod
    def tool_description(cls) -> str:
        return "Run lint checks (orphan pages, stale edges, contradictions, dangling links, etc.) per schema.md Lint Rules."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            # VaultFS exposes lint via reindex? Actually lint is a separate
            # method per RFC 002 §3. We call it here; if not implemented,
            # surface a clear error.
            if not hasattr(vault, "lint"):
                return self.fail(
                    "vault backend does not implement lint()",
                    error_code="NOT_IMPLEMENTED",
                )
            issues = await vault.lint()
            return self.ok(
                {
                    "issues": [
                        {
                            "rule": i.rule,
                            "severity": i.severity,
                            "path": i.path,
                            "edge_id": i.edge_id,
                            "message": i.message,
                        }
                        for i in issues
                    ]
                }
            )
        except Exception as e:
            return self.fail(str(e))
