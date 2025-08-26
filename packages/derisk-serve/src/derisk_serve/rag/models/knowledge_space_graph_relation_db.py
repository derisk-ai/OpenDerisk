from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from derisk.storage.metadata import Model, BaseDao


class KnowledgeSpaceGraphRelationEntity(Model):
    __tablename__ = "knowledge_space_graph_relation"
    id = Column(Integer, primary_key=True)
    knowledge_id = Column(String(100))
    storage_type = Column(String(100))
    project_id = Column(Integer)
    project_name = Column(String(100))
    user_token = Column(String(100))
    user_login_name = Column(String(100))
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)

    def __repr__(self):
        return (
            f"KnowledgeSpaceGraphRelationEntity(id={self.id}, knowledge_id='{self.knowledge_id}', "
            f"storage_type='{self.storage_type}', project_id='{self.project_id}', "
            f"project_name='{self.project_name}', user_token='{self.user_token}', "
            f"user_login_name='{self.user_login_name}', "
            f"gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}'"
        )

    def to_dict(self):
        return {
            "__tablename__": self.__tablename__,
            "id": self.id,
            "knowledge_id": self.knowledge_id,
            "storage_type": self.storage_type,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "user_token": self.user_token,
            "user_login_name": self.user_login_name,
            "gmt_created": self.gmt_created,
            "gmt_modified": self.gmt_modified,
        }


class KnowledgeSpaceGraphRelationDao(BaseDao):
    def create_relation(self, relation: KnowledgeSpaceGraphRelationEntity):
        session = self.get_raw_session()
        graph_relation = KnowledgeSpaceGraphRelationEntity(
            knowledge_id=relation.knowledge_id,
            storage_type=relation.storage_type,
            project_id=relation.project_id,
            project_name=relation.project_name,
            user_token=relation.user_token,
            user_login_name=relation.user_login_name,
            gmt_created=datetime.now(),
            gmt_modified=datetime.now(),
        )
        session.add(graph_relation)
        session.commit()
        relation_id = graph_relation.id
        session.close()

        return relation_id


    def get_relations(self, query: KnowledgeSpaceGraphRelationEntity, page=1, page_size=20):
        session = self.get_raw_session()
        relations = session.query(KnowledgeSpaceGraphRelationEntity)
        if query.id is not None:
            relations = relations.filter(KnowledgeSpaceGraphRelationEntity.id == query.id)
        if query.knowledge_id is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.knowledge_id == query.knowledge_id
            )
        if query.project_id is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.project_id == query.project_id
            )
        if query.storage_type is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.storage_type == query.storage_type
            )
        if query.user_login_name is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.user_login_name == query.user_login_name
            )

        relations = relations.order_by(KnowledgeSpaceGraphRelationEntity.id.asc())
        relations = relations.offset((page - 1) * page_size).limit(page_size)

        result = relations.all()
        session.close()
        return result


    def raw_delete(self, query: KnowledgeSpaceGraphRelationEntity):
        session = self.get_raw_session()
        relations = session.query(KnowledgeSpaceGraphRelationEntity)
        if query.id is not None:
            relations = relations.filter(KnowledgeSpaceGraphRelationEntity.id == query.id)
        if query.knowledge_id is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.knowledge_id == query.knowledge_id
            )
        if query.project_id is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.project_id == query.project_id
            )
        if query.storage_type is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.storage_type == query.storage_type
            )
        if query.user_login_name is not None:
            relations = relations.filter(
                KnowledgeSpaceGraphRelationEntity.user_login_name == query.user_login_name
            )
        relations.delete()
        session.commit()
        session.close()
