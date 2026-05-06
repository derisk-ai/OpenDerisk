"""Data access layer for system configuration."""

import json
import logging
from typing import Any, Dict, Optional

from derisk.storage.metadata.db_manager import db

from .system_config_model import SystemConfigEntity

logger = logging.getLogger(__name__)


class SystemConfigDao:
    """系统配置数据访问层"""

    def get_config(self, config_key: str, config_type: str = "feature_plugin") -> Optional[Dict[str, Any]]:
        """获取配置项"""
        with db.session(commit=False) as s:
            config = s.query(SystemConfigEntity).filter(
                SystemConfigEntity.config_key == config_key,
                SystemConfigEntity.config_type == config_type
            ).first()
            if config and config.config_value:
                try:
                    return json.loads(config.config_value)
                except (json.JSONDecodeError, TypeError):
                    return None
            return None

    def set_config(
        self,
        config_key: str,
        config_value: Dict[str, Any],
        config_type: str = "feature_plugin",
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """设置配置项（upsert）"""
        with db.session() as s:
            config = s.query(SystemConfigEntity).filter(
                SystemConfigEntity.config_key == config_key,
                SystemConfigEntity.config_type == config_type
            ).first()

            value_json = json.dumps(config_value, ensure_ascii=False)

            if config:
                config.config_value = value_json
                if description:
                    config.description = description
                s.flush()
                s.refresh(config)
            else:
                config = SystemConfigEntity(
                    config_key=config_key,
                    config_value=value_json,
                    config_type=config_type,
                    description=description
                )
                s.add(config)
                s.flush()
                s.refresh(config)

            return {
                "id": config.id,
                "config_key": config.config_key,
                "config_value": json.loads(config.config_value) if config.config_value else {},
                "config_type": config.config_type,
            }

    def delete_config(self, config_key: str, config_type: str = "feature_plugin") -> bool:
        """删除配置项"""
        with db.session() as s:
            config = s.query(SystemConfigEntity).filter(
                SystemConfigEntity.config_key == config_key,
                SystemConfigEntity.config_type == config_type
            ).first()
            if config:
                s.delete(config)
                return True
            return False

    def get_all_configs(self, config_type: str = "feature_plugin") -> Dict[str, Dict[str, Any]]:
        """获取所有指定类型的配置"""
        with db.session(commit=False) as s:
            configs = s.query(SystemConfigEntity).filter(
                SystemConfigEntity.config_type == config_type
            ).all()

            result = {}
            for config in configs:
                if config.config_value:
                    try:
                        result[config.config_key] = json.loads(config.config_value)
                    except (json.JSONDecodeError, TypeError):
                        result[config.config_key] = {}
                else:
                    result[config.config_key] = {}
            return result