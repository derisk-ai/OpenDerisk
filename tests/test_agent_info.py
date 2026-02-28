"""
单元测试 - AgentInfo配置模型

测试AgentInfo、PermissionRuleset等核心模型
"""

import pytest
from derisk.agent.core_v2 import (
    AgentInfo,
    AgentMode,
    PermissionRuleset,
    PermissionRule,
    PermissionAction,
    get_agent_info,
    register_agent,
)


class TestPermissionRuleset:
    """PermissionRuleset测试"""

    def test_create_empty_ruleset(self):
        """测试创建空规则集"""
        ruleset = PermissionRuleset()
        assert ruleset.default_action == PermissionAction.ASK
        assert len(ruleset.rules) == 0

    def test_add_rule(self):
        """测试添加规则"""
        ruleset = PermissionRuleset()
        ruleset.add_rule("bash", PermissionAction.ALLOW)

        assert len(ruleset.rules) == 1
        assert ruleset.check("bash") == PermissionAction.ALLOW

    def test_check_permission_wildcard(self):
        """测试通配符权限检查"""
        ruleset = PermissionRuleset(
            rules=[
                PermissionRule(pattern="*", action=PermissionAction.ALLOW),
                PermissionRule(pattern="*.env", action=PermissionAction.ASK),
            ]
        )

        # 匹配第一个规则
        assert ruleset.check("bash") == PermissionAction.ALLOW
        assert ruleset.check("read") == PermissionAction.ALLOW

        # 匹配第二个规则
        assert ruleset.check("file.env") == PermissionAction.ASK
        assert ruleset.check(".env") == PermissionAction.ASK

    def test_from_dict(self):
        """测试从字典创建"""
        ruleset = PermissionRuleset.from_dict(
            {"*": "allow", "*.env": "ask", "bash": "deny"}
        )

        assert ruleset.check("read") == PermissionAction.ALLOW
        assert ruleset.check("file.env") == PermissionAction.ASK
        assert ruleset.check("bash") == PermissionAction.DENY


class TestAgentInfo:
    """AgentInfo测试"""

    def test_create_default_agent(self):
        """测试创建默认Agent"""
        agent_info = AgentInfo(name="test")

        assert agent_info.name == "test"
        assert agent_info.mode == AgentMode.PRIMARY
        assert agent_info.hidden is False
        assert agent_info.max_steps == 20
        assert agent_info.timeout == 300

    def test_create_agent_with_custom_params(self):
        """测试创建自定义参数Agent"""
        agent_info = AgentInfo(
            name="custom",
            description="Custom Agent",
            mode=AgentMode.SUBAGENT,
            max_steps=15,
            temperature=0.7,
            color="#FF0000",
        )

        assert agent_info.name == "custom"
        assert agent_info.description == "Custom Agent"
        assert agent_info.mode == AgentMode.SUBAGENT
        assert agent_info.max_steps == 15
        assert agent_info.temperature == 0.7
        assert agent_info.color == "#FF0000"

    def test_agent_with_permission(self):
        """测试带权限的Agent"""
        agent_info = AgentInfo(
            name="restricted",
            permission=PermissionRuleset.from_dict({"read": "allow", "bash": "deny"}),
        )

        assert agent_info.permission.check("read") == PermissionAction.ALLOW
        assert agent_info.permission.check("bash") == PermissionAction.DENY

    def test_get_builtin_agent(self):
        """测试获取内置Agent"""
        primary = get_agent_info("primary")
        assert primary is not None
        assert primary.name == "primary"
        assert primary.mode == AgentMode.PRIMARY

        plan = get_agent_info("plan")
        assert plan is not None
        assert plan.name == "plan"

    def test_register_custom_agent(self):
        """测试注册自定义Agent"""
        custom = AgentInfo(name="my_agent", description="My custom agent")

        register_agent(custom)

        retrieved = get_agent_info("my_agent")
        assert retrieved is not None
        assert retrieved.name == "my_agent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
