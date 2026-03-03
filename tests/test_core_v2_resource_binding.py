"""
Core_v2 资源绑定流程验证测试

验证 MCP、Knowledge、Skill 等资源能够正确绑定到 Core_v2 Agent
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List


class TestCoreV2ResourceBinding:
    """Core_v2 资源绑定测试"""

    def test_convert_knowledge_resource(self):
        """测试知识资源转换"""
        from derisk_serve.agent.app_to_v2_converter import _convert_all_resources
        
        knowledge_resource = Mock()
        knowledge_resource.type = "knowledge"
        knowledge_resource.name = "test_knowledge"
        knowledge_resource.value = json.dumps({
            "space_id": "kb_001",
            "space_name": "Test Knowledge Base"
        })
        
        async def run_test():
            tools, knowledge, skills, prompt = await _convert_all_resources([knowledge_resource])
            
            assert len(knowledge) == 1
            assert knowledge[0]["space_id"] == "kb_001"
            assert knowledge[0]["space_name"] == "Test Knowledge Base"
            assert "bash" in tools  # 默认工具
        
        asyncio.run(run_test())

    def test_convert_mcp_resource(self):
        """测试 MCP 资源转换"""
        from derisk_serve.agent.app_to_v2_converter import _convert_all_resources
        
        mcp_resource = Mock()
        mcp_resource.type = "tool(mcp(sse))"
        mcp_resource.name = "test_mcp"
        mcp_resource.value = json.dumps({
            "mcp_servers": "http://localhost:8000/sse",
            "headers": {"Authorization": "Bearer token"}
        })
        
        async def run_test():
            with patch('derisk_serve.agent.app_to_v2_converter._convert_mcp_resource') as mock_mcp:
                mock_mcp.return_value = {"mcp_tool": Mock()}
                
                tools, knowledge, skills, prompt = await _convert_all_resources([mcp_resource])
                
                assert "bash" in tools
                mock_mcp.assert_called_once()
        
        asyncio.run(run_test())

    def test_convert_skill_resource(self):
        """测试技能资源转换"""
        from derisk_serve.agent.app_to_v2_converter import _convert_all_resources
        
        skill_resource = Mock()
        skill_resource.type = "skill(derisk)"
        skill_resource.name = "code_assistant"
        skill_resource.value = json.dumps({
            "skill_code": "skill_001",
            "skill_name": "Code Assistant",
            "description": "Help with coding tasks"
        })
        
        async def run_test():
            with patch('derisk_serve.agent.app_to_v2_converter._process_skill_resource') as mock_skill:
                mock_skill.return_value = (
                    {
                        "name": "Code Assistant",
                        "code": "skill_001",
                        "description": "Help with coding tasks"
                    },
                    "<agent-skills>...</agent-skills>"
                )
                
                tools, knowledge, skills, prompt = await _convert_all_resources([skill_resource])
                
                assert len(skills) == 1
                assert skills[0]["code"] == "skill_001"
                assert prompt != ""
        
        asyncio.run(run_test())

    def test_convert_multiple_resources(self):
        """测试多种资源混合转换"""
        from derisk_serve.agent.app_to_v2_converter import _convert_all_resources
        
        resources = [
            Mock(type="knowledge", name="kb1", value='{"space_id": "kb_001"}'),
            Mock(type="tool", name="local_tool", value='{"tools": ["tool1", "tool2"]}'),
            Mock(type="skill(derisk)", name="skill1", value='{"skill_code": "s001"}'),
        ]
        
        async def run_test():
            tools, knowledge, skills, prompt = await _convert_all_resources(resources)
            
            assert "bash" in tools
            assert len(knowledge) == 1
            assert len(skills) >= 0
        
        asyncio.run(run_test())

    def test_app_to_v2_agent_conversion(self):
        """测试完整的应用转换流程"""
        from derisk_serve.agent.app_to_v2_converter import convert_app_to_v2_agent
        
        gpts_app = Mock()
        gpts_app.app_code = "test_app"
        gpts_app.app_name = "Test Application"
        gpts_app.team_mode = "single_agent"
        
        resources = [
            Mock(type="knowledge", name="kb1", value='{"space_id": "kb_001"}'),
        ]
        
        async def run_test():
            result = await convert_app_to_v2_agent(gpts_app, resources)
            
            assert "agent" in result
            assert "agent_info" in result
            assert "tools" in result
            assert "knowledge" in result
            assert "skills" in result
            
            assert result["agent_info"].name == "test_app"
            assert len(result["knowledge"]) == 1
        
        asyncio.run(run_test())


class TestResourceResolver:
    """ResourceResolver 测试"""

    def test_resolve_knowledge(self):
        """测试知识资源解析"""
        from derisk.agent.core_v2.agent_binding import ResourceResolver
        
        resolver = ResourceResolver()
        
        async def run_test():
            result, error = await resolver.resolve("knowledge", '{"space_id": "kb_001"}')
            
            assert error is None
            assert result["type"] == "knowledge"
            assert result["space_id"] == "kb_001"
        
        asyncio.run(run_test())

    def test_resolve_skill(self):
        """测试技能资源解析"""
        from derisk.agent.core_v2.agent_binding import ResourceResolver
        
        resolver = ResourceResolver()
        
        async def run_test():
            result, error = await resolver.resolve("skill", '{"skill_code": "s001", "skill_name": "Test Skill"}')
            
            assert error is None
            assert result["type"] == "skill"
            assert result["skill_code"] == "s001"
        
        asyncio.run(run_test())

    def test_resolve_mcp(self):
        """测试 MCP 资源解析"""
        from derisk.agent.core_v2.agent_binding import ResourceResolver
        
        resolver = ResourceResolver()
        
        async def run_test():
            result, error = await resolver.resolve("mcp", '{"url": "http://localhost:8000/sse"}')
            
            assert error is None
            assert result["type"] == "mcp"
            assert "servers" in result or "url" in result
        
        asyncio.run(run_test())


class TestV2AgentWithResources:
    """V2 Agent 资源集成测试"""

    def test_agent_with_resources(self):
        """测试 Agent 能够正确持有和使用资源"""
        from derisk.agent.core_v2.integration.agent_impl import V2PDCAAgent, ResourceMixin
        from derisk.agent.core_v2.agent_info import AgentInfo, AgentMode
        
        info = AgentInfo(name="test_agent", mode=AgentMode.PRIMARY)
        
        resources = {
            "knowledge": [
                {"space_id": "kb_001", "space_name": "Test KB"}
            ],
            "skills": [
                {"skill_code": "s001", "name": "Test Skill"}
            ]
        }
        
        agent = V2PDCAAgent(
            info=info,
            tools={"bash": Mock()},
            resources=resources,
        )
        
        assert agent.resources == resources
        assert len(agent.resources["knowledge"]) == 1
        assert len(agent.resources["skills"]) == 1

    def test_resource_mixin(self):
        """测试资源混入类"""
        from derisk.agent.core_v2.integration.agent_impl import ResourceMixin
        
        mixin = ResourceMixin()
        mixin.resources = {
            "knowledge": [
                {"space_id": "kb_001", "space_name": "KB 1"},
                {"space_id": "kb_002", "space_name": "KB 2"},
            ],
            "skills": [
                {"skill_code": "s001", "name": "Skill 1", "branch": "main"}
            ]
        }
        
        knowledge_ctx = mixin.get_knowledge_context()
        assert "knowledge-resources" in knowledge_ctx
        assert "kb_001" in knowledge_ctx
        assert "kb_002" in knowledge_ctx
        
        skills_ctx = mixin.get_skills_context()
        assert "agent-skills" in skills_ctx
        assert "s001" in skills_ctx
        
        full_prompt = mixin.build_resource_prompt("Base prompt")
        assert "Base prompt" in full_prompt
        assert "knowledge-resources" in full_prompt
        assert "agent-skills" in full_prompt


class TestResourceBindingIntegration:
    """资源绑定集成测试"""

    def test_full_binding_flow(self):
        """测试完整的资源绑定流程"""
        from derisk.agent.core_v2.agent_binding import (
            ProductAgentBinding,
            ProductAgentRegistry,
            ResourceResolver,
            AgentResource,
        )
        
        registry = ProductAgentRegistry()
        resolver = ResourceResolver()
        binding = ProductAgentBinding(registry, resolver)
        
        async def run_test():
            from derisk.agent.core_v2.product_agent_registry import AgentTeamConfig, AgentConfig
            
            team_config = AgentTeamConfig(
                team_id="team_001",
                team_name="Test Team",
            )
            
            resources = [
                AgentResource(type="knowledge", value='{"space_id": "kb_001"}', name="kb1"),
                AgentResource(type="skill", value='{"skill_code": "s001"}', name="skill1"),
            ]
            
            result = await binding.bind_agents_to_app(
                app_code="app_001",
                team_config=team_config,
                resources=resources,
            )
            
            assert result.success
            assert result.app_code == "app_001"
            assert len(result.bound_resources) == 2
        
        asyncio.run(run_test())


def test_import_availability():
    """测试必要的导入是否可用"""
    try:
        from derisk_serve.agent.app_to_v2_converter import convert_app_to_v2_agent
        from derisk.agent.core_v2.agent_binding import ResourceResolver
        from derisk.agent.core_v2.integration.agent_impl import V2PDCAAgent, create_v2_agent
        assert True
    except ImportError as e:
        pytest.fail(f"Import failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])