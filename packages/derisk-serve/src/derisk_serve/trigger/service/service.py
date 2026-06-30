"""Trigger service — creates a Task from a fired trigger source.

MVP: timer/webhook/alert/manual all funnel through `fire()` which creates
a Task in `pending_trigger` status pointing at the target playbook.
The CronService wiring is left as an integration point — the timer
trigger's `config.cron` is stored but actual scheduling is the
responsibility of the caller (MVP relies on manual fire + external cron).
"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    TriggerFireRequest, TriggerListFilter, TriggerSourceRequest,
    TriggerSourceResponse,
)
from ..config import ServeConfig
from ..models.models import TriggerSourceDao, TriggerSourceEntity

TRIGGER_SERVICE_COMPONENT_NAME = "serve_trigger_service"
logger = logging.getLogger(__name__)


class TriggerService(BaseService[TriggerSourceEntity, TriggerSourceRequest, TriggerSourceResponse]):
    name = TRIGGER_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[TriggerSourceDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: TriggerSourceDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or TriggerSourceDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: TriggerSourceRequest) -> TriggerSourceResponse:
        return self._dao.create(request)

    def update(self, request: TriggerSourceRequest) -> TriggerSourceResponse:
        if not request.id:
            raise ValueError("trigger id required for update")
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == request.id
            ).first()
            if not entity:
                raise ValueError(f"trigger {request.id} not found")
            entity.name = request.name
            entity.type = request.type
            entity.target_playbook_id = request.target_playbook_id
            entity.config_json = json.dumps(request.config or {}, ensure_ascii=False)
            entity.is_active = request.is_active
            session.commit()
            return self._dao.to_response(entity)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, trigger_id: int) -> bool:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == trigger_id
            ).first()
            if not entity:
                return False
            session.delete(entity)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_triggers(self, f: TriggerListFilter) -> List[TriggerSourceResponse]:
        return self._dao.list_by_filter(f)

    def get_by_id(self, trigger_id: int) -> Optional[TriggerSourceResponse]:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == trigger_id
            ).first()
            return self._dao.to_response(entity) if entity else None
        finally:
            session.close()

    def fire(self, request: TriggerFireRequest) -> dict:
        """Fire the trigger — create a Task in pending_trigger status.

        MVP: this creates the Task through the task serve's API by direct
        component lookup. Returns the created task id.
        """
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == request.trigger_id,
                TriggerSourceEntity.workspace_id == request.workspace_id,
            ).first()
            if not entity:
                raise ValueError(f"trigger {request.trigger_id} not found in workspace {request.workspace_id}")
            entity.last_fired_at = datetime.now()
            session.commit()

            # Create the Task through task service component
            from derisk_serve.task.service.service import (
                TASK_SERVICE_COMPONENT_NAME, TaskService,
            )
            from derisk_serve.task.api.schemas import TaskRequest

            task_service: TaskService = self._system_app.get_component(
                TASK_SERVICE_COMPONENT_NAME, TaskService,
            )
            task_req = TaskRequest(
                workspace_id=entity.workspace_id,
                type="routine" if entity.type == "timer" else (
                    "incident" if entity.type == "alert" else "adhoc"
                ),
                title=f"Triggered by {entity.name}",
                description=f"Triggered via {entity.type} (trigger_id={entity.id})",
                status="pending_trigger",
                triggered_by=entity.type,
                trigger_ref=str(entity.id),
                playbook_id=entity.target_playbook_id,
                context={
                    "trigger_payload": request.payload or {},
                    "trigger_config": json.loads(entity.config_json) if entity.config_json else {},
                },
            )
            task = task_service.create(task_req)
            return {"task_id": task.id, "trigger_id": entity.id}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
