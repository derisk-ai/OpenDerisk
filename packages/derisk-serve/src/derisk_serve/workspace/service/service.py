"""Workspace service: business logic + member / resource management."""
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    WorkspaceListFilter,
    WorkspaceMemberRequest,
    WorkspaceMemberResponse,
    WorkspaceRequest,
    WorkspaceResourceRequest,
    WorkspaceResourceResponse,
    WorkspaceResponse,
)
from ..config import ServeConfig
from ..models.models import (
    WorkspaceConversationLinkDao,
    WorkspaceConversationLinkEntity,
    WorkspaceDao,
    WorkspaceEntity,
    WorkspaceMemberDao,
    WorkspaceMemberEntity,
    WorkspaceResourceDao,
    WorkspaceResourceEntity,
)

WORKSPACE_SERVICE_COMPONENT_NAME = "serve_workspace_service"

logger = logging.getLogger(__name__)


class WorkspaceService(BaseService[WorkspaceEntity, WorkspaceRequest, WorkspaceResponse]):
    """Workspace CRUD + member/resource orchestration"""

    name = WORKSPACE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[WorkspaceDao] = None,
        member_dao: Optional[WorkspaceMemberDao] = None,
        resource_dao: Optional[WorkspaceResourceDao] = None,
        conv_link_dao: Optional[WorkspaceConversationLinkDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: WorkspaceDao = dao
        self._member_dao: WorkspaceMemberDao = member_dao
        self._resource_dao: WorkspaceResourceDao = resource_dao
        self._conv_link_dao: WorkspaceConversationLinkDao = conv_link_dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or WorkspaceDao()
        self._member_dao = self._member_dao or WorkspaceMemberDao()
        self._resource_dao = self._resource_dao or WorkspaceResourceDao()
        self._conv_link_dao = self._conv_link_dao or WorkspaceConversationLinkDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def member_dao(self) -> WorkspaceMemberDao:
        return self._member_dao

    @property
    def resource_dao(self) -> WorkspaceResourceDao:
        return self._resource_dao

    @property
    def conv_link_dao(self) -> WorkspaceConversationLinkDao:
        return self._conv_link_dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    # ---------------- Workspace CRUD ----------------
    def create(self, request: WorkspaceRequest) -> WorkspaceResponse:
        if not request.workspace_code:
            request.workspace_code = f"ws_{uuid.uuid4().hex[:12]}"
        existing = self._dao.get_one({"workspace_code": request.workspace_code})
        if existing:
            raise ValueError(f"workspace_code '{request.workspace_code}' already exists")
        if request.owner_user_id is None:
            raise ValueError("owner_user_id is required")

        response = self._dao.create(request)
        # auto add owner as a member with role=owner
        owner_request = WorkspaceMemberRequest(
            workspace_id=response.id,
            user_id=response.owner_user_id,
            role="owner",
        )
        try:
            self._member_dao.create(owner_request)
        except Exception as e:
            logger.warning(f"auto add owner member failed: {e}")
        return self.get_by_id(response.id)  # reload to get member_count

    def update(self, request: WorkspaceRequest) -> WorkspaceResponse:
        if not request.workspace_code:
            raise ValueError("workspace_code is required for update")
        existing = self._dao.get_one({"workspace_code": request.workspace_code})
        if not existing:
            raise ValueError(f"workspace '{request.workspace_code}' not found")
        update_dict: Dict[str, Any] = {}
        for k in ["name", "description", "type", "scenario_type",
                  "default_agent_app_code", "is_archived"]:
            v = getattr(request, k, None)
            if v is not None:
                update_dict[k] = v
        if request.settings is not None:
            update_dict["settings_json"] = json.dumps(
                request.settings, ensure_ascii=False
            )
        self._dao.update(
            {"workspace_code": request.workspace_code}, update_dict, force_update=True
        )
        return self.get_by_id(existing.id)

    def archive(self, workspace_code: str) -> WorkspaceResponse:
        existing = self._dao.get_one({"workspace_code": workspace_code})
        if not existing:
            raise ValueError(f"workspace '{workspace_code}' not found")
        self._dao.update(
            {"workspace_code": workspace_code},
            {"is_archived": True},
            force_update=True,
        )
        return self.get_by_id(existing.id)

    def get_by_code(self, workspace_code: str) -> Optional[WorkspaceResponse]:
        entity = self._dao.get_raw_session().query(WorkspaceEntity).filter(
            WorkspaceEntity.workspace_code == workspace_code
        ).first()
        if not entity:
            return None
        return self._dao.to_response(
            entity, member_count=self._member_dao.count_by_workspace(entity.id)
        )

    def get_by_id(self, workspace_id: int) -> Optional[WorkspaceResponse]:
        entity = self._dao.get_raw_session().query(WorkspaceEntity).filter(
            WorkspaceEntity.id == workspace_id
        ).first()
        if not entity:
            return None
        return self._dao.to_response(
            entity, member_count=self._member_dao.count_by_workspace(entity.id)
        )

    def list_workspaces(
        self, user_id: Optional[int], scenario_type: Optional[str] = None,
        include_archived: bool = False,
    ) -> List[WorkspaceResponse]:
        return self._dao.filter_list(
            WorkspaceListFilter(
                user_id=user_id,
                scenario_type=scenario_type,
                include_archived=include_archived,
            )
        )

    # ---------------- Member management ----------------
    def list_members(self, workspace_id: int) -> List[WorkspaceMemberResponse]:
        entities = self._member_dao.list_by_workspace(workspace_id)
        return [self._member_dao.to_response(e) for e in entities]

    def add_member(self, request: WorkspaceMemberRequest) -> WorkspaceMemberResponse:
        entities = self._member_dao.list_by_workspace(request.workspace_id)
        existing = next((e for e in entities if e.user_id == request.user_id), None)
        if existing:
            self._member_dao.update(
                {"workspace_id": request.workspace_id, "user_id": request.user_id},
                {"role": request.role},
                force_update=True,
            )
            refreshed = next(
                (
                    e for e in self._member_dao.list_by_workspace(request.workspace_id)
                    if e.user_id == request.user_id
                ),
                None,
            )
            return self._member_dao.to_response(refreshed) if refreshed else None
        return self._member_dao.create(request)

    def remove_member(self, workspace_id: int, user_id: int) -> bool:
        entities = self._member_dao.list_by_workspace(workspace_id)
        target = next((e for e in entities if e.user_id == user_id), None)
        if not target:
            return False
        if target.role == "owner":
            raise ValueError("cannot remove owner; transfer ownership first")
        self._member_dao.delete({"workspace_id": workspace_id, "user_id": user_id})
        return True

    def update_member_role(
        self, workspace_id: int, user_id: int, role: str
    ) -> WorkspaceMemberResponse:
        entities = self._member_dao.list_by_workspace(workspace_id)
        target = next((e for e in entities if e.user_id == user_id), None)
        if not target:
            raise ValueError("member not found")
        self._member_dao.update(
            {"workspace_id": workspace_id, "user_id": user_id},
            {"role": role},
            force_update=True,
        )
        refreshed = next(
            (e for e in self._member_dao.list_by_workspace(workspace_id) if e.user_id == user_id),
            None,
        )
        return self._member_dao.to_response(refreshed) if refreshed else None

    def check_membership(self, workspace_id: int, user_id: int) -> Optional[str]:
        return self._member_dao.get_role(workspace_id, user_id)

    # ---------------- Resource management ----------------
    def list_resources(
        self, workspace_id: int, type_filter: Optional[str] = None
    ) -> List[WorkspaceResourceResponse]:
        entities = self._resource_dao.list_by_workspace(workspace_id, type_filter)
        return [self._resource_dao.to_response(e) for e in entities]

    def add_resource(self, request: WorkspaceResourceRequest) -> WorkspaceResourceResponse:
        return self._resource_dao.create(request)

    def remove_resource(self, resource_id: int) -> bool:
        entity = self._resource_dao.get_raw_session().query(
            WorkspaceResourceEntity
        ).filter(WorkspaceResourceEntity.id == resource_id).first()
        if not entity:
            return False
        with self._resource_dao.session() as session:
            row = session.query(WorkspaceResourceEntity).filter(
                WorkspaceResourceEntity.id == resource_id
            ).first()
            if row:
                session.delete(row)
        return True

    def update_resource(
        self, resource_id: int, request: WorkspaceResourceRequest
    ) -> WorkspaceResourceResponse:
        update_dict = {
            "type": request.type,
            "name": request.name,
            "category": request.category,
            "physical_ref": request.physical_ref,
            "config_json": json.dumps(request.config or {}, ensure_ascii=False),
            "access_mode": request.access_mode,
            "is_active": request.is_active,
        }
        self._resource_dao.update({"id": resource_id}, update_dict, force_update=True)
        entity = self._resource_dao.get_raw_session().query(
            WorkspaceResourceEntity
        ).filter(WorkspaceResourceEntity.id == resource_id).first()
        return self._resource_dao.to_response(entity)

    # ---------------- Growth ----------------
    def get_growth(self, workspace_id: int) -> dict:
        """返回空间本月成长数据。

        P0 阶段演化提议数恒为 0（提议生成 P2 才做），知识图谱节点数 P1 才接入 llm-wiki。
        """
        from datetime import datetime, timedelta

        from derisk_serve.task.api.schemas import TaskListFilter
        from derisk_serve.task.service.service import (
            TASK_SERVICE_COMPONENT_NAME,
            TaskService,
        )
        from derisk_serve.workspace_asset.api.schemas import AssetListFilter
        from derisk_serve.workspace_asset.service.service import (
            ASSET_SERVICE_COMPONENT_NAME,
            AssetService,
        )

        now = datetime.now()
        month_ago = now - timedelta(days=30)

        try:
            asset_svc: AssetService = self._system_app.get_component(
                ASSET_SERVICE_COMPONENT_NAME, AssetService
            )
            assets = asset_svc.list_assets(
                AssetListFilter(workspace_id=workspace_id, limit=10000)
            ) or []
            assets_count = len(assets)
        except Exception as e:
            logger.warning(f"get_growth assets failed: {e}")
            assets_count = 0

        try:
            task_svc: TaskService = self._system_app.get_component(
                TASK_SERVICE_COMPONENT_NAME, TaskService
            )
            tasks = task_svc.list_tasks(
                TaskListFilter(workspace_id=workspace_id, limit=10000)
            ) or []
            trend_map: dict = {}
            for t in tasks:
                created_str = getattr(t, "gmt_created", None)
                if not created_str:
                    continue
                try:
                    created = datetime.fromisoformat(created_str)
                    if created >= month_ago:
                        key = created.strftime("%Y-%m-%d")
                        trend_map[key] = trend_map.get(key, 0) + 1
                except Exception:
                    continue
            tasks_trend = [
                {"date": k, "count": v}
                for k, v in sorted(trend_map.items())
            ]
        except Exception as e:
            logger.warning(f"get_growth tasks failed: {e}")
            tasks_trend = []

        return {
            "assets_count": assets_count,
            "evolution_proposals_count": 0,  # P0 占位，P2 才做生成
            "tasks_trend": tasks_trend,
            "knowledge_graph_nodes": 0,  # P0 占位，P1 接入 llm-wiki
        }

    # ---------------- Conversation link ----------------
    def link_conversation(
        self, workspace_id: int, conv_uid: str,
        task_id: Optional[int] = None, user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        entity = self._conv_link_dao.link(
            workspace_id=workspace_id, conv_uid=conv_uid,
            task_id=task_id, user_id=user_id,
        )
        return self._conv_link_dao.to_response(entity)

    def list_conversations(
        self, workspace_id: int, user_id: Optional[int] = None, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        rows = self._conv_link_dao.list_by_workspace(workspace_id, user_id, limit)
        return [self._conv_link_dao.to_response(r) for r in rows]

    def get_conversation_workspace(self, conv_uid: str) -> Optional[Dict[str, Any]]:
        row = self._conv_link_dao.get_by_conv(conv_uid)
        return self._conv_link_dao.to_response(row) if row else None
