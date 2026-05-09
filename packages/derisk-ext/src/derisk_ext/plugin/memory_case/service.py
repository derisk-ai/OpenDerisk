from __future__ import annotations

import logging
import math
import uuid
from asyncio import TimeoutError as AsyncTimeoutError
from asyncio import wait_for
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set

from derisk._private.pydantic import BaseModel, Field
from derisk.component import SystemApp

from .case_context import (
    KEY_APP_CODE,
    KEY_ENVIRONMENT,
    KEY_FAILURE_LAYER,
    KEY_RELATED_SERVICES,
    KEY_RUNTIME,
    cross_validate_relation,
)
from .dao_protocol import MemoryCaseDaoLike
from .markdown import parse_markdown_sections, render_case_markdown
from .models import (
    FB_KEY,
    FB_LAMBDA_ACCEPTED,
    FB_LAMBDA_DRAFT,
    FB_MIN_SAMPLES,
    FB_WEIGHT_CAP,
    CandidateCase,
    CandidateCaseLifecycle,
    CaseRelationType,
    FeedbackStats,
    MemoryRequestContext,
    wilson_score,
)
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
        self._search_log: Dict[str, Set[str]] = {}
        self._feedback_log: Dict[str, Set[str]] = {}
        self._max_tracked_conv = 1000

    @property
    def enabled(self) -> bool:
        return self._enabled

    def list_tools(self) -> List[MemoryToolSpec]:
        return [
            MemoryToolSpec(
                name="memory_case_search",
                description=(
                    "STEP 1/2 — FIRST for ops/SRE/inspection/RCA tasks: call once "
                    "BEFORE read/bash/git. Returns lightweight summaries (symptom, "
                    "diagnosis preview 300 chars, root_cause, resolution, confidence, "
                    "lifecycle). Short NL query (symptom + product/service + scenario "
                    "e.g. 华为云 节前巡检); never paste full logs. Default top_k=5. "
                    "THEN call memory_case_render with chosen case_ids to read full "
                    "markdown — do NOT feed search results directly into context."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "object",
                            "description": (
                                "Routing isolation ONLY (app_code for app scope; "
                                "environment for deploy env prod/staging). "
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
                    "Include symptom_summary, diagnosis (free Markdown: hypotheses, "
                    "actions taken, dead ends, reasoning chain), resolution, root_cause, "
                    "confidence."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["case"],
                    "properties": {
                        "case": {
                            "type": "object",
                            "description": (
                                "CandidateCase: symptom_summary, diagnosis (free Markdown "
                                "covering hypotheses, actions, dead ends, and reasoning), "
                                "resolution, root_cause, confidence; "
                                "metadata.case_context for routing and provenance: "
                                "application_name, data_sources, related_services, region, "
                                "tags; "
                                "CRITICAL for cross-case matching — also include "
                                "failure_layer (jvm/k8s/network/db/application), "
                                "runtime (java/go/python/nodejs), middleware (dubbo/spring-boot/gin); "
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

    # ---------------- search-result summary helpers ------------------

    _DIAGNOSIS_PREVIEW_LEN = 300

    @staticmethod
    def _to_summary(case: "CandidateCase") -> Dict[str, Any]:
        """Lightweight summary for ``memory_case_search`` results.

        Omits ``markdown_summary``, full ``diagnosis``, and full ``metadata``
        so the Agent sees just enough to decide which cases to drill into via
        ``memory_case_render``.
        """
        diag = case.diagnosis or ""
        preview = diag[:300] + "..." if len(diag) > 300 else diag
        similar_count = len(case.metadata.get("similar_cases") or []) if case.metadata else 0
        fb = (case.metadata or {}).get(FB_KEY, {}) or {}
        global_fb = fb.get("global", {}) or {}
        return {
            "case_id": case.case_id,
            "symptom_summary": case.symptom_summary,
            "diagnosis_preview": preview,
            "diagnosis_len": len(diag),
            "root_cause": case.root_cause,
            "resolution": case.resolution,
            "confidence": case.confidence,
            "lifecycle": case.lifecycle.value,
            "similar_count": similar_count,
            "source_conv_id": case.source_conv_id,
            "fingerprint": case.fingerprint,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "feedback_h": global_fb.get("h", 0),
            "feedback_u": global_fb.get("u", 0),
            "feedback_cv_count": len(global_fb.get("cv", []) or []),
        }

    # ---------------- rank scoring -----------------------------------

    @staticmethod
    def _lookup_fb_stats(
        fb: Dict[str, Any], scope: Dict[str, Any]
    ) -> Optional[FeedbackStats]:
        """Three-level scope-aware lookup: by_app_env > by_app > global."""
        if not fb or not isinstance(fb, dict):
            return None
        app = str(scope.get("app_code") or "default").strip().lower()
        env = str(scope.get("environment") or "default").strip().lower()

        # Level 1: by_app_env
        by_app_env = fb.get("by_app_env", {}) or {}
        env_entry = by_app_env.get(f"{app}:{env}")
        if isinstance(env_entry, dict):
            s = FeedbackStats(
                h=int(env_entry.get("h", 0)),
                u=int(env_entry.get("u", 0)),
                ts=str(env_entry.get("ts", "")),
            )
            if s.total >= FB_MIN_SAMPLES:
                return s

        # Level 2: by_app
        by_app = fb.get("by_app", {}) or {}
        app_entry = by_app.get(app)
        if isinstance(app_entry, dict):
            s = FeedbackStats(
                h=int(app_entry.get("h", 0)),
                u=int(app_entry.get("u", 0)),
                ts=str(app_entry.get("ts", "")),
            )
            if s.total >= FB_MIN_SAMPLES:
                return s

        # Level 3: global
        g = fb.get("global", {}) or {}
        s = FeedbackStats(
            h=int(g.get("h", 0)),
            u=int(g.get("u", 0)),
            ts=str(g.get("ts", "")),
        )
        return s if s.total > 0 else None  # None if zero feedback: use prior

    @staticmethod
    def _compute_rank_score(
        case: CandidateCase, scope: Dict[str, Any], now: Optional[datetime] = None
    ) -> float:
        """Composite rank: Wilson empirical score (scope-aware) + LLM prior + time decay.

        - Cases with enough feedback use Wilson lower bound weighted by sample count.
        - Cases with insufficient feedback fall back to LLM confidence as prior.
        - All scores are multiplied by a time-decay factor.
        """
        if now is None:
            now = datetime.now(UTC)
        fb = (case.metadata or {}).get(FB_KEY)
        stats = MemoryCasePluginService._lookup_fb_stats(fb, scope)

        # ---- empirical vs prior blend ----
        if stats is not None and stats.total >= FB_MIN_SAMPLES:
            empirical = wilson_score(stats.h, stats.total)
            weight = min(1.0, stats.total / FB_WEIGHT_CAP)
            base = weight * empirical + (1.0 - weight) * case.confidence
        else:
            base = case.confidence

        # ---- time decay ----
        ts_str = stats.ts if (stats is not None and stats.ts) else None
        if not ts_str and case.updated_at:
            ts_str = case.updated_at.isoformat()
        if ts_str:
            try:
                last_dt = datetime.fromisoformat(ts_str)
                days = (now - last_dt).total_seconds() / 86400.0
            except (ValueError, TypeError):
                days = 0.0
        else:
            days = 0.0

        lambd = (
            FB_LAMBDA_ACCEPTED
            if case.lifecycle == CandidateCaseLifecycle.ACCEPTED
            else FB_LAMBDA_DRAFT
        )
        decay = math.exp(-lambd * days)
        return base * decay

    # ----------------------------------------------------------------

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
        search_scope = context.scope_dict()
        ordered_cases = sorted(
            case_by_id.values(),
            key=lambda item: self._compute_rank_score(item, search_scope),
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
        eligible = [case for case in candidate_pool if _eligible(case)]
        items = [self._to_summary(case) for case in eligible]
        result = {
            "code": "OK",
            "cases": items,
            "count": len(items),
            "degraded": len(semantic_case_ids) == 0,
        }
        self._track_search_hits(scope, items)
        return result

    def _track_search_hits(
        self, scope: Dict[str, Any], items: List[Dict[str, Any]]
    ) -> None:
        conv_id = (scope or {}).get("conv_id")
        if not conv_id or not items:
            logger.info(
                "memory_case search tracking skipped: conv_id=%r, items=%d",
                conv_id, len(items),
            )
            return
        if conv_id not in self._search_log:
            self._search_log[conv_id] = set()
        for item in items:
            self._search_log[conv_id].add(item["case_id"])
        logger.info(
            "memory_case search tracked: conv_id=%r case_ids=%s",
            conv_id, [item["case_id"] for item in items],
        )
        self._trim_tracking()

    def _trim_tracking(self) -> None:
        while len(self._search_log) > self._max_tracked_conv:
            oldest = next(iter(self._search_log))
            self._search_log.pop(oldest, None)
            self._feedback_log.pop(oldest, None)

    async def _upsert(self, args: Dict[str, Any]) -> Dict[str, Any]:
        case_data = args.get("case")
        if not case_data:
            logger.warning(
                "memory_case_upsert called without 'case' field; keys received: %s",
                sorted(args.keys()) if args else "<empty>",
            )
            raise MemoryPluginError(
                "MISSING_CASE",
                "case payload is required. Pass a 'case' object with at least "
                "symptom_summary, hypotheses, actions, resolution, and confidence.",
            )
        if not case_data.get("case_id"):
            case_data["case_id"] = f"case-{uuid.uuid4().hex}"
        # strip system-managed keys from incoming metadata
        incoming_meta = case_data.get("metadata")
        if isinstance(incoming_meta, dict):
            incoming_meta.pop(FB_KEY, None)
            incoming_meta.pop("similar_cases", None)
        case = CandidateCase(**case_data)
        if not case.markdown_summary:
            case.markdown_summary = render_case_markdown(case)
        saved = self._dao.upsert(case)
        similar_cases = await self._find_similar_cases(saved)
        if similar_cases:
            saved.metadata["similar_cases"] = similar_cases
            saved = self._dao.upsert(saved)
        try:
            await self._vector_index.upsert(saved)
        except Exception:
            logger.warning(
                "memory_case vector upsert failed for %s, will retry later",
                saved.case_id,
                exc_info=True,
            )
        result: Dict[str, Any] = {"code": "OK", "case": saved.model_dump(mode="json")}
        unreviewed = self._get_unreviewed_cases(
            args.get("scope", {}).get("conv_id"), saved.case_id
        )
        if unreviewed:
            result["unreviewed_cases"] = unreviewed
            result["hint"] = (
                "以上案例在本轮排查中被检索但尚未评价，"
                "请逐一调用 memory_case_feedback 标记是否对本次排查有帮助"
            )
        return result

    def _get_unreviewed_cases(
        self, conv_id: Optional[str], current_case_id: str
    ) -> List[str]:
        if not conv_id:
            logger.info("memory_case unreviewed skipped: no conv_id in upsert scope")
            return []
        searched = self._search_log.get(conv_id, set())
        if not searched:
            logger.info(
                "memory_case unreviewed empty: no prior searches for conv_id=%r",
                conv_id,
            )
            return []
        feedbacked = self._feedback_log.get(conv_id, set())
        unreviewed = sorted(searched - feedbacked - {current_case_id})
        logger.debug(
            "memory_case unreviewed conv_id=%r: searched=%d feedbacked=%d unreviewed=%d",
            conv_id, len(searched), len(feedbacked), len(unreviewed),
        )
        return unreviewed[:10]

    # ---------------- weighted section weights ----------------
    _W_SYMPTOM = 0.1
    _W_DIAGNOSIS = 0.5
    _W_ROOT_CAUSE = 0.4

    _SEC_MIN_SCORE = 0.3   # per-section floor before a hit counts
    _MIN_SCORE = 0.6       # final weighted floor
    _TOP_K = 10            # per-section candidate pool (wider than final)

    @staticmethod
    def _classify_relation(
        *,
        score_symptom: float,
        score_diagnosis: float,
        score_root_cause: float,
        struct_match: bool,
    ) -> CaseRelationType:
        if score_root_cause >= 0.8 and struct_match:
            return CaseRelationType.SAME_ROOT_CAUSE
        if score_diagnosis >= 0.7 and struct_match:
            return CaseRelationType.SIMILAR_DIAGNOSIS
        if score_symptom >= 0.8 and not struct_match:
            return CaseRelationType.SURFACE_SIMILAR
        if score_diagnosis >= 0.6:
            return CaseRelationType.SIMILAR_DIAGNOSIS
        return CaseRelationType.SURFACE_SIMILAR

    async def _find_similar_cases(
        self, case: CandidateCase, top_k: int = 5, min_score: float | None = None
    ) -> List[Dict[str, Any]]:
        """Multi-signal case similarity: weighted section vectors + struct cross-check.

        1. Search symptom / diagnosis / root_cause separately against stored vectors.
        2. Merge with weighted scores (0.1 / 0.5 / 0.4).
        3. Cross-validate structured dimensions (failure_layer, runtime, services).
        4. Classify relation type per candidate pair.
        """
        ctx = case.metadata.get("case_context", {}) if case.metadata else {}
        scope = {
            "app_code": ctx.get("app_code") or "default",
            "environment": ctx.get("environment") or "default",
        }
        min_score = self._MIN_SCORE if min_score is None else min_score

        # --- nothing to embed ------------------------------------------------
        sections = {
            "symptom": case.symptom_summary,
            "diagnosis": case.diagnosis,
            "root_cause": case.root_cause,
        }
        active = {k: v for k, v in sections.items() if v and str(v).strip()}
        if not active:
            return []

        # --- per-section parallel search ------------------------------------
        per_section: Dict[str, Dict[str, float]] = {}
        for section_name, text in active.items():
            results = await self._vector_index.search_with_scores(
                str(text), scope, self._TOP_K
            )
            per_section[section_name] = {
                cid: score
                for cid, score in results
                if cid != case.case_id and score >= self._SEC_MIN_SCORE
            }

        # --- weighted merge --------------------------------------------------
        weights = {
            "symptom": self._W_SYMPTOM,
            "diagnosis": self._W_DIAGNOSIS,
            "root_cause": self._W_ROOT_CAUSE,
        }
        merged: Dict[str, Dict[str, float]] = {}
        for section_name, hits in per_section.items():
            w = weights.get(section_name, 0.0)
            for cid, score in hits.items():
                if cid not in merged:
                    merged[cid] = {"symptom": 0.0, "diagnosis": 0.0, "root_cause": 0.0}
                merged[cid][section_name] = score * w

        # --- final scoring + relation classification -------------------------
        source_ctx = case.metadata.get("case_context", {}) if case.metadata else {}
        similar: List[Dict[str, Any]] = []
        for cid, section_scores in merged.items():
            weighted = sum(section_scores.values())
            if weighted < min_score:
                continue

            # fetch candidate context for struct cross-check
            candidate = self._dao.get_by_case_id(cid)
            candidate_ctx = (
                candidate.metadata.get("case_context", {})
                if candidate and candidate.metadata
                else {}
            )
            struct_match = cross_validate_relation(source_ctx, candidate_ctx)
            relation_type = self._classify_relation(
                score_symptom=section_scores.get("symptom", 0.0) / max(self._W_SYMPTOM, 0.01),
                score_diagnosis=section_scores.get("diagnosis", 0.0) / max(self._W_DIAGNOSIS, 0.01),
                score_root_cause=section_scores.get("root_cause", 0.0) / max(self._W_ROOT_CAUSE, 0.01),
                struct_match=struct_match,
            )
            similar.append({
                "case_id": cid,
                "score": round(weighted, 4),
                "relation": relation_type.value,
                "struct_match": struct_match,
            })

        similar.sort(key=lambda item: -item["score"])
        return similar[:top_k]

    # ---- lifecycle transition thresholds ----
    _LIFECYCLE_ACCEPT_CONFIDENCE = 0.8
    _LIFECYCLE_ACCEPT_FEEDBACK_COUNT = 2
    _LIFECYCLE_REJECT_CONFIDENCE = 0.2

    async def _feedback(self, args: Dict[str, Any]) -> Dict[str, Any]:
        case_id = args.get("case_id")
        if not case_id:
            raise MemoryPluginError("MISSING_CASE_ID", "case_id is required")
        case = self._dao.get_by_case_id(case_id)
        if not case:
            raise MemoryPluginError("CASE_NOT_FOUND", f"case not found: {case_id}")

        helpful = args.get("helpful")
        signal = args.get("signal")
        current_conv_id = args.get("conv_id") or args.get("scope", {}).get("conv_id", "")

        # ---- confidence delta (same as before) ----
        if helpful is True:
            case.confidence = min(1.0, case.confidence + 0.1)
        elif helpful is False:
            case.confidence = max(0.0, case.confidence - 0.2)

        if signal == "stale":
            case.confidence = max(0.0, case.confidence - 0.1)
        elif signal == "success":
            case.confidence = min(1.0, case.confidence + 0.05)
        elif signal == "rollback":
            case.confidence = max(0.0, case.confidence - 0.1)

        # ---- structured fb recording ----
        fb = self._ensure_fb_structure(case)
        is_cross_session = (
            bool(current_conv_id)
            and bool(case.source_conv_id)
            and current_conv_id != case.source_conv_id
        )

        if helpful is not None:
            fb = self._record_fb_event(
                fb, case, helpful, current_conv_id, is_cross_session
            )

        # ---- lifecycle transition (feedback-count gated) ----
        if signal == "stale":
            case.lifecycle = CandidateCaseLifecycle.STALE
        elif signal == "rollback" and case.confidence < self._LIFECYCLE_REJECT_CONFIDENCE:
            case.lifecycle = CandidateCaseLifecycle.REJECTED
        elif helpful is False and case.confidence < self._LIFECYCLE_REJECT_CONFIDENCE:
            case.lifecycle = CandidateCaseLifecycle.REJECTED
        elif helpful is True and case.lifecycle == CandidateCaseLifecycle.DRAFT:
            g = fb.get("global", {})
            fb_count = g.get("h", 0)
            cross_count = len(g.get("cv", []))
            if (
                case.confidence >= self._LIFECYCLE_ACCEPT_CONFIDENCE
                and fb_count >= self._LIFECYCLE_ACCEPT_FEEDBACK_COUNT
                and cross_count >= 1
            ):
                case.lifecycle = CandidateCaseLifecycle.ACCEPTED

        case.metadata[FB_KEY] = fb

        # ---- human-review flag (unchanged) ----
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
        self._track_feedback_hit(saved.source_conv_id, saved.case_id)
        return {"code": "OK", "case": saved.model_dump(mode="json")}

    @staticmethod
    def _ensure_fb_structure(case: CandidateCase) -> Dict[str, Any]:
        fb = case.metadata.get(FB_KEY)
        if not isinstance(fb, dict):
            fb = {}
        fb.setdefault("global", {"h": 0, "u": 0, "ts": "", "cv": []})
        fb.setdefault("by_app", {})
        fb.setdefault("by_app_env", {})
        return fb

    @staticmethod
    def _record_fb_event(
        fb: Dict[str, Any],
        case: CandidateCase,
        helpful: bool,
        conv_id: str,
        is_cross_session: bool,
    ) -> Dict[str, Any]:
        now_ts = datetime.now(UTC).isoformat()
        ctx = (case.metadata or {}).get("case_context", {}) or {}
        app = str(ctx.get(KEY_APP_CODE) or "default").strip().lower()
        env = str(ctx.get(KEY_ENVIRONMENT) or "default").strip().lower()

        # --- global ---
        g = fb["global"]
        if helpful:
            g["h"] = g.get("h", 0) + 1
        else:
            g["u"] = g.get("u", 0) + 1
        g["ts"] = now_ts
        if is_cross_session and conv_id not in (g.get("cv") or []):
            g.setdefault("cv", []).append(conv_id)

        # --- by_app ---
        by_app = fb.setdefault("by_app", {})
        app_entry = by_app.setdefault(app, {"h": 0, "u": 0, "ts": ""})
        if helpful:
            app_entry["h"] = app_entry.get("h", 0) + 1
        else:
            app_entry["u"] = app_entry.get("u", 0) + 1
        app_entry["ts"] = now_ts

        # --- by_app_env ---
        by_app_env = fb.setdefault("by_app_env", {})
        scope_key = f"{app}:{env}"
        env_entry = by_app_env.setdefault(scope_key, {"h": 0, "u": 0, "ts": ""})
        if helpful:
            env_entry["h"] = env_entry.get("h", 0) + 1
        else:
            env_entry["u"] = env_entry.get("u", 0) + 1
        env_entry["ts"] = now_ts

        return fb

    def _track_feedback_hit(
        self, conv_id: Optional[str], case_id: str
    ) -> None:
        if not conv_id:
            return
        if conv_id not in self._feedback_log:
            self._feedback_log[conv_id] = set()
        self._feedback_log[conv_id].add(case_id)

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
