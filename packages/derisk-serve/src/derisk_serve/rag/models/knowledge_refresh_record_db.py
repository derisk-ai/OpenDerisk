import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text
from derisk.storage.metadata import Model, BaseDao

logger = logging.getLogger(__name__)


class KnowledgeRefreshRecordEntity(Model):
    __tablename__ = "knowledge_refresh_record"
    id = Column(Integer, primary_key=True)
    refresh_id = Column(String(100))
    knowledge_id = Column(String(100))
    refresh_time = Column(String(100))
    host = Column(String(100))
    status = Column(String(100))
    operator = Column(String(100))
    error_msg = Column(String(100))
    context = Column(Text)
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)

    def __repr__(self):
        return (
            f"KnowledgeRefreshRecordEntity(id={self.id}, refresh_id='{self.refresh_id}',"
            f"knowledge_id='{self.knowledge_id}', refresh_time='{self.refresh_time}', host='{self.host}',"
            f"status='{self.status}', operator='{self.operator}', error_msg='{self.error_msg}'), "
            f"context='{self.context}', gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}')"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "refresh_id": self.refresh_id,
            "knowledge_id": self.knowledge_id,
            "refresh_time": self.refresh_time,
            "host": self.host,
            "status": self.status,
            "operator": self.operator,
            "error_msg": self.error_msg,
            "context": self.context,
            "gmt_created": self.gmt_created,
            "gmt_modified": self.gmt_modified,
        }


class KnowledgeRefreshRecordDao(BaseDao):
    def create_knowledge_refresh_records(
        self, records: List, batch_size: Optional[int] = 200
    ):
        session = self.get_raw_session()
        try:
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                records = [
                    KnowledgeRefreshRecordEntity(
                        refresh_id=record.refresh_id,
                        knowledge_id=record.knowledge_id,
                        refresh_time=record.refresh_time,
                        host=record.host,
                        status=record.status,
                        operator=record.operator,
                        error_msg=record.error_msg,
                        context=record.context,
                        gmt_created=datetime.now(),
                        gmt_modified=datetime.now(),
                    )
                    for record in batch
                ]
                session.add_all(records)
                session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Error in create_knowledge_refresh_records: {str(e)}")
            raise

        finally:
            session.close()

    def get_knowledge_refresh_records(
        self,
        query: KnowledgeRefreshRecordEntity,
        ignore_status: Optional[List[str]] = None,
        page=1,
        page_size=20,
    ):
        session = self.get_raw_session()
        records = session.query(KnowledgeRefreshRecordEntity)
        if query.id is not None:
            records = records.filter(KnowledgeRefreshRecordEntity.id == query.id)
        if query.refresh_id is not None:
            records = records.filter(
                KnowledgeRefreshRecordEntity.refresh_id == query.refresh_id
            )
        if query.knowledge_id is not None:
            records = records.filter(
                KnowledgeRefreshRecordEntity.knowledge_id == query.knowledge_id
            )
        if query.host is not None:
            records = records.filter(KnowledgeRefreshRecordEntity.host == query.host)
        if query.status is not None:
            records = records.filter(
                KnowledgeRefreshRecordEntity.status == query.status
            )
        if query.operator is not None:
            records = records.filter(
                KnowledgeRefreshRecordEntity.operator == query.operator
            )
        if query.refresh_time is not None:
            records = records.filter(
                KnowledgeRefreshRecordEntity.refresh_time == query.refresh_time
            )
        if ignore_status is not None:
            records = records.filter(
                KnowledgeRefreshRecordEntity.status.notin_(ignore_status)
            )

        records = records.order_by(KnowledgeRefreshRecordEntity.id.asc())
        records = records.offset((page - 1) * page_size).limit(page_size)

        result = records.all()
        session.close()
        return result

    def get_not_finished_refresh_records(
        self, ignore_status: Optional[List[str]] = None
    ):
        session = self.get_raw_session()
        try:
            query = (
                session.query(KnowledgeRefreshRecordEntity.knowledge_id)
                .distinct()
                .filter(KnowledgeRefreshRecordEntity.status.notin_(ignore_status))
            )

            results = query.all()

            return [row[0] for row in results if row[0] is not None]

        finally:
            session.close()

    def update_knowledge_refresh_records_batch(
        self, records: List[KnowledgeRefreshRecordEntity], batch_size: int = 100
    ):
        session = self.get_raw_session()
        updated_ids = []

        try:
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                task_ids = [task.id for task in batch]

                # Lock the tasks using SELECT ... FOR UPDATE to prevent concurrent modifications
                session.query(KnowledgeRefreshRecordEntity).filter(
                    KnowledgeRefreshRecordEntity.id.in_(task_ids)
                ).with_for_update().all()

                for task in batch:
                    updated_document = session.merge(task)
                    updated_ids.append(updated_document.id)

                session.commit()

            return updated_ids

        except Exception as e:
            logger.error(
                f"update_knowledge_refresh_records_batch error updating task batch: {str(e)}"
            )
            session.rollback()
            raise

        finally:
            session.close()

    def delete_knowledge_refresh_records(
        self, refresh_id: Optional[str] = None, refresh_time: Optional[str] = None
    ):
        session = self.get_raw_session()
        try:
            if refresh_id is None and refresh_time is None:
                raise Exception("refresh_id and refresh_time are both None")

            records = session.query(KnowledgeRefreshRecordEntity)
            if refresh_id is not None:
                records = records.filter(
                    KnowledgeRefreshRecordEntity.refresh_id == refresh_id
                )
            if refresh_time is not None:
                records = records.filter(
                    KnowledgeRefreshRecordEntity.refresh_time == refresh_time
                )
            records.delete()
            session.commit()
        finally:
            session.close()

    def check_record_exists(self, knowledge_id: str, refresh_time: str):
        session = self.get_raw_session()
        try:
            query = session.query(KnowledgeRefreshRecordEntity).filter(
                KnowledgeRefreshRecordEntity.knowledge_id == knowledge_id,
                KnowledgeRefreshRecordEntity.refresh_time == refresh_time,
            )
            result = query.first()

            return result is not None

        finally:
            session.close()
