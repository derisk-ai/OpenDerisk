"""This is an auto-generated model file
You can define your own models and DAOs here
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, Union, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text
)

from derisk.storage.metadata import BaseDao, Model
from derisk.util.host_util import get_local_host

from ..api.schemas import ServeRequest, ServerResponse
from ..config import SERVER_APP_TABLE_NAME, ServeConfig

logger = logging.getLogger(__name__)


class ServeEntity(Model):
    __tablename__ = SERVER_APP_TABLE_NAME
    id = Column(Integer, primary_key=True, comment="Auto increment id")

    name = Column(String(255), nullable=False, comment="config key")
    value = Column(String(4096), nullable=True, comment="config value")
    type = Column(String(255), nullable=True, default="string", comment="config type[string, json, int, float]")
    valid_time = Column(Integer, nullable=True, comment="当前配置项的有效时间(单位秒),不设置为长期有效")
    operator = Column(String(255), nullable=True, comment="config operator")
    creator = Column(String(255), nullable=True, comment="config creator")
    version = Column(String(255), nullable=True, comment="config version serial")
    category = Column(String(255), nullable=True, comment="配置项类别，做领域区分使用，可空")
    upload_cls = Column(String(255), nullable=True, comment="需要自动更新值的配置项的更新类实现")
    upload_param = Column(String(1000), nullable=True, comment="需要自动更新值的配置项的更新参数")
    upload_instance = Column(String(255), nullable=True, comment="自动更新值的作业节点实例")
    upload_stamp = Column(Integer, nullable=True, comment="自动更新值的时间戳")
    upload_retry = Column(Integer, default=0, nullable=True, comment="自动更新值的重试次数")

    gmt_created = Column(DateTime, default=datetime.now, comment="Record creation time")
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="Record update time")

    __table_args__ = (UniqueConstraint("name", name="uk_config"),
                      Index("idx_creator", "creator"),
                      Index("idx_upload_cls", "upload_cls"),
                      Index("idx_category", "category"),)

    def __repr__(self):
        return (
            f"ServeEntity(id={self.id}, gmt_created='{self.gmt_created}', "
            f"gmt_modified='{self.gmt_modified}')"
        )


class ServeDao(BaseDao[ServeEntity, ServeRequest, ServerResponse]):
    """The DAO class for Config"""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[ServeRequest, Dict[str, Any]]) -> ServeEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        if isinstance(request, ServeRequest):
            # 如果是 ServeRequest 对象，转换为字典
            request_dict = request.to_dict()  # 或者 request.dict() 在较老版本的 pydantic 中
        else:
            # 如果已经是字典，直接使用
            request_dict = request

        # 创建实体对象
        entity = ServeEntity(**request_dict)  # type:ignore

        return entity

    def to_request(self, entity: ServeEntity) -> ServeRequest:
        """Convert the entity to a request

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        # 将实体转换为字典
        entity_dict = {
            'id': entity.id,
            'name': entity.name,
            'value': entity.value,
            'type': entity.type,
            'valid_time': entity.valid_time,
            'operator': entity.operator,
            'creator': entity.creator,
            'version': entity.version,
            'category': entity.category,
            'upload_cls': entity.upload_cls,
            'upload_param': entity.upload_param,
            'upload_instance': entity.upload_instance,
            'upload_stamp': entity.upload_stamp,
            'upload_retry': entity.upload_retry,
            'gmt_created': entity.gmt_created,
            'gmt_modified': entity.gmt_modified
        }

        # 过滤掉 None 值
        entity_dict = {k: v for k, v in entity_dict.items() if v is not None}

        # 创建 ServeRequest 对象
        request = ServeRequest(**entity_dict)

        return request

    def to_response(self, entity: ServeEntity) -> ServerResponse:
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            RES: The response
        """
        return self.to_request(entity)

    def try_lock_config(self, config_key: str) -> bool:
        """尝试获取配置项的处理锁"""
        try:
            session = self.get_raw_session()
            result = session.execute(
                text("SELECT GET_LOCK(:lock_name, 1)"),
                {"lock_name": f"config_lock_{config_key}"}
            ).scalar()
            return result == 1
        except Exception as e:
            logger.error(f"Error getting lock for config {config_key}: {e}")
            return False

    def release_config_lock(self, config_key: str):
        """释放配置项的处理锁"""
        try:
            session = self.get_raw_session()
            session.execute(
                text("SELECT RELEASE_LOCK(:lock_name)"),
                {"lock_name": f"config_lock_{config_key}"}
            )
        except Exception as e:
            logger.error(f"Error releasing lock for config {config_key}: {e}")

    def get_available_configs(self, batch_size: int = 10) -> List[ServerResponse]:
        """获取需要更新的配置项
        条件:
        1. 无机器锁定且过期的配置项
        2. 有机器锁定但超过3个有效期还未更新成功的配置项
        """
        with self.session() as session:
            current_time = int(time.time())
            query = session.query(ServeEntity).filter(
                ServeEntity.upload_cls.isnot(None),  # 需要自动更新的配置项
                ServeEntity.valid_time.isnot(None),  # valid_time必须有值
                ServeEntity.upload_retry < 6,  # 重试次数限制
                (
                    # 条件1: 无机器锁定且过期的配置项
                    (
                        ServeEntity.upload_instance.is_(None) &
                        (ServeEntity.upload_stamp + ServeEntity.valid_time < current_time)
                    ) |
                    # 条件2: 有机器锁定但超过3个有效期还未更新成功的配置项
                    (
                        ServeEntity.upload_instance.isnot(None) &
                        (ServeEntity.upload_stamp + ServeEntity.valid_time * 3 < current_time)
                    )
                )
            ).order_by(
                ServeEntity.upload_stamp.asc()  # 优先处理最久未更新的
            ).limit(batch_size)
            result = query.all()
            return [self.to_response(item) for item in result]

    def try_acquire_config(self, config: ServerResponse, force: bool = False) -> bool:
        """尝试锁定配置项进行更新

        Args:
            config: 配置响应对象
            force: 是否强制锁定（忽略时间条件），默认为 False
        """
        try:
            with self.session() as session:
                current_time = int(time.time())
                host, ip = get_local_host()

                # 使用行级锁（SELECT ... FOR UPDATE）
                entity = session.query(ServeEntity).filter(
                    ServeEntity.name == config.name
                ).with_for_update().first()

                if not entity:
                    return False

                # 如果强制模式开启，直接锁定
                if force :
                    entity.upload_instance = host
                    entity.upload_stamp = current_time
                    session.commit()
                    return True

                # 否则按原有逻辑判断是否满足更新条件
                if (entity.upload_instance is None and
                    entity.upload_stamp + entity.valid_time < current_time) or \
                    (entity.upload_instance is not None and
                     entity.upload_stamp + entity.valid_time * 3 < current_time):
                    entity.upload_instance = host
                    entity.upload_stamp = current_time
                    session.commit()
                    return True

                return False
        except Exception as e:
            logger.error(f"Error acquiring config {config.name}: {e}")
            return False

    def acquire_config(self) -> Optional[ServerResponse]:
        """获取一个需要更新的配置项"""
        configs = self.get_available_configs(batch_size=10)
        if not configs:
            logger.debug("No configs available for update")
            return None

        for config in configs:
            logger.info(f"Trying to acquire config: {config.name}")
            if self.try_acquire_config(config):
                logger.info(f"Successfully acquired config: {config.name}")
                return config

        return None

    def complete_config_update(self, config: ServerResponse, new_value: str, operator: Optional[str] = None):
        """完成配置更新"""
        try:
            with self.session() as session:
                rows_affected = session.query(ServeEntity).filter(
                    ServeEntity.name == config.name,
                    ServeEntity.upload_instance == get_local_host()[0]
                ).update({
                    ServeEntity.upload_stamp: int(time.time()),
                    ServeEntity.gmt_modified: datetime.now(),
                    ServeEntity.value: new_value,
                    ServeEntity.upload_retry: 0,
                    ServeEntity.upload_instance: None,
                    ServeEntity.operator: operator or "system",
                })
                session.commit()
                if rows_affected == 0:
                    logger.warning(f"No config updated for {config.name}, might have been modified by others")
        except Exception as e:
            logger.error(f"Error completing config update for {config.name}: {e}")
            raise

    def fail_config_update(self, config: ServerResponse):
        """标记配置更新失败"""
        try:
            with self.session() as session:
                session.query(ServeEntity).filter(
                    ServeEntity.name == config.name,
                    # 确保只更新由当前实例锁定的配置项
                    ServeEntity.upload_instance == get_local_host()[0]
                ).update({
                    ServeEntity.upload_retry: config.upload_retry + 1 if config.upload_retry else 1,
                    ServeEntity.upload_instance: None,  # 释放锁定
                    ServeEntity.upload_stamp: int(time.time())  # 更新时间戳，避免立即重试
                })
                session.commit()
        except Exception as e:
            logger.error(f"Error fail config update for {config.name}: {e}")
            raise
