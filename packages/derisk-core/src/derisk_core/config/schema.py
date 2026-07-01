from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from pathlib import Path
from enum import Enum
import base64
import json

from .home import get_derisk_home


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
    default_role: str = Field(
        default="viewer",
        description="新OAuth2用户首次登录时分配的默认角色 (guest/viewer/operator/editor/admin)",
    )


class LLMProviderModelConfig(BaseModel):
    """模型配置（provider下的模型）"""

    name: str = Field(..., description="模型名称，如 gpt-4o, deepseek-chat")
    temperature: float = Field(0.7, description="模型温度参数")
    max_new_tokens: int = Field(4096, description="最大生成token数")
    # 新增：模型类型与能力标签
    model_type: str = Field("llm", description="模型类型: llm/embedding/rerank/video/image/audio/speech/moderation")
    capabilities: List[str] = Field(default_factory=list, description="能力标签: text/vision/audio_input/audio_output/video_input/function_call/streaming")
    is_default: bool = Field(False, description="是否为该provider下的默认模型")
    # 兼容旧配置
    is_multimodal: bool = Field(False, description="是否支持多模态（图片输入），旧配置兼容字段")

    def model_post_init(self, __context: Any) -> None:
        """旧配置兼容：将 is_multimodal 转换为 capabilities 中的 vision"""
        if self.is_multimodal and "vision" not in self.capabilities:
            self.capabilities = list(self.capabilities) + ["vision"]


class LLMProviderConfig(BaseModel):
    """LLM Provider 配置

    provider: 来源/品牌，如 openai, alibaba, aws, azure, anthropic
    protocol: 接入协议，如 openai, anthropic, theta, openai-compatible
    """

    provider: str = "openai"
    protocol: Optional[str] = None
    api_base: str = "https://api.openai.com/v1"
    api_key_ref: str = ""  # 引用 secrets 中的 key 名称
    models: List[LLMProviderModelConfig] = Field(
        default_factory=lambda: [
            LLMProviderModelConfig(name="gpt-4"),
        ]
    )

    def model_post_init(self, __context: Any) -> None:
        """旧配置兼容：未设置 protocol 时，根据 provider 推断"""
        if not self.protocol:
            self.protocol = infer_protocol_from_provider(self.provider)


def infer_protocol_from_provider(provider: str) -> str:
    """根据 provider 名称推断接入协议"""
    name = (provider or "").strip().lower()
    openai_compatible = {
        "openai", "alibaba", "aliyun", "dashscope", "aws", "azure",
        "deepseek", "zhipu", "moonshot", "openrouter", "siliconflow",
        "custom", "tencent", "baidu", "volcengine", "minimax",
    }
    if name in openai_compatible:
        return "openai"
    if name in {"anthropic", "claude"}:
        return "anthropic"
    if name == "theta":
        return "theta"
    return name or "openai"


class AgentLLMConfig(BaseModel):
    """Agent LLM 全局配置"""

    temperature: float = 0.5
    providers: List[LLMProviderConfig] = Field(default_factory=list)


class EmbeddingModelConfig(BaseModel):
    """向量（embedding）模型配置。

    用于持久化通过模型管理页（/models）添加的 text2vec 向量模型，使其在重启后
    仍可用。``provider`` 决定使用哪个 embedding 适配器（如 proxy/tongyi、
    proxy/openai、proxy/ollama、hf 等），其余字段按 provider 透传给对应的
    EmbeddingDeployModelParameters 子类。
    """

    name: str = Field(..., description="向量模型名称，部署时的唯一标识")
    provider: str = Field(
        "proxy/openai",
        description="向量模型 provider，如 proxy/tongyi、proxy/openai、hf",
    )
    api_key: Optional[str] = Field(None, description="API Key 或其 secrets 引用")
    api_url: Optional[str] = Field(None, description="API 地址（部分 provider 需要）")
    backend: Optional[str] = Field(
        None, description="传给 provider 的真实模型名（如 text-embedding-v3）"
    )
    # 允许 provider 特有的额外字段（如 path/device 等本地模型参数）透传。
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="provider 特有的额外部署参数"
    )


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

    # Oracle thick mode 配置（用于 Oracle 11g 及更早版本）
    oracle_enable_thick_mode: bool = Field(
        False,
        description="启用 Oracle thick mode。Oracle 11g 及更早版本需要开启此选项。开启后所有 Oracle 连接将使用 thick mode。需要安装 Oracle Instant Client。",
    )
    oracle_instant_client_path: Optional[str] = Field(
        None,
        description="Oracle Instant Client 路径。不设置则自动检测（ORACLE_INSTANT_CLIENT_HOME 环境变量或常见安装路径）。",
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


class MemoryStorageConfig(BaseModel):
    """Memory storage configuration for the memory module."""

    type: str = "simple_sqlite"
    palace_path: Optional[str] = None
    enable_kg: bool = True
    default_wing: Optional[str] = None
    use_builtin_embedding: bool = False
    auto_memory: bool = True
    auto_memory_top_k: int = 5
    auto_memory_max_distance: float = 0.4


class VectorStorageConfig(BaseModel):
    """Vector storage configuration."""

    type: str = "chroma"
    persist_path: Optional[str] = None


class GraphStorageConfig(BaseModel):
    """Graph storage configuration."""

    enabled: bool = False


class FullTextStorageConfig(BaseModel):
    """Full text storage configuration."""

    enabled: bool = False
    account: Optional[str] = None
    secret: Optional[str] = None


class StorageConfig(BaseModel):
    """Storage configuration for RAG."""

    vector: VectorStorageConfig = Field(default_factory=VectorStorageConfig)
    graph: GraphStorageConfig = Field(default_factory=GraphStorageConfig)
    full_text: FullTextStorageConfig = Field(default_factory=FullTextStorageConfig)
    memory: MemoryStorageConfig = Field(default_factory=MemoryStorageConfig)


class RagConfig(BaseModel):
    """RAG configuration."""

    chunk_size: int = 500
    chunk_overlap: int = 50
    similarity_top_k: int = 10
    similarity_score_threshold: float = 0.0
    query_rewrite: bool = False
    max_chunks_once_load: int = 10
    max_threads: int = 1
    rerank_top_k: int = 3
    storage: StorageConfig = Field(default_factory=StorageConfig)


class AppConfig(BaseModel):
    name: str = "OpenDeRisk"
    version: str = "0.1.0"

    system: SystemConfig = Field(default_factory=SystemConfig)
    web: WebServiceConfig = Field(default_factory=WebServiceConfig)

    default_model: ModelConfig = Field(default_factory=ModelConfig)
    agent_llm: AgentLLMConfig = Field(default_factory=AgentLLMConfig)
    # 向量模型：通过模型管理页添加的 text2vec 模型，持久化于此以便重启后重放部署。
    embeddings: List[EmbeddingModelConfig] = Field(default_factory=list)
    # 默认向量模型名称；为空时取 embeddings 列表的第一个（先添加者优先）。
    default_embedding: Optional[str] = Field(default=None)
    sse: SSEConfig = Field(default_factory=SSEConfig)
    agents: Dict[str, AgentConfig] = Field(default_factory=_get_default_system_agents)

    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    datasource: DatasourceConfig = Field(default_factory=DatasourceConfig)
    file_service: FileServiceConfig = Field(default_factory=FileServiceConfig)

    oauth2: Optional[OAuth2Config] = Field(default_factory=OAuth2Config)

    feature_plugins: Dict[str, FeaturePluginEntry] = Field(default_factory=dict)

    secrets: SecretsConfig = Field(default_factory=_get_default_secrets_config)

    rag: RagConfig = Field(default_factory=RagConfig)

    workspace: str = Field(
        default_factory=lambda: str(get_derisk_home() / "workspace")
    )

    class Config:
        extra = "allow"

    def resolve_secrets(self) -> Dict[str, Any]:
        from .encryption import ConfigReferenceResolver

        config_dict = self.model_dump()
        return ConfigReferenceResolver.resolve_config(config_dict)
