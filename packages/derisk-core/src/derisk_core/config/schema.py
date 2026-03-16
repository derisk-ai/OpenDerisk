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


class OAuth2ProviderType(str, Enum):
    """OAuth2 提供商类型"""
    GITHUB = "github"
    CUSTOM = "custom"


class OAuth2ProviderConfig(BaseModel):
    """OAuth2 提供商配置"""
    id: str = "github"
    type: OAuth2ProviderType = OAuth2ProviderType.GITHUB
    client_id: str = ""
    client_secret: str = ""
    # custom 类型必填
    authorization_url: Optional[str] = None
    token_url: Optional[str] = None
    userinfo_url: Optional[str] = None
    scope: Optional[str] = None


class OAuth2Config(BaseModel):
    """OAuth2 登录配置"""
    enabled: bool = False
    providers: List[OAuth2ProviderConfig] = Field(default_factory=list)
    admin_users: List[str] = Field(
        default_factory=list,
        description="初始管理员列表，填写 OAuth 登录后的用户名（GitHub login）",
    )


class AppConfig(BaseModel):
    """应用主配置"""
    name: str = "OpenDeRisk"
    version: str = "0.1.0"
    
    default_model: ModelConfig = Field(default_factory=ModelConfig)
    
    agents: Dict[str, AgentConfig] = Field(default_factory=lambda: {
        "primary": AgentConfig(name="primary", description="主Agent")
    })
    
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    
    oauth2: Optional[OAuth2Config] = Field(default_factory=OAuth2Config)
    
    workspace: str = str(Path.home() / ".derisk" / "workspace")
    
    log_level: str = "INFO"
    
    server: Dict[str, Any] = Field(default_factory=lambda: {
        "host": "127.0.0.1",
        "port": 7777
    })
    
    class Config:
        extra = "allow"