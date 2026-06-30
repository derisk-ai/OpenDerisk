"""WorkspaceAsset service."""
import json
import logging
from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    AssetListFilter, AssetRequest, AssetResponse, AssetSearchRequest,
    AssetVersionResponse, TaskAssetLinkRequest, TaskAssetLinkResponse,
)
from ..config import ServeConfig
from ..models.models import (
    AssetDao, AssetEntity, AssetVersionDao, TaskAssetLinkDao,
)

ASSET_SERVICE_COMPONENT_NAME = "serve_workspace_asset_service"
logger = logging.getLogger(__name__)


class AssetService(BaseService[AssetEntity, AssetRequest, AssetResponse]):
    name = ASSET_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[AssetDao] = None,
        version_dao: Optional[AssetVersionDao] = None,
        link_dao: Optional[TaskAssetLinkDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: AssetDao = dao
        self._version_dao: AssetVersionDao = version_dao
        self._link_dao: TaskAssetLinkDao = link_dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or AssetDao()
        self._version_dao = self._version_dao or AssetVersionDao()
        self._link_dao = self._link_dao or TaskAssetLinkDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def version_dao(self) -> AssetVersionDao:
        return self._version_dao

    @property
    def link_dao(self) -> TaskAssetLinkDao:
        return self._link_dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: AssetRequest) -> AssetResponse:
        response = self._dao.create(request)
        self._version_dao.create_version(
            asset_id=response.id, version=1,
            content_ref=request.content_ref,
            created_by=request.created_by,
        )
        if request.source_task_id:
            self._link_dao.link(
                task_id=request.source_task_id,
                asset_id=response.id,
                link_type="produced",
            )
        return response

    def update(self, request: AssetRequest) -> AssetResponse:
        if not request.id:
            raise ValueError("asset id required for update")
        session = self._dao.get_raw_session()
        try:
            existing = session.query(AssetEntity).filter(
                AssetEntity.id == request.id
            ).first()
            if not existing:
                raise ValueError(f"asset {request.id} not found")
            existing.name = request.name
            existing.description = request.description
            existing.content_ref = request.content_ref
            existing.content_text = request.content_text
            existing.tags_json = json.dumps(request.tags or [], ensure_ascii=False)
            if request.is_published is not None:
                existing.is_published = request.is_published
            existing.current_version = (existing.current_version or 1) + 1
            session.commit()
            self._version_dao.create_version(
                asset_id=existing.id, version=existing.current_version,
                content_ref=request.content_ref,
                created_by=request.created_by,
            )
            return self._dao.to_response(existing)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_by_id(self, asset_id: int) -> Optional[AssetResponse]:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(AssetEntity).filter(
                AssetEntity.id == asset_id
            ).first()
            return self._dao.to_response(entity) if entity else None
        finally:
            session.close()

    def list_assets(self, f: AssetListFilter) -> List[AssetResponse]:
        return self._dao.list_by_filter(f)

    def search(self, req: AssetSearchRequest) -> List[AssetResponse]:
        return self._dao.search(req)

    def list_versions(self, asset_id: int) -> List[AssetVersionResponse]:
        return self._version_dao.list_versions(asset_id)

    def link_to_task(self, request: TaskAssetLinkRequest) -> TaskAssetLinkResponse:
        entity = self._link_dao.link(
            task_id=request.task_id,
            asset_id=request.asset_id,
            link_type=request.link_type,
        )
        return self._link_dao.to_response(entity)

    def list_links_by_task(self, task_id: int) -> List[TaskAssetLinkResponse]:
        return self._link_dao.list_by_task(task_id)
