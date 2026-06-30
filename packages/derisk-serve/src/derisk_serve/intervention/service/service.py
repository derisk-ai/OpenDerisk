"""Intervention service."""
import json
import logging
from datetime import datetime
from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    InterventionListFilter, InterventionRequest, InterventionResolveRequest,
    InterventionResponse,
)
from ..config import ServeConfig
from ..models.models import InterventionDao, InterventionEntity

INTERVENTION_SERVICE_COMPONENT_NAME = "serve_intervention_service"
logger = logging.getLogger(__name__)


class InterventionService(BaseService[InterventionEntity, InterventionRequest, InterventionResponse]):
    name = INTERVENTION_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[InterventionDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: InterventionDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or InterventionDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: InterventionRequest) -> InterventionResponse:
        response = self._dao.create(request)
        return response

    def resolve(
        self, intervention_id: int, request: InterventionResolveRequest,
    ) -> InterventionResponse:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(InterventionEntity).filter(
                InterventionEntity.id == intervention_id
            ).first()
            if not entity:
                raise ValueError(f"intervention {intervention_id} not found")
            if request.decision is not None:
                entity.decision_json = json.dumps(request.decision, ensure_ascii=False)
            if request.distillation is not None:
                entity.distillation_json = json.dumps(request.distillation, ensure_ascii=False)
            if request.linked_asset_id is not None:
                entity.linked_asset_id = request.linked_asset_id
            entity.resolved_by_user_id = request.resolved_by_user_id
            entity.resolved_at = datetime.now()
            entity.status = "resolved"
            session.commit()
            return self._dao.to_response(entity)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def abort(self, intervention_id: int) -> InterventionResponse:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(InterventionEntity).filter(
                InterventionEntity.id == intervention_id
            ).first()
            if not entity:
                raise ValueError(f"intervention {intervention_id} not found")
            entity.status = "aborted"
            session.commit()
            return self._dao.to_response(entity)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_interventions(self, f: InterventionListFilter) -> List[InterventionResponse]:
        return self._dao.list_by_filter(f)

    def get_by_id(self, intervention_id: int) -> Optional[InterventionResponse]:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(InterventionEntity).filter(
                InterventionEntity.id == intervention_id
            ).first()
            return self._dao.to_response(entity) if entity else None
        finally:
            session.close()

    def is_task_distill_completed(self, task_id: int) -> bool:
        """A task is distill-complete if all its interventions are resolved
        AND each resolved intervention has non-empty distillation_json.
        """
        session = self._dao.get_raw_session()
        try:
            rows = session.query(InterventionEntity).filter(
                InterventionEntity.task_id == task_id
            ).all()
            if not rows:
                return False
            for r in rows:
                if r.status != "resolved":
                    return False
                if not r.distillation_json:
                    return False
            return True
        finally:
            session.close()
