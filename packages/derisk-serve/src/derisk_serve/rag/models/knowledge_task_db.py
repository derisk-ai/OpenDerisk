import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, DateTime, Integer, String

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)

class KnowledgeTaskEntity(Model):
    __tablename__ = "knowledge_task"
    id = Column(Integer, primary_key=True)
    task_id = Column(String(100))
    knowledge_id = Column(String(100))
    doc_id = Column(String(100))
    doc_type = Column(String(100))
    doc_content = Column(String(100))
    group_login = Column(String(100))
    book_slug = Column(String(100))
    chunk_parameters = Column(String(100))
    status = Column(String(100))
    owner = Column(String(100))
    batch_id = Column(String(100))
    retry_times = Column(Integer)
    error_msg = Column(String(100))
    start_time = Column(String(100))
    end_time = Column(String(100))
    host = Column(String(100))
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)

    def __repr__(self):
        return (
            f"KnowledgeTaskEntity(id={self.id}, task_id='{self.task_id}', "
            f"doc_id='{self.doc_id}', knowledge_id='{self.knowledge_id}', doc_type='{self.doc_type}', "
            f"doc_content='{self.doc_content}', group_login='{self.group_login}',"
            f"book_slug='{self.book_slug}', chunk_parameters='{self.chunk_parameters}',  "
            f"status='{self.status}', owner='{self.owner}', batch_id='{self.batch_id}', retry_times='{self.retry_times}', "
            f"error_msg='{self.error_msg}', start_time='{self.start_time}', end_time='{self.end_time}', host='{self.host}', "
            f"gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}')"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "knowledge_id": self.knowledge_id,
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "doc_content": self.doc_content,
            "group_login": self.group_login,
            "book_slug": self.book_slug,
            "chunk_parameters": self.chunk_parameters,
            "status": self.status,
            "owner": self.owner,
            "batch_id": self.batch_id,
            "retry_times": self.retry_times,
            "error_msg": self.error_msg,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "host": self.host,
            "gmt_created": self.gmt_created,
            "gmt_modified": self.gmt_modified,
        }

class KnowledgeTaskDao(BaseDao):

    def create_knowledge_task(self, tasks: List, batch_size: Optional[int] = 200):
        session = self.get_raw_session()

        try:
            for i in range(0, len(tasks), batch_size):
                # Slice the tasks list to get the current batch
                batch = tasks[i:i + batch_size]

                docs = [
                    KnowledgeTaskEntity(
                        task_id=task.task_id,
                        knowledge_id=task.knowledge_id,
                        doc_id=task.doc_id,
                        doc_type=task.doc_type,
                        doc_content=task.doc_content,
                        group_login=task.group_login,
                        book_slug=task.book_slug,
                        chunk_parameters=task.chunk_parameters,
                        status=task.status,
                        owner=task.owner,
                        batch_id=task.batch_id,
                        retry_times=task.retry_times,
                        error_msg=task.error_msg,
                        start_time=task.start_time,
                        end_time=task.end_time,
                        host=task.host,
                        gmt_created=datetime.now(),
                        gmt_modified=datetime.now(),
                    )
                    for task in batch
                ]

                # Add current batch to the session
                session.add_all(docs)

                # Commit the current batch
                session.commit()

        except Exception as e:
            # If there is an error, rollback the session
            session.rollback()
            logger.error(f"Error in create_knowledge_task: {str(e)}")
            raise

        finally:
            # Always ensure the session is closed
            session.close()


    def get_knowledge_tasks(self, query: KnowledgeTaskEntity, ignore_status: Optional[List[str]] = None, page=1, page_size=20):
        session = self.get_raw_session()
        tasks = session.query(KnowledgeTaskEntity)
        if query.id is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.id == query.id)
        if query.task_id is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.task_id == query.task_id)
        if query.knowledge_id is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.knowledge_id == query.knowledge_id)
        if query.doc_id is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.doc_id == query.doc_id)
        if query.doc_type is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.doc_type == query.doc_type)
        if query.doc_content is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.doc_content == query.doc_content)

        if query.group_login is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.group_login == query.group_login)
        if query.book_slug is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.book_slug == query.book_slug)
        if ignore_status is not None:
            tasks = tasks.filter(KnowledgeTaskEntity.status.notin_(ignore_status))

        tasks = tasks.order_by(KnowledgeTaskEntity.id.asc())
        tasks = tasks.offset((page - 1) * page_size).limit(
            page_size
        )

        result = tasks.all()
        session.close()
        return result


    def delete_knowledge_tasks(self, query: KnowledgeTaskEntity):
        session = self.get_raw_session()
        try:
            if query.knowledge_id is None:
                raise Exception("knowledge_id is None")

            tasks = session.query(KnowledgeTaskEntity)
            tasks = tasks.filter(
                KnowledgeTaskEntity.knowledge_id == query.knowledge_id
            )

            if query.task_id is not None:
                tasks = tasks.filter(
                    KnowledgeTaskEntity.task_id == query.task_id
                )
            if query.batch_id is not None:
                tasks = tasks.filter(
                    KnowledgeTaskEntity.batch_id == query.batch_id
                )

            tasks.delete()
            session.commit()
        finally:
            session.close()

    def get_not_finished_knowledge_ids(self, ignore_status: Optional[List[str]] = None):
        session = self.get_raw_session()
        try:
            query = session.query(
                KnowledgeTaskEntity.knowledge_id
            ).distinct().filter(
                KnowledgeTaskEntity.status.notin_(ignore_status)
            )

            results = query.all()

            return [row[0] for row in results if row[0] is not None]

        finally:
            session.close()


    def get_knowledge_tasks_by_status(self, ignore_status: Optional[List[str]] = None, limit=1):
        session = self.get_raw_session()
        try:
            tasks = session.query(KnowledgeTaskEntity)
            if ignore_status is not None:
                tasks = tasks.filter(KnowledgeTaskEntity.status.notin_(ignore_status))

            tasks = tasks.order_by(KnowledgeTaskEntity.id.asc())
            tasks = tasks.limit(limit)

            # Use FOR UPDATE to lock rows during the transaction
            results = tasks.with_for_update().all()

            return results

        finally:
            session.close()

    def update_knowledge_task_batch(self, tasks: List[KnowledgeTaskEntity], batch_size: int = 100):
        session = self.get_raw_session()
        updated_ids = []

        try:
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i: i + batch_size]
                task_ids = [task.id for task in batch]

                # Lock the tasks using SELECT ... FOR UPDATE to prevent concurrent modifications
                session.query(KnowledgeTaskEntity).filter(KnowledgeTaskEntity.id.in_(task_ids)).with_for_update().all()

                for task in batch:
                    updated_document = session.merge(task)
                    updated_ids.append(updated_document.id)

                session.commit()

            return updated_ids

        except Exception as e:
            logger.error(f"Error updating task batch: {str(e)}")
            session.rollback()
            raise

        finally:
            session.close()


