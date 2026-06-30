"""Artifact service."""
import json
import logging
from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    ArtifactListFilter, ArtifactRequest, ArtifactResponse, ArtifactVersionResponse,
)
from ..config import ServeConfig
from ..models.models import (
    ArtifactDao, ArtifactEntity, ArtifactVersionDao,
)

ARTIFACT_SERVICE_COMPONENT_NAME = "serve_artifact_service"
logger = logging.getLogger(__name__)


class ArtifactService(BaseService[ArtifactEntity, ArtifactRequest, ArtifactResponse]):
    name = ARTIFACT_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[ArtifactDao] = None,
        version_dao: Optional[ArtifactVersionDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: ArtifactDao = dao
        self._version_dao: ArtifactVersionDao = version_dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or ArtifactDao()
        self._version_dao = self._version_dao or ArtifactVersionDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def version_dao(self) -> ArtifactVersionDao:
        return self._version_dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: ArtifactRequest) -> ArtifactResponse:
        response = self._dao.create(request)
        # record v1
        self._version_dao.create_version(
            artifact_id=response.id, version=1,
            content_ref=request.content_ref,
            created_by=request.created_by_agent or str(request.created_by_user or ""),
        )
        return response

    def update(self, request: ArtifactRequest) -> ArtifactResponse:
        if not request.id:
            raise ValueError("artifact id required for update")
        existing = self._dao.get_raw_session().query(ArtifactEntity).filter(
            ArtifactEntity.id == request.id
        ).first()
        if not existing:
            raise ValueError(f"artifact {request.id} not found")
        existing.title = request.title
        existing.content_ref = request.content_ref
        existing.content_text = request.content_text
        existing.provenance_json = json.dumps(request.provenance or {}, ensure_ascii=False)
        if request.is_shared is not None:
            existing.is_shared = request.is_shared
        existing.current_version = (existing.current_version or 1) + 1
        self._dao.get_raw_session().commit()
        self._version_dao.create_version(
            artifact_id=existing.id, version=existing.current_version,
            content_ref=request.content_ref,
            created_by=request.created_by_agent or str(request.created_by_user or ""),
        )
        return self._dao.to_response(existing)

    def get_by_id(self, artifact_id: int) -> Optional[ArtifactResponse]:
        entity = self._dao.get_raw_session().query(ArtifactEntity).filter(
            ArtifactEntity.id == artifact_id
        ).first()
        return self._dao.to_response(entity) if entity else None

    def list_artifacts(self, f: ArtifactListFilter) -> List[ArtifactResponse]:
        return self._dao.list_by_filter(f)

    def list_versions(self, artifact_id: int) -> List[ArtifactVersionResponse]:
        return self._version_dao.list_versions(artifact_id)
