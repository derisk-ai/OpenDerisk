"""DB / Knowledge / AgentStart 工具 V2 迁移测试 —— 验证 context.get_resource() 路径。

Task 20: DB (execute_sql/list_tables/get_table_spec), Knowledge (KnowledgeSearch),
AgentStart 工具迁移到 ToolContext。
策略: get_resource 优先 (V2), BAIZE 回退 (kwargs 路径)。
"""

import sys
from unittest.mock import AsyncMock, MagicMock
import pytest

# Mock openai module (reasoning_engine.py imports BaseModel from openai)
sys.modules["openai"] = MagicMock()
sys.modules["openai"].BaseModel = MagicMock()

from derisk.agent.tools.context import ToolContext
from derisk.agent.expand.actions.knowledge_action import KnowledgeSearch
from derisk.agent.expand.actions.agent_action import AgentStart
from derisk.agent.resource.database import DBResource


def _make_db_resource(connector=None, datasource_id=7):
    """创建模拟的 DBResource，用于测试 _resolve_db_from_agent 的 BAIZE 回退路径。"""
    db_res = DBResource(name="test_db", db_name="test_db")
    if connector:
        db_res._connector = connector
    if datasource_id:
        db_res._datasource_id = datasource_id
    return db_res


class TestDBToolsV2Context:
    """验证 _resolve_db_from_agent 从 context.get_resource("db_resource") 读取。"""

    def test_resolve_db_from_v2_context(self):
        """V2 路径: context.get_resource("db_resource") 命中。"""
        from derisk_serve.agent.resource.db_tools import _resolve_db_from_agent

        mock_connector = MagicMock()
        mock_db_resource = MagicMock()
        mock_db_resource._connector = mock_connector
        mock_db_resource._datasource_id = 42

        ctx = ToolContext()
        ctx.set_resource("db_resource", mock_db_resource)

        connector, ds_id = _resolve_db_from_agent("test_db", {}, context=ctx)
        assert connector is mock_connector
        assert ds_id == 42

    def test_resolve_db_from_v2_context_connector_attr(self):
        """V2 路径: db_resource 使用 connector 属性（非 _connector）。"""
        from derisk_serve.agent.resource.db_tools import _resolve_db_from_agent

        mock_connector = MagicMock()
        mock_db_resource = MagicMock()
        mock_db_resource._connector = None
        mock_db_resource.connector = mock_connector
        mock_db_resource._datasource_id = 99

        ctx = ToolContext()
        ctx.set_resource("db_resource", mock_db_resource)

        connector, ds_id = _resolve_db_from_agent("test_db", {}, context=ctx)
        assert connector is mock_connector
        assert ds_id == 99

    def test_resolve_db_v2_priority_over_baize(self):
        """V2 路径优先: 同时设置 context 和 agent kwargs 时，context 优先。"""
        from derisk_serve.agent.resource.db_tools import _resolve_db_from_agent

        v2_connector = MagicMock()
        v2_db_resource = MagicMock()
        v2_db_resource._connector = v2_connector
        v2_db_resource._datasource_id = 1

        baize_connector = MagicMock()
        baize_db_res = _make_db_resource(connector=baize_connector, datasource_id=2)

        mock_agent = MagicMock()
        mock_agent.resource_map = {"DBResource": [baize_db_res]}

        ctx = ToolContext()
        ctx.set_resource("db_resource", v2_db_resource)

        connector, ds_id = _resolve_db_from_agent(
            "test_db", {"agent": mock_agent}, context=ctx
        )
        assert connector is v2_connector
        assert ds_id == 1

    def test_resolve_db_baize_fallback(self):
        """BAIZE 回退: context=None 时从 agent.resource_map 获取。"""
        from derisk_serve.agent.resource.db_tools import _resolve_db_from_agent

        mock_connector = MagicMock()
        db_res = _make_db_resource(connector=mock_connector, datasource_id=7)

        mock_agent = MagicMock()
        mock_agent.resource_map = {"DBResource": [db_res]}

        connector, ds_id = _resolve_db_from_agent(
            "test_db", {"agent": mock_agent}, context=None
        )
        assert connector is mock_connector
        assert ds_id == 7

    def test_resolve_db_v2_context_no_resource(self):
        """V2 context 激活但无 db_resource: 回退到 BAIZE 路径。"""
        from derisk_serve.agent.resource.db_tools import _resolve_db_from_agent

        mock_connector = MagicMock()
        db_res = _make_db_resource(connector=mock_connector, datasource_id=7)

        mock_agent = MagicMock()
        mock_agent.resource_map = {"DBResource": [db_res]}

        ctx = ToolContext()
        # 不设置 db_resource

        connector, ds_id = _resolve_db_from_agent(
            "test_db", {"agent": mock_agent}, context=ctx
        )
        assert connector is mock_connector
        assert ds_id == 7

    def test_resolve_db_no_agent_no_context(self):
        """无 agent 无 context: 返回 None, None。"""
        from derisk_serve.agent.resource.db_tools import _resolve_db_from_agent

        connector, ds_id = _resolve_db_from_agent("test_db", {}, context=None)
        assert connector is None
        assert ds_id is None


class TestKnowledgeSearchV2Execute:
    """验证 KnowledgeSearch.execute() 从 context.get_resource("knowledge_retriever") 读取。"""

    def test_execute_with_v2_retriever(self):
        """V2 路径: context 中有 knowledge_retriever 时调用 retriever.retrieve()。"""
        mock_retriever = AsyncMock()
        ctx = ToolContext()
        ctx.set_resource("knowledge_retriever", mock_retriever)

        tool = KnowledgeSearch()
        tool.execute(
            {"query": "test query", "func": "search"},
            context=ctx,
        )
        mock_retriever.retrieve.assert_called_once_with("test query")

    def test_execute_v2_context_no_retriever(self):
        """V2 context 激活但无 knowledge_retriever: 回退到 BAIZE 路径。"""
        ctx = ToolContext()
        # 不设置 knowledge_retriever

        tool = KnowledgeSearch()
        result = tool.execute(
            {"query": "test query", "func": "search"},
            context=ctx,
        )
        # BAIZE 回退: 返回 args[0]（工具输入 dict）
        assert isinstance(result, dict)
        assert result.get("query") == "test query"

    def test_execute_baize_fallback_output(self):
        """BAIZE 回退: kwargs 中有 output 时返回 output。"""
        tool = KnowledgeSearch()
        result = tool.execute(output="knowledge result")
        assert result == "knowledge result"

    def test_execute_baize_fallback_final_answer(self):
        """BAIZE 回退: kwargs 中有 final_answer 时返回 final_answer。"""
        tool = KnowledgeSearch()
        result = tool.execute(final_answer="final answer")
        assert result == "final answer"

    def test_execute_baize_fallback_no_context(self):
        """BAIZE 回退: 无 context 时返回 args[0]。"""
        tool = KnowledgeSearch()
        result = tool.execute({"query": "test"})
        assert isinstance(result, dict)
        assert result.get("query") == "test"

    async def test_execute_integration_v2_retriever(self):
        """async_execute() 集成测试: V2 context 路径调用 retriever.retrieve()。"""
        mock_retriever = AsyncMock()
        ctx = ToolContext()
        ctx.set_resource("knowledge_retriever", mock_retriever)

        tool = KnowledgeSearch()
        await tool.async_execute(
            {"query": "integration test", "func": "search"},
            context=ctx,
        )
        mock_retriever.retrieve.assert_called_once_with("integration test")

    async def test_execute_integration_baize_fallback(self):
        """execute() 集成测试: BAIZE 回退路径。"""
        tool = KnowledgeSearch()
        result = await tool.async_execute(
            {"query": "integration test"},
        )
        assert isinstance(result, dict)
        assert result.get("query") == "integration test"


class TestAgentStartV2Execute:
    """验证 AgentStart.execute() 从 context.get_resource("app_resource") 读取。"""

    def test_execute_with_v2_app_resource(self):
        """V2 路径: context 中有 app_resource 时调用 app_resource.async_execute()。"""
        mock_app_resource = AsyncMock()
        ctx = ToolContext()
        ctx.set_resource("app_resource", mock_app_resource)

        tool = AgentStart()
        tool.execute(
            {"agent_id": "test_agent", "input": "do something"},
            context=ctx,
        )
        mock_app_resource.async_execute.assert_called_once_with(user_input="do something")

    def test_execute_v2_context_no_app_resource(self):
        """V2 context 激活但无 app_resource: 返回提示信息（不抛异常）。"""
        ctx = ToolContext()
        # 不设置 app_resource

        tool = AgentStart()
        result = tool.execute(
            {"agent_id": "test_agent", "input": "do something"},
            context=ctx,
        )
        assert "no app_resource" in result

    def test_execute_baize_fallback_raises(self):
        """BAIZE 回退: 无 context 时抛出 RuntimeError（保持原有行为）。"""
        tool = AgentStart()
        with pytest.raises(RuntimeError, match="不能直接作为工具调用"):
            tool.execute({"agent_id": "test_agent", "input": "do something"})

    async def test_execute_integration_v2_app_resource(self):
        """async_execute() 集成测试: V2 context 路径调用 app_resource.async_execute()。"""
        mock_app_resource = AsyncMock()
        ctx = ToolContext()
        ctx.set_resource("app_resource", mock_app_resource)

        tool = AgentStart()
        await tool.async_execute(
            {"agent_id": "sub_agent", "input": "integration task"},
            context=ctx,
        )
        mock_app_resource.async_execute.assert_called_once_with(user_input="integration task")

    async def test_execute_integration_baize_raises(self):
        """execute() 集成测试: BAIZE 回退路径抛出 RuntimeError。"""
        tool = AgentStart()
        with pytest.raises(RuntimeError, match="不能直接作为工具调用"):
            await tool.async_execute({"agent_id": "sub_agent", "input": "task"})
