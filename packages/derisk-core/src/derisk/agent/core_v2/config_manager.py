"""
ConfigManager - 配置管理系统

实现配置的加载、验证、热更新、版本管理
支持多种配置源和格式
"""

from typing import Dict, Any, List, Optional, Callable, TypeVar, Generic
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum
import json
import yaml
import os
import copy
import hashlib
import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass, field as dataclass_field

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConfigSource(str, Enum):
    """配置来源"""
    FILE = "file"
    ENV = "environment"
    ENVIRONMENT = "environment"
    DEFAULT = "default"
    RUNTIME = "runtime"
    DATABASE = "database"


class ConfigChange(BaseModel):
    """配置变更"""
    key: str
    old_value: Any
    new_value: Any
    source: ConfigSource
    timestamp: datetime = Field(default_factory=datetime.now)
    changed_by: Optional[str] = None


@dataclass
class ConfigVersion:
    """配置版本"""
    version: str
    config: Dict[str, Any]
    timestamp: datetime = dataclass_field(default_factory=datetime.now)
    checksum: str = ""
    source: ConfigSource = ConfigSource.DEFAULT
    
    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._compute_checksum()
    
    def _compute_checksum(self) -> str:
        config_str = json.dumps(self.config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()


class AgentConfig(BaseModel):
    """Agent配置"""
    name: str = "default"
    version: str = "1.0.0"
    
    model_provider: str = "openai"
    model_name: str = "gpt-4"
    model_temperature: float = 0.7
    model_max_tokens: int = 4096
    
    max_steps: int = 20
    timeout: int = 60
    
    enable_memory: bool = True
    memory_max_messages: int = 100
    
    enable_tools: bool = True
    enable_sandbox: bool = False
    
    enable_observability: bool = True
    log_level: str = "INFO"
    
    reasoning_strategy: str = "react"
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConfigSchema(BaseModel):
    """配置Schema"""
    name: str
    type: str
    default: Any = None
    description: str = ""
    required: bool = False
    validation: Optional[Dict[str, Any]] = None
    
    env_key: Optional[str] = None
    sensitive: bool = False


class ConfigLoader:
    """配置加载器"""
    
    @staticmethod
    def from_file(path: str, format: Optional[str] = None) -> Dict[str, Any]:
        """从文件加载"""
        path_obj = Path(path)
        
        if not path_obj.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        if format is None:
            format = path_obj.suffix.lstrip(".")
        
        content = path_obj.read_text()
        
        if format in ["yaml", "yml"]:
            return yaml.safe_load(content)
        elif format in ["json"]:
            return json.loads(content)
        else:
            raise ValueError(f"Unsupported config format: {format}")
    
    @staticmethod
    def from_env(prefix: str = "AGENT_") -> Dict[str, Any]:
        """从环境变量加载"""
        config = {}
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                config[config_key] = ConfigLoader._parse_env_value(value)
        
        return config
    
    @staticmethod
    def _parse_env_value(value: str) -> Any:
        """解析环境变量值"""
        if value.lower() in ["true", "yes", "1"]:
            return True
        elif value.lower() in ["false", "no", "0"]:
            return False
        
        try:
            return int(value)
        except ValueError:
            pass
        
        try:
            return float(value)
        except ValueError:
            pass
        
        if value.startswith("[") or value.startswith("{"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        return value


class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        self._validators: Dict[str, Callable[[Any], bool]] = {}
    
    def register_validator(self, key: str, validator: Callable[[Any], bool]):
        """注册验证器"""
        self._validators[key] = validator
    
    def validate(
        self,
        config: Dict[str, Any],
        schema: Optional[Dict[str, ConfigSchema]] = None
    ) -> List[str]:
        """验证配置"""
        errors = []
        
        if schema:
            for key, sch in schema.items():
                if sch.required and key not in config:
                    errors.append(f"Missing required config: {key}")
                    continue
                
                if key in config:
                    value = config[key]
                    
                    if sch.type == "int":
                        if not isinstance(value, int):
                            errors.append(f"Config {key} should be int, got {type(value)}")
                    elif sch.type == "float":
                        if not isinstance(value, (int, float)):
                            errors.append(f"Config {key} should be float, got {type(value)}")
                    elif sch.type == "bool":
                        if not isinstance(value, bool):
                            errors.append(f"Config {key} should be bool, got {type(value)}")
                    elif sch.type == "str":
                        if not isinstance(value, str):
                            errors.append(f"Config {key} should be str, got {type(value)}")
                    
                    if sch.validation:
                        min_val = sch.validation.get("min")
                        max_val = sch.validation.get("max")
                        
                        if min_val is not None and value < min_val:
                            errors.append(f"Config {key} value {value} < min {min_val}")
                        
                        if max_val is not None and value > max_val:
                            errors.append(f"Config {key} value {value} > max {max_val}")
        
        for key, validator in self._validators.items():
            if key in config:
                try:
                    if not validator(config[key]):
                        errors.append(f"Config {key} validation failed")
                except Exception as e:
                    errors.append(f"Config {key} validation error: {e}")
        
        return errors


class ConfigManager:
    """
    配置管理器
    
    职责：
    1. 多源配置加载
    2. 配置合并
    3. 配置验证
    4. 配置热更新
    5. 版本管理
    
    示例:
        config = ConfigManager()
        
        config.load_file("config.yaml")
        config.load_env("AGENT_")
        
        model_name = config.get("model_name")
        config.set("temperature", 0.8)
        
        config.watch_file("config.yaml", callback=on_change)
    """
    
    def __init__(
        self,
        default_config: Optional[Dict[str, Any]] = None,
        enable_hot_reload: bool = False
    ):
        self._config: Dict[str, Any] = default_config or {}
        self._sources: Dict[str, ConfigSource] = {}
        self._versions: List[ConfigVersion] = []
        self._watchers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._validator = ConfigValidator()
        self._enable_hot_reload = enable_hot_reload
        
        self._watch_tasks: Dict[str, asyncio.Task] = {}
        self._change_history: List[ConfigChange] = []
    
    def load_file(
        self,
        path: str,
        format: Optional[str] = None,
        merge: bool = True
    ) -> Dict[str, Any]:
        """加载文件配置"""
        loaded = ConfigLoader.from_file(path, format)
        
        if merge:
            self._merge_config(loaded, ConfigSource.FILE)
        else:
            self._config = loaded
            self._sources = {k: ConfigSource.FILE for k in loaded}
        
        self._save_version(ConfigSource.FILE)
        
        logger.info(f"[ConfigManager] 加载配置文件: {path}")
        return loaded
    
    def load_env(self, prefix: str = "AGENT_", merge: bool = True) -> Dict[str, Any]:
        """加载环境变量配置"""
        loaded = ConfigLoader.from_env(prefix)
        
        if merge:
            self._merge_config(loaded, ConfigSource.ENVIRONMENT)
        else:
            self._config = loaded
            self._sources = {k: ConfigSource.ENVIRONMENT for k in loaded}
        
        self._save_version(ConfigSource.ENVIRONMENT)
        
        logger.info(f"[ConfigManager] 加载环境变量: {len(loaded)}项")
        return loaded
    
    def set(
        self,
        key: str,
        value: Any,
        source: ConfigSource = ConfigSource.RUNTIME,
        notify: bool = True
    ):
        """设置配置"""
        old_value = self._config.get(key)
        
        self._config[key] = value
        self._sources[key] = source
        
        change = ConfigChange(
            key=key,
            old_value=old_value,
            new_value=value,
            source=source
        )
        self._change_history.append(change)
        
        if notify:
            self._notify_watchers(key)
        
        logger.debug(f"[ConfigManager] 设置配置: {key}={value}")
    
    def get(
        self,
        key: str,
        default: Any = None,
        sensitive: bool = False
    ) -> Any:
        """获取配置"""
        value = self._config.get(key, default)
        
        if sensitive and value is not None:
            return self._mask_sensitive(str(value))
        
        return value
    
    def get_all(self, sensitive: bool = False) -> Dict[str, Any]:
        """获取所有配置"""
        if not sensitive:
            return copy.deepcopy(self._config)
        
        masked = {}
        for key, value in self._config.items():
            if self._is_sensitive_key(key):
                masked[key] = self._mask_sensitive(str(value))
            else:
                masked[key] = value
        
        return masked
    
    def delete(self, key: str, notify: bool = True):
        """删除配置"""
        if key in self._config:
            old_value = self._config.pop(key)
            self._sources.pop(key, None)
            
            change = ConfigChange(
                key=key,
                old_value=old_value,
                new_value=None,
                source=ConfigSource.RUNTIME
            )
            self._change_history.append(change)
            
            if notify:
                self._notify_watchers(key)
    
    def watch(
        self,
        key: str,
        callback: Callable[[Any, Any], None]
    ):
        """监听配置变化"""
        if key not in self._watchers:
            self._watchers[key] = []
        
        self._watchers[key].append(callback)
    
    def unwatch(self, key: str, callback: Optional[Callable] = None):
        """取消监听"""
        if key not in self._watchers:
            return
        
        if callback:
            if callback in self._watchers[key]:
                self._watchers[key].remove(callback)
        else:
            self._watchers.pop(key, None)
    
    def _notify_watchers(self, key: str):
        """通知监听器"""
        if key in self._watchers:
            value = self._config.get(key)
            for callback in self._watchers[key]:
                try:
                    callback(key, value)
                except Exception as e:
                    logger.error(f"[ConfigManager] Watcher callback error: {e}")
    
    def _merge_config(self, new_config: Dict[str, Any], source: ConfigSource):
        """合并配置"""
        for key, value in new_config.items():
            self._config[key] = value
            self._sources[key] = source
    
    def _save_version(self, source: ConfigSource):
        """保存版本"""
        version = ConfigVersion(
            version=f"v{len(self._versions) + 1}",
            config=copy.deepcopy(self._config),
            source=source
        )
        self._versions.append(version)
    
    def _is_sensitive_key(self, key: str) -> bool:
        """判断是否是敏感Key"""
        sensitive_keywords = [
            "password", "secret", "key", "token", "credential",
            "api_key", "access_key", "private"
        ]
        key_lower = key.lower()
        return any(kw in key_lower for kw in sensitive_keywords)
    
    def _mask_sensitive(self, value: str) -> str:
        """掩码敏感值"""
        if len(value) <= 4:
            return "****"
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    
    def validate(
        self,
        schema: Optional[Dict[str, ConfigSchema]] = None
    ) -> List[str]:
        """验证配置"""
        return self._validator.validate(self._config, schema)
    
    def list_versions(self, limit: int = 10) -> List[ConfigVersion]:
        """列出版本历史"""
        return self._versions[-limit:]
    
    def restore_version(self, version: str) -> bool:
        """恢复到指定版本"""
        for v in reversed(self._versions):
            if v.version == version:
                self._config = copy.deepcopy(v.config)
                self._save_version(ConfigSource.RUNTIME)
                logger.info(f"[ConfigManager] 恢复到版本: {version}")
                return True
        return False
    
    def get_change_history(
        self,
        key: Optional[str] = None,
        limit: int = 100
    ) -> List[ConfigChange]:
        """获取变更历史"""
        history = self._change_history
        
        if key:
            history = [c for c in history if c.key == key]
        
        return history[-limit:]
    
    def export(
        self,
        format: str = "json",
        path: Optional[str] = None
    ) -> str:
        """导出配置"""
        if format == "json":
            content = json.dumps(self._config, indent=2, default=str)
        elif format in ["yaml", "yml"]:
            content = yaml.dump(self._config, default_flow_style=False)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        if path:
            Path(path).write_text(content)
            logger.info(f"[ConfigManager] 导出配置到: {path}")
        
        return content
    
    def reset(self):
        """重置配置"""
        self._config.clear()
        self._sources.clear()
        self._versions.clear()
        self._change_history.clear()
        self._watchers.clear()
        logger.info("[ConfigManager] 配置已重置")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        by_source = {}
        for source in self._sources.values():
            by_source[source.value] = by_source.get(source.value, 0) + 1
        
        return {
            "total_keys": len(self._config),
            "by_source": by_source,
            "version_count": len(self._versions),
            "change_count": len(self._change_history),
            "watcher_count": sum(len(w) for w in self._watchers.values()),
        }


class GlobalConfig:
    """全局配置"""
    
    _instance: Optional[ConfigManager] = None
    
    @classmethod
    def get_instance(cls) -> ConfigManager:
        if cls._instance is None:
            cls._instance = ConfigManager()
        return cls._instance
    
    @classmethod
    def initialize(cls, config: Optional[Dict[str, Any]] = None):
        cls._instance = ConfigManager(default_config=config)
    
    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        return cls.get_instance().get(key, default)
    
    @classmethod
    def set(cls, key: str, value: Any):
        cls.get_instance().set(key, value)


def get_config(key: str, default: Any = None) -> Any:
    """便捷函数：获取配置"""
    return GlobalConfig.get(key, default)


def set_config(key: str, value: Any):
    """便捷函数：设置配置"""
    GlobalConfig.set(key, value)


config_manager = ConfigManager()