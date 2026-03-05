"""
ToolResult - 工具执行结果

提供统一的执行结果格式：
- 执行状态
- 输出内容
- 错误信息
- 执行元数据
- 产出物
- 可视化数据
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import uuid


class ResultStatus(str, Enum):
    """结果状态"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PENDING = "pending"


class Artifact(BaseModel):
    """产出物"""
    
    name: str = Field(..., description="产出物名称")
    type: str = Field(..., description="类型: file, image, link, data")
    content: Any = Field(None, description="内容")
    path: Optional[str] = Field(None, description="文件路径")
    url: Optional[str] = Field(None, description="URL")
    mime_type: Optional[str] = Field(None, description="MIME类型")
    size: Optional[int] = Field(None, description="大小(字节)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class Visualization(BaseModel):
    """可视化数据"""
    
    type: str = Field(..., description="类型: chart, table, markdown, html, image")
    content: Any = Field(..., description="内容")
    title: Optional[str] = Field(None, description="标题")
    format: str = Field("json", description="格式: json, html, markdown, svg")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class ToolResult(BaseModel):
    """
    工具执行结果
    
    统一的执行结果格式
    """
    
    success: bool = Field(..., description="是否成功")
    status: ResultStatus = Field(ResultStatus.SUCCESS, description="结果状态")
    output: Any = Field(None, description="输出内容")
    error: Optional[str] = Field(None, description="错误信息")
    error_code: Optional[str] = Field(None, description="错误代码")
    
    tool_name: str = Field(..., description="工具名称")
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="执行ID")
    execution_time_ms: int = Field(0, description="执行时间(毫秒)")
    tokens_used: int = Field(0, description="使用的Token数")
    
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    artifacts: List[Artifact] = Field(default_factory=list, description="产出物")
    visualizations: List[Visualization] = Field(default_factory=list, description="可视化数据")
    
    is_stream: bool = Field(False, description="是否流式")
    stream_complete: bool = Field(True, description="流是否完成")
    
    trace_id: Optional[str] = Field(None, description="追踪ID")
    span_id: Optional[str] = Field(None, description="Span ID")
    
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    
    class Config:
        arbitrary_types_allowed = True
    
    @classmethod
    def ok(cls, output: Any, tool_name: str, **kwargs) -> "ToolResult":
        """创建成功结果"""
        return cls(
            success=True,
            status=ResultStatus.SUCCESS,
            output=output,
            tool_name=tool_name,
            **kwargs
        )
    
    @classmethod
    def fail(cls, error: str, tool_name: str, error_code: str = None, **kwargs) -> "ToolResult":
        """创建失败结果"""
        return cls(
            success=False,
            status=ResultStatus.FAILED,
            error=error,
            error_code=error_code,
            tool_name=tool_name,
            **kwargs
        )
    
    @classmethod
    def timeout(cls, tool_name: str, timeout_seconds: int, **kwargs) -> "ToolResult":
        """创建超时结果"""
        return cls(
            success=False,
            status=ResultStatus.TIMEOUT,
            error=f"Tool execution timed out after {timeout_seconds} seconds",
            error_code="TIMEOUT",
            tool_name=tool_name,
            **kwargs
        )
    
    def add_artifact(self, artifact: Artifact) -> "ToolResult":
        """添加产出物"""
        self.artifacts.append(artifact)
        return self
    
    def add_visualization(self, visualization: Visualization) -> "ToolResult":
        """添加可视化"""
        self.visualizations.append(visualization)
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump(exclude_none=True)
    
    def to_openai_message(self) -> Dict[str, Any]:
        """转换为OpenAI消息格式"""
        if self.success:
            return {
                "tool_call_id": self.execution_id,
                "role": "tool",
                "content": str(self.output) if self.output else ""
            }
        else:
            return {
                "tool_call_id": self.execution_id,
                "role": "tool",
                "content": f"Error: {self.error}"
            }
    
    def get_output_string(self, max_length: int = 10000) -> str:
        """获取输出字符串"""
        if self.output is None:
            return ""
        
        output_str = str(self.output)
        if len(output_str) > max_length:
            return output_str[:max_length] + f"\n... (truncated, total {len(output_str)} chars)"
        return output_str