import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
from .schema import AppConfig

class ConfigLoader:
    """配置加载器 - 简化配置体验"""
    
    DEFAULT_CONFIG_NAME = "derisk.json"
    DEFAULT_LOCATIONS = [
        Path.cwd() / "derisk.json",
        Path.home() / ".derisk" / "config.json",
        Path.home() / ".derisk" / "derisk.json",
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
                pattern = r'\$\{([^}]+)\}'
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
            json.dump(config.model_dump(mode="json", exclude_none=True), f, indent=2, ensure_ascii=False)
    
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
    
    @classmethod
    def get(cls) -> AppConfig:
        """获取当前配置"""
        if cls._config is None:
            cls._config = ConfigLoader.load()
        return cls._config
    
    @classmethod
    def init(cls, path: Optional[str] = None) -> AppConfig:
        """初始化配置"""
        cls._config = ConfigLoader.load(path)
        return cls._config
    
    @classmethod
    def reload(cls, path: Optional[str] = None) -> AppConfig:
        """重新加载配置"""
        cls._config = None
        return cls.get()