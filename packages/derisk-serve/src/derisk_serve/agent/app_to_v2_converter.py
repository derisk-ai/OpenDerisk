"""
App 构建 -> Core_v2 Agent 转换器
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List

from derisk.agent.core_v2 import AgentInfo, AgentMode, PermissionRuleset, PermissionAction
from derisk.agent.core_v2.integration import create_v2_agent
from derisk.agent.tools_v2 import BashTool, tool_registry
from derisk.agent.resource import ResourceType

logger = logging.getLogger(__name__)


async def convert_app_to_v2_agent(gpts_app, resources: List[Any] = None) -> Dict[str, Any]:
    """
    将 GptsApp 转换为 Core_v2 Agent
    
    Args:
        gpts_app: 原有的 GptsApp 对象
        resources: App 关联的资源列表
    
    Returns:
        Dict: 包含 agent, agent_info, tools 等信息
    """
    from derisk_serve.agent.team.base import TeamMode
    
    team_mode = getattr(gpts_app, "team_mode", "single_agent")
    mode_map = {
        TeamMode.SINGLE_AGENT.value: AgentMode.PRIMARY,
        TeamMode.AUTO_PLAN.value: AgentMode.PLANNER,
    }
    agent_mode = mode_map.get(team_mode, AgentMode.PRIMARY)
    
    permission = _build_permission_from_app(gpts_app)
    tools = await _convert_resources_to_tools(resources or [])
    
    agent_info = AgentInfo(
        name=gpts_app.app_code or "v2_agent",
        mode=agent_mode,
        description=getattr(gpts_app, "app_name", ""),
        max_steps=20,
        permission=permission,
    )
    
    agent = create_v2_agent(
        name=agent_info.name,
        mode=agent_info.mode.value,
        tools=tools,
        permission=_permission_to_dict(permission),
    )
    
    return {"agent": agent, "agent_info": agent_info, "tools": tools}


def _build_permission_from_app(gpts_app) -> PermissionRuleset:
    """从 App 配置构建权限规则"""
    rules = {}
    app_code = getattr(gpts_app, "app_code", "")
    
    if "read_only" in app_code.lower():
        rules["read"] = PermissionAction.ALLOW
        rules["glob"] = PermissionAction.ALLOW
        rules["grep"] = PermissionAction.ALLOW
        rules["write"] = PermissionAction.DENY
        rules["edit"] = PermissionAction.DENY
        rules["bash"] = PermissionAction.ASK
    else:
        rules["*"] = PermissionAction.ALLOW
        rules["*.env"] = PermissionAction.ASK
    
    return PermissionRuleset.from_dict({k: v.value for k, v in rules.items()})


async def _convert_resources_to_tools(resources: List[Any]) -> Dict[str, Any]:
    """将 App 资源转换为 Core_v2 工具"""
    tools = {"bash": BashTool()}
    
    for resource in resources:
        resource_type = _get_resource_type(resource)
        if resource_type == ResourceType.Tool:
            tool_name = getattr(resource, "name", None)
            if tool_name and tool_name in tool_registry._tools:
                tools[tool_name] = tool_registry.get(tool_name)
    
    return tools


def _get_resource_type(resource) -> Optional[ResourceType]:
    """获取资源类型"""
    if hasattr(resource, "type"):
        rtype = resource.type
        if isinstance(rtype, ResourceType):
            return rtype
        elif isinstance(rtype, str):
            try:
                return ResourceType(rtype)
            except:
                pass
    return None


def _permission_to_dict(permission: PermissionRuleset) -> Dict[str, str]:
    """将 PermissionRuleset 转换为字典"""
    return {k: v.value for k, v in permission.rules.items()}
