"""
AgentResource集成适配器

将现有的AgentResource体系转换为Core_V2的AgentInfo
"""

from typing import Dict, Any, Optional, List
from derisk.agent.core_v2 import (
    AgentInfo,
    AgentMode,
    PermissionRuleset,
    PermissionRule,
    PermissionAction,
)
from derisk.agent.core.resource import AgentResource


class AgentResourceAdapter:
    """
    AgentResource适配器 - 桥接现有资源体系与Core_V2

    负责将AgentResource转换为AgentInfo配置

    示例:
        adapter = AgentResourceAdapter()
        agent_info = adapter.to_agent_info(agent_resource)
    """

    @staticmethod
    def to_agent_info(resource: AgentResource) -> AgentInfo:
        """
        将AgentResource转换为AgentInfo

        Args:
            resource: 现有Agent资源定义

        Returns:
            AgentInfo: Core_V2的Agent配置
        """
        # 1. 基本信息转换
        agent_info = AgentInfo(
            name=resource.name or "primary",
            description=resource.description,
            mode=AgentResourceAdapter._convert_mode(resource),
            hidden=getattr(resource, "hidden", False),
            color=getattr(resource, "color", "#4A90E2"),
        )

        # 2. 模型配置转换
        if hasattr(resource, "llm_config") and resource.llm_config:
            llm_config = resource.llm_config
            agent_info.model_id = getattr(llm_config, "model_name", None)
            agent_info.provider_id = getattr(llm_config, "provider", None)
            agent_info.temperature = getattr(llm_config, "temperature", None)
            agent_info.max_tokens = getattr(llm_config, "max_tokens", None)

        # 3. 执行限制转换
        agent_info.max_steps = getattr(resource, "max_steps", 20)
        agent_info.timeout = getattr(resource, "timeout", 300)

        # 4. 权限配置转换
        agent_info.permission = AgentResourceAdapter._convert_permission(resource)

        # 5. 工具配置
        if hasattr(resource, "tools"):
            agent_info.tools = [
                tool.name if hasattr(tool, "name") else str(tool)
                for tool in resource.tools
            ]

        # 6. 提示词
        if hasattr(resource, "prompt_template"):
            agent_info.prompt = resource.prompt_template

        return agent_info

    @staticmethod
    def _convert_mode(resource: AgentResource) -> AgentMode:
        """转换Agent模式"""
        agent_type = getattr(resource, "agent_type", "primary")

        mode_mapping = {
            "primary": AgentMode.PRIMARY,
            "main": AgentMode.PRIMARY,
            "subagent": AgentMode.SUBAGENT,
            "sub": AgentMode.SUBAGENT,
            "utility": AgentMode.UTILITY,
        }

        return mode_mapping.get(agent_type.lower(), AgentMode.PRIMARY)

    @staticmethod
    def _convert_permission(resource: AgentResource) -> PermissionRuleset:
        """转换权限配置"""
        rules = []

        # 从resource中提取权限配置
        if hasattr(resource, "permissions"):
            permissions = resource.permissions

            if isinstance(permissions, dict):
                for pattern, action_str in permissions.items():
                    action = PermissionAction(action_str)
                    rules.append(PermissionRule(pattern=pattern, action=action))
            elif isinstance(permissions, list):
                for perm in permissions:
                    if isinstance(perm, dict):
                        rules.append(
                            PermissionRule(
                                pattern=perm.get("pattern", "*"),
                                action=PermissionAction(perm.get("action", "ask")),
                            )
                        )

        # 默认权限规则
        if not rules:
            # 根据agent类型设置默认权限
            agent_type = getattr(resource, "agent_type", "primary")

            if agent_type == "primary":
                rules = [
                    PermissionRule(pattern="*", action=PermissionAction.ALLOW),
                    PermissionRule(pattern="*.env", action=PermissionAction.ASK),
                    PermissionRule(pattern="bash", action=PermissionAction.ASK),
                ]
            elif agent_type == "plan":
                rules = [
                    PermissionRule(pattern="read", action=PermissionAction.ALLOW),
                    PermissionRule(pattern="glob", action=PermissionAction.ALLOW),
                    PermissionRule(pattern="grep", action=PermissionAction.ALLOW),
                    PermissionRule(pattern="write", action=PermissionAction.DENY),
                    PermissionRule(pattern="edit", action=PermissionAction.DENY),
                ]
            else:
                rules = [
                    PermissionRule(pattern="*", action=PermissionAction.ASK),
                ]

        return PermissionRuleset(rules=rules, default_action=PermissionAction.ASK)

    @staticmethod
    def from_agent_info(agent_info: AgentInfo) -> Dict[str, Any]:
        """
        将AgentInfo转换回字典格式（用于序列化）

        Args:
            agent_info: Core_V2的Agent配置

        Returns:
            Dict: 可序列化的Agent配置
        """
        return {
            "name": agent_info.name,
            "description": agent_info.description,
            "mode": agent_info.mode,
            "hidden": agent_info.hidden,
            "model_id": agent_info.model_id,
            "provider_id": agent_info.provider_id,
            "temperature": agent_info.temperature,
            "max_tokens": agent_info.max_tokens,
            "max_steps": agent_info.max_steps,
            "timeout": agent_info.timeout,
            "permission": {
                "rules": [
                    {"pattern": r.pattern, "action": r.action}
                    for r in agent_info.permission.rules
                ],
                "default_action": agent_info.permission.default_action,
            },
            "tools": agent_info.tools,
            "excluded_tools": agent_info.excluded_tools,
            "color": agent_info.color,
            "prompt": agent_info.prompt,
            "options": agent_info.options,
        }


class AgentFactory:
    """
    Agent工厂 - 统一创建Agent实例

    整合AgentResource和Core_V2的AgentBase
    """

    def __init__(self):
        self.resource_adapter = AgentResourceAdapter()

    def create_agent(self, resource: AgentResource, agent_class=None, **kwargs):
        """
        创建Agent实例

        Args:
            resource: Agent资源定义
            agent_class: 自定义Agent类（需继承AgentBase）
            **kwargs: 额外参数

        Returns:
            Agent实例
        """
        # 转换配置
        agent_info = self.resource_adapter.to_agent_info(resource)

        # 如果没有指定agent_class，使用资源中的agent类
        if agent_class is None:
            agent_class = getattr(resource, "agent_class", None)

        # 创建实例
        if agent_class:
            return agent_class(agent_info, **kwargs)
        else:
            # 返回默认Agent
            from derisk.agent.core_v2.agent_base import SimpleAgent

            return SimpleAgent(agent_info)

    def create_from_config(self, config: Dict[str, Any], agent_class=None):
        """
        从配置字典创建Agent

        Args:
            config: Agent配置字典
            agent_class: Agent类

        Returns:
            Agent实例
        """
        agent_info = AgentInfo(**config)

        if agent_class:
            return agent_class(agent_info)
        else:
            from derisk.agent.core_v2.agent_base import SimpleAgent

            return SimpleAgent(agent_info)
