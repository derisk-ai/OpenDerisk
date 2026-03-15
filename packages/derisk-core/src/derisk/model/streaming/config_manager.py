"""
Streaming Configuration Manager

配置管理器，支持：
1. 从数据库加载配置
2. 配置缓存
3. 动态更新
4. 与应用/工具绑定
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
import json

from .chunk_strategies import ChunkStrategy

logger = logging.getLogger(__name__)


@dataclass
class ParamStreamingConfig:
    """单个参数的流式配置"""

    param_name: str
    threshold: int = 256
    strategy: ChunkStrategy = ChunkStrategy.ADAPTIVE
    chunk_size: int = 100
    chunk_by_line: bool = True
    renderer: str = "default"
    enabled: bool = True
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "param_name": self.param_name,
            "threshold": self.threshold,
            "strategy": self.strategy.value,
            "chunk_size": self.chunk_size,
            "chunk_by_line": self.chunk_by_line,
            "renderer": self.renderer,
            "enabled": self.enabled,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParamStreamingConfig":
        return cls(
            param_name=data.get("param_name", ""),
            threshold=data.get("threshold", 256),
            strategy=ChunkStrategy(data.get("strategy", "adaptive")),
            chunk_size=data.get("chunk_size", 100),
            chunk_by_line=data.get("chunk_by_line", True),
            renderer=data.get("renderer", "default"),
            enabled=data.get("enabled", True),
            description=data.get("description"),
        )


@dataclass
class ToolStreamingConfig:
    """工具级别的流式配置"""

    tool_name: str
    app_code: str
    param_configs: Dict[str, ParamStreamingConfig] = field(default_factory=dict)
    global_threshold: int = 256
    global_strategy: ChunkStrategy = ChunkStrategy.ADAPTIVE
    global_renderer: str = "default"
    enabled: bool = True
    priority: int = 0

    def get_param_config(self, param_name: str) -> ParamStreamingConfig:
        """获取参数配置，返回全局配置作为默认"""
        if param_name in self.param_configs:
            return self.param_configs[param_name]

        # 返回全局默认配置
        return ParamStreamingConfig(
            param_name=param_name,
            threshold=self.global_threshold,
            strategy=self.global_strategy,
            renderer=self.global_renderer,
        )

    def should_stream(self, param_name: str, value: Any) -> bool:
        """判断参数是否应该流式传输"""
        if not self.enabled:
            return False

        if not isinstance(value, str):
            return False

        config = self.get_param_config(param_name)
        if not config.enabled:
            return False

        return len(value) >= config.threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "app_code": self.app_code,
            "param_configs": {k: v.to_dict() for k, v in self.param_configs.items()},
            "global_threshold": self.global_threshold,
            "global_strategy": self.global_strategy.value,
            "global_renderer": self.global_renderer,
            "enabled": self.enabled,
            "priority": self.priority,
        }


class StreamingConfigManager:
    """
    流式配置管理器

    核心功能：
    1. 从数据库/文件加载配置
    2. 配置缓存 (带 TTL)
    3. 动态更新通知
    4. 按应用/工具查询

    使用方式：
        manager = StreamingConfigManager(db_session)

        # 获取应用的流式配置
        config = manager.get_tool_config("app_001", "write")

        # 判断参数是否应该流式
        if config.should_stream("content", large_content):
            # 启用流式传输
    """

    # 默认配置 TTL (秒)
    DEFAULT_CACHE_TTL = 300  # 5分钟

    # 内置默认工具配置
    BUILTIN_TOOL_CONFIGS: Dict[str, Dict[str, Any]] = {
        "write": {
            "content": {"threshold": 1024, "strategy": "semantic", "renderer": "code"}
        },
        "edit": {
            "newString": {
                "threshold": 512,
                "strategy": "line_based",
                "renderer": "code",
            },
            "oldString": {
                "threshold": 512,
                "strategy": "line_based",
                "renderer": "code",
            },
        },
        "bash": {
            "command": {"threshold": 256, "strategy": "fixed_size", "renderer": "code"}
        },
        "execute_code": {
            "code": {"threshold": 512, "strategy": "semantic", "renderer": "code"}
        },
    }

    def __init__(
        self,
        db_session=None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ):
        """
        初始化配置管理器

        Args:
            db_session: 数据库会话
            cache_ttl: 缓存过期时间（秒）
        """
        self.db_session = db_session
        self.cache_ttl = cache_ttl

        # 配置缓存: {app_code: {tool_name: ToolStreamingConfig}}
        self._config_cache: Dict[str, Dict[str, ToolStreamingConfig]] = {}

        # 缓存时间戳
        self._cache_timestamps: Dict[str, datetime] = {}

        # 变更监听器
        self._change_listeners: List[callable] = []

    def get_tool_config(
        self,
        app_code: str,
        tool_name: str,
    ) -> ToolStreamingConfig:
        """
        获取工具的流式配置

        优先级：
        1. 应用级数据库配置
        2. 内置默认配置
        3. 全局默认配置

        Args:
            app_code: 应用代码
            tool_name: 工具名称

        Returns:
            ToolStreamingConfig: 工具流式配置
        """
        # 检查缓存
        cache_key = f"{app_code}:{tool_name}"

        if self._is_cache_valid(app_code):
            app_configs = self._config_cache.get(app_code, {})
            if tool_name in app_configs:
                return app_configs[tool_name]

        # 从数据库加载
        db_config = self._load_from_db(app_code, tool_name)
        if db_config:
            self._update_cache(app_code, tool_name, db_config)
            return db_config

        # 使用内置默认配置
        default_config = self._get_builtin_config(app_code, tool_name)
        self._update_cache(app_code, tool_name, default_config)
        return default_config

    def get_app_configs(self, app_code: str) -> Dict[str, ToolStreamingConfig]:
        """
        获取应用的所有工具流式配置

        Args:
            app_code: 应用代码

        Returns:
            Dict[str, ToolStreamingConfig]: 工具名 -> 配置
        """
        # 检查缓存
        if self._is_cache_valid(app_code):
            return self._config_cache.get(app_code, {})

        # 从数据库加载所有配置
        configs = self._load_all_from_db(app_code)

        # 合并内置配置
        for tool_name, builtin_config in self.BUILTIN_TOOL_CONFIGS.items():
            if tool_name not in configs:
                configs[tool_name] = self._create_tool_config_from_builtin(
                    app_code, tool_name, builtin_config
                )

        # 更新缓存
        self._config_cache[app_code] = configs
        self._cache_timestamps[app_code] = datetime.now()

        return configs

    def save_tool_config(
        self,
        app_code: str,
        tool_name: str,
        config: ToolStreamingConfig,
    ) -> bool:
        """
        保存工具流式配置到数据库

        Args:
            app_code: 应用代码
            tool_name: 工具名称
            config: 配置对象

        Returns:
            bool: 是否保存成功
        """
        if not self.db_session:
            logger.warning("[StreamingConfigManager] No db_session, config not saved")
            return False

        try:
            from .db_models import StreamingToolConfig

            # 查找现有配置
            existing = (
                self.db_session.query(StreamingToolConfig)
                .filter(
                    StreamingToolConfig.app_code == app_code,
                    StreamingToolConfig.tool_name == tool_name,
                )
                .first()
            )

            if existing:
                # 更新现有配置
                existing.param_configs = {
                    k: v.to_dict() for k, v in config.param_configs.items()
                }
                existing.global_threshold = config.global_threshold
                existing.global_strategy = config.global_strategy.value
                existing.global_renderer = config.global_renderer
                existing.enabled = config.enabled
                existing.priority = config.priority
                existing.updated_at = datetime.now()
            else:
                # 创建新配置
                new_config = StreamingToolConfig(
                    app_code=app_code,
                    tool_name=tool_name,
                    param_configs={
                        k: v.to_dict() for k, v in config.param_configs.items()
                    },
                    global_threshold=config.global_threshold,
                    global_strategy=config.global_strategy.value,
                    global_renderer=config.global_renderer,
                    enabled=config.enabled,
                    priority=config.priority,
                )
                self.db_session.add(new_config)

            self.db_session.commit()

            # 更新缓存
            self._update_cache(app_code, tool_name, config)

            # 通知变更
            self._notify_change(app_code, tool_name, config)

            logger.info(
                f"[StreamingConfigManager] Saved config for {app_code}/{tool_name}"
            )
            return True

        except Exception as e:
            logger.error(f"[StreamingConfigManager] Error saving config: {e}")
            self.db_session.rollback()
            return False

    def delete_tool_config(self, app_code: str, tool_name: str) -> bool:
        """删除工具流式配置"""
        if not self.db_session:
            return False

        try:
            from .db_models import StreamingToolConfig

            self.db_session.query(StreamingToolConfig).filter(
                StreamingToolConfig.app_code == app_code,
                StreamingToolConfig.tool_name == tool_name,
            ).delete()

            self.db_session.commit()

            # 清除缓存
            if (
                app_code in self._config_cache
                and tool_name in self._config_cache[app_code]
            ):
                del self._config_cache[app_code][tool_name]

            return True

        except Exception as e:
            logger.error(f"[StreamingConfigManager] Error deleting config: {e}")
            self.db_session.rollback()
            return False

    def invalidate_cache(self, app_code: Optional[str] = None):
        """使缓存失效"""
        if app_code:
            self._config_cache.pop(app_code, None)
            self._cache_timestamps.pop(app_code, None)
        else:
            self._config_cache.clear()
            self._cache_timestamps.clear()

    def add_change_listener(self, listener: callable):
        """添加配置变更监听器"""
        self._change_listeners.append(listener)

    # ========== 私有方法 ==========

    def _is_cache_valid(self, app_code: str) -> bool:
        """检查缓存是否有效"""
        if app_code not in self._cache_timestamps:
            return False

        elapsed = datetime.now() - self._cache_timestamps[app_code]
        return elapsed.total_seconds() < self.cache_ttl

    def _update_cache(self, app_code: str, tool_name: str, config: ToolStreamingConfig):
        """更新缓存"""
        if app_code not in self._config_cache:
            self._config_cache[app_code] = {}

        self._config_cache[app_code][tool_name] = config
        self._cache_timestamps[app_code] = datetime.now()

    def _load_from_db(
        self, app_code: str, tool_name: str
    ) -> Optional[ToolStreamingConfig]:
        """从数据库加载配置"""
        if not self.db_session:
            return None

        try:
            from .db_models import StreamingToolConfig

            record = (
                self.db_session.query(StreamingToolConfig)
                .filter(
                    StreamingToolConfig.app_code == app_code,
                    StreamingToolConfig.tool_name == tool_name,
                )
                .first()
            )

            if not record:
                return None

            return self._record_to_config(record)

        except Exception as e:
            logger.error(f"[StreamingConfigManager] Error loading from DB: {e}")
            return None

    def _load_all_from_db(self, app_code: str) -> Dict[str, ToolStreamingConfig]:
        """从数据库加载应用的所有配置"""
        if not self.db_session:
            return {}

        try:
            from .db_models import StreamingToolConfig

            records = (
                self.db_session.query(StreamingToolConfig)
                .filter(
                    StreamingToolConfig.app_code == app_code,
                )
                .all()
            )

            return {r.tool_name: self._record_to_config(r) for r in records}

        except Exception as e:
            logger.error(f"[StreamingConfigManager] Error loading all from DB: {e}")
            return {}

    def _record_to_config(self, record) -> ToolStreamingConfig:
        """将数据库记录转换为配置对象"""
        param_configs = {}
        for param_name, param_data in (record.param_configs or {}).items():
            param_configs[param_name] = ParamStreamingConfig.from_dict(param_data)

        return ToolStreamingConfig(
            tool_name=record.tool_name,
            app_code=record.app_code,
            param_configs=param_configs,
            global_threshold=record.global_threshold or 256,
            global_strategy=ChunkStrategy(record.global_strategy or "adaptive"),
            global_renderer=record.global_renderer or "default",
            enabled=record.enabled,
            priority=record.priority or 0,
        )

    def _get_builtin_config(self, app_code: str, tool_name: str) -> ToolStreamingConfig:
        """获取内置默认配置"""
        builtin = self.BUILTIN_TOOL_CONFIGS.get(tool_name, {})
        return self._create_tool_config_from_builtin(app_code, tool_name, builtin)

    def _create_tool_config_from_builtin(
        self, app_code: str, tool_name: str, builtin: Dict[str, Any]
    ) -> ToolStreamingConfig:
        """从内置配置创建工具配置对象"""
        param_configs = {}
        for param_name, param_data in builtin.items():
            param_configs[param_name] = ParamStreamingConfig(
                param_name=param_name,
                threshold=param_data.get("threshold", 256),
                strategy=ChunkStrategy(param_data.get("strategy", "adaptive")),
                renderer=param_data.get("renderer", "default"),
            )

        return ToolStreamingConfig(
            tool_name=tool_name,
            app_code=app_code,
            param_configs=param_configs,
        )

    def _notify_change(
        self, app_code: str, tool_name: str, config: ToolStreamingConfig
    ):
        """通知配置变更"""
        for listener in self._change_listeners:
            try:
                listener(app_code, tool_name, config)
            except Exception as e:
                logger.error(f"[StreamingConfigManager] Listener error: {e}")


# 全局配置管理器实例
_config_manager: Optional[StreamingConfigManager] = None


def get_config_manager() -> StreamingConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = StreamingConfigManager()
    return _config_manager


def set_config_manager(manager: StreamingConfigManager):
    """设置全局配置管理器"""
    global _config_manager
    _config_manager = manager
