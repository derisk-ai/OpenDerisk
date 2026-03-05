"""
ToolConfig - 工具配置系统

提供分级配置：
- GlobalToolConfig: 全局配置
- AgentToolConfig: Agent级配置
- UserToolConfig: 用户级配置
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from pathlib import Path
import logging

from .base import ToolCategory, ToolRiskLevel, ToolEnvironment

logger = logging.getLogger(__name__)


class GlobalToolConfig(BaseModel):
    """全局工具配置"""
    
    enabled_categories: List[ToolCategory] = Field(
        default_factory=lambda: list(ToolCategory),
        description="启用的工具类别"
    )
    disabled_tools: List[str] = Field(default_factory=list, description="禁用的工具")
    
    default_timeout: int = Field(120, description="默认超时(秒)")
    default_environment: ToolEnvironment = Field(ToolEnvironment.LOCAL, description="默认执行环境")
    default_risk_approval: Dict[str, bool] = Field(
        default_factory=lambda: {
            "safe": False,
            "low": False,
            "medium": True,
            "high": True,
            "critical": True,
        },
        description="各风险等级是否需要审批"
    )
    
    max_concurrent_tools: int = Field(5, description="最大并发工具数")
    max_output_size: int = Field(100 * 1024, description="最大输出大小(字节)")
    enable_caching: bool = Field(True, description="是否启用缓存")
    cache_ttl: int = Field(3600, description="缓存过期时间(秒)")
    
    sandbox_enabled: bool = Field(False, description="是否启用沙箱")
    docker_image: str = Field("python:3.11", description="Docker镜像")
    memory_limit: str = Field("512m", description="内存限制")
    
    log_level: str = Field("INFO", description="日志级别")
    log_tool_calls: bool = Field(True, description="是否记录工具调用")
    log_arguments: bool = Field(True, description="是否记录参数(敏感参数脱敏)")
    
    class Config:
        use_enum_values = True
    
    @classmethod
    def from_file(cls, path: Path) -> "GlobalToolConfig":
        """从文件加载配置"""
        import yaml
        import json
        
        if path.suffix in ['.yaml', '.yml']:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        elif path.suffix == '.json':
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            raise ValueError(f"不支持的配置文件格式: {path.suffix}")
        
        return cls(**data)


class AgentToolConfig(BaseModel):
    """Agent级工具配置"""
    
    agent_id: str = Field(..., description="Agent ID")
    agent_name: str = Field(..., description="Agent名称")
    
    available_tools: List[str] = Field(default_factory=list, description="可用工具列表(空则全部可用)")
    excluded_tools: List[str] = Field(default_factory=list, description="排除的工具")
    
    tool_overrides: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="工具参数覆盖"
    )
    
    execution_mode: str = Field("sequential", description="执行模式: sequential, parallel")
    max_retries: int = Field(0, description="最大重试次数")
    retry_delay: float = Field(1.0, description="重试延迟(秒)")
    
    auto_approve_safe: bool = Field(True, description="自动批准安全工具")
    auto_approve_low_risk: bool = Field(False, description="自动批准低风险工具")
    require_approval_high_risk: bool = Field(True, description="高风险工具需要审批")
    
    def get_tool_override(self, tool_name: str) -> Dict[str, Any]:
        """获取工具配置覆盖"""
        return self.tool_overrides.get(tool_name, {})
    
    def is_tool_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        if tool_name in self.excluded_tools:
            return False
        if self.available_tools and tool_name not in self.available_tools:
            return False
        return True


class UserToolConfig(BaseModel):
    """用户级工具配置"""
    
    user_id: str = Field(..., description="用户ID")
    
    permissions: List[str] = Field(default_factory=list, description="用户权限")
    
    custom_tools: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="用户自定义工具配置"
    )
    
    preferred_tools: Dict[str, str] = Field(
        default_factory=dict,
        description="首选工具映射"
    )
    tool_aliases: Dict[str, str] = Field(
        default_factory=dict,
        description="工具别名"
    )


class ToolConfig(BaseModel):
    """工具配置管理器"""
    
    global_config: GlobalToolConfig = Field(default_factory=GlobalToolConfig)
    agent_configs: Dict[str, AgentToolConfig] = Field(default_factory=dict)
    user_configs: Dict[str, UserToolConfig] = Field(default_factory=dict)
    
    def get_agent_config(self, agent_id: str) -> Optional[AgentToolConfig]:
        """获取Agent配置"""
        return self.agent_configs.get(agent_id)
    
    def get_user_config(self, user_id: str) -> Optional[UserToolConfig]:
        """获取用户配置"""
        return self.user_configs.get(user_id)
    
    def merge_config(
        self,
        tool_name: str,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        合并配置
        
        优先级: 用户 > Agent > 全局
        """
        config = {}
        
        config['timeout'] = self.global_config.default_timeout
        config['environment'] = self.global_config.default_environment
        
        if agent_id and agent_id in self.agent_configs:
            agent_config = self.agent_configs[agent_id]
            config.update(agent_config.get_tool_override(tool_name))
        
        if user_id and user_id in self.user_configs:
            user_config = self.user_configs[user_id]
            if tool_name in user_config.preferred_tools:
                config['preferred'] = user_config.preferred_tools[tool_name]
        
        return config