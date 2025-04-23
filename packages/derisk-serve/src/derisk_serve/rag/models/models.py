from datetime import datetime
from typing import Any, Dict, Union

from sqlalchemy import Column, DateTime, Integer, String, Text

from derisk._private.pydantic import model_to_dict
from derisk.storage.metadata import BaseDao, Model
from derisk_app.knowledge.request.request import KnowledgeSpaceRequest
from derisk_serve.rag.api.schemas import SpaceServeRequest, SpaceServeResponse


class KnowledgeSpaceEntity(Model):
    __tablename__ = "knowledge_space"
    id = Column(Integer, primary_key=True)
    knowledge_id = Column(String(100))
    name = Column(String(100))
    storage_type = Column(String(100))
    domain_type = Column(String(100))
    tags = Column(String(500))
    desc = Column(String(100), name="description")
    owner = Column(String(100))
    sys_code = Column(String(128))
    context = Column(Text)
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)

    def __repr__(self):
        return (
            f"KnowledgeSpaceEntity(id={self.id}, name='{self.name}', "
            f"storage_type='{self.storage_type}', desc='{self.desc}', tags='{self.tags}', "
            f"owner='{self.owner}' context='{self.context}', "
            f"gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}')"
        )


class KnowledgeSpaceDao(BaseDao):
    def create_knowledge_space(self, space: KnowledgeSpaceRequest):
        """Create knowledge space"""
        session = self.get_raw_session()
        knowledge_space = KnowledgeSpaceEntity(
            knowledge_id=space.knowledge_id,
            name=space.name,
            storage_type=space.storage_type,
            domain_type=space.domain_type,
            desc=space.desc,
            tags=space.tags,
            owner=space.owner,
            sys_code=space.sys_code,
            gmt_created=datetime.now(),
            gmt_modified=datetime.now(),
        )
        session.add(knowledge_space)
        session.commit()
        session.close()
        ks = self.get_knowledge_space(KnowledgeSpaceEntity(name=space.name))
        if ks is not None and len(ks) == 1:
            return ks[0].id
        raise Exception("create space error, find more than 1 or 0 space.")

    def get_knowledge_space_by_ids(self, ids):
        session = self.get_raw_session()
        if ids:
            knowledge_spaces = session.query(KnowledgeSpaceEntity).filter(
                KnowledgeSpaceEntity.id.in_(ids)
            )
        else:
            return []
        knowledge_spaces_list = knowledge_spaces.all()
        session.close()
        return knowledge_spaces_list

    def get_knowledge_space(self, query: KnowledgeSpaceEntity):
        """Get knowledge space by query"""
        session = self.get_raw_session()
        knowledge_spaces = session.query(KnowledgeSpaceEntity)
        if query.id is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.id == query.id
            )
        if query.knowledge_id is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.knowledge_id == query.knowledge_id
            )
        if query.name is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.name == query.name
            )
        if query.storage_type is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.storage_type == query.storage_type
            )
        if query.domain_type is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.domain_type == query.domain_type
            )
        if query.desc is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.desc == query.desc
            )
        if query.owner is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.owner == query.owner
            )
        if query.gmt_created is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.gmt_created == query.gmt_created
            )
        if query.gmt_modified is not None:
            knowledge_spaces = knowledge_spaces.filter(
                KnowledgeSpaceEntity.gmt_modified == query.gmt_modified
            )
        knowledge_spaces = knowledge_spaces.order_by(
            KnowledgeSpaceEntity.gmt_created.desc()
        )
        result = knowledge_spaces.all()
        session.close()
        return result

    def update_knowledge_space(self, space: KnowledgeSpaceEntity):
        """Update knowledge space"""

        session = self.get_raw_session()
        request = SpaceServeRequest(id=space.id)
        update_request = self.to_request(space)
        query = self._create_query_object(session, request)
        entry = query.first()
        if entry is None:
            raise Exception("Invalid request")
        for key, value in model_to_dict(update_request).items():  # type: ignore
            if value is not None:
                setattr(entry, key, value)
        session.merge(entry)
        session.commit()
        session.close()
        return self.to_response(space)

    def delete_knowledge_space(self, space: KnowledgeSpaceEntity):
        """Delete knowledge space"""
        session = self.get_raw_session()
        if space:
            session.delete(space)
            session.commit()
        session.close()

    def from_request(
        self, request: Union[SpaceServeRequest, Dict[str, Any]]
    ) -> KnowledgeSpaceEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        request_dict = (
            model_to_dict(request)
            if isinstance(request, SpaceServeRequest)
            else request
        )
        if "vector_type" in request_dict:
            request_dict.pop("vector_type")
        entity = KnowledgeSpaceEntity(**request_dict)
        return entity

    def to_request(self, entity: KnowledgeSpaceEntity) -> SpaceServeRequest:
        """Convert the entity to a request

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return SpaceServeRequest(
            id=entity.id,
            knowledge_id=entity.knowledge_id,
            name=entity.name,
            storage_type=entity.storage_type,
            desc=entity.desc,
            owner=entity.owner,
            context=entity.context,
        )

    def to_response(self, entity: KnowledgeSpaceEntity) -> SpaceServeResponse:
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return SpaceServeResponse(
            id=entity.id,
            knowledge_id=entity.knowledge_id,
            name=entity.name,
            storage_type=entity.storage_type,
            desc=entity.desc,
            owner=entity.owner,
            context=entity.context,
            domain_type=entity.domain_type,
        )
