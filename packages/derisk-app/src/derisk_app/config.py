import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from derisk.datasource.parameter import BaseDatasourceParameters
from derisk.model.parameter import (
    ModelsDeployParameters,
    ModelServiceConfig,
)
from derisk.storage.cache.manager import ModelCacheParameters
from derisk.storage.vector_store.base import VectorStoreConfig
from derisk.util.configure import HookConfig
from derisk.util.i18n_utils import _
from derisk.util.parameter_utils import BaseParameters
from derisk.util.tracer import TracerParameters
from derisk.util.logger import LoggingParameters
from derisk_ext.storage.knowledge_graph.knowledge_graph import (
    BuiltinKnowledgeGraphConfig,
)
from derisk_serve.core import BaseServeConfig
from derisk_serve.core.config import GPTsAppConfig


@dataclass
class SystemParameters:
    """System parameters."""

    workers: Optional[int] = field(
        default=None,
        metadata={
            "help": _("worker node size"),
        },
    )
    language: str = field(
        default="en",
        metadata={
            "help": _("Language setting"),
            "valid_values": ["en", "zh", "fr", "ja", "ko", "ru"],
        },
    )
    log_level: str = field(
        default="INFO",
        metadata={
            "help": _("Logging level"),
            "valid_values": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        },
    )
    api_keys: List[str] = field(
        default_factory=list,
        metadata={
            "help": _("API keys"),
        },
    )
    encrypt_key: Optional[str] = field(
        default="your_secret_key",
        metadata={"help": _("The key to encrypt the data")},
    )
    enable_performance_sampling: Optional[bool] = field(
        default=False,
        metadata={"help": _("Whether to enable performance sampling")},
    )
    enable_llm_stream_print: Optional[bool] = field(
        default=False,
        metadata={"help": _("Whether to enable llm stream print")},
    )


@dataclass
class StorageConfig(BaseParameters):
    vector: VectorStoreConfig = field(
        default_factory=VectorStoreConfig,
        metadata={
            "help": _("default vector type"),
        },
    )
    graph: BuiltinKnowledgeGraphConfig = field(
        default_factory=BuiltinKnowledgeGraphConfig,
        metadata={
            "help": _("default graph type"),
        },
    )
    full_text: VectorStoreConfig = field(
        default_factory=VectorStoreConfig,
        metadata={
            "help": _("default full text type"),
        },
    )


@dataclass
class RagParameters(BaseParameters):
    """Rag configuration."""

    chunk_size: Optional[int] = field(
        default=500,
        metadata={"help": _("Whether to verify the SSL certificate of the database")},
    )
    chunk_overlap: Optional[int] = field(
        default=50,
        metadata={
            "help": _(
                "The default thread pool size, If None, use default config of python "
                "thread pool"
            )
        },
    )
    similarity_top_k: Optional[int] = field(
        default=10,
        metadata={"help": _("knowledge search top k")},
    )
    similarity_score_threshold: Optional[int] = field(
        default=0.0,
        metadata={"help": _("knowledge search top similarity score")},
    )
    query_rewrite: Optional[bool] = field(
        default=False,
        metadata={"help": _("knowledge search rewrite")},
    )
    max_chunks_once_load: Optional[int] = field(
        default=10,
        metadata={"help": _("knowledge max chunks once load")},
    )
    max_threads: Optional[int] = field(
        default=1,
        metadata={"help": _("knowledge max load thread")},
    )
    rerank_top_k: Optional[int] = field(
        default=3,
        metadata={"help": _("knowledge rerank top k")},
    )
    storage: StorageConfig = field(
        default_factory=lambda: StorageConfig(),
        metadata={"help": _("Storage configuration")},
    )
    graph_search_top_k: Optional[int] = field(
        default=3,
        metadata={"help": _("knowledge graph search top k")},
    )
    graph_community_summary_enabled: Optional[bool] = field(
        default=False,
        metadata={"help": _("graph community summary enabled")},
    )


@dataclass
class ServiceWebParameters(BaseParameters):
    host: str = field(default="0.0.0.0", metadata={"help": _("Webserver deploy host")})
    port: int = field(
        default=7777, metadata={"help": _("Webserver deploy port, default is 7777")}
    )
    light: Optional[bool] = field(
        default=False, metadata={"help": _("Run Webserver in light mode")}
    )
    controller_addr: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "The Model controller address to connect. If None, read model "
                "controller address from environment key `MODEL_SERVER`."
            )
        },
    )
    database: BaseDatasourceParameters = field(
        default=None,
        metadata={
            "help": _(
                "Database connection config, now support SQLite, OceanBase and MySQL"
            )
        },
    )
    model_storage: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "The storage type of model configures, if None, use the default "
                "storage(current database). When you run in light mode, it will not "
                "use any storage."
            ),
            "valid_values": ["database", "memory"],
        },
    )
    trace: Optional[TracerParameters] = field(
        default=None,
        metadata={
            "help": _("Tracer config for web server, if None, use global tracer config")
        },
    )
    log: Optional[LoggingParameters] = field(
        default=None,
        metadata={
            "help": _(
                "Logging configuration for web server, if None, use global config"
            )
        },
    )
    disable_alembic_upgrade: Optional[bool] = field(
        default=False,
        metadata={
            "help": _(
                "Whether to disable alembic to initialize and upgrade database metadata"
            )
        },
    )
    db_ssl_verify: Optional[bool] = field(
        default=False,
        metadata={"help": _("Whether to verify the SSL certificate of the database")},
    )
    default_thread_pool_size: Optional[int] = field(
        default=32,
        metadata={
            "help": _(
                "The default thread pool size, If None, use default config of python "
                "thread pool. Recommended: 32 for SQLite, 64+ for MySQL/PostgreSQL"
            )
        },
    )
    remote_embedding: Optional[bool] = field(
        default=False,
        metadata={
            "help": _(
                "Whether to enable remote embedding models. If it is True, you need"
                " to start a embedding model through `derisk start worker --worker_type "
                "text2vec --model_name xxx --model_path xxx`"
            )
        },
    )
    remote_rerank: Optional[bool] = field(
        default=False,
        metadata={
            "help": _(
                "Whether to enable remote rerank models. If it is True, you need"
                " to start a rerank model through `derisk start worker --worker_type "
                "text2vec --rerank --model_name xxx --model_path xxx`"
            )
        },
    )
    awel_dirs: Optional[str] = field(
        default=None,
        metadata={"help": _("The directories to search awel files, split by `,`")},
    )
    new_web_ui: bool = field(
        default=True,
        metadata={"help": _("Whether to use the new web UI, default is True")},
    )
    model_cache: ModelCacheParameters = field(
        default_factory=ModelCacheParameters,
        metadata={"help": _("Model cache configuration")},
    )
    embedding_model_max_seq_len: Optional[int] = field(
        default=512,
        metadata={
            "help": _("The max sequence length of the embedding model, default is 512")
        },
    )
    web_url: Optional[str] = field(
        default=None,
        metadata={"help": _("The real web url `,`")},
    )


@dataclass
class ServiceConfig(BaseParameters):
    web: ServiceWebParameters = field(
        default_factory=ServiceWebParameters,
        metadata={"help": _("Web service configuration")},
    )
    model: ModelServiceConfig = field(
        default_factory=ModelServiceConfig,
        metadata={"help": _("Model service configuration")},
    )


@dataclass
class MCPConfigParameters(BaseParameters):
    mode: Optional[str] = field(
        default="origin",
        metadata={"help": _("The mcp client mode，default origin `,`")},
    )
    enable_mcp_gateway: bool = field(
        default=False, metadata={"help": _("enable mcp gateway, default disable")}
    )


@dataclass
class SandboxConfigParameters(BaseParameters):
    type: Optional[str] = field(
        default="local",
        metadata={"help": _("The sandbox type.")},
    )
    template_id: Optional[str] = field(
        default=None,
        metadata={"help": _("The sandbox template code.")},
    )
    user_id: Optional[str] = field(
        default=None,
        metadata={"help": _("The sandbox default user id.")},
    )
    agent_name: Optional[str] = field(
        default=None,
        metadata={"help": _("The sandbox defualt agent name.")},
    )
    repo_url: Optional[str] = field(
        default=None,
        metadata={"help": _("The sandbox skill repo url.")},
    )
    work_dir: Optional[str] = field(
        default=None,
        metadata={"help": _("The sandbox work dir.")},
    )
    skill_dir: Optional[str] = field(
        default=None,
        metadata={"help": _("The sandbox skill dir.")},
    )

    oss_ak: Optional[str] = field(
        default=None,
        metadata={
            "help": _("Deprecated: Use FileStorageClient instead. The sandbox oss ak.")
        },
    )
    oss_sk: Optional[str] = field(
        default=None,
        metadata={
            "help": _("Deprecated: Use FileStorageClient instead. The sandbox oss sk.")
        },
    )
    oss_endpoint: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "Deprecated: Use FileStorageClient instead. The sandbox oss endpoint."
            )
        },
    )
    oss_bucket_name: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "Deprecated: Use FileStorageClient instead. The sandbox oss bucket."
            )
        },
    )


@dataclass
class ApplicationConfig:
    """Application configuration."""

    hooks: List[HookConfig] = field(
        default_factory=list,
        metadata={
            "help": _(
                "Configuration hooks, which will be executed before the configuration "
                "loading"
            ),
        },
    )

    system: SystemParameters = field(
        default_factory=SystemParameters,
        metadata={
            "help": _("System configuration"),
        },
    )
    service: ServiceConfig = field(default_factory=ServiceConfig)
    models: ModelsDeployParameters = field(
        default_factory=ModelsDeployParameters,
        metadata={
            "help": _("Model deployment configuration"),
        },
    )
    serves: List[BaseServeConfig] = field(
        default_factory=list,
        metadata={
            "help": _("Serve configuration"),
        },
    )
    rag: RagParameters = field(
        default_factory=lambda: RagParameters(),
        metadata={"help": _("Rag Knowledge Parameters")},
    )
    app: GPTsAppConfig = field(
        default_factory=lambda: GPTsAppConfig(),
        metadata={"help": _("GPTs application configuration")},
    )
    trace: TracerParameters = field(
        default_factory=TracerParameters,
        metadata={
            "help": _("Global tracer configuration"),
        },
    )
    log: LoggingParameters = field(
        default_factory=LoggingParameters,
        metadata={
            "help": _("Logging configuration"),
        },
    )
    mcp: MCPConfigParameters = field(
        default_factory=MCPConfigParameters,
        metadata={
            "help": _("MCP configuration"),
        },
    )
    sandbox: SandboxConfigParameters = field(
        default_factory=SandboxConfigParameters,
        metadata={"help": _("SandBox configuration")},
    )
    agent: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "help": _("Agent configuration"),
        },
    )
