from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from pydantic import BaseModel, Field
from enum import Enum

class ToolCategory(str, Enum):
    CODE = "code"          # 代码操作
    FILE = "file"          # 文件操作
    SYSTEM = "system"      # 系统操作
    NETWORK = "network"    # 网络操作
    SEARCH = "search"      # 搜索操作

class ToolRisk(str, Enum):
    LOW = "low"            # 低风险：只读
    MEDIUM = "medium"      # 中风险：修改
    HIGH = "high"          # 高风险：系统操作

class ToolMetadata(BaseModel):
    """工具元数据"""
    name: str
    description: str
    category: ToolCategory
    risk: ToolRisk = ToolRisk.MEDIUM
    requires_permission: bool = True
    examples: List[str] = Field(default_factory=list)

class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ToolBase(ABC):
    """工具基类"""
    
    def __init__(self):
        self.metadata = self._define_metadata()
        self.parameters_schema = self._define_parameters()
    
    @abstractmethod
    def _define_metadata(self) -> ToolMetadata:
        """定义工具元数据"""
        pass
    
    @abstractmethod
    def _define_parameters(self) -> Dict[str, Any]:
        """定义参数Schema (JSON Schema格式)"""
        pass
    
    @abstractmethod
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """执行工具"""
        pass
    
    def validate_args(self, args: Dict[str, Any]) -> List[str]:
        """验证参数，返回错误列表"""
        errors = []
        schema = self.parameters_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        
        for req in required:
            if req not in args:
                errors.append(f"缺少必需参数: {req}")
        
        for key, value in args.items():
            if key in properties:
                prop = properties[key]
                if prop.get("type") == "string" and not isinstance(value, str):
                    errors.append(f"参数 {key} 应为字符串")
                elif prop.get("type") == "integer" and not isinstance(value, int):
                    errors.append(f"参数 {key} 应为整数")
                elif prop.get("type") == "boolean" and not isinstance(value, bool):
                    errors.append(f"参数 {key} 应为布尔值")
        
        return errors