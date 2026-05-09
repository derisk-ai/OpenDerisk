"""Case routing and descriptive context stored only in ``metadata_json``.

**Table model:** ``derisk_plugin_memory_case`` has **no** ``app_code`` / ``environment``
columns. Those values exist only under
``metadata["case_context"]`` (JSON inside ``metadata_json``).

**Search narrowing (``memory_case_search``):**
- Optional ``scope`` keys ``app_code``, ``environment`` filter
  via ``JSON_EXTRACT(metadata_json, '$.case_context.*')`` only.
- For ``app_code`` / ``environment``: value missing, empty, or literal ``default`` → **no**
  filter on that key (wildcard). Non-default → equality on stored ``case_context``.

**Lexical ``query``:** FULLTEXT / LIKE over ``FULLTEXT_LEXICAL_COLUMNS`` (must match DB index).

See ``MemoryCaseDao.search`` and ``MemoryCasePluginService._search`` for implementation.
"""

from __future__ import annotations

from typing import Any, Dict, Final, Optional, Tuple

CASE_CONTEXT_KEY = "case_context"

# InnoDB FULLTEXT + LIKE fallback columns (must match ``assets/schema/derisk.sql``).
FULLTEXT_LEXICAL_COLUMNS: Final[Tuple[str, ...]] = (
    "symptom_summary",
    "markdown_summary",
    "resolution",
    "handling_path",
    "root_cause",
    "incident_title",
    "hypotheses",
    "actions",
)

# Routing hints (optional; defaults align with tool_pack / MemoryRequestContext)
KEY_APP_CODE = "app_code"
KEY_ENVIRONMENT = "environment"
# Descriptive / operational context (extend as needed)
KEY_APPLICATION_NAME = "application_name"
KEY_REGION = "region"
KEY_DATA_SOURCES = "data_sources"
KEY_TELEMETRY_CHANNELS = "telemetry_channels"
KEY_RELATED_SERVICES = "related_services"
KEY_TAGS = "tags"
KEY_OPERATOR_NOTES = "operator_notes"


def case_context_from_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not metadata:
        return {}
    raw = metadata.get(CASE_CONTEXT_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def merge_case_context(
    metadata: Optional[Dict[str, Any]], patch: Dict[str, Any]
) -> Dict[str, Any]:
    """Return a copy of metadata with ``case_context`` shallow-merged with ``patch``."""
    meta = dict(metadata or {})
    cur = case_context_from_metadata(meta)
    for k, v in patch.items():
        if v is not None:
            cur[k] = v
    if cur:
        meta[CASE_CONTEXT_KEY] = cur
    return meta


def scope_filters_match(metadata: Optional[Dict[str, Any]], scope: Dict[str, Any]) -> bool:
    """Whether stored metadata matches search scope (in-process / tests)."""
    ctx = case_context_from_metadata(metadata)
    wild_app = is_memory_search_scope_app_wildcard(scope)
    wild_env = is_memory_search_scope_env_wildcard(scope)
    if not wild_app:
        want_app = str(scope.get(KEY_APP_CODE) or "default").strip().lower()
        got_app = str(ctx.get(KEY_APP_CODE) or "default").strip().lower()
        if got_app != want_app:
            return False
    if not wild_env:
        want_env = str(scope.get(KEY_ENVIRONMENT) or "default").strip().lower()
        got_env = str(ctx.get(KEY_ENVIRONMENT) or "default").strip().lower()
        if got_env != want_env:
            return False
    return True


def is_memory_search_scope_app_wildcard(scope: Optional[Dict[str, Any]]) -> bool:
    """True → DB / vector search does not filter by ``case_context.app_code``.

    Omitted or ``default`` matches any stored app_code (recall-first for ad-hoc agents).
    Pass an explicit non-default ``scope.app_code`` to narrow.
    """
    if not scope:
        return True
    v = scope.get(KEY_APP_CODE)
    if v is None:
        return True
    s = str(v).strip().lower()
    return s == "" or s == "default"


def is_memory_search_scope_env_wildcard(scope: Optional[Dict[str, Any]]) -> bool:
    """True → DB / vector search does not filter by ``case_context.environment``.

    Omitted or ``default`` matches any stored environment (cases often use ``oversea``,
    ``mc-cn-shared``, etc., while the runtime injects ``environment: default``).
    """
    if not scope:
        return True
    v = scope.get(KEY_ENVIRONMENT)
    if v is None:
        return True
    s = str(v).strip().lower()
    return s == "" or s == "default"


def vector_metadata_from_case(case_id: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Flatten ``case_context`` for Chroma metadata filters."""
    ctx = case_context_from_metadata(metadata)
    return {
        "case_id": case_id,
        KEY_APP_CODE: ctx.get(KEY_APP_CODE) or "default",
        KEY_ENVIRONMENT: ctx.get(KEY_ENVIRONMENT) or "default",
    }
