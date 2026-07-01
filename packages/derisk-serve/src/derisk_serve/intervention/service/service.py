"""Intervention service."""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

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

    def _is_approved(self, decision: Union[str, Dict[str, Any], None]) -> bool:
        """Resolve whether the decision payload means approval.

        Supports the plan's string form ("approved") as well as the actual
        schema form of ``InterventionResolveRequest.decision`` which is a dict.
        """
        if decision is None:
            return False
        if isinstance(decision, dict):
            return (
                decision.get("action") == "approved"
                or decision.get("approved") is True
            )
        return decision == "approved"

    def _load_question(self, entity) -> Dict[str, Any]:
        raw = entity.question_json
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except Exception as e:
            logger.warning(
                "failed to parse question_json for intervention %s: %s",
                entity.id,
                e,
            )
            return {}

    async def execute_resolved(
        self,
        intervention_id: int,
        decision: Union[str, Dict[str, Any], None],
        distillation: Optional[Dict[str, Any]],
        resolved_by_user_id: Optional[int],
    ) -> InterventionEntity:
        """Resolve an intervention and, if approved, execute its bound tool."""
        session = self._dao.get_raw_session()
        try:
            entity = (
                session.query(InterventionEntity)
                .filter(InterventionEntity.id == intervention_id)
                .first()
            )
            if not entity:
                raise ValueError(f"intervention {intervention_id} not found")

            approved = self._is_approved(decision)
            if not approved:
                entity.status = "rejected"
                entity.resolved_by_user_id = resolved_by_user_id
                entity.resolved_at = datetime.now()
                if decision is not None:
                    entity.decision_json = json.dumps(
                        decision, ensure_ascii=False
                    )
                if distillation is not None:
                    entity.distillation_json = json.dumps(
                        distillation, ensure_ascii=False
                    )
                session.commit()
                return entity

            question = self._load_question(entity)
            tool_name = question.get("tool")
            args = question.get("args", {}) or {}

            result = await self._route_and_execute(tool_name, args, entity)

            entity.status = "resolved"
            entity.resolved_by_user_id = resolved_by_user_id
            entity.resolved_at = datetime.now()
            if decision is not None:
                entity.decision_json = json.dumps(decision, ensure_ascii=False)
            if distillation is not None:
                entity.distillation_json = json.dumps(
                    distillation, ensure_ascii=False
                )
            session.commit()

            try:
                await self._post_message_back(
                    conv_uid=entity.conv_uid,
                    tool_name=tool_name,
                    result=result,
                    user_id=resolved_by_user_id,
                    workspace_id=entity.workspace_id,
                )
            except Exception:
                logger.exception("failed to post message back after execution")

            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def _route_and_execute(
        self, tool_name: str, args: dict, entity
    ) -> dict:
        if not tool_name:
            raise ValueError("tool name is required")

        system_app = self._system_app
        if tool_name == "start_task":
            from derisk_serve.task.service.service import (
                TASK_SERVICE_COMPONENT_NAME,
                TaskService,
            )
            from derisk_serve.task.api.schemas import TaskRequest

            svc = system_app.get_component(
                TASK_SERVICE_COMPONENT_NAME, TaskService
            )
            task = svc.create(TaskRequest(**args))
            return {"task_id": getattr(task, "id", None)}

        if tool_name == "close_task":
            from derisk_serve.task.service.service import (
                TASK_SERVICE_COMPONENT_NAME,
                TaskService,
            )

            svc = system_app.get_component(
                TASK_SERVICE_COMPONENT_NAME, TaskService
            )
            task_id = args["task_id"]
            svc.transition(task_id, "closed")
            return {"task_id": task_id, "status": "closed"}

        if tool_name == "publish_asset":
            from derisk_serve.workspace_asset.service.service import (
                ASSET_SERVICE_COMPONENT_NAME,
                AssetService,
            )
            from derisk_serve.workspace_asset.api.schemas import AssetRequest

            svc = system_app.get_component(
                ASSET_SERVICE_COMPONENT_NAME, AssetService
            )
            asset = svc.create(AssetRequest(**{**args, "is_published": True}))
            return {"asset_id": getattr(asset, "id", None)}

        if tool_name == "create_delivery":
            from derisk_serve.delivery.service.service import (
                DELIVERY_SERVICE_COMPONENT_NAME,
                DeliveryService,
            )
            from derisk_serve.delivery.api.schemas import DeliveryRequest

            svc = system_app.get_component(
                DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService
            )
            delivery = svc.create(DeliveryRequest(**args))
            return {"delivery_id": getattr(delivery, "id", None)}

        if tool_name == "update_workspace":
            from derisk_serve.workspace.service.service import (
                WORKSPACE_SERVICE_COMPONENT_NAME,
                WorkspaceService,
            )
            from derisk_serve.workspace.api.schemas import WorkspaceRequest

            svc = system_app.get_component(
                WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService
            )
            ws = svc.update(WorkspaceRequest(**args))
            return {"workspace_id": getattr(ws, "id", None)}

        if tool_name == "launch_playbook":
            from derisk_serve.playbook.runtime import run_task

            result = await run_task(system_app, **args)
            return result

        if tool_name == "update_playbook":
            from derisk_serve.playbook.service.service import (
                PLAYBOOK_SERVICE_COMPONENT_NAME,
                PlaybookService,
            )
            from derisk_serve.playbook.api.schemas import PlaybookRequest

            svc = system_app.get_component(
                PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
            )
            pb = svc.update(PlaybookRequest(**args))
            return {"playbook_id": getattr(pb, "id", None)}

        if tool_name == "archive_playbook":
            from derisk_serve.playbook.service.service import (
                PLAYBOOK_SERVICE_COMPONENT_NAME,
                PlaybookService,
            )
            from derisk_serve.playbook.models.models import PlaybookEntity

            svc = system_app.get_component(
                PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
            )
            playbook_id = args["playbook_id"]
            pb_session = svc.dao.get_raw_session()
            try:
                pb = (
                    pb_session.query(PlaybookEntity)
                    .filter(PlaybookEntity.id == playbook_id)
                    .first()
                )
                if not pb:
                    raise ValueError(f"playbook {playbook_id} not found")
                pb.is_active = False
                pb_session.commit()
                return {"playbook_id": playbook_id, "archived": True}
            except Exception:
                pb_session.rollback()
                raise
            finally:
                pb_session.close()

        raise ValueError(f"Unknown tool: {tool_name}")

    def _resolve_gpts_name(self, workspace_id: Optional[int]) -> str:
        """Return the workspace's default agent app code, or fall back.

        Falls back to ``chat_normal`` when the workspace is missing or has no
        configured default agent.
        """
        if not workspace_id:
            return "chat_normal"
        try:
            from derisk_serve.workspace.service.service import (
                WORKSPACE_SERVICE_COMPONENT_NAME,
                WorkspaceService,
            )

            workspace_service = self._system_app.get_component(
                WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService
            )
            workspace = workspace_service.get_by_id(workspace_id)
            if workspace and workspace.default_agent_app_code:
                return workspace.default_agent_app_code
        except Exception:
            logger.warning(
                "failed to resolve default_agent_app_code for workspace %s",
                workspace_id,
                exc_info=True,
            )
        logger.warning(
            "workspace %s has no default_agent_app_code, falling back to chat_normal",
            workspace_id,
        )
        return "chat_normal"

    async def _post_message_back(
        self,
        conv_uid: Optional[str],
        tool_name: str,
        result: dict,
        user_id: Optional[int],
        workspace_id: Optional[int] = None,
    ):
        if not conv_uid:
            return
        try:
            from derisk_serve.agent.agents.controller import multi_agents

            gpts_name = self._resolve_gpts_name(workspace_id)
            synthetic_query = f"[已确认执行工具 {tool_name}] 结果：{result}"
            async for _ in multi_agents.app_chat(
                conv_uid=conv_uid,
                gpts_name=gpts_name,
                user_query=synthetic_query,
                user_code=str(user_id) if user_id is not None else None,
            ):
                pass
        except Exception:
            logger.exception("failed to post message back")
