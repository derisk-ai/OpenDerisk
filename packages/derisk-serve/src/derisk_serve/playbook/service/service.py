"""Playbook service: CRUD + version + DSL validation + runtime context assembly."""
import json
import logging
from typing import Any, Dict, List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    PlaybookListFilter, PlaybookRequest, PlaybookResponse,
    PlaybookValidateRequest, PlaybookVersionResponse,
)
from ..config import ServeConfig
from ..models.models import (
    PlaybookDao, PlaybookEntity, PlaybookVersionDao, PlaybookVersionEntity,
)

PLAYBOOK_SERVICE_COMPONENT_NAME = "serve_playbook_service"
logger = logging.getLogger(__name__)


class PlaybookService(BaseService[PlaybookEntity, PlaybookRequest, PlaybookResponse]):
    name = PLAYBOOK_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[PlaybookDao] = None,
        version_dao: Optional[PlaybookVersionDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: PlaybookDao = dao
        self._version_dao: PlaybookVersionDao = version_dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or PlaybookDao()
        self._version_dao = self._version_dao or PlaybookVersionDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def version_dao(self) -> PlaybookVersionDao:
        return self._version_dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def validate_declaration(self, declaration: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the strategy declaration DSL.
        Returns {valid: bool, errors: [str]}.

        v1 schema (no gates):
        - skills: list of strings (skill codes or refs)
        - context: {assets_required: [...], resources: [...]}
        - deliverables: list of {type, delivery: [...]}
        - distill: {forced: bool, produce: [...]}
        """
        errors = []
        if not isinstance(declaration, dict):
            return {"valid": False, "errors": ["declaration must be a dict"]}
        for key in ["skills", "deliverables", "distill"]:
            if key not in declaration:
                errors.append(f"missing required block: {key}")
        if "skills" in declaration and not isinstance(declaration["skills"], list):
            errors.append("skills must be a list")
        if "deliverables" in declaration:
            if not isinstance(declaration["deliverables"], list):
                errors.append("deliverables must be a list")
            else:
                for i, d in enumerate(declaration["deliverables"]):
                    if not isinstance(d, dict) or "type" not in d:
                        errors.append(f"deliverables[{i}] must have 'type'")
        if "distill" in declaration:
            distill = declaration["distill"]
            if not isinstance(distill, dict):
                errors.append("distill must be a dict")
            elif distill.get("forced") not in (True, False, None):
                errors.append("distill.forced must be bool")
            elif distill.get("forced") is True and not distill.get("produce"):
                errors.append("distill.forced=true requires non-empty produce list")
        return {"valid": len(errors) == 0, "errors": errors}

    def create(self, request: PlaybookRequest) -> PlaybookResponse:
        validation = self.validate_declaration(request.declaration or {})
        if not validation["valid"]:
            raise ValueError(f"invalid declaration DSL: {validation['errors']}")
        response = self._dao.create(request)
        # record initial version
        self._version_dao.create_version(
            playbook_id=response.id,
            version=1,
            declaration=request.declaration or {},
            changelog="initial",
            created_by_user_id=request.id and None,
        )
        return response

    def update(self, request: PlaybookRequest) -> PlaybookResponse:
        if not request.id:
            raise ValueError("playbook id required for update")
        validation = self.validate_declaration(request.declaration or {})
        if not validation["valid"]:
            raise ValueError(f"invalid declaration DSL: {validation['errors']}")
        existing = self._dao.get_raw_session().query(PlaybookEntity).filter(
            PlaybookEntity.id == request.id
        ).first()
        if not existing:
            raise ValueError(f"playbook {request.id} not found")
        existing.name = request.name
        existing.scenario_type = request.scenario_type
        existing.task_type = request.task_type
        existing.trigger_json = json.dumps(request.trigger or {}, ensure_ascii=False)
        existing.declaration_dsl_json = json.dumps(
            request.declaration or {}, ensure_ascii=False
        )
        if request.is_active is not None:
            existing.is_active = request.is_active
        # bump version
        existing.current_version = (existing.current_version or 1) + 1
        self._dao.get_raw_session().commit()
        # record version
        self._version_dao.create_version(
            playbook_id=existing.id,
            version=existing.current_version,
            declaration=request.declaration or {},
            changelog="update",
        )
        return self._dao.to_response(existing)

    def get_by_id(self, playbook_id: int) -> Optional[PlaybookResponse]:
        entity = self._dao.get_raw_session().query(PlaybookEntity).filter(
            PlaybookEntity.id == playbook_id
        ).first()
        return self._dao.to_response(entity) if entity else None

    def list_playbooks(self, f: PlaybookListFilter) -> List[PlaybookResponse]:
        return self._dao.list_by_filter(f)

    def delete(self, playbook_id: int) -> bool:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(PlaybookEntity).filter(
                PlaybookEntity.id == playbook_id
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

    def list_versions(self, playbook_id: int) -> List[PlaybookVersionResponse]:
        return self._version_dao.list_versions(playbook_id)

    def assemble_context(self, playbook: PlaybookResponse, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Assemble Agent execution context from Playbook declaration.

        Returns dict with: skills, assets_required, resources, deliverables, distill,
        plus task_input merged in. The runtime layer will use this to inject into Agent prompt.
        """
        declaration = playbook.declaration or {}
        return {
            "playbook_id": playbook.id,
            "playbook_name": playbook.name,
            "scenario_type": playbook.scenario_type,
            "task_type": playbook.task_type,
            "skills": declaration.get("skills", []),
            "context": declaration.get("context", {}),
            "deliverables": declaration.get("deliverables", []),
            "distill": declaration.get("distill", {}),
            "task_input": task_input or {},
        }
