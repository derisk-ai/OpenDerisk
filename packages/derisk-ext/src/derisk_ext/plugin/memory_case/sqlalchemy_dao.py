"""SQLAlchemy persistence for plugin case memory (table ``derisk_plugin_memory_case``)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Float, String, Text, func, or_, text
from sqlalchemy.exc import OperationalError

from derisk.storage.metadata import BaseDao, Model

from .case_context import (
    CASE_CONTEXT_KEY,
    FULLTEXT_LEXICAL_COLUMNS,
    is_memory_search_scope_app_wildcard,
    is_memory_search_scope_env_wildcard,
    scope_filters_match,
)
from .models import CandidateCase, CandidateCaseLifecycle

logger = logging.getLogger(__name__)


class MemoryCaseEntity(Model):
    __tablename__ = "derisk_plugin_memory_case"

    case_id = Column(String(255), primary_key=True, nullable=False)
    fingerprint = Column(String(512), nullable=False)
    incident_title = Column(String(512), nullable=True)
    symptom_summary = Column(Text, nullable=True)
    hypotheses = Column(Text, nullable=True)
    actions = Column(Text, nullable=True)
    resolution = Column(Text, nullable=True)
    handling_path = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    effectiveness = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    lifecycle = Column(String(64), nullable=False, default=CandidateCaseLifecycle.DRAFT.value)
    source_conv_id = Column(String(255), nullable=True)
    source_session_id = Column(String(255), nullable=True)
    markdown_summary = Column(Text(length=2**31 - 1), nullable=True)
    metadata_json = Column(Text(length=2**31 - 1), nullable=True)
    gmt_created = Column(DateTime, default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


def _is_mysql_fulltext_index_mismatch(exc: BaseException) -> bool:
    """MySQL 1191: MATCH column list has no matching FULLTEXT index."""
    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "args", None):
        code = orig.args[0]
        if code == 1191:
            return True
    msg = str(exc).lower()
    return "1191" in msg or ("fulltext" in msg and "matching" in msg)


def _memory_case_like_clause(like: str):
    """Substring fallback when not using MySQL InnoDB FULLTEXT."""
    parts = [MemoryCaseEntity.fingerprint.like(like)]
    for name in FULLTEXT_LEXICAL_COLUMNS:
        col = getattr(MemoryCaseEntity, name, None)
        if col is not None:
            parts.append(col.like(like))
    return or_(*parts)


def _mysql_match_against_clause():
    cols_sql = ", ".join(FULLTEXT_LEXICAL_COLUMNS)
    return text(f"MATCH ({cols_sql}) AGAINST (:__memory_ft IN NATURAL LANGUAGE MODE)")


def _apply_scope_sql_filters(q, scope: Dict[str, Any], dialect: str):
    app = scope.get("app_code") or "default"
    env = scope.get("environment") or "default"
    wild_app = is_memory_search_scope_app_wildcard(scope)
    wild_env = is_memory_search_scope_env_wildcard(scope)
    m = MemoryCaseEntity.metadata_json
    if dialect == "mysql":
        if not wild_app:
            q = q.filter(
                text(
                    "LOWER(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(COALESCE(metadata_json, '{}'), "
                    "'$.case_context.app_code')),'default')) = LOWER(:__mem_app)"
                ).bindparams(__mem_app=app),
            )
        if not wild_env:
            q = q.filter(
                text(
                    "LOWER(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(COALESCE(metadata_json, '{}'), "
                    "'$.case_context.environment')),'default')) = LOWER(:__mem_env)"
                ).bindparams(__mem_env=env),
            )
        if scope.get("tenant_id"):
            q = q.filter(
                text(
                    "JSON_UNQUOTE(JSON_EXTRACT(COALESCE(metadata_json, '{}'), "
                    "'$.case_context.tenant_id')) = :__mem_tenant"
                ).bindparams(__mem_tenant=scope["tenant_id"])
            )
        if scope.get("team_id"):
            q = q.filter(
                text(
                    "JSON_UNQUOTE(JSON_EXTRACT(COALESCE(metadata_json, '{}'), "
                    "'$.case_context.team_id')) = :__mem_team"
                ).bindparams(__mem_team=scope["team_id"])
            )
        return q, False
    if dialect == "sqlite":
        if not wild_app:
            q = q.filter(
                func.lower(
                    func.coalesce(func.json_extract(m, "$.case_context.app_code"), "default")
                )
                == str(app).lower(),
            )
        if not wild_env:
            q = q.filter(
                func.lower(
                    func.coalesce(func.json_extract(m, "$.case_context.environment"), "default")
                )
                == str(env).lower(),
            )
        if scope.get("tenant_id"):
            q = q.filter(
                func.coalesce(func.json_extract(m, "$.case_context.tenant_id"), "")
                == str(scope["tenant_id"])
            )
        if scope.get("team_id"):
            q = q.filter(
                func.coalesce(func.json_extract(m, "$.case_context.team_id"), "")
                == str(scope["team_id"])
            )
        return q, False
    logger.warning(
        "memory_case DAO: dialect %r has no JSON scope SQL; applying in-Python filter",
        dialect,
    )
    return q, True


class MemoryCaseDao(BaseDao):
    """Persistence for ``derisk_plugin_memory_case`` — routing lives in ``metadata_json`` only."""

    def to_model(self, entity: MemoryCaseEntity) -> CandidateCase:
        hp = entity.handling_path or ""
        if hp.strip().startswith(("[", "{")):
            try:
                raw = json.loads(hp)
                if isinstance(raw, list):
                    hp = "\n".join(
                        json.dumps(x, ensure_ascii=False)
                        if isinstance(x, dict)
                        else str(x)
                        for x in raw
                    )
                elif isinstance(raw, dict):
                    hp = json.dumps(raw, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass
        return CandidateCase(
            case_id=entity.case_id,
            fingerprint=entity.fingerprint,
            incident_title=entity.incident_title or "",
            symptom_summary=entity.symptom_summary or "",
            hypotheses=json.loads(entity.hypotheses) if entity.hypotheses else [],
            actions=json.loads(entity.actions) if entity.actions else [],
            resolution=entity.resolution or "",
            handling_path=hp,
            root_cause=entity.root_cause or "",
            effectiveness=entity.effectiveness or "",
            confidence=entity.confidence or 0.5,
            lifecycle=CandidateCaseLifecycle(entity.lifecycle),
            source_conv_id=entity.source_conv_id,
            source_session_id=entity.source_session_id,
            markdown_summary=entity.markdown_summary or "",
            metadata=json.loads(entity.metadata_json) if entity.metadata_json else {},
            created_at=entity.gmt_created,
            updated_at=entity.gmt_modified,
        )

    def upsert(self, case: CandidateCase) -> CandidateCase:
        session = self.get_raw_session()
        try:
            entity = (
                session.query(MemoryCaseEntity)
                .filter(MemoryCaseEntity.case_id == case.case_id)
                .one_or_none()
            )
            if entity is None:
                entity = MemoryCaseEntity(case_id=case.case_id)
                session.add(entity)
                entity.fingerprint = case.fingerprint
                entity.incident_title = case.incident_title or None
                entity.symptom_summary = case.symptom_summary
                entity.hypotheses = json.dumps(case.hypotheses, ensure_ascii=False)
                entity.actions = json.dumps(case.actions, ensure_ascii=False)
                entity.resolution = case.resolution
                entity.handling_path = case.handling_path or None
                entity.root_cause = case.root_cause or None
                entity.effectiveness = case.effectiveness
                entity.confidence = case.confidence
                entity.lifecycle = case.lifecycle.value
                entity.source_conv_id = case.source_conv_id
                entity.source_session_id = case.source_session_id
                entity.markdown_summary = case.markdown_summary
                entity.metadata_json = json.dumps(case.metadata or {}, ensure_ascii=False)
            else:
                entity.fingerprint = case.fingerprint
                if case.incident_title:
                    entity.incident_title = case.incident_title
                if case.symptom_summary:
                    entity.symptom_summary = case.symptom_summary
                if case.hypotheses:
                    entity.hypotheses = json.dumps(case.hypotheses, ensure_ascii=False)
                if case.actions:
                    entity.actions = json.dumps(case.actions, ensure_ascii=False)
                if case.resolution:
                    entity.resolution = case.resolution
                if case.handling_path:
                    entity.handling_path = case.handling_path
                if case.root_cause:
                    entity.root_cause = case.root_cause
                if case.effectiveness:
                    entity.effectiveness = case.effectiveness
                if case.markdown_summary:
                    entity.markdown_summary = case.markdown_summary
                entity.confidence = case.confidence
                entity.lifecycle = case.lifecycle.value
                entity.source_conv_id = case.source_conv_id
                entity.source_session_id = case.source_session_id
                existing_meta = json.loads(entity.metadata_json) if entity.metadata_json else {}
                for k, v in (case.metadata or {}).items():
                    if k == CASE_CONTEXT_KEY and isinstance(v, dict) and isinstance(existing_meta.get(k), dict):
                        existing_meta[k].update(v)
                    else:
                        existing_meta[k] = v
                entity.metadata_json = json.dumps(existing_meta, ensure_ascii=False)
            session.commit()
            session.refresh(entity)
            return self.to_model(entity)
        finally:
            session.close()

    def get_by_case_id(self, case_id: str) -> Optional[CandidateCase]:
        session = self.get_raw_session()
        try:
            entity = (
                session.query(MemoryCaseEntity)
                .filter(MemoryCaseEntity.case_id == case_id)
                .one_or_none()
            )
            return self.to_model(entity) if entity else None
        finally:
            session.close()

    def search(
        self,
        scope: Dict[str, Any],
        query_text: Optional[str] = None,
        limit: int = 10,
    ) -> List[CandidateCase]:
        session = self.get_raw_session()
        try:
            q = session.query(MemoryCaseEntity)
            bind = session.get_bind()
            dialect = bind.dialect.name if bind is not None else ""
            q, post_filter = _apply_scope_sql_filters(q, scope, dialect)
            if query_text:
                if dialect == "mysql":
                    q = q.filter(_mysql_match_against_clause().bindparams(__memory_ft=query_text))
                else:
                    like = f"%{query_text}%"
                    q = q.filter(_memory_case_like_clause(like))
            fetch_limit = limit * 50 if post_filter else limit
            stmt = q.order_by(
                MemoryCaseEntity.confidence.desc(), MemoryCaseEntity.gmt_modified.desc()
            ).limit(fetch_limit)
            try:
                entities = stmt.all()
            except OperationalError as exc:
                if (
                    dialect == "mysql"
                    and query_text
                    and _is_mysql_fulltext_index_mismatch(exc)
                ):
                    logger.warning(
                        "memory_case search: FULLTEXT unavailable (1191), using LIKE fallback"
                    )
                    q_fb, post_filter = _apply_scope_sql_filters(
                        session.query(MemoryCaseEntity), scope, dialect
                    )
                    like = f"%{query_text}%"
                    entities = (
                        q_fb.filter(_memory_case_like_clause(like))
                        .order_by(
                            MemoryCaseEntity.confidence.desc(),
                            MemoryCaseEntity.gmt_modified.desc(),
                        )
                        .limit(fetch_limit)
                        .all()
                    )
                else:
                    raise
            if post_filter:
                out: List[CandidateCase] = []
                for entity in entities:
                    md = json.loads(entity.metadata_json or "{}")
                    if scope_filters_match(md, scope):
                        out.append(self.to_model(entity))
                    if len(out) >= limit:
                        break
                return out
            return [self.to_model(entity) for entity in entities]
        finally:
            session.close()
