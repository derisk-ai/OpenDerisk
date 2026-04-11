import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
from .home import get_derisk_home
from .schema import AppConfig

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器 - 简化配置体验"""

    DEFAULT_CONFIG_NAME = "derisk.json"
    # 默认配置文件路径优先级：用户目录下的 .derisk/derisk.json
    DEFAULT_CONFIG_PATH = get_derisk_home() / "derisk.json"

    DEFAULT_LOCATIONS = [
        get_derisk_home() / "derisk.json",  # 优先级最高
        Path.cwd() / "derisk.json",
        get_derisk_home() / "config.json",
    ]

    @classmethod
    def load(cls, path: Optional[str] = None) -> AppConfig:
        """加载配置

        查找顺序：
        1. 指定的路径
        2. 当前目录的 derisk.json
        3. ~/.derisk/config.json
        4. ~/.derisk/derisk.json
        """
        if path:
            return cls._load_from_path(Path(path))

        for location in cls.DEFAULT_LOCATIONS:
            if location.exists():
                return cls._load_from_path(location)

        return cls._load_defaults()

    @classmethod
    def _load_from_path(cls, path: Path) -> AppConfig:
        """从指定路径加载"""
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data = cls._resolve_env_vars(data)

        return AppConfig(**data)

    @classmethod
    def _load_defaults(cls) -> AppConfig:
        """加载默认配置"""
        config = AppConfig()

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            config.default_model.api_key = api_key

        return config

    @classmethod
    def _resolve_env_vars(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析环境变量 ${VAR_NAME} 格式"""

        def resolve_value(value):
            if isinstance(value, str):
                pattern = r"\$\{([^}]+)\}"

                def replace(match):
                    var_name = match.group(1)
                    return os.getenv(var_name, match.group(0))

                return re.sub(pattern, replace, value)
            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(item) for item in value]
            return value

        return resolve_value(data)

    @classmethod
    def save(cls, config: AppConfig, path: str) -> None:
        """保存配置"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                config.model_dump(mode="json", exclude_none=True),
                f,
                indent=2,
                ensure_ascii=False,
            )

    @classmethod
    def generate_default(cls, path: str) -> None:
        """生成默认配置文件"""
        config = AppConfig()
        cls.save(config, path)
        print(f"已生成默认配置文件: {path}")


class ConfigManager:
    """配置管理器 - 全局配置访问"""

    _instance = None
    _config: Optional[AppConfig] = None
    _config_path: Optional[str] = None
    _auto_save: bool = True  # 是否在修改时自动保存

    @classmethod
    def get_default_config_path(cls) -> str:
        """获取默认配置文件路径"""
        return str(ConfigLoader.DEFAULT_CONFIG_PATH)

    @classmethod
    def get(cls) -> AppConfig:
        """获取当前配置"""
        if cls._config is None:
            loaded_path = None
            for location in ConfigLoader.DEFAULT_LOCATIONS:
                if location.exists():
                    cls._config_path = str(location)
                    loaded_path = location
                    break
            cls._config = ConfigLoader.load(str(loaded_path) if loaded_path else None)
        return cls._config

    @classmethod
    def init(cls, path: Optional[str] = None, auto_save: bool = True) -> AppConfig:
        """初始化配置

        Args:
            path: 配置文件路径，如果为 None 则使用默认路径
            auto_save: 是否在修改配置时自动保存
        """
        cls._auto_save = auto_save

        if path is None:
            path = cls.get_default_config_path()

        if not Path(path).exists():
            logger.info(f"配置文件不存在，将创建默认配置: {path}")
            cls._ensure_default_config()

        cls._config_path = path
        cls._config = ConfigLoader.load(path)
        logger.info(f"配置已加载: {path}")
        return cls._config

    @classmethod
    def _ensure_default_config(cls) -> None:
        """确保默认配置文件存在"""
        path = Path(cls.get_default_config_path())
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            config = AppConfig()
            ConfigLoader.save(config, str(path))
            logger.info(f"已创建默认配置文件: {path}")

    @classmethod
    def reload(cls, path: Optional[str] = None) -> AppConfig:
        """重新加载配置（从文件重新读取）"""
        load_path = path or cls._config_path
        if load_path is None:
            load_path = cls.get_default_config_path()

        cls._config_path = load_path
        cls._config = ConfigLoader.load(load_path)
        logger.info(f"配置已重新加载: {load_path}")
        return cls._config

    @classmethod
    def save(cls, path: Optional[str] = None) -> None:
        """保存当前配置到文件"""
        if cls._config is None:
            raise RuntimeError("No config to save")
        save_path = path or cls._config_path
        if save_path is None:
            save_path = cls.get_default_config_path()

        path_obj = Path(save_path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        ConfigLoader.save(cls._config, str(path_obj))
        cls._config_path = str(path_obj)
        logger.info(f"配置已保存: {save_path}")

    @classmethod
    def update_and_save(cls, updates: Dict[str, Any]) -> AppConfig:
        """更新配置并保存到文件

        Args:
            updates: 要更新的配置项（支持嵌套，如 {"default_model.temperature": 0.5}）

        Returns:
            更新后的配置
        """
        if cls._config is None:
            cls._config = cls.get()

        for key, value in updates.items():
            cls._set_nested_value(cls._config, key, value)

        if cls._auto_save:
            cls.save()

        return cls._config

    @classmethod
    def _set_nested_value(cls, obj: Any, key: str, value: Any) -> None:
        """设置嵌套属性的值"""
        parts = key.split(".")
        current = obj

        for part in parts[:-1]:
            if hasattr(current, part):
                current = getattr(current, part)
            else:
                raise ValueError(f"Invalid config path: {key}")

        final_key = parts[-1]
        if hasattr(current, final_key):
            setattr(current, final_key, value)
        else:
            raise ValueError(f"Invalid config path: {key}")

    @classmethod
    def get_config_path(cls) -> Optional[str]:
        """获取当前配置文件路径"""
        return cls._config_path
