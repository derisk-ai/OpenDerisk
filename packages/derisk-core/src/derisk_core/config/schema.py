from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from pathlib import Path
from enum import Enum
import base64
import json


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ALIBABA = "alibaba"
    CUSTOM = "custom"


class ModelConfig(BaseModel):
    """模型配置"""

    provider: str = "openai"
    model_id: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096


class PermissionConfig(BaseModel):
    """权限配置"""

    default_action: str = "ask"
    rules: Dict[str, str] = Field(
        default_factory=lambda: {
            "*": "allow",
            "*.env": "ask",
            "*.secret*": "ask",
        }
    )


class SandboxConfig(BaseModel):
    """沙箱配置"""

    enabled: bool = False
    type: str = "local"
    image: str = "python:3.11-slim"
    memory_limit: str = "512m"
    timeout: int = 300
    network_enabled: bool = False
    # 为空时使用运行时默认路径: local 模式为 pilot/data/workspace
    work_dir: str = ""
    agent_name: str = "default"
    user_id: Optional[str] = None
    template_id: Optional[str] = None
    # 为空时使用运行时默认路径: local 模式为 pilot/data/skill
    skill_dir: Optional[str] = None
    oss_ak: Optional[str] = None
    oss_sk: Optional[str] = None
    oss_endpoint: Optional[str] = None
    oss_bucket_name: Optional[str] = None


class AgentConfig(BaseModel):
    """单个Agent配置"""

    name: str = "primary"
    description: str = ""
    model: Optional[ModelConfig] = None
    permission: PermissionConfig = Field(default_factory=PermissionConfig)
    max_steps: int = 20
    color: str = "#4A90E2"
    tools: List[str] = Field(default_factory=list)
    system_prompt: Optional[str] = None


def _get_default_system_agents() -> Dict[str, AgentConfig]:
    """获取系统默认的 Agent 配置"""
    return {
        "primary": AgentConfig(
            name="primary",
            description="主Agent - 负责协调和管理其他Agent",
            max_steps=30,
            color="#4A90E2",
            tools=["bash", "python", "read_file", "write_file"],
        ),
        "sre_agent": AgentConfig(
            name="sre_agent",
            description="SRE-Agent - 站点可靠性工程Agent，负责系统监控、故障诊断和运维自动化",
            max_steps=50,
            color="#52C41A",
            tools=["bash", "python", "read_file", "http_request", "execute_sql"],
            system_prompt="你是一个专业的SRE工程师，负责系统监控、故障诊断和运维自动化。",
        ),
        "code_agent": AgentConfig(
            name="code_agent",
            description="Code-Agent - 代码分析与生成Agent，负责代码审查、重构和开发",
            max_steps=40,
            color="#722ED1",
            tools=["bash", "python", "read_file", "write_file", "execute_code"],
            system_prompt="你是一个专业的软件工程师，负责代码分析、生成和重构。",
        ),
        "data_agent": AgentConfig(
            name="data_agent",
            description="Data-Agent - 数据分析Agent，负责数据处理、分析和可视化",
            max_steps=35,
            color="#FA8C16",
            tools=["python", "execute_sql", "read_file", "write_file", "http_request"],
            system_prompt="你是一个专业的数据分析师，负责数据处理、分析和可视化。",
        ),
        "report_agent": AgentConfig(
            name="report_agent",
            description="ReportAgent - 报告生成Agent，负责分析结果汇总和报告撰写",
            max_steps=25,
            color="#13C2C2",
            tools=["read_file", "write_file", "python"],
            system_prompt="你是一个专业的技术文档撰写者，负责生成分析报告和技术文档。",
        ),
    }


class OAuth2ProviderType(str, Enum):
    """OAuth2 提供商类型"""

    GITHUB = "github"
    ALIBABA_INC = "alibaba-inc"
    CUSTOM = "custom"


class OAuth2ProviderConfig(BaseModel):
    """OAuth2 提供商配置"""

    id: str = "github"
    type: OAuth2ProviderType = OAuth2ProviderType.GITHUB
    client_id: str = ""
    client_secret: str = ""
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
    )


class LLMProviderModelConfig(BaseModel):
    """模型配置（provider下的模型）"""

    name: str = Field(..., description="模型名称，如 gpt-4o, deepseek-chat")
    temperature: float = Field(0.7, description="模型温度参数")
    max_new_tokens: int = Field(4096, description="最大生成token数")
    is_multimodal: bool = Field(False, description="是否支持多模态（图片输入）")
    is_default: bool = Field(False, description="是否为该provider下的默认模型")


class LLMProviderConfig(BaseModel):
    """LLM Provider 配置"""

    provider: str = "openai"
    api_base: str = "https://api.openai.com/v1"
    api_key_ref: str = ""  # 引用 secrets 中的 key 名称
    models: List[LLMProviderModelConfig] = Field(
        default_factory=lambda: [
            LLMProviderModelConfig(name="gpt-4"),
        ]
    )


class AgentLLMConfig(BaseModel):
    """Agent LLM 全局配置"""

    temperature: float = 0.5
    providers: List[LLMProviderConfig] = Field(default_factory=list)


class FileBackendType(str, Enum):
    LOCAL = "local"
    OSS = "oss"
    S3 = "s3"


class FileBackendConfig(BaseModel):
    """文件存储后端配置"""

    type: FileBackendType = FileBackendType.LOCAL
    storage_path: str = "./data/files"
    endpoint: Optional[str] = None
    region: Optional[str] = None
    access_key_ref: str = ""  # 引用 secrets 中的 key
    access_secret_ref: str = ""  # 引用 secrets 中的 secret
    bucket: str = "derisk-files"


class FileServiceConfig(BaseModel):
    """文件服务配置"""

    enabled: bool = True
    default_backend: str = "local"
    backends: List[FileBackendConfig] = Field(
        default_factory=lambda: [FileBackendConfig()]
    )


class DatabaseConfig(BaseModel):
    """数据库配置"""

    type: str = "sqlite"
    path: str = "pilot/meta_data/derisk.db"
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password_ref: str = ""  # 引用 secrets 中的密码
    name: str = "derisk"


class WebServiceConfig(BaseModel):
    """Web 服务配置"""

    host: str = "0.0.0.0"
    port: int = 7777
    model_storage: str = "database"
    web_url: str = "http://localhost:7777"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


class DistributedConfig(BaseModel):
    """分布式配置"""

    enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    execution_ttl: int = 3600
    heartbeat_interval: int = 10


class DatasourceConfig(BaseModel):
    """数据源配置"""

    learning_worker_concurrency: int = Field(
        5, description="单节点 schema learning 并发 worker 数", ge=1, le=20
    )
    learning_subtask_timeout: int = Field(
        300, description="subtask 超时回收时间（秒）", ge=60, le=3600
    )


class SystemConfig(BaseModel):
    """系统配置"""

    language: str = "zh"
    log_level: str = "INFO"
    api_keys: List[str] = Field(default_factory=list)
    encrypt_key_ref: str = "master_encrypt_key"
    distributed: DistributedConfig = Field(default_factory=DistributedConfig)


class SecretsConfig(BaseModel):
    """密钥引用配置

    密钥值存储在单独的加密文件 ~/.derisk/secrets.enc 中
    配置中使用 ${secrets.key_name} 语法引用密钥
    """

    references: Dict[str, str] = Field(
        default_factory=lambda: {
            "openai_api_key": "${secrets.openai_api_key}",
            "dashscope_api_key": "${secrets.dashscope_api_key}",
            "anthropic_api_key": "${secrets.anthropic_api_key}",
            "oss_access_key_id": "${secrets.oss_access_key_id}",
            "oss_access_key_secret": "${secrets.oss_access_key_secret}",
            "db_password": "${secrets.db_password}",
        }
    )


def _get_default_secrets_config() -> SecretsConfig:
    return SecretsConfig()


class SSEConfig(BaseModel):
    input_check_interval: int = 100
    notify_step_complete: bool = True
    max_wait_input_time: int = 0


class FeaturePluginEntry(BaseModel):
    """Per-plugin state persisted in derisk.json (builtin marketplace)."""

    enabled: bool = False
    settings: Dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    name: str = "OpenDeRisk"
    version: str = "0.1.0"

    system: SystemConfig = Field(default_factory=SystemConfig)
    web: WebServiceConfig = Field(default_factory=WebServiceConfig)

    default_model: ModelConfig = Field(default_factory=ModelConfig)
    agent_llm: AgentLLMConfig = Field(default_factory=AgentLLMConfig)
    sse: SSEConfig = Field(default_factory=SSEConfig)

    agents: Dict[str, AgentConfig] = Field(default_factory=_get_default_system_agents)

    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    datasource: DatasourceConfig = Field(default_factory=DatasourceConfig)
    file_service: FileServiceConfig = Field(default_factory=FileServiceConfig)

    oauth2: Optional[OAuth2Config] = Field(default_factory=OAuth2Config)

    feature_plugins: Dict[str, FeaturePluginEntry] = Field(default_factory=dict)

    secrets: SecretsConfig = Field(default_factory=_get_default_secrets_config)

    workspace: str = str(Path.home() / ".derisk" / "workspace")

    class Config:
        extra = "allow"

    def resolve_secrets(self) -> Dict[str, Any]:
        from .encryption import ConfigReferenceResolver

        config_dict = self.model_dump()
        return ConfigReferenceResolver.resolve_config(config_dict)
