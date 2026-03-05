from typing import List, Tuple
from pathlib import Path
from .schema import AppConfig

class ConfigValidator:
    """配置验证器"""
    
    @staticmethod
    def validate(config: AppConfig) -> List[Tuple[str, str]]:
        """验证配置，返回警告列表 [(level, message)]"""
        warnings = []
        
        if not config.default_model.api_key:
            warnings.append(("warn", "未配置API Key，请设置 OPENAI_API_KEY 环境变量或在配置中指定"))
        
        workspace = Path(config.workspace)
        if not workspace.exists():
            warnings.append(("info", f"工作目录不存在，将创建: {workspace}"))
        
        if config.sandbox.enabled:
            warnings.append(("info", "沙箱模式已启用，工具将在Docker容器中执行"))
        
        return warnings
    
    @staticmethod
    def diagnose() -> List[Tuple[str, str]]:
        """诊断配置问题"""
        from .loader import ConfigManager
        config = ConfigManager.get()
        return ConfigValidator.validate(config)