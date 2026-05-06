"""Database model for system configuration storage."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from derisk.storage.metadata import Model


class SystemConfigEntity(Model):
    """系统配置表 - 用于存储功能插件等系统配置状态"""

    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(128), unique=True, nullable=False, comment="配置键名")
    config_value = Column(Text, nullable=True, comment="配置值（JSON 格式）")
    config_type = Column(String(32), default="feature_plugin", comment="配置类型")
    description = Column(String(512), nullable=True, comment="配置描述")
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    gmt_modify = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="修改时间"
    )