"""
单元测试 - Permission权限系统

测试PermissionChecker、PermissionManager等
"""

import pytest
from derisk.agent.core_v2 import (
    PermissionRuleset,
    PermissionAction,
    PermissionChecker,
    PermissionManager,
    PermissionRequest,
    PermissionResponse,
    PermissionDeniedError,
)


class TestPermissionChecker:
    """PermissionChecker测试"""

    @pytest.fixture
    def ruleset(self):
        """创建测试用规则集"""
        return PermissionRuleset.from_dict(
            {"*": "allow", "*.env": "ask", "bash": "deny"}
        )

    @pytest.fixture
    def checker(self, ruleset):
        """创建权限检查器"""
        return PermissionChecker(ruleset)

    def test_check_allow(self, checker):
        """测试允许权限"""
        response = checker.check("read")
        assert response.granted is True
        assert response.action == PermissionAction.ALLOW

    def test_check_deny(self, checker):
        """测试拒绝权限"""
        response = checker.check("bash")
        assert response.granted is False
        assert response.action == PermissionAction.DENY

    def test_check_ask_sync(self, checker):
        """测试询问权限(同步模式默认拒绝)"""
        response = checker.check("file.env")
        assert response.granted is False
        assert response.action == PermissionAction.ASK

    @pytest.mark.asyncio
    async def test_check_ask_with_callback(self, checker):
        """测试询问权限(异步,带回调)"""

        async def ask_callback(request: PermissionRequest) -> bool:
            return True  # 用户批准

        response = await checker.check_async(
            "file.env",
            tool_args={"path": "/etc/config"},
            ask_user_callback=ask_callback,
        )

        assert response.granted is True
        assert response.action == PermissionAction.ASK

    @pytest.mark.asyncio
    async def test_check_ask_rejected_by_user(self, checker):
        """测试用户拒绝权限"""

        async def ask_callback(request: PermissionRequest) -> bool:
            return False  # 用户拒绝

        response = await checker.check_async("test.env", ask_user_callback=ask_callback)

        assert response.granted is False


class TestPermissionManager:
    """PermissionManager测试"""

    @pytest.fixture
    def manager(self):
        """创建权限管理器"""
        return PermissionManager()

    def test_register_agent_permission(self, manager):
        """测试注册Agent权限"""
        ruleset = PermissionRuleset.from_dict({"read": "allow", "write": "deny"})

        manager.register("test_agent", ruleset)

        checker = manager.get_checker("test_agent")
        assert checker is not None
        assert checker.check("read").granted is True
        assert checker.check("write").granted is False

    @pytest.mark.asyncio
    async def test_check_permission_via_manager(self, manager):
        """测试通过管理器检查权限"""
        ruleset = PermissionRuleset.from_dict({"*": "allow"})
        manager.register("my_agent", ruleset)

        response = await manager.check_async("my_agent", "bash", {"command": "ls"})

        assert response.granted is True

    @pytest.mark.asyncio
    async def test_check_nonexistent_agent(self, manager):
        """测试检查不存在的Agent"""
        response = await manager.check_async("nonexistent", "bash", {"command": "ls"})

        assert response.granted is False
        assert "未找到" in response.reason


class TestPermissionDeniedError:
    """PermissionDeniedError测试"""

    def test_create_error(self):
        """测试创建错误"""
        error = PermissionDeniedError(message="工具执行被拒绝", tool_name="bash")

        assert str(error) == "工具执行被拒绝"
        assert error.tool_name == "bash"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
