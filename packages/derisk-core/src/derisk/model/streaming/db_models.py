"""
Streaming Tool Configuration - Database Models

数据库模型定义，支持应用级别的流式参数配置。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Text,
    JSON,
    Integer,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from derisk.storage.metadata.db_storage import BaseModel


class StreamingToolConfig(BaseModel):
    """
    流式工具配置表

    存储每个应用下每个工具的流式参数配置。
    支持应用级别的独立配置。
    """

    __tablename__ = "streaming_tool_config"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 应用标识 (与 apps 表关联)
    app_code = Column(String(128), nullable=False, index=True, comment="应用代码")

    # 工具信息
    tool_name = Column(String(128), nullable=False, index=True, comment="工具名称")
    tool_display_name = Column(String(256), nullable=True, comment="工具显示名称")
    tool_description = Column(Text, nullable=True, comment="工具描述")

    # 参数配置 (JSON 格式)
    # 格式: { "param_name": { "threshold": 1024, "strategy": "semantic", ... }, ... }
    param_configs = Column(JSON, nullable=False, default=dict, comment="参数配置")

    # 全局配置 (应用于该工具所有参数)
    global_threshold = Column(Integer, nullable=True, default=256, comment="全局阈值")
    global_strategy = Column(
        String(32), nullable=True, default="adaptive", comment="全局策略"
    )
    global_renderer = Column(
        String(32), nullable=True, default="default", comment="全局渲染器"
    )

    # 状态
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用流式")

    # 优先级 (当多个配置冲突时使用)
    priority = Column(Integer, nullable=False, default=0, comment="优先级")

    # 元数据
    created_at = Column(
        DateTime, nullable=False, default=datetime.now, comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )
    created_by = Column(String(128), nullable=True, comment="创建人")
    updated_by = Column(String(128), nullable=True, comment="更新人")

    # 索引
    __table_args__ = (
        # 联合唯一索引：一个应用下的一个工具只有一条配置
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "app_code": self.app_code,
            "tool_name": self.tool_name,
            "tool_display_name": self.tool_display_name,
            "tool_description": self.tool_description,
            "param_configs": self.param_configs,
            "global_threshold": self.global_threshold,
            "global_strategy": self.global_strategy,
            "global_renderer": self.global_renderer,
            "enabled": self.enabled,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }


class StreamingParamConfigDetail:
    """
    单个参数的流式配置详情

    用于 API 响应和前端展示。
    """

    def __init__(
        self,
        param_name: str,
        threshold: int = 256,
        strategy: str = "adaptive",
        chunk_size: int = 100,
        chunk_by_line: bool = True,
        renderer: str = "default",
        enabled: bool = True,
        description: Optional[str] = None,
    ):
        self.param_name = param_name
        self.threshold = threshold
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.chunk_by_line = chunk_by_line
        self.renderer = renderer
        self.enabled = enabled
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "param_name": self.param_name,
            "threshold": self.threshold,
            "strategy": self.strategy,
            "chunk_size": self.chunk_size,
            "chunk_by_line": self.chunk_by_line,
            "renderer": self.renderer,
            "enabled": self.enabled,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamingParamConfigDetail":
        return cls(
            param_name=data.get("param_name", ""),
            threshold=data.get("threshold", 256),
            strategy=data.get("strategy", "adaptive"),
            chunk_size=data.get("chunk_size", 100),
            chunk_by_line=data.get("chunk_by_line", True),
            renderer=data.get("renderer", "default"),
            enabled=data.get("enabled", True),
            description=data.get("description"),
        )


# ============================================================
# Pydantic Models for API
# ============================================================

from pydantic import BaseModel as PydanticModel, Field
from typing import List


class ParamConfigInput(PydanticModel):
    """参数配置输入"""

    param_name: str = Field(..., description="参数名称")
    threshold: int = Field(256, description="流式阈值（字符数）")
    strategy: str = Field(
        "adaptive", description="分片策略: fixed_size, line_based, semantic, adaptive"
    )
    chunk_size: int = Field(100, description="分片大小")
    chunk_by_line: bool = Field(True, description="按行分片")
    renderer: str = Field("default", description="渲染器: code, text, default")
    enabled: bool = Field(True, description="是否启用")
    description: Optional[str] = Field(None, description="描述")


class StreamingToolConfigInput(PydanticModel):
    """流式工具配置输入"""

    app_code: str = Field(..., description="应用代码")
    tool_name: str = Field(..., description="工具名称")
    tool_display_name: Optional[str] = Field(None, description="工具显示名称")
    tool_description: Optional[str] = Field(None, description="工具描述")
    param_configs: List[ParamConfigInput] = Field(..., description="参数配置列表")
    global_threshold: Optional[int] = Field(256, description="全局阈值")
    global_strategy: Optional[str] = Field("adaptive", description="全局策略")
    global_renderer: Optional[str] = Field("default", description="全局渲染器")
    enabled: bool = Field(True, description="是否启用")
    priority: int = Field(0, description="优先级")


class StreamingToolConfigResponse(PydanticModel):
    """流式工具配置响应"""

    id: int
    app_code: str
    tool_name: str
    tool_display_name: Optional[str]
    tool_description: Optional[str]
    param_configs: List[Dict[str, Any]]
    global_threshold: int
    global_strategy: str
    global_renderer: str
    enabled: bool
    priority: int
    created_at: Optional[str]
    updated_at: Optional[str]


class AvailableToolResponse(PydanticModel):
    """可用工具响应"""

    tool_name: str
    tool_display_name: Optional[str]
    description: Optional[str]
    parameters: List[Dict[str, Any]]  # 工具参数列表
    has_streaming_config: bool  # 是否已有流式配置


class StreamingConfigListResponse(PydanticModel):
    """配置列表响应"""

    app_code: str
    configs: List[StreamingToolConfigResponse]
    total: int
