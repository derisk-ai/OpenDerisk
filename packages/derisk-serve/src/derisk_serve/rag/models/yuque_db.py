import logging
from datetime import datetime
from typing import List

from sqlalchemy import Column, DateTime, Integer, String

from derisk.storage.metadata import BaseDao, Model


logger = logging.getLogger(__name__)


class KnowledgeYuqueEntity(Model):
    __tablename__ = "knowledge_yuque"
    id = Column(Integer, primary_key=True)
    yuque_id = Column(String(100))
    doc_id = Column(String(100))
    knowledge_id = Column(String(100))
    title = Column(String(100))
    token = Column(String(100))
    token_type = Column(String(100))
    group_login = Column(String(100))
    group_login_name = Column(String(100))
    book_slug = Column(String(100))
    book_slug_name = Column(String(100))
    doc_slug = Column(String(100))
    doc_uuid = Column(String(100))
    backup_doc_uuid = Column(String(100))
    word_cnt = Column(Integer)
    latest_version_id = Column(String(100))
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)

    def __repr__(self):
        return (
            f"KnowledgeYuqueEntity(id={self.id}, yuque_id='{self.yuque_id}', "
            f"doc_id='{self.doc_id}', knowledge_id='{self.knowledge_id}', title='{self.title}', "
            f"token='{self.token}', token_type='{self.token_type}', group_login='{self.group_login}', group_login_name='{self.group_login_name}',"
            f"book_slug='{self.book_slug}', book_slug_name='{self.book_slug_name}', doc_slug='{self.doc_slug}', doc_uuid='{self.doc_uuid}', "
            f"backup_doc_uuid='{self.backup_doc_uuid}, word_cnt='{self.word_cnt}', latest_version_id='{self.latest_version_id}', "
            f"gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}')"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "yuque_id": self.yuque_id,
            "doc_id": self.doc_id,
            "knowledge_id": self.knowledge_id,
            "title": self.title,
            "token": self.token,
            "token_type": self.token_type,
            "group_login": self.group_login,
            "group_login_name": self.group_login_name,
            "book_slug": self.book_slug,
            "book_slug_name": self.book_slug_name,
            "doc_slug": self.doc_slug,
            "doc_uuid": self.doc_uuid,
            "backup_doc_uuid": self.backup_doc_uuid,
            "word_cnt": self.word_cnt,
            "latest_version_id": self.latest_version_id,
            "gmt_created": self.gmt_created,
            "gmt_modified": self.gmt_modified,
        }


class KnowledgeYuqueDao(BaseDao):
    def create_knowledge_yuque(self, docs: List):
        session = self.get_raw_session()
        docs = [
            KnowledgeYuqueEntity(
                yuque_id=document.yuque_id,
                doc_id=document.doc_id,
                knowledge_id=document.knowledge_id,
                title=document.title,
                token=document.token,
                token_type=document.token_type,
                group_login=document.group_login,
                group_login_name=document.group_login_name,
                book_slug=document.book_slug,
                book_slug_name=document.book_slug_name,
                doc_slug=document.doc_slug,
                doc_uuid=document.doc_uuid,
                word_cnt=document.word_cnt,
                latest_version_id=document.latest_version_id,
                gmt_created=datetime.now(),
                gmt_modified=datetime.now(),
            )
            for document in docs
        ]
        session.add_all(docs)
        session.commit()
        session.close()

    def get_knowledge_yuque(self, query: KnowledgeYuqueEntity):
        session = self.get_raw_session()
        yuque_docs = session.query(KnowledgeYuqueEntity)
        if query.id is not None:
            yuque_docs = yuque_docs.filter(KnowledgeYuqueEntity.id == query.id)
        if query.yuque_id is not None:
            yuque_docs = yuque_docs.filter(
                KnowledgeYuqueEntity.yuque_id == query.yuque_id
            )
        if query.doc_id is not None:
            yuque_docs = yuque_docs.filter(KnowledgeYuqueEntity.doc_id == query.doc_id)
        if query.knowledge_id is not None:
            yuque_docs = yuque_docs.filter(
                KnowledgeYuqueEntity.knowledge_id == query.knowledge_id
            )
        if query.group_login is not None:
            yuque_docs = yuque_docs.filter(
                KnowledgeYuqueEntity.group_login == query.group_login
            )
        if query.book_slug is not None:
            yuque_docs = yuque_docs.filter(
                KnowledgeYuqueEntity.book_slug == query.book_slug
            )
        if query.token is not None:
            yuque_docs = yuque_docs.filter(KnowledgeYuqueEntity.token == query.token)

        yuque_docs = yuque_docs.order_by(KnowledgeYuqueEntity.id.asc())

        result = yuque_docs.all()
        session.close()
        return result

    def update_knowledge_yuque(self, yuque_doc: KnowledgeYuqueEntity):
        try:
            session = self.get_raw_session()
            updated_document = session.merge(yuque_doc)
            session.commit()
            return updated_document.id
        finally:
            session.close()

    def update_knowledge_yuque_batch(
        self, yuque_docs: List[KnowledgeYuqueEntity], batch_size: int = 100
    ):
        try:
            session = self.get_raw_session()
            updated_ids = []

            for i in range(0, len(yuque_docs), batch_size):
                batch = yuque_docs[i : i + batch_size]
                for yuque_doc in batch:
                    updated_document = session.merge(yuque_doc)
                    updated_ids.append(updated_document.id)

                session.commit()

            return updated_ids

        finally:
            session.close()

    def raw_delete(self, query: KnowledgeYuqueEntity):
        logger.info(f"yuque doc raw_delete {query}")

        session = self.get_raw_session()
        yuque_docs = session.query(KnowledgeYuqueEntity)
        if query.id is not None:
            yuque_docs = yuque_docs.filter(KnowledgeYuqueEntity.id == query.id)
        if query.doc_id is not None:
            yuque_docs = yuque_docs.filter(KnowledgeYuqueEntity.doc_id == query.doc_id)
        yuque_docs.delete()
        session.commit()
        session.close()
