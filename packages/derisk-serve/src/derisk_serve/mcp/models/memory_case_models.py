import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Float, String, Text

from derisk.storage.metadata import BaseDao, Model
from derisk_serve.mcp.memory_case.models import CandidateCase, CandidateCaseLifecycle


class MemoryCaseEntity(Model):
    __tablename__ = "derisk_serve_mcp_memory_case"

    case_id = Column(String(255), primary_key=True, nullable=False)
    tenant_id = Column(String(255), nullable=True)
    team_id = Column(String(255), nullable=True)
    app_code = Column(String(255), nullable=False)
    environment = Column(String(255), nullable=False)
    fingerprint = Column(String(512), nullable=False)
    symptom_summary = Column(Text, nullable=True)
    hypotheses = Column(Text, nullable=True)
    actions = Column(Text, nullable=True)
    resolution = Column(Text, nullable=True)
    effectiveness = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    lifecycle = Column(String(64), nullable=False, default=CandidateCaseLifecycle.DRAFT.value)
    source_conv_id = Column(String(255), nullable=True)
    source_session_id = Column(String(255), nullable=True)
    markdown_summary = Column(Text(length=2**31 - 1), nullable=True)
    metadata_json = Column(Text(length=2**31 - 1), nullable=True)
    gmt_created = Column(DateTime, default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MemoryCaseDao(BaseDao):
    def to_model(self, entity: MemoryCaseEntity) -> CandidateCase:
        return CandidateCase(
            case_id=entity.case_id,
            tenant_id=entity.tenant_id,
            team_id=entity.team_id,
            app_code=entity.app_code,
            environment=entity.environment,
            fingerprint=entity.fingerprint,
            symptom_summary=entity.symptom_summary or "",
            hypotheses=json.loads(entity.hypotheses) if entity.hypotheses else [],
            actions=json.loads(entity.actions) if entity.actions else [],
            resolution=entity.resolution or "",
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
            entity.tenant_id = case.tenant_id
            entity.team_id = case.team_id
            entity.app_code = case.app_code
            entity.environment = case.environment
            entity.fingerprint = case.fingerprint
            entity.symptom_summary = case.symptom_summary
            entity.hypotheses = json.dumps(case.hypotheses, ensure_ascii=False)
            entity.actions = json.dumps(case.actions, ensure_ascii=False)
            entity.resolution = case.resolution
            entity.effectiveness = case.effectiveness
            entity.confidence = case.confidence
            entity.lifecycle = case.lifecycle.value
            entity.source_conv_id = case.source_conv_id
            entity.source_session_id = case.source_session_id
            entity.markdown_summary = case.markdown_summary
            entity.metadata_json = json.dumps(case.metadata or {}, ensure_ascii=False)
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
            if scope.get("tenant_id"):
                q = q.filter(MemoryCaseEntity.tenant_id == scope["tenant_id"])
            if scope.get("team_id"):
                q = q.filter(MemoryCaseEntity.team_id == scope["team_id"])
            q = q.filter(MemoryCaseEntity.app_code == scope["app_code"])
            q = q.filter(MemoryCaseEntity.environment == scope["environment"])
            if query_text:
                like = f"%{query_text}%"
                q = q.filter(
                    (MemoryCaseEntity.fingerprint.like(like))
                    | (MemoryCaseEntity.symptom_summary.like(like))
                    | (MemoryCaseEntity.markdown_summary.like(like))
                )
            entities = (
                q.order_by(MemoryCaseEntity.confidence.desc(), MemoryCaseEntity.gmt_modified.desc())
                .limit(limit)
                .all()
            )
            return [self.to_model(entity) for entity in entities]
        finally:
            session.close()

