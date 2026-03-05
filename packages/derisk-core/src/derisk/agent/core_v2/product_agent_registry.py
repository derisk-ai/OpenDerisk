"""
Product Agent Registry - 产品Agent注册中心

实现产品层与Agent的关联：
1. 产品Agent映射 - app_code到AgentTeamConfig的映射
2. Agent团队配置 - 管理产品的Agent团队配置
3. 资源绑定 - 产品资源与Agent的绑定

@see ARCHITECTURE.md#12.9-productagentregistry-产品Agent注册中心
"""

from typing import Any, Dict, List, Optional, Set
from datetime import datetime
import logging
import json

from pydantic import BaseModel, Field

from .multi_agent.shared_context import ResourceBinding, ResourceScope
from .multi_agent.team import TeamConfig

logger = logging.getLogger(__name__)


class AgentConfig(BaseModel):
    """Agent配置"""
    agent_type: str
    agent_name: Optional[str] = None
    description: Optional[str] = None
    
    capabilities: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    
    llm_config: Dict[str, Any] = Field(default_factory=dict)
    prompt_template: Optional[str] = None
    
    max_steps: int = 10
    timeout: int = 300
    
    is_coordinator: bool = False
    
    class Config:
        extra = "allow"


class AgentTeamConfig(BaseModel):
    """Agent团队配置"""
    team_id: str
    team_name: str
    app_code: str                              # 关联的产品应用代码
    
    description: Optional[str] = None
    
    coordinator_config: Optional[AgentConfig] = None  # 协调者配置
    worker_configs: List[AgentConfig] = Field(default_factory=list)  # 工作Agent配置列表
    
    execution_strategy: str = "adaptive"       # sequential/parallel/hierarchical/adaptive
    max_parallel_workers: int = 3              # 最大并行Worker数
    timeout: int = 3600                        # 总超时时间
    
    shared_resources: List[ResourceBinding] = Field(default_factory=list)  # 共享资源绑定
    
    fallback_config: Optional["AgentTeamConfig"] = None  # 回退配置
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def to_team_config(self) -> TeamConfig:
        """转换为TeamConfig"""
        return TeamConfig(
            team_id=self.team_id,
            team_name=self.team_name,
            app_code=self.app_code,
            coordinator_type=self.coordinator_config.agent_type if self.coordinator_config else None,
            worker_types=[w.agent_type for w in self.worker_configs],
            max_parallel_workers=self.max_parallel_workers,
            task_timeout=self.timeout,
            shared_resources=self.shared_resources,
            execution_strategy=self.execution_strategy,
        )


class AppAgentMapping(BaseModel):
    """应用-Agent映射"""
    app_code: str
    app_name: Optional[str] = None
    
    team_config_id: str
    
    enabled: bool = True
    
    priority: int = 0  # 高优先级优先
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProductAgentRegistry:
    """
    产品Agent注册中心
    
    管理产品应用与Agent团队的映射关系。
    
    @example
    ```python
    registry = ProductAgentRegistry()
    
    # 注册Agent团队
    team_config = AgentTeamConfig(
        team_id="dev-team-1",
        team_name="Development Team",
        app_code="code_app",
        worker_configs=[
            AgentConfig(agent_type="analyst", capabilities=["analysis"]),
            AgentConfig(agent_type="coder", capabilities=["coding"]),
            AgentConfig(agent_type="tester", capabilities=["testing"]),
        ],
    )
    registry.register_team(team_config)
    
    # 获取产品的Agent配置
    config = registry.get_team_config("code_app")
    
    # 绑定资源
    registry.bind_resources("code_app", [
        ResourceBinding(resource_type="knowledge", resource_name="code_wiki"),
    ])
    ```
    """
    
    def __init__(self):
        self._teams: Dict[str, AgentTeamConfig] = {}  # team_id -> config
        self._app_mapping: Dict[str, AppAgentMapping] = {}  # app_code -> mapping
        self._agent_types: Dict[str, AgentConfig] = {}  # agent_type -> config
    
    def register_team(self, config: AgentTeamConfig) -> None:
        """
        注册Agent团队
        
        Args:
            config: Agent团队配置
        """
        self._teams[config.team_id] = config
        
        self._app_mapping[config.app_code] = AppAgentMapping(
            app_code=config.app_code,
            team_config_id=config.team_id,
        )
        
        for worker_config in config.worker_configs:
            self._agent_types[worker_config.agent_type] = worker_config
        
        if config.coordinator_config:
            self._agent_types[config.coordinator_config.agent_type] = config.coordinator_config
        
        logger.info(f"[ProductAgentRegistry] Registered team: {config.team_id} for app: {config.app_code}")
    
    def unregister_team(self, team_id: str) -> bool:
        """
        注销Agent团队
        
        Args:
            team_id: 团队ID
        
        Returns:
            是否成功
        """
        if team_id not in self._teams:
            return False
        
        config = self._teams[team_id]
        
        if config.app_code in self._app_mapping:
            del self._app_mapping[config.app_code]
        
        del self._teams[team_id]
        
        logger.info(f"[ProductAgentRegistry] Unregistered team: {team_id}")
        return True
    
    def get_team_config(self, app_code: str) -> Optional[AgentTeamConfig]:
        """
        获取产品的Agent团队配置
        
        Args:
            app_code: 产品应用代码
        
        Returns:
            Agent团队配置或None
        """
        mapping = self._app_mapping.get(app_code)
        if not mapping or not mapping.enabled:
            return None
        
        return self._teams.get(mapping.team_config_id)
    
    def get_team_by_id(self, team_id: str) -> Optional[AgentTeamConfig]:
        """通过ID获取团队配置"""
        return self._teams.get(team_id)
    
    def update_team_config(
        self,
        team_id: str,
        updates: Dict[str, Any],
    ) -> Optional[AgentTeamConfig]:
        """
        更新团队配置
        
        Args:
            team_id: 团队ID
            updates: 更新内容
        
        Returns:
            更新后的配置或None
        """
        config = self._teams.get(team_id)
        if not config:
            return None
        
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        config.updated_at = datetime.now()
        
        logger.info(f"[ProductAgentRegistry] Updated team: {team_id}")
        return config
    
    def enable_app(self, app_code: str) -> bool:
        """启用应用的Agent团队"""
        mapping = self._app_mapping.get(app_code)
        if mapping:
            mapping.enabled = True
            mapping.updated_at = datetime.now()
            return True
        return False
    
    def disable_app(self, app_code: str) -> bool:
        """禁用应用的Agent团队"""
        mapping = self._app_mapping.get(app_code)
        if mapping:
            mapping.enabled = False
            mapping.updated_at = datetime.now()
            return True
        return False
    
    def bind_resources(
        self,
        app_code: str,
        resources: List[ResourceBinding],
    ) -> Optional[AgentTeamConfig]:
        """
        绑定资源到Agent团队
        
        Args:
            app_code: 产品应用代码
            resources: 资源绑定列表
        
        Returns:
            更新后的配置或None
        """
        config = self.get_team_config(app_code)
        if not config:
            return None
        
        existing_types = {r.resource_type for r in config.shared_resources}
        
        for resource in resources:
            if resource.resource_type in existing_types:
                for i, r in enumerate(config.shared_resources):
                    if r.resource_type == resource.resource_type:
                        config.shared_resources[i] = resource
                        break
            else:
                config.shared_resources.append(resource)
        
        config.updated_at = datetime.now()
        
        logger.info(f"[ProductAgentRegistry] Bound {len(resources)} resources to {app_code}")
        return config
    
    def unbind_resource(
        self,
        app_code: str,
        resource_type: str,
    ) -> Optional[AgentTeamConfig]:
        """解绑资源"""
        config = self.get_team_config(app_code)
        if not config:
            return None
        
        config.shared_resources = [
            r for r in config.shared_resources
            if r.resource_type != resource_type
        ]
        config.updated_at = datetime.now()
        
        return config
    
    def get_agent_config(self, agent_type: str) -> Optional[AgentConfig]:
        """获取Agent类型配置"""
        return self._agent_types.get(agent_type)
    
    def get_all_agent_types(self) -> Set[str]:
        """获取所有Agent类型"""
        return set(self._agent_types.keys())
    
    def list_apps(self) -> List[str]:
        """列出所有注册的应用"""
        return list(self._app_mapping.keys())
    
    def list_teams(self) -> List[AgentTeamConfig]:
        """列出所有团队配置"""
        return list(self._teams.values())
    
    def get_capabilities_for_app(self, app_code: str) -> Set[str]:
        """获取应用支持的团队能力"""
        config = self.get_team_config(app_code)
        if not config:
            return set()
        
        capabilities = set()
        for worker in config.worker_configs:
            capabilities.update(worker.capabilities)
        
        if config.coordinator_config:
            capabilities.update(config.coordinator_config.capabilities)
        
        return capabilities
    
    def create_default_team_config(
        self,
        app_code: str,
        app_name: Optional[str] = None,
    ) -> AgentTeamConfig:
        """创建默认团队配置"""
        config = AgentTeamConfig(
            team_id=f"default-{app_code}",
            team_name=f"Default Team for {app_name or app_code}",
            app_code=app_code,
            worker_configs=[
                AgentConfig(
                    agent_type="assistant",
                    capabilities=["general"],
                )
            ],
            execution_strategy="sequential",
            max_parallel_workers=1,
        )
        return config
    
    def get_or_create_config(self, app_code: str) -> AgentTeamConfig:
        """获取或创建配置"""
        config = self.get_team_config(app_code)
        if config:
            return config
        
        default_config = self.create_default_team_config(app_code)
        self.register_team(default_config)
        return default_config
    
    def export_config(self, app_code: str) -> Optional[Dict[str, Any]]:
        """导出配置为字典"""
        config = self.get_team_config(app_code)
        if not config:
            return None
        
        return config.model_dump()
    
    def import_config(
        self,
        config_dict: Dict[str, Any],
    ) -> AgentTeamConfig:
        """从字典导入配置"""
        config = AgentTeamConfig(**config_dict)
        self.register_team(config)
        return config
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        enabled_count = sum(1 for m in self._app_mapping.values() if m.enabled)
        
        total_workers = sum(
            len(config.worker_configs) for config in self._teams.values()
        )
        
        all_capabilities = set()
        for config in self._teams.values():
            for worker in config.worker_configs:
                all_capabilities.update(worker.capabilities)
        
        return {
            "total_teams": len(self._teams),
            "total_apps": len(self._app_mapping),
            "enabled_apps": enabled_count,
            "disabled_apps": len(self._app_mapping) - enabled_count,
            "total_worker_types": total_workers,
            "unique_capabilities": len(all_capabilities),
            "capabilities": list(all_capabilities),
        }


product_agent_registry = ProductAgentRegistry()