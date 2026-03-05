"""
Agent 选择 API - 支持按版本获取可用 Agent 列表

用于应用构建时选择主 Agent
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/agent", tags=["Agent Selection"])


@router.get("/list")
async def list_agents(
    version: str = Query(default="v1", description="Agent版本: v1 或 v2")
) -> Dict[str, Any]:
    """
    获取可用的 Agent 列表
    
    根据 agent_version 返回不同的 Agent 列表:
    - v1: 从 AgentManager 获取预注册的 Agent
    - v2: 返回 V2 预定义模板
    
    Args:
        version: Agent 版本 ("v1" | "v2")
    
    Returns:
        {
            "version": "v1" | "v2",
            "agents": [
                {
                    "name": "agent_name",
                    "display_name": "显示名称",
                    "description": "描述",
                    "tools": ["tool1", "tool2"],  # v2才有
                }
            ]
        }
    """
    if version == "v2":
        from derisk.agent.core.plan.unified_context import get_v2_agent_templates
        agents = get_v2_agent_templates()
    else:
        from derisk.agent import get_agent_manager
        agent_manager = get_agent_manager()
        all_agents = agent_manager.all_agents()
        agents = [
            {
                "name": name,
                "display_name": name,
                "description": desc,
            }
            for name, desc in all_agents.items()
        ]
    
    return {
        "version": version,
        "agents": agents,
    }


@router.get("/templates")
async def get_v2_templates() -> List[Dict[str, Any]]:
    """
    获取 V2 Agent 模板列表
    
    用于前端展示 V2 架构可用的 Agent 模板
    """
    from derisk.agent.core.plan.unified_context import get_v2_agent_templates
    return get_v2_agent_templates()


@router.get("/template/{name}")
async def get_template_detail(name: str) -> Dict[str, Any]:
    """
    获取指定 V2 Agent 模板的详细信息
    """
    from derisk.agent.core.plan.unified_context import get_v2_agent_template
    template = get_v2_agent_template(name)
    if not template:
        return {"error": f"Template '{name}' not found"}
    return template