"""
Tests for SubagentManager and TaskTool

测试子Agent委派功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from derisk.agent.core_v2.subagent_manager import (
    SubagentManager,
    SubagentRegistry,
    SubagentInfo,
    SubagentResult,
    SubagentSession,
    SubagentStatus,
    TaskPermission,
    TaskPermissionConfig,
    TaskPermissionRule,
)
from derisk.agent.core_v2.agent_info import AgentMode


class TestSubagentRegistry:
    """测试子Agent注册表"""
    
    def test_register_subagent(self):
        """测试注册子Agent"""
        registry = SubagentRegistry()
        
        info = SubagentInfo(
            name="test-agent",
            description="测试Agent",
            capabilities=["test"],
        )
        
        registry.register(info)
        
        assert registry.get("test-agent") == info
        assert len(registry.list_all()) == 1
    
    def test_unregister_subagent(self):
        """测试注销子Agent"""
        registry = SubagentRegistry()
        
        info = SubagentInfo(
            name="test-agent",
            description="测试Agent",
        )
        
        registry.register(info)
        assert registry.get("test-agent") is not None
        
        result = registry.unregister("test-agent")
        assert result is True
        assert registry.get("test-agent") is None
    
    def test_list_for_llm(self):
        """测试生成给LLM的子Agent列表"""
        registry = SubagentRegistry()
        
        registry.register(SubagentInfo(
            name="explore",
            description="探索Agent",
            capabilities=["search"],
        ))
        
        registry.register(SubagentInfo(
            name="code-reviewer",
            description="代码审查Agent",
            capabilities=["review"],
            hidden=True,
        ))
        
        llm_list = registry.list_for_llm()
        
        assert len(llm_list) == 1
        assert llm_list[0]["name"] == "explore"


class TestTaskPermissionConfig:
    """测试任务权限配置"""
    
    def test_check_permission_allow(self):
        """测试允许权限"""
        config = TaskPermissionConfig(
            rules=[
                TaskPermissionRule(pattern="explore", action=TaskPermission.ALLOW),
            ],
        )
        
        assert config.check("explore") == TaskPermission.ALLOW
    
    def test_check_permission_deny(self):
        """测试拒绝权限"""
        config = TaskPermissionConfig(
            rules=[
                TaskPermissionRule(pattern="*", action=TaskPermission.DENY),
                TaskPermissionRule(pattern="explore", action=TaskPermission.ALLOW),
            ],
        )
        
        assert config.check("explore") == TaskPermission.ALLOW
        assert config.check("other") == TaskPermission.DENY
    
    def test_check_permission_wildcard(self):
        """测试通配符匹配"""
        config = TaskPermissionConfig(
            rules=[
                TaskPermissionRule(pattern="code-*", action=TaskPermission.ALLOW),
            ],
        )
        
        assert config.check("code-reviewer") == TaskPermission.ALLOW
        assert config.check("code-writer") == TaskPermission.ALLOW
        assert config.check("explore") == TaskPermission.DENY


class TestSubagentSession:
    """测试子Agent会话"""
    
    def test_create_session(self):
        """测试创建会话"""
        session = SubagentSession(
            session_id="test-session",
            parent_session_id="parent-session",
            subagent_name="explore",
            task="搜索文件",
        )
        
        assert session.session_id == "test-session"
        assert session.status == SubagentStatus.IDLE
        assert session.result is None
    
    def test_session_to_dict(self):
        """测试会话序列化"""
        session = SubagentSession(
            session_id="test-session",
            parent_session_id="parent-session",
            subagent_name="explore",
            task="搜索文件",
        )
        
        data = session.to_dict()
        
        assert data["session_id"] == "test-session"
        assert data["subagent_name"] == "explore"
        assert data["status"] == "idle"


class TestSubagentResult:
    """测试子Agent结果"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = SubagentResult(
            success=True,
            subagent_name="explore",
            task="搜索文件",
            output="找到了5个文件",
            session_id="test-session",
        )
        
        assert result.success is True
        assert "找到了5个文件" in result.to_llm_message()
    
    def test_failure_result(self):
        """测试失败结果"""
        result = SubagentResult(
            success=False,
            subagent_name="explore",
            task="搜索文件",
            error="超时",
            session_id="test-session",
        )
        
        assert result.success is False
        assert "失败" in result.to_llm_message()


class TestSubagentManager:
    """测试子Agent管理器"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        manager = SubagentManager()
        
        manager.register(SubagentInfo(
            name="mock-agent",
            description="模拟Agent",
            capabilities=["test"],
        ))
        
        return manager
    
    @pytest.mark.asyncio
    async def test_delegate_nonexistent_agent(self, manager):
        """测试委派给不存在的Agent"""
        result = await manager.delegate(
            subagent_name="nonexistent",
            task="测试任务",
            parent_session_id="parent-123",
        )
        
        assert result.success is False
        assert "不存在" in result.error
    
    @pytest.mark.asyncio
    async def test_can_delegate(self, manager):
        """测试检查委派权限"""
        can_delegate = await manager.can_delegate(
            subagent_name="mock-agent",
            task="测试任务",
        )
        
        assert can_delegate is True
    
    @pytest.mark.asyncio
    async def test_can_delegate_with_permission_deny(self, manager):
        """测试权限拒绝的委派"""
        permission = TaskPermissionConfig(
            rules=[
                TaskPermissionRule(pattern="mock-agent", action=TaskPermission.DENY),
            ],
        )
        
        can_delegate = await manager.can_delegate(
            subagent_name="mock-agent",
            task="测试任务",
            caller_permission=permission,
        )
        
        assert can_delegate is False
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, manager):
        """测试获取统计信息"""
        stats = manager.get_statistics()
        
        assert "total_sessions" in stats
        assert "registered_subagents" in stats


class TestSubagentManagerWithFactory:
    """测试带工厂的子Agent管理器"""
    
    @pytest.fixture
    def manager_with_factory(self):
        """创建带工厂的管理器"""
        manager = SubagentManager()
        
        async def mock_factory(subagent_info, context):
            agent = MagicMock()
            agent.run = AsyncMock(return_value=MagicMock(
                content="模拟执行结果",
            ))
            return agent
        
        manager.register(
            SubagentInfo(
                name="test-agent",
                description="测试Agent",
                capabilities=["test"],
            ),
            factory=mock_factory,
        )
        
        return manager
    
    @pytest.mark.asyncio
    async def test_delegate_with_factory(self, manager_with_factory):
        """测试使用工厂委派任务"""
        result = await manager_with_factory.delegate(
            subagent_name="test-agent",
            task="执行测试",
            parent_session_id="parent-123",
        )
        
        assert result.success is True
        assert result.output == "模拟执行结果"


class TestTaskPermission:
    """测试任务权限系统"""
    
    def test_permission_from_dict(self):
        """测试从字典创建权限配置"""
        config = TaskPermissionConfig.from_dict({
            "explore": "allow",
            "code-*": "allow",
            "*": "ask",
        })
        
        assert config.check("explore") == TaskPermission.ALLOW
        assert config.check("code-reviewer") == TaskPermission.ALLOW
        assert config.check("other") == TaskPermission.ASK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])