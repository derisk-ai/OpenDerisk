"""
Agent Binding - Agent资源绑定服务

实现产品应用与Agent、资源的绑定：
1. 产品-Agent绑定 - 将Agent团队绑定到产品应用
2. 资源注入 - 为Agent团队注入产品资源
3. 配置解析 - 解析产品配置生成Agent配置

@see ARCHITECTURE.md#12.10-agentbinding-绑定服务
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import logging

from pydantic import BaseModel, Field, ConfigDict

from .product_agent_registry import (
    ProductAgentRegistry,
    AgentTeamConfig,
    AgentConfig,
)
from .multi_agent.shared_context import SharedContext, ResourceBinding, ResourceScope
from .multi_agent.team import TeamConfig

logger = logging.getLogger(__name__)


class AgentResource(BaseModel):
    """Agent资源定义"""
    type: str
    value: Any
    name: Optional[str] = None
    is_dynamic: bool = False


class AppResource(BaseModel):
    """应用资源"""
    app_code: str
    app_name: Optional[str] = None
    resources: List[AgentResource] = Field(default_factory=list)


class BindingResult(BaseModel):
    """绑定结果"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    success: bool
    app_code: str
    team_config: Optional[AgentTeamConfig] = None
    shared_context: Optional[SharedContext] = None
    
    error: Optional[str] = None
    
    bound_resources: List[str] = Field(default_factory=list)
    bound_agents: List[str] = Field(default_factory=list)


class ResourceResolver:
    """
    资源解析器 - 完整支持 MCP、Knowledge、Skill 等资源类型
    
    负责将资源配置解析为实际可用的资源实例
    """
    
    def __init__(self, system_app: Optional[Any] = None):
        self._system_app = system_app
        self._mcp_tools_cache: Dict[str, Any] = {}
        self._knowledge_cache: Dict[str, Any] = {}
        self._skill_cache: Dict[str, Any] = {}
    
    async def resolve(
        self,
        resource_type: str,
        resource_value: Any,
    ) -> Tuple[Any, Optional[str]]:
        """
        解析资源
        
        Args:
            resource_type: 资源类型 (knowledge, tool, mcp, skill, database, workflow)
            resource_value: 资源值
        
        Returns:
            (资源实例, 错误信息)
        """
        try:
            resource_type_lower = resource_type.lower() if isinstance(resource_type, str) else resource_type
            
            if resource_type_lower in ("knowledge", "knowledge_pack", ResourceType.Knowledge if hasattr(ResourceType, 'Knowledge') else "knowledge"):
                return await self._resolve_knowledge(resource_value), None
            
            elif resource_type_lower in ("database",):
                return await self._resolve_database(resource_value), None
            
            elif resource_type_lower in ("tool", "local_tool"):
                return await self._resolve_tool(resource_value), None
            
            elif resource_type_lower in ("mcp", "tool(mcp)", "tool(mcp(sse))"):
                return await self._resolve_mcp(resource_value), None
            
            elif resource_type_lower in ("skill", "skill(derisk)"):
                return await self._resolve_skill(resource_value), None
            
            elif resource_type_lower in ("workflow",):
                return await self._resolve_workflow(resource_value), None
            
            else:
                return resource_value, None
                
        except Exception as e:
            logger.error(f"[ResourceResolver] Failed to resolve {resource_type}: {e}")
            return None, str(e)
    
    async def _resolve_knowledge(self, value: Any) -> Any:
        """
        解析知识资源
        
        返回知识空间的完整配置信息
        """
        import json
        
        knowledge_info = {"type": "knowledge"}
        
        if isinstance(value, dict):
            knowledge_info.update(value)
            space_id = value.get("space_id") or value.get("spaceId") or value.get("id")
            if space_id:
                knowledge_info["space_id"] = space_id
                knowledge_info["space_name"] = value.get("space_name") or value.get("name", space_id)
        
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                knowledge_info.update(parsed)
                space_id = parsed.get("space_id") or parsed.get("spaceId") or parsed.get("id")
                if space_id:
                    knowledge_info["space_id"] = space_id
            except:
                knowledge_info["space_id"] = value
                knowledge_info["space_name"] = value
        
        else:
            knowledge_info["space_id"] = str(value)
        
        cache_key = knowledge_info.get("space_id", str(value))
        if cache_key and cache_key in self._knowledge_cache:
            return self._knowledge_cache[cache_key]
        
        try:
            from derisk_serve.knowledge.service.service import KnowledgeService
            from derisk.agent.resource.manage import _SYSTEM_APP
            
            if _SYSTEM_APP and knowledge_info.get("space_id"):
                service = _SYSTEM_APP.get_component("knowledge_service", KnowledgeService, default=None)
                if service:
                    knowledge_space = service.get_knowledge_space(knowledge_info["space_id"])
                    if knowledge_space:
                        knowledge_info["space_name"] = knowledge_space.name
                        knowledge_info["vector_type"] = getattr(knowledge_space, "vector_type", None)
                        knowledge_info["owner"] = getattr(knowledge_space, "owner", None)
        except Exception as e:
            logger.debug(f"Could not fetch knowledge details: {e}")
        
        if cache_key:
            self._knowledge_cache[cache_key] = knowledge_info
        
        return knowledge_info
    
    async def _resolve_database(self, value: Any) -> Any:
        """解析数据库资源"""
        import json
        
        db_info = {"type": "database"}
        
        if isinstance(value, dict):
            db_info.update(value)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                db_info.update(parsed)
            except:
                db_info["name"] = value
        
        return db_info
    
    async def _resolve_tool(self, value: Any) -> Any:
        """
        解析本地工具资源
        
        返回工具配置信息
        """
        import json
        
        tool_info = {"type": "tool"}
        
        if isinstance(value, dict):
            tool_info.update(value)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                tool_info.update(parsed)
            except:
                tool_info["name"] = value
        
        return tool_info
    
    async def _resolve_mcp(self, value: Any) -> Any:
        """
        解析 MCP 资源
        
        返回 MCP 服务器配置和可用工具列表
        """
        import json
        
        mcp_info = {"type": "mcp"}
        
        if isinstance(value, dict):
            mcp_info.update(value)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                mcp_info.update(parsed)
            except:
                mcp_info["url"] = value
        
        servers = mcp_info.get("mcp_servers") or mcp_info.get("servers") or mcp_info.get("url")
        if isinstance(servers, str):
            servers = [s.strip() for s in servers.split(";") if s.strip()]
            mcp_info["servers"] = servers
        
        cache_key = str(servers)
        if cache_key in self._mcp_tools_cache:
            return self._mcp_tools_cache[cache_key]
        
        return mcp_info
    
    async def _resolve_skill(self, value: Any) -> Any:
        """
        解析技能资源
        
        返回技能的完整配置信息，包括沙箱路径
        """
        import json
        
        skill_info = {"type": "skill"}
        
        if isinstance(value, dict):
            skill_info.update(value)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                skill_info.update(parsed)
            except:
                skill_info["name"] = value
                skill_info["skill_name"] = value
        
        skill_code = skill_info.get("skill_code") or skill_info.get("skillCode") or skill_info.get("skill_name")
        if skill_code:
            skill_info["skill_code"] = skill_code
            
            cache_key = skill_code
            if cache_key in self._skill_cache:
                return self._skill_cache[cache_key]
            
            try:
                from derisk_serve.skill.service.service import Service, SKILL_SERVICE_COMPONENT_NAME
                from derisk.agent.resource.manage import _SYSTEM_APP
                
                if _SYSTEM_APP:
                    service = _SYSTEM_APP.get_component(SKILL_SERVICE_COMPONENT_NAME, Service, default=None)
                    if service:
                        skill_dir = service.get_skill_directory(skill_code)
                        if skill_dir:
                            skill_info["sandbox_path"] = skill_dir
                            skill_info["path"] = skill_dir
                            
                            skill_meta = service.get_skill_by_code(skill_code)
                            if skill_meta:
                                skill_info["name"] = skill_meta.name
                                skill_info["description"] = skill_meta.description
                                skill_info["author"] = skill_meta.author
                                skill_info["branch"] = getattr(skill_meta, "branch", "main")
            except Exception as e:
                logger.debug(f"Could not fetch skill details: {e}")
            
            self._skill_cache[cache_key] = skill_info
        
        return skill_info
    
    async def _resolve_workflow(self, value: Any) -> Any:
        """解析工作流资源"""
        import json
        
        workflow_info = {"type": "workflow"}
        
        if isinstance(value, dict):
            workflow_info.update(value)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                workflow_info.update(parsed)
            except:
                workflow_info["id"] = value
        
        return workflow_info
    
    def clear_cache(self):
        """清除所有缓存"""
        self._mcp_tools_cache.clear()
        self._knowledge_cache.clear()
        self._skill_cache.clear()


class ProductAgentBinding:
    """
    产品-Agent绑定服务
    
    将产品应用与Agent团队和资源进行绑定。
    
    @example
    ```python
    binding = ProductAgentBinding(registry, resource_resolver)
    
    # 绑定Agent团队到产品
    result = await binding.bind_agents_to_app(
        app_code="code_app",
        team_config=team_config,
    )
    
    # 解析产品的Agent和资源
    team_config, context = await binding.resolve_agents_for_app("code_app")
    ```
    """
    
    def __init__(
        self,
        registry: ProductAgentRegistry,
        resource_resolver: Optional[ResourceResolver] = None,
    ):
        self._registry = registry
        self._resolver = resource_resolver or ResourceResolver()
    
    async def bind_agents_to_app(
        self,
        app_code: str,
        team_config: AgentTeamConfig,
        resources: Optional[List[AgentResource]] = None,
    ) -> BindingResult:
        """
        将Agent团队绑定到产品应用
        
        Args:
            app_code: 产品应用代码
            team_config: Agent团队配置
            resources: 可选的资源列表
        
        Returns:
            BindingResult: 绑定结果
        """
        try:
            team_config.app_code = app_code
            
            if resources:
                resource_bindings = [
                    ResourceBinding(
                        resource_type=r.type,
                        resource_name=r.name or f"resource-{i}",
                        shared_scope=ResourceScope.TEAM,
                    )
                    for i, r in enumerate(resources)
                ]
                team_config.shared_resources = resource_bindings
            
            self._registry.register_team(team_config)
            
            result = BindingResult(
                success=True,
                app_code=app_code,
                team_config=team_config,
                bound_agents=[w.agent_type for w in team_config.worker_configs],
                bound_resources=[r.type for r in team_config.shared_resources],
            )
            
            logger.info(f"[AgentBinding] Bound team {team_config.team_id} to app {app_code}")
            return result
            
        except Exception as e:
            logger.error(f"[AgentBinding] Failed to bind: {e}")
            return BindingResult(
                success=False,
                app_code=app_code,
                error=str(e),
            )
    
    async def resolve_agents_for_app(
        self,
        app_code: str,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[AgentTeamConfig], SharedContext]:
        """
        解析产品应用关联的Agent和资源
        
        Args:
            app_code: 产品应用代码
            session_id: 会话ID（可选）
        
        Returns:
            (AgentTeamConfig, SharedContext): Agent团队配置和共享上下文
        """
        team_config = self._registry.get_team_config(app_code)
        
        if not team_config:
            team_config = self._registry.create_default_team_config(app_code)
        
        context = SharedContext(
            session_id=session_id or f"session-{app_code}",
        )
        
        for binding in team_config.shared_resources:
            resolved, error = await self._resolver.resolve(
                binding.resource_type,
                binding.resource_name,
            )
            
            if resolved and not error:
                context.set_resource(binding.resource_type, resolved)
        
        return team_config, context
    
    async def inject_resources(
        self,
        context: SharedContext,
        resources: List[AgentResource],
    ) -> int:
        """
        将资源注入共享上下文
        
        Args:
            context: 共享上下文
            resources: 资源列表
        
        Returns:
            成功注入的资源数量
        """
        injected = 0
        
        for resource in resources:
            resolved, error = await self._resolver.resolve(
                resource.type,
                resource.value,
            )
            
            if resolved and not error:
                context.set_resource(resource.type, resolved)
                injected += 1
        
        return injected
    
    async def create_execution_context(
        self,
        app_code: str,
        goal: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[TeamConfig], SharedContext]:
        """
        创建执行上下文
        
        Args:
            app_code: 应用代码
            goal: 目标
            user_context: 用户上下文
        
        Returns:
            (TeamConfig, SharedContext): 团队配置和共享上下文
        """
        team_config, context = await self.resolve_agents_for_app(app_code)
        
        if not team_config:
            return None, context
        
        if user_context:
            for key, value in user_context.items():
                if key.startswith("resource_"):
                    resource_type = key[9:]  # 去掉 "resource_" 前缀
                    context.set_resource(resource_type, value)
                else:
                    context._blackboard._data[key] = value
        
        await context.add_memory(
            content=f"Goal: {goal}",
            source="user",
            importance=1.0,
        )
        
        team_config_obj = team_config.to_team_config()
        
        return team_config_obj, context
    
    def get_app_capabilities(self, app_code: str) -> Dict[str, List[str]]:
        """
        获取应用的Agent能力
        
        Args:
            app_code: 应用代码
        
        Returns:
            {agent_type: [capabilities]} 映射
        """
        team_config = self._registry.get_team_config(app_code)
        if not team_config:
            return {}
        
        capabilities = {}
        
        for worker in team_config.worker_configs:
            capabilities[worker.agent_type] = worker.capabilities
        
        if team_config.coordinator_config:
            capabilities[team_config.coordinator_config.agent_type] = (
                team_config.coordinator_config.capabilities
            )
        
        return capabilities
    
    def update_agent_config(
        self,
        app_code: str,
        agent_type: str,
        updates: Dict[str, Any],
    ) -> bool:
        """
        更新应用的Agent配置
        
        Args:
            app_code: 应用代码
            agent_type: Agent类型
            updates: 更新内容
        
        Returns:
            是否成功
        """
        team_config = self._registry.get_team_config(app_code)
        if not team_config:
            return False
        
        for i, worker in enumerate(team_config.worker_configs):
            if worker.agent_type == agent_type:
                for key, value in updates.items():
                    if hasattr(worker, key):
                        setattr(worker, key, value)
                team_config.updated_at = datetime.now()
                return True
        
        if team_config.coordinator_config and team_config.coordinator_config.agent_type == agent_type:
            for key, value in updates.items():
                if hasattr(team_config.coordinator_config, key):
                    setattr(team_config.coordinator_config, key, value)
            team_config.updated_at = datetime.now()
            return True
        
        return False
    
    def get_binding_status(self, app_code: str) -> Dict[str, Any]:
        """获取绑定状态"""
        team_config = self._registry.get_team_config(app_code)
        
        if not team_config:
            return {
                "bound": False,
                "app_code": app_code,
                "error": "No team configuration found",
            }
        
        return {
            "bound": True,
            "app_code": app_code,
            "team_id": team_config.team_id,
            "team_name": team_config.team_name,
            "worker_count": len(team_config.worker_configs),
            "has_coordinator": team_config.coordinator_config is not None,
            "resource_count": len(team_config.shared_resources),
            "execution_strategy": team_config.execution_strategy,
            "created_at": team_config.created_at.isoformat(),
            "updated_at": team_config.updated_at.isoformat(),
        }
    
    def unbind_app(self, app_code: str) -> bool:
        """解除应用绑定"""
        team_config = self._registry.get_team_config(app_code)
        if not team_config:
            return False
        
        return self._registry.unregister_team(team_config.team_id)


product_agent_binding: Optional[ProductAgentBinding] = None


def get_product_agent_binding(
    registry: Optional[ProductAgentRegistry] = None,
) -> ProductAgentBinding:
    """获取产品Agent绑定服务实例"""
    global product_agent_binding
    
    if product_agent_binding is None:
        product_agent_binding = ProductAgentBinding(
            registry=registry or ProductAgentRegistry(),
        )
    
    return product_agent_binding