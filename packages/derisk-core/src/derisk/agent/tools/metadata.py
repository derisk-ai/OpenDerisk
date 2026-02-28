"""
ToolMetadata - 工具元数据定义

提供完整的工具元数据模型：
- 基本信息（名称、描述、版本）
- 分类信息（类别、来源、标签）
- 风险与权限
- 执行配置
- 输入输出定义
- 依赖关系
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from .base import ToolCategory, ToolRiskLevel, ToolSource, ToolEnvironment


class ToolExample(BaseModel):
    """工具使用示例"""
    
    input: Dict[str, Any] = Field(default_factory=dict, description="输入参数示例")
    output: Any = Field(None, description="输出结果示例")
    description: str = Field("", description="示例说明")


class ToolDependency(BaseModel):
    """工具依赖声明"""
    
    tool_name: str = Field(..., description="依赖的工具名称")
    required: bool = Field(True, description="是否必须")
    version: Optional[str] = Field(None, description="版本要求")


class ToolMetadata(BaseModel):
    """
    工具元数据 - 完整定义
    
    包含工具的所有描述信息和配置
    """
    
    # === 基本信息 ===
    name: str = Field(..., description="唯一标识")
    display_name: str = Field("", description="展示名称")
    description: str = Field(..., description="详细描述")
    version: str = Field("1.0.0", description="版本号")
    
    # === 分类信息 ===
    category: ToolCategory = Field(ToolCategory.UTILITY, description="工具类别")
    subcategory: Optional[str] = Field(None, description="子类别")
    source: ToolSource = Field(ToolSource.SYSTEM, description="来源")
    tags: List[str] = Field(default_factory=list, description="标签")
    
    # === 风险与权限 ===
    risk_level: ToolRiskLevel = Field(ToolRiskLevel.LOW, description="风险等级")
    requires_permission: bool = Field(True, description="是否需要权限")
    required_permissions: List[str] = Field(default_factory=list, description="所需权限列表")
    approval_message: Optional[str] = Field(None, description="审批提示信息")
    
    # === 执行配置 ===
    environment: ToolEnvironment = Field(ToolEnvironment.LOCAL, description="执行环境")
    timeout: int = Field(120, description="默认超时(秒)")
    max_retries: int = Field(0, description="最大重试次数")
    concurrency_limit: int = Field(1, description="并发限制")
    
    # === 输入输出 ===
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="输入Schema")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="输出Schema")
    examples: List[ToolExample] = Field(default_factory=list, description="使用示例")
    
    # === 依赖关系 ===
    dependencies: List[str] = Field(default_factory=list, description="依赖的工具")
    conflicts: List[str] = Field(default_factory=list, description="冲突的工具")
    
    # === 文档 ===
    doc_url: Optional[str] = Field(None, description="文档链接")
    author: Optional[str] = Field(None, description="作者")
    license: Optional[str] = Field(None, description="许可证")
    
    # === 元信息 ===
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    
    class Config:
        use_enum_values = True
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name.replace("_", " ").title()
    
    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()
    
    def get_risk_badge(self) -> str:
        """获取风险等级标识"""
        badges = {
            ToolRiskLevel.SAFE: "🟢 SAFE",
            ToolRiskLevel.LOW: "🟢 LOW",
            ToolRiskLevel.MEDIUM: "🟡 MEDIUM",
            ToolRiskLevel.HIGH: "🔴 HIGH",
            ToolRiskLevel.CRITICAL: "⛔ CRITICAL",
        }
        return badges.get(self.risk_level, "⚪ UNKNOWN")
    
    def get_category_badge(self) -> str:
        """获取分类标识"""
        return f"[{self.category.value.upper()}]"