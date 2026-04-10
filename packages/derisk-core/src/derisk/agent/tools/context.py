"""
ToolContext - 工具执行上下文

提供完整的执行上下文信息：
- Agent信息
- 用户信息
- 执行环境
- 追踪信息
- 资源引用
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import uuid


class SandboxConfig(BaseModel):
    """沙箱配置"""
    
    enabled: bool = Field(False, description="是否启用沙箱")
    sandbox_type: str = Field("docker", description="沙箱类型: docker, wasm, remote")
    image: str = Field("python:3.11", description="Docker镜像")
    memory_limit: str = Field("512m", description="内存限制")
    cpu_limit: str = Field("1", description="CPU限制")
    timeout: int = Field(300, description="超时时间(秒)")
    network_enabled: bool = Field(False, description="是否允许网络")
    volumes: Dict[str, str] = Field(default_factory=dict, description="卷挂载")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="环境变量")


class ToolContext(BaseModel):
    """
    工具执行上下文
    
    包含工具执行所需的所有上下文信息
    """
    
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Agent ID")
    agent_name: str = Field("default_agent", description="Agent名称")
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="会话ID")
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="消息ID")
    
    user_id: Optional[str] = Field(None, description="用户ID")
    user_name: Optional[str] = Field(None, description="用户名")
    user_permissions: List[str] = Field(default_factory=list, description="用户权限")
    
    working_directory: str = Field(".", description="工作目录")
    environment_variables: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    sandbox_config: Optional[SandboxConfig] = Field(None, description="沙箱配置")
    
    trace_id: Optional[str] = Field(None, description="追踪ID")
    span_id: Optional[str] = Field(None, description="Span ID")
    parent_span_id: Optional[str] = Field(None, description="父Span ID")
    
    config: Dict[str, Any] = Field(default_factory=dict, description="工具配置")
    max_output_bytes: int = Field(50 * 1024, description="最大输出字节数")
    max_output_lines: int = Field(50, description="最大输出行数")

    skill_dir: Optional[str] = Field(None, description="Skill 目录路径")
    available_skills: Dict[str, str] = Field(default_factory=dict, description="可用技能: name -> path")
    
    class Config:
        arbitrary_types_allowed = True
    
    def get_resource(self, name: str) -> Any:
        """获取资源"""
        return getattr(self, f"_{name}", None)
    
    def set_resource(self, name: str, value: Any) -> None:
        """设置资源"""
        setattr(self, f"_{name}", value)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump(exclude_none=True)
    
    @classmethod
    def from_agent(cls, agent: Any, **kwargs) -> "ToolContext":
        """从Agent创建上下文"""
        return cls(
            agent_id=getattr(agent, 'agent_id', str(uuid.uuid4())),
            agent_name=getattr(agent, 'name', 'default_agent'),
            conversation_id=getattr(agent, 'conversation_id', str(uuid.uuid4())),
            user_id=getattr(agent, 'user_id', None),
            **kwargs
        )
    
    def has_permission(self, permission: str) -> bool:
        """检查是否有权限"""
        return permission in self.user_permissions or "*" in self.user_permissions