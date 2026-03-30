"""
App 构建 -> Core_v2 Agent 转换器

完整支持 MCP、Knowledge、Skill 等资源类型的转换
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, Tuple

from derisk.agent.core_v2 import (
    AgentInfo,
    AgentMode,
    PermissionRuleset,
    PermissionAction,
)
from derisk.agent.core_v2.integration import create_v2_agent
from derisk.agent.tools import BashTool, tool_registry
from derisk.agent.resource import ResourceType

logger = logging.getLogger(__name__)


async def convert_app_to_v2_agent(
    gpts_app, resources: List[Any] = None
) -> Dict[str, Any]:
    """
    将 GptsApp 转换为 Core_v2 Agent

    Args:
        gpts_app: 原有的 GptsApp 对象
        resources: App 关联的资源列表

    Returns:
        Dict: 包含 agent, agent_info, tools, knowledge, skills 等信息
    """
    from derisk_serve.agent.team.base import TeamMode

    team_mode = getattr(gpts_app, "team_mode", "single_agent")
    mode_map = {
        TeamMode.SINGLE_AGENT.value: AgentMode.PRIMARY,
        TeamMode.AUTO_PLAN.value: AgentMode.PRIMARY,
    }
    agent_mode = mode_map.get(team_mode, AgentMode.PRIMARY)

    permission = _build_permission_from_app(gpts_app)

    resources = resources or []
    tools, knowledge, skills, prompt_appendix = await _convert_all_resources(resources)

    agent_info = AgentInfo(
        name=gpts_app.app_code or "v2_agent",
        mode=agent_mode,
        description=getattr(gpts_app, "app_name", ""),
        max_steps=20,
        permission=permission,
        prompt=prompt_appendix or None,
    )

    agent = create_v2_agent(
        name=agent_info.name,
        mode=agent_info.mode.value,
        tools=tools,
        resources={
            "knowledge": knowledge,
            "skills": skills,
        },
        permission=_permission_to_dict(permission),
    )

    return {
        "agent": agent,
        "agent_info": agent_info,
        "tools": tools,
        "knowledge": knowledge,
        "skills": skills,
    }


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


async def _convert_all_resources(
    resources: List[Any],
) -> Tuple[Dict[str, Any], List[Dict], List[Dict], str]:
    """
    转换所有类型的资源

    Returns:
        Tuple[tools, knowledge, skills, prompt_appendix]
    """
    tools = {"bash": BashTool()}
    knowledge = []
    skills = []
    prompt_parts = []

    for resource in resources:
        try:
            resource_type = _get_resource_type(resource)
            resource_value = _get_resource_value(resource)

            if resource_type is None:
                logger.warning(
                    f"Unknown resource type: {getattr(resource, 'type', resource)}"
                )
                continue

            if resource_type == ResourceType.Tool or resource_type == "tool":
                await _process_tool_resource(resource, resource_value, tools)

            elif resource_type in (
                ResourceType.Knowledge,
                ResourceType.KnowledgePack,
            ) or resource_type in ("knowledge", "knowledge_pack"):
                knowledge_info = _process_knowledge_resource(resource, resource_value)
                if knowledge_info:
                    knowledge.append(knowledge_info)

            elif resource_type == "skill" or resource_type.startswith("skill"):
                skill_info, skill_prompt = await _process_skill_resource(
                    resource, resource_value
                )
                if skill_info:
                    skills.append(skill_info)
                if skill_prompt:
                    prompt_parts.append(skill_prompt)

            elif resource_type == ResourceType.App or resource_type == "app":
                await _process_app_resource(
                    resource, resource_value, tools, knowledge, skills
                )

            else:
                logger.warning(
                    f"Unsupported resource type for Core_v2: {resource_type}"
                )

        except Exception as e:
            logger.error(
                f"Error converting resource {getattr(resource, 'name', 'unknown')}: {e}"
            )
            continue

    prompt_appendix = "\n\n".join(prompt_parts) if prompt_parts else ""

    return tools, knowledge, skills, prompt_appendix


async def _process_tool_resource(
    resource: Any, resource_value: Any, tools: Dict[str, Any]
):
    """处理工具资源，包括 MCP、本地工具等"""
    resource_type_str = getattr(resource, "type", "")
    name = getattr(resource, "name", "tool")

    if "mcp" in resource_type_str.lower() or (
        isinstance(resource_value, dict) and "mcp_servers" in resource_value
    ):
        mcp_tools = await _convert_mcp_resource(resource, resource_value)
        tools.update(mcp_tools)

    elif "local" in resource_type_str.lower():
        local_tools = _convert_local_tool_resource(resource, resource_value)
        tools.update(local_tools)

    else:
        if name and name in tool_registry._tools:
            tools[name] = tool_registry.get(name)


async def _convert_mcp_resource(resource: Any, resource_value: Any) -> Dict[str, Any]:
    """
    转换 MCP 资源为 Core_v2 工具

    支持:
    - MCPToolPack / MCPSSEToolPack
    - MCP 连接配置
    """
    tools = {}

    try:
        from derisk.agent.tools.builtin.mcp import (
            MCPToolAdapter,
            MCPToolRegistry,
            mcp_connection_manager,
        )

        mcp_servers = None
        headers = {}
        tool_name = getattr(resource, "name", "mcp")

        if isinstance(resource_value, dict):
            mcp_servers = (
                resource_value.get("mcp_servers")
                or resource_value.get("servers")
                or resource_value.get("url")
            )
            headers = resource_value.get("headers", {})
            if isinstance(headers, str):
                try:
                    headers = json.loads(headers)
                except:
                    headers = {}
        elif isinstance(resource_value, str):
            try:
                parsed = json.loads(resource_value)
                mcp_servers = parsed.get("mcp_servers") or parsed.get("url")
                headers = parsed.get("headers", {})
            except:
                mcp_servers = resource_value

        if not mcp_servers:
            logger.warning(f"MCP resource {tool_name} has no server configuration")
            return tools

        if isinstance(mcp_servers, str):
            server_list = [s.strip() for s in mcp_servers.split(";") if s.strip()]
        else:
            server_list = (
                mcp_servers if isinstance(mcp_servers, list) else [mcp_servers]
            )

        for server_url in server_list:
            try:
                server_name = server_url.split("/")[-1] or f"mcp_server_{len(tools)}"

                mcp_tools = await _load_mcp_tools_from_server(
                    server_url, server_name, headers, tool_name
                )
                tools.update(mcp_tools)

            except Exception as e:
                logger.error(f"Failed to load MCP tools from {server_url}: {e}")
                continue

    except ImportError as e:
        logger.warning(f"MCP tool adapter not available: {e}")
    except Exception as e:
        logger.error(f"Error converting MCP resource: {e}")

    return tools


async def _load_mcp_tools_from_server(
    server_url: str, server_name: str, headers: Dict[str, Any], resource_name: str
) -> Dict[str, Any]:
    """从 MCP 服务器加载工具"""
    tools = {}

    try:
        from derisk_serve.agent.resource.tool.mcp import MCPToolPack
        from derisk.agent.tools.builtin.mcp import MCPToolAdapter

        mcp_pack = MCPToolPack(
            mcp_servers=server_url,
            headers=headers if headers else None,
            name=resource_name,
        )

        await mcp_pack.preload_resource()

        for tool_name, base_tool in mcp_pack._commands.items():
            try:
                adapter = MCPToolAdapter(
                    mcp_tool=base_tool,
                    server_name=server_name,
                    mcp_client=mcp_pack,
                )
                adapted_name = f"mcp_{server_name}_{tool_name}"
                tools[adapted_name] = adapter
                tools[tool_name] = adapter

            except Exception as e:
                logger.warning(f"Failed to adapt MCP tool {tool_name}: {e}")
                continue

        logger.info(f"Loaded {len(tools)} MCP tools from {server_url}")

    except Exception as e:
        logger.error(f"Failed to load MCP tools from {server_url}: {e}")

    return tools


def _convert_local_tool_resource(resource: Any, resource_value: Any) -> Dict[str, Any]:
    """转换本地工具资源"""
    tools = {}

    try:
        name = getattr(resource, "name", "local_tool")

        if name and name in tool_registry._tools:
            tools[name] = tool_registry.get(name)

        if isinstance(resource_value, dict):
            tool_names = resource_value.get("tools", [])
            for tname in tool_names:
                if tname in tool_registry._tools:
                    tools[tname] = tool_registry.get(tname)

    except Exception as e:
        logger.error(f"Error converting local tool resource: {e}")

    return tools


def _process_knowledge_resource(
    resource: Any, resource_value: Any
) -> Optional[Dict[str, Any]]:
    """处理知识资源"""
    try:
        name = getattr(resource, "name", "knowledge")

        knowledge_info = {
            "name": name,
            "type": getattr(resource, "type", "knowledge"),
        }

        if isinstance(resource_value, dict):
            knowledge_info.update(resource_value)
        elif isinstance(resource_value, str):
            try:
                parsed = json.loads(resource_value)
                knowledge_info.update(parsed)
            except:
                knowledge_info["space_id"] = resource_value
                knowledge_info["space_name"] = name

        return knowledge_info

    except Exception as e:
        logger.error(f"Error processing knowledge resource: {e}")
        return None


async def _process_skill_resource(
    resource: Any, resource_value: Any
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """处理技能资源"""
    skill_info = None
    skill_prompt = None

    try:
        from derisk_serve.agent.resource.derisk_skill import DeriskSkillResource

        name = getattr(resource, "name", "skill")

        skill_params = {}
        if isinstance(resource_value, dict):
            skill_params = resource_value.copy()
        elif isinstance(resource_value, str):
            try:
                skill_params = json.loads(resource_value)
            except:
                skill_params = {"skill_name": resource_value}

        skill_params.setdefault("name", name)

        skill_resource = DeriskSkillResource(
            name=name,
            skill_name=skill_params.get("skill_name", skill_params.get("name")),
            skill_code=skill_params.get("skill_code") or skill_params.get("skillCode"),
            skill_description=skill_params.get("skill_description")
            or skill_params.get("description"),
            skill_path=skill_params.get("skill_path") or skill_params.get("path"),
            skill_branch=skill_params.get("skill_branch")
            or skill_params.get("branch", "main"),
            skill_author=skill_params.get("skill_author") or skill_params.get("owner"),
        )

        skill_info = {
            "name": skill_resource.skill_name,
            "code": skill_resource.skill_code,
            "description": skill_resource.description,
            "path": skill_resource.path,
            "branch": skill_resource.branch,
            "owner": skill_resource.owner,
        }

        prompt_result = await skill_resource.get_prompt()
        if prompt_result:
            skill_prompt = prompt_result[0]

    except ImportError:
        logger.warning("DeriskSkillResource not available")
    except Exception as e:
        logger.error(f"Error processing skill resource: {e}")

    return skill_info, skill_prompt


async def _process_app_resource(
    resource: Any,
    resource_value: Any,
    tools: Dict[str, Any],
    knowledge: List[Dict],
    skills: List[Dict],
):
    """处理嵌套的 App 资源"""
    try:
        app_code = None

        if isinstance(resource_value, dict):
            app_code = resource_value.get("app_code")
        elif isinstance(resource_value, str):
            try:
                parsed = json.loads(resource_value)
                app_code = parsed.get("app_code")
            except:
                pass

        if app_code:
            logger.info(f"Found nested app resource: {app_code}")

    except Exception as e:
        logger.error(f"Error processing app resource: {e}")


def _get_resource_type(resource: Any) -> Optional[str]:
    """获取资源类型"""
    if hasattr(resource, "type"):
        rtype = resource.type
        if isinstance(rtype, ResourceType):
            return rtype
        elif isinstance(rtype, str):
            return rtype
    return None


def _get_resource_value(resource: Any) -> Any:
    """获取资源值"""
    if hasattr(resource, "value"):
        return resource.value
    elif hasattr(resource, "config"):
        return resource.config
    return None


def _permission_to_dict(permission: PermissionRuleset) -> Dict[str, str]:
    """将 PermissionRuleset 转换为字典"""
    return {k: v.value for k, v in permission.rules.items()}
