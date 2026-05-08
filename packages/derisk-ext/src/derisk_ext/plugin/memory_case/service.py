from __future__ import annotations

import logging
import uuid
from asyncio import TimeoutError as AsyncTimeoutError
from asyncio import wait_for
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, Field
from derisk.component import SystemApp

from .dao_protocol import MemoryCaseDaoLike
from .markdown import parse_markdown_sections, render_case_markdown
from .models import CandidateCase, CandidateCaseLifecycle, MemoryRequestContext
from .vector_index import CandidateCaseVectorIndex, EmptyCandidateCaseVectorIndex

logger = logging.getLogger(__name__)

BUILTIN_MEMORY_MCP = "memory_case"
BUILTIN_MEMORY_MCP_NAME = "案例记忆"
MEMORY_PLUGIN_ENABLED_KEY = "derisk_serve.mcp.memory_plugin_enabled"
MEMORY_PLUGIN_TIMEOUT_KEY = "derisk_serve.mcp.memory_plugin_timeout"


class MemoryPluginError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class MemoryToolSpec(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any] = Field(default_factory=dict)


class MemoryCasePluginService:
    def __init__(
        self,
        system_app: SystemApp,
        dao: MemoryCaseDaoLike,
        enabled: bool = True,
        timeout_seconds: int = 10,
        vector_index: Optional[CandidateCaseVectorIndex] = None,
    ):
        self._system_app = system_app
        self._dao = dao
        self._enabled = enabled
        self._timeout_seconds = timeout_seconds
        self._vector_index = vector_index or EmptyCandidateCaseVectorIndex()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def list_tools(self) -> List[MemoryToolSpec]:
        return [
            MemoryToolSpec(
                name="memory_case_search",
                description=(
                    "FIRST for ops/SRE/inspection/RCA tasks when this tool exists: call "
                    "once BEFORE read/bash/git or opening local skill files—past runbooks "
                    "live here, not only under pilot/data/skill. Short NL query "
                    "(symptom + product/service + scenario e.g. 华为云 节前巡检); never "
                    "paste full logs. Default top_k=5; narrow query and retry if weak."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "object",
                            "description": (
                                "Routing isolation ONLY (app_code/tenant_id/team_id for "
                                "multi-tenant; environment for deploy env prod/staging). "
                                "Cloud-vendor or region info belongs in case metadata "
                                "(region/tags), NOT in scope. "
                                "Omit or set to 'default' for wildcard (recommended)."
                            ),
                        },
                        "query": {
                            "type": "string",
                            "description": (
                                "Short search text. Avoid pasting entire logs or "
                                "system prompts."
                            ),
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 20,
                            "description": "Max cases (default 5).",
                        },
                    },
                },
            ),
            MemoryToolSpec(
                name="memory_case_upsert",
                description=(
                    "End-of-task: persist RCA/playbook. BEFORE new row, "
                    "memory_case_search for near-dupes; merge via case_id if match. "
                    "Include symptom_summary, hypotheses, actions, resolution, "
                    "confidence."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["case"],
                    "properties": {
                        "case": {
                            "type": "object",
                            "description": (
                                "CandidateCase: symptom_summary, hypotheses, actions, "
                                "resolution, confidence; optional incident_title; "
                                "handling_path (free text, narrative reference—not a strict playbook); "
                                "root_cause; metadata.case_context for routing and provenance "
                                "(application_name, data_sources, related_services, region, tags, …); "
                                "optional case_id to merge; fingerprint optional "
                                "(derived from case_context + summary if omitted)."
                            ),
                        }
                    },
                },
            ),
            MemoryToolSpec(
                name="memory_case_feedback",
                description=(
                    "After using a retrieved case, log helpful true/false; optional "
                    "signal stale|success|rollback adjusts lifecycle "
                    "(see plugin rules)."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["case_id"],
                    "properties": {
                        "case_id": {
                            "type": "string",
                            "description": "case_id from search or upsert.",
                        },
                        "helpful": {
                            "type": "boolean",
                            "description": "True if this case helped.",
                        },
                        "signal": {
                            "type": "string",
                            "description": "Optional: stale, success, rollback, etc.",
                        },
                    },
                },
            ),
            MemoryToolSpec(
                name="memory_case_render",
                description=(
                    "Render search hits as Markdown. Pass cases from search JSON or "
                    "case_ids."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "case_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Load by id.",
                        },
                        "cases": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Inline dicts from search results.",
                        },
                    },
                },
            ),
        ]

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        args = arguments or {}
        if not self.enabled:
            raise MemoryPluginError(
                "MEMORY_PLUGIN_DISABLED",
                "memory MCP plugin is disabled",
            )

        try:
            if tool_name == "memory_case_search":
                return await wait_for(self._search(args), timeout=self._timeout_seconds)
            if tool_name == "memory_case_upsert":
                return await wait_for(self._upsert(args), timeout=self._timeout_seconds)
            if tool_name == "memory_case_feedback":
                return await wait_for(
                    self._feedback(args),
                    timeout=self._timeout_seconds,
                )
            if tool_name == "memory_case_render":
                return await wait_for(
                    self._render(args),
                    timeout=self._timeout_seconds,
                )
            raise MemoryPluginError(
                "TOOL_NOT_FOUND",
                f"Unknown memory tool: {tool_name}",
            )
        except AsyncTimeoutError as exc:
            raise MemoryPluginError(
                "TOOL_TIMEOUT",
                f"tool timeout: {tool_name}",
            ) from exc

    def _validate_scope(self, scope: Dict[str, Any]) -> MemoryRequestContext:
        try:
            return MemoryRequestContext(**scope)
        except Exception as exc:
            raise MemoryPluginError("INVALID_SCOPE", str(exc)) from exc

    async def _search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        scope = args.get("scope") or {}
        context = self._validate_scope(scope)
        query = args.get("query")
        top_k = int(args.get("top_k", 5))
        if top_k <= 0:
            raise MemoryPluginError("INVALID_TOP_K", "top_k must be positive")

        query_limit = min(top_k, 20)
        lexical_cases = self._dao.search(
            context.scope_dict(), query_text=query, limit=query_limit
        )
        semantic_case_ids = await self._vector_index.search(
            query or context.alert_text or "",
            context.scope_dict(),
            query_limit,
        )
        case_by_id = {case.case_id: case for case in lexical_cases}
        for case_id in semantic_case_ids:
            if case_id and case_id not in case_by_id:
                match = self._dao.get_by_case_id(case_id)
                if match:
                    case_by_id[case_id] = match
        # Lazy backfill: DB hits missing from vector index get reindexed
        for case in lexical_cases:
            if case.case_id not in set(semantic_case_ids):
                try:
                    await self._vector_index.upsert(case)
                except Exception:
                    pass
        ordered_cases = sorted(
            case_by_id.values(),
            key=lambda item: (item.confidence, item.updated_at or datetime.min),
            reverse=True,
        )[:query_limit]

        def _eligible(case: CandidateCase) -> bool:
            if case.lifecycle == CandidateCaseLifecycle.REJECTED:
                return False
            return case.confidence >= 0.5

        accepted_cases = [
            case
            for case in ordered_cases
            if case.lifecycle == CandidateCaseLifecycle.ACCEPTED
        ]
        candidate_pool = accepted_cases or ordered_cases
        items = [
            case.model_dump(mode="json")
            for case in candidate_pool
            if _eligible(case)
        ]
        return {
            "code": "OK",
            "cases": items,
            "count": len(items),
            "degraded": len(semantic_case_ids) == 0,
        }

    async def _upsert(self, args: Dict[str, Any]) -> Dict[str, Any]:
        case_data = args.get("case")
        if not case_data:
            raise MemoryPluginError("MISSING_CASE", "case payload is required")
        if not case_data.get("case_id"):
            case_data["case_id"] = f"case-{uuid.uuid4().hex}"
        case = CandidateCase(**case_data)
        if not case.markdown_summary:
            case.markdown_summary = render_case_markdown(case)
        saved = self._dao.upsert(case)
        try:
            await self._vector_index.upsert(saved)
        except Exception:
            logger.warning(
                "memory_case vector upsert failed for %s, will retry later",
                saved.case_id,
                exc_info=True,
            )
        return {"code": "OK", "case": saved.model_dump(mode="json")}

    async def _feedback(self, args: Dict[str, Any]) -> Dict[str, Any]:
        case_id = args.get("case_id")
        if not case_id:
            raise MemoryPluginError("MISSING_CASE_ID", "case_id is required")
        case = self._dao.get_by_case_id(case_id)
        if not case:
            raise MemoryPluginError("CASE_NOT_FOUND", f"case not found: {case_id}")

        helpful = args.get("helpful")
        signal = args.get("signal")

        if helpful is True:
            case.confidence = min(1.0, case.confidence + 0.1)
            case.lifecycle = CandidateCaseLifecycle.ACCEPTED
        elif helpful is False:
            case.confidence = max(0.0, case.confidence - 0.2)
            if case.confidence < 0.2:
                case.lifecycle = CandidateCaseLifecycle.REJECTED

        if signal == "stale":
            case.lifecycle = CandidateCaseLifecycle.STALE
            case.confidence = max(0.0, case.confidence - 0.1)
        elif signal == "success":
            case.confidence = min(1.0, case.confidence + 0.05)
        elif signal == "rollback":
            case.confidence = max(0.0, case.confidence - 0.1)

        requires_review = False
        review_reasons: List[str] = []
        if case.confidence < 0.3:
            requires_review = True
            review_reasons.append("low_confidence")
        if signal in {"rollback", "conflict", "high_risk"}:
            requires_review = True
            review_reasons.append(f"signal:{signal}")

        case.metadata["requires_human_review"] = requires_review
        case.metadata["review_reasons"] = review_reasons
        case.metadata["last_feedback_signal"] = signal
        case.metadata["last_feedback_at"] = datetime.now(UTC).isoformat()
        saved = self._dao.upsert(case)
        if saved.lifecycle == CandidateCaseLifecycle.STALE:
            await self._vector_index.invalidate(saved.case_id)
        return {"code": "OK", "case": saved.model_dump(mode="json")}

    async def _render(self, args: Dict[str, Any]) -> Dict[str, Any]:
        blocks: List[str] = []
        for case_payload in args.get("cases") or []:
            case = CandidateCase(**case_payload)
            markdown = case.markdown_summary or render_case_markdown(case)
            sections = parse_markdown_sections(markdown)
            blocks.append(markdown if sections else case.markdown_summary)

        for case_id in args.get("case_ids") or []:
            case = self._dao.get_by_case_id(case_id)
            if case:
                blocks.append(case.markdown_summary or render_case_markdown(case))

        if not blocks:
            return {"code": "OK", "markdown": "", "count": 0}
        merged = "\n\n---\n\n".join(blocks[:5])
        return {"code": "OK", "markdown": merged, "count": len(blocks[:5])}
