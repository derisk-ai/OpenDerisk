"""DB Model for connect_config."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from derisk.storage.metadata import BaseDao, Model
from derisk_serve.datasource.api.schemas import (
    DatasourceServeRequest,
    DatasourceServeResponse,
)

logger = logging.getLogger(__name__)


class ConnectConfigEntity(Model):
    """DB connector config entity."""

    __tablename__ = "connect_config"
    id = Column(
        Integer, primary_key=True, autoincrement=True, comment="autoincrement id"
    )

    db_type = Column(String(255), nullable=False, comment="db type")
    db_name = Column(String(255), nullable=False, comment="db name")
    db_path = Column(String(255), nullable=True, comment="file db path")
    db_host = Column(String(255), nullable=True, comment="db connect host(not file db)")
    db_port = Column(String(255), nullable=True, comment="db connect port(not file db)")
    db_user = Column(String(255), nullable=True, comment="db user")
    db_pwd = Column(String(255), nullable=True, comment="db password")
    comment = Column(Text, nullable=True, comment="db comment")
    sys_code = Column(String(128), index=True, nullable=True, comment="System code")
    user_id = Column(String(128), index=True, nullable=True, comment="User id")
    user_name = Column(String(128), index=True, nullable=True, comment="User name")
    gmt_created = Column(DateTime, default=datetime.now, comment="Record creation time")
    gmt_modified = Column(DateTime, default=datetime.now, comment="Record update time")
    ext_config = Column(
        Text, nullable=True, comment="Extended configuration, json format"
    )
    __table_args__ = (
        UniqueConstraint("db_name", name="uk_db"),
        Index("idx_q_db_type", "db_type"),
    )


class ConnectConfigDao(BaseDao):
    """DB connector config dao."""

    def get_by_names(self, db_name: str) -> Optional[ConnectConfigEntity]:
        """Get db connect info by name."""
        session = self.get_raw_session()
        db_connect = session.query(ConnectConfigEntity)
        db_connect = db_connect.filter(ConnectConfigEntity.db_name == db_name)
        result = db_connect.first()
        session.close()
        return result

    def add_url_db(
        self,
        db_name,
        db_type,
        db_host: str,
        db_port: int,
        db_user: str,
        db_pwd: str,
        comment: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Add db connect info.

        Args:
            db_name: db name
            db_type: db type
            db_host: db host
            db_port: db port
            db_user: db user
            db_pwd: db password
            comment: comment
        """
        try:
            session = self.get_raw_session()

            from sqlalchemy import text

            insert_statement = text(
                """
                INSERT INTO connect_config (
                    db_name, db_type, db_path, db_host, db_port, db_user, db_pwd,
                    comment, user_id) VALUES (:db_name, :db_type, :db_path, :db_host,
                    :db_port, :db_user, :db_pwd, :comment, :user_id
                )
            """
            )

            params = {
                "db_name": db_name,
                "db_type": db_type,
                "db_path": "",
                "db_host": db_host,
                "db_port": db_port,
                "db_user": db_user,
                "db_pwd": db_pwd,
                "comment": comment if comment else "",
                "user_id": user_id if user_id else "",
            }
            session.execute(insert_statement, params)
            session.commit()
            session.close()
        except Exception as e:
            logger.warning("add db connect info error！" + str(e))

    def add_file_db(
        self,
        db_name,
        db_type,
        db_path: str,
        comment: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Add file db connect info."""
        try:
            session = self.get_raw_session()
            insert_statement = text(
                """
                INSERT INTO connect_config(
                    db_name, db_type, db_path, db_host, db_port, db_user, db_pwd,
                    comment, user_id) VALUES (
                    :db_name, :db_type, :db_path, :db_host, :db_port, :db_user, :db_pwd
                    , :comment, :user_id
                )
            """
            )
            params = {
                "db_name": db_name,
                "db_type": db_type,
                "db_path": db_path,
                "db_host": "",
                "db_port": 0,
                "db_user": "",
                "db_pwd": "",
                "comment": comment if comment else "",
                "user_id": user_id if user_id else "",
            }

            session.execute(insert_statement, params)

            session.commit()
            session.close()
        except Exception as e:
            logger.warning("add db connect info error！" + str(e))

    def update_db_info(
        self,
        db_name,
        db_type,
        db_path: str = "",
        db_host: str = "",
        db_port: int = 0,
        db_user: str = "",
        db_pwd: str = "",
        comment: str = "",
        ext_config: Optional[str] = None,
    ):
        """Update db connect info."""
        old_db_conf = self.get_db_config(db_name)
        if old_db_conf:
            try:
                session = self.get_raw_session()
                if not db_path:
                    update_statement = text(
                        f"UPDATE connect_config set db_type='{db_type}', "
                        f"db_host='{db_host}', db_port={db_port}, db_user='{db_user}', "
                        f"db_pwd='{db_pwd}', comment='{comment}' where "
                        f"db_name='{db_name}'"
                    )
                else:
                    update_statement = text(
                        f"UPDATE connect_config set db_type='{db_type}', "
                        f"db_path='{db_path}', comment='{comment}' where "
                        f"db_name='{db_name}'"
                    )
                session.execute(update_statement)
                session.commit()
                session.close()
            except Exception as e:
                logger.warning("edit db connect info error！" + str(e))
            return True
        raise ValueError(f"{db_name} not have config info!")

    def get_db_config(self, db_name):
        """Return db connect info by name."""
        session = self.get_raw_session()
        if db_name:
            select_statement = text(
                """
                SELECT
                    *
                FROM
                    connect_config
                WHERE
                    db_name = :db_name
            """
            )
            params = {"db_name": db_name}
            result = session.execute(select_statement, params)

        else:
            raise ValueError("Cannot get database by name" + db_name)

        logger.info(f"Result: {result}")
        fields = [field[0] for field in result.cursor.description]
        row_dict = {}
        row_1 = list(result.cursor.fetchall()[0])
        for i, field in enumerate(fields):
            row_dict[field] = row_1[i]
        return row_dict

    def get_db_list(self, db_name: Optional[str] = None, user_id: Optional[str] = None):
        """Get db list."""
        session = self.get_raw_session()
        if db_name and user_id:
            sql = f"SELECT * FROM connect_config where (user_id='{user_id}' or user_id='' or user_id IS NULL) and db_name='{db_name}'"  # noqa
        elif user_id:
            sql = f"SELECT * FROM connect_config where user_id='{user_id}' or user_id='' or user_id IS NULL"  # noqa
        elif db_name:
            sql = f"SELECT * FROM connect_config where  db_name='{db_name}'"  # noqa
        else:
            sql = f"SELECT * FROM connect_config"  # noqa

        result = session.execute(text(sql))
        fields = [field[0] for field in result.cursor.description]  # type: ignore
        data = []
        for row in result.cursor.fetchall():  # type: ignore
            row_dict = {}
            for i, field in enumerate(fields):
                row_dict[field] = row[i]
            data.append(row_dict)
        return data

    def delete_db(self, db_name):
        """Delete db connect info."""
        session = self.get_raw_session()
        delete_statement = text("""DELETE FROM connect_config where db_name=:db_name""")
        params = {"db_name": db_name}
        session.execute(delete_statement, params)
        session.commit()
        session.close()
        return True

    def from_request(
        self, request: Union[DatasourceServeRequest, Dict[str, Any]]
    ) -> ConnectConfigEntity:
        """Convert the request to an entity.

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        request_dict = (
            request.dict() if isinstance(request, DatasourceServeRequest) else request
        )
        ext_config = request_dict.get("ext_config")
        if ext_config and isinstance(ext_config, dict):
            request_dict["ext_config"] = json.dumps(ext_config, ensure_ascii=False)
        entity = ConnectConfigEntity(**request_dict)
        return entity

    def to_request(self, entity: ConnectConfigEntity) -> DatasourceServeRequest:
        """Convert the entity to a request.

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        ext_config = entity.ext_config
        if ext_config:
            ext_config = json.loads(ext_config)
        return DatasourceServeRequest(
            id=entity.id,
            db_type=entity.db_type,
            db_name=entity.db_name,
            db_path=entity.db_path,
            db_host=entity.db_host,
            db_port=entity.db_port,
            db_user=entity.db_user,
            db_pwd=entity.db_pwd,
            comment=entity.comment,
            ext_config=ext_config,
        )

    def to_response(self, entity: ConnectConfigEntity) -> DatasourceServeResponse:
        """Convert the entity to a response.

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        ext_config = entity.ext_config
        if ext_config:
            ext_config = json.loads(ext_config)
        gmt_created = (
            entity.gmt_created.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_created
            else None
        )
        gmt_modified = (
            entity.gmt_modified.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_modified
            else None
        )
        return DatasourceServeResponse(
            id=entity.id,
            db_type=entity.db_type,
            db_name=entity.db_name,
            db_path=entity.db_path,
            db_host=entity.db_host,
            db_port=entity.db_port,
            db_user=entity.db_user,
            db_pwd=entity.db_pwd,
            comment=entity.comment,
            ext_config=ext_config,
            gmt_created=gmt_created,
            gmt_modified=gmt_modified,
        )
