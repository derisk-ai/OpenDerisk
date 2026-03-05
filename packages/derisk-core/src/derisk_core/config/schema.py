from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from pathlib import Path
from enum import Enum

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ALIBABA = "alibaba"
    CUSTOM = "custom"

class ModelConfig(BaseModel):
    """模型配置"""
    provider: LLMProvider = LLMProvider.OPENAI
    model_id: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    
class PermissionConfig(BaseModel):
    """权限配置"""
    default_action: str = "ask"
    rules: Dict[str, str] = Field(default_factory=lambda: {
        "*": "allow",
        "*.env": "ask",
        "*.secret*": "ask",
    })

class SandboxConfig(BaseModel):
    """沙箱配置"""
    enabled: bool = False
    image: str = "python:3.11-slim"
    memory_limit: str = "512m"
    timeout: int = 300
    network_enabled: bool = False

class AgentConfig(BaseModel):
    """单个Agent配置"""
    name: str = "primary"
    description: str = ""
    model: Optional[ModelConfig] = None
    permission: PermissionConfig = Field(default_factory=PermissionConfig)
    max_steps: int = 20
    color: str = "#4A90E2"

class AppConfig(BaseModel):
    """应用主配置"""
    name: str = "OpenDeRisk"
    version: str = "0.1.0"
    
    default_model: ModelConfig = Field(default_factory=ModelConfig)
    
    agents: Dict[str, AgentConfig] = Field(default_factory=lambda: {
        "primary": AgentConfig(name="primary", description="主Agent")
    })
    
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    
    workspace: str = str(Path.home() / ".derisk" / "workspace")
    
    log_level: str = "INFO"
    
    server: Dict[str, Any] = Field(default_factory=lambda: {
        "host": "127.0.0.1",
        "port": 7777
    })
    
    class Config:
        extra = "allow"