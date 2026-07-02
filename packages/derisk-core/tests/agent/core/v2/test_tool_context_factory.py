"""ToolContextFactory 测试。"""
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.tool_call_types import V2ToolCall


class FakeSandboxManager:
    @property
    def client(self):
        return "fake_sandbox_client"


class FakeDBResource:
    pass


class FakeRetrieverResource:
    pass


class FakeAppResource:
    pass


def _make_factory(resource_map=None, sandbox_manager=None):
    return ToolContextFactory(
        agent_id="agent-1",
        conv_id="conv-1",
        user_id="user-1",
        scene="data_analyst",
        scenario_id="wm-sales",
        language="zh",
        resource_map=resource_map or {},
        sandbox_manager=sandbox_manager,
        skill_dir="/skills",
        available_skills={"sql_review": "/skills/sql_review"},
    )


def test_basic_context_fields():
    factory = _make_factory()
    tc = V2ToolCall(name="read_file", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.agent_id == "agent-1"
    assert ctx.conversation_id == "conv-1"
    assert ctx.user_id == "user-1"
    assert ctx.scene == "data_analyst"
    assert ctx.scenario_id == "wm-sales"
    assert ctx.language == "zh"
    assert ctx.skill_dir == "/skills"
    assert ctx.available_skills["sql_review"] == "/skills/sql_review"


def test_sandbox_client_injected():
    factory = _make_factory(sandbox_manager=FakeSandboxManager())
    tc = V2ToolCall(name="bash", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("sandbox_client") == "fake_sandbox_client"


def test_db_resource_injected_for_db_tool():
    db = FakeDBResource()
    factory = _make_factory(resource_map={"DBResource": [db]})
    tc = V2ToolCall(name="execute_sql", args={"sql": "SELECT 1"})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("db_resource") is db


def test_knowledge_retriever_injected():
    retriever = FakeRetrieverResource()
    factory = _make_factory(resource_map={"RetrieverResource": [retriever]})
    tc = V2ToolCall(name="KnowledgeSearch", args={"query": "test"})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("knowledge_retriever") is retriever


def test_app_resource_injected_for_agent_start():
    app = FakeAppResource()
    factory = _make_factory(resource_map={"AppResource": [app]})
    tc = V2ToolCall(name="AgentStart", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("app_resource") is app


def test_no_resource_injected_for_unrelated_tool():
    factory = _make_factory(
        resource_map={
            "DBResource": [FakeDBResource()],
            "RetrieverResource": [FakeRetrieverResource()],
        }
    )
    tc = V2ToolCall(name="read_file", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("db_resource") is None
    assert ctx.get_resource("knowledge_retriever") is None