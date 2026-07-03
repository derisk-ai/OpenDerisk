"""满配 BAIZE agent V2 承接端到端验证。

验证 V2 run_loop 在满配（所有工具类型、hook、memory、subagent）下能正确完成。

测试维度覆盖：
  - system prompt + scene info 注入            → 直接测试（ToolContext 字段）
  - skill 工具（mocked）                        → 直接测试（ToolResolver 注册 + 执行）
  - DB 工具（mocked DBResource）                → 直接测试（get_resource 路径）
  - KnowledgeSearch（mocked RetrieverResource） → 直接测试（get_resource 路径）
  - sandbox 工具（mocked sandbox_client）       → 直接测试（get_resource 路径）
  - sub-agent shared_conv 模式                  → 参考 test_subagent_shared_conv.py（Task 14）
  - memory tier1/2/3 hooks 注册                → 参考 test_memory_hook_setup.py（Task 11）
  - pre/post_tool_use hooks 触发               → 参考 test_default_acting.py（Task 10）
  - turn_complete / conversation_complete hooks → 参考 test_run_loop.py（Task 15/16）
"""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock

from derisk.agent.core.v2.run_loop import run_loop, trigger_conversation_complete
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.core.v2.default_acting import make_default_acting_fn
from derisk.agent.core.v2.tool_resolver import ToolResolver, _find_tool_in_pack
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.tools.context import ToolContext
from derisk.agent.core.agent import Agent


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


@pytest.fixture
def mock_tool_context():
    """构造满配 ToolContext：包含所有 V2 资源类型。"""
    ctx = ToolContext(
        agent_id="agent-full",
        agent_name="BAIZE",
        conversation_id="conv-full",
        scene="data_analyst",
        scenario_id="scenario-001",
        language="zh",
        skill_dir="/skills",
        available_skills={"sql_review": "/skills/sql_review"},
    )
    # DB resource
    mock_db = MagicMock()
    mock_db._connector = MagicMock()
    mock_db._datasource_id = 42
    ctx.set_resource("db_resource", mock_db)
    # Knowledge retriever
    mock_retriever = AsyncMock()
    mock_retriever.retrieve = AsyncMock(return_value="knowledge results")
    ctx.set_resource("knowledge_retriever", mock_retriever)
    # Sandbox client
    mock_sandbox = MagicMock()
    mock_sandbox.work_dir = "/home/ubuntu"
    mock_sandbox.shell = MagicMock()
    mock_sandbox.shell.exec_command = AsyncMock()
    mock_sandbox.file = MagicMock()
    mock_sandbox.file.read = AsyncMock()
    mock_sandbox.file.write = AsyncMock()
    ctx.set_resource("sandbox_client", mock_sandbox)
    return ctx


# =============================================================================
# Fake / mock tools for full-config ToolResolver
# =============================================================================


class FakeSkillTool:
    """模拟 skill 工具（ListSkillsTool）。"""
    name = "list_skills"

    async def execute(self, args, context=None):
        return V2ToolResult.ok(
            output="Available skills: sql_review",
            tool_name="list_skills",
        )


class FakeDBTool:
    """模拟 DB 工具（execute_sql）。"""
    name = "execute_sql"

    async def execute(self, args, context=None):
        return V2ToolResult.ok(
            output="Query executed successfully",
            tool_name="execute_sql",
        )


class FakeKnowledgeTool:
    """模拟 KnowledgeSearch 工具。"""
    name = "knowledge_search"

    async def execute(self, args, context=None):
        return V2ToolResult.ok(
            output="Knowledge search results",
            tool_name="knowledge_search",
        )


class FakeSandboxTool:
    """模拟 sandbox 工具（BashTool）。"""
    name = "bash"

    async def execute(self, args, context=None):
        return V2ToolResult.ok(
            output="bash output",
            tool_name="bash",
        )


class FakeDoomLoop:
    async def check(self, tool_name, args):
        return True


class FakeTruncator:
    async def truncate(self, content, tool_name, args):
        return MagicMock(truncated=False, truncated_content=content)


# =============================================================================
# Helpers
# =============================================================================


def _make_full_config_tool_resolver():
    """构造满配 ToolResolver：包含 skill、DB、knowledge、sandbox 工具。"""
    return ToolResolver(system_tools={
        "list_skills": FakeSkillTool(),
        "execute_sql": FakeDBTool(),
        "knowledge_search": FakeKnowledgeTool(),
        "bash": FakeSandboxTool(),
    })


def _make_full_config_acting_fn(tool_resolver=None, hook_manager=None):
    """构造满配 acting_fn，使用真实 default_acting_fn 工厂。"""
    if tool_resolver is None:
        tool_resolver = _make_full_config_tool_resolver()
    return make_default_acting_fn(
        tool_resolver=tool_resolver,
        doom_loop_detector=FakeDoomLoop(),
        failure_tracker=ToolFailureTracker(max_failures=3),
        truncator=FakeTruncator(),
        tool_context_factory=ToolContextFactory(agent_id="agent-full", conv_id="conv-full"),
        hook_manager=hook_manager,
    )


def _make_thinking_full_config():
    """创建满配 thinking_fn（闭包内状态：第一轮 emit tool_calls，后续轮返回 final answer）。"""
    call_count = {"n": 0}

    async def thinking(input_):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # 第一轮：emit system prompt token + scene info
            yield {"token": "[System: BAIZE agent, scene: data_analyst] "}
            # 然后 emit tool_calls（覆盖 skill、DB、knowledge、sandbox）
            yield {
                "token": "",
                "tool_calls": [
                    {"tool": "list_skills", "input": {}},
                    {"tool": "execute_sql", "input": {"sql": "SELECT 1"}},
                    {"tool": "knowledge_search", "input": {"query": "test"}},
                    {"tool": "bash", "input": {"command": "echo hello"}},
                ],
            }
        else:
            # 后续轮：返回 final answer，不再 emit tool_calls
            yield {"token": "Final answer after all tools executed."}

    return thinking


async def _thinking_simple(input_):
    """简单 thinking_fn：不 emit tool_calls，直接返回 final answer。"""
    yield {"token": "final answer"}


# =============================================================================
# Tests: 满配端到端
# =============================================================================


async def test_full_config_agent_runs_end_to_end(store):
    """满配 BAIZE agent 通过 V2 run_loop 完成多轮对话。

    验证:
    - 所有 4 种工具类型（skill、DB、knowledge、sandbox）被调用
    - run_loop 正常结束，产生 DONE 事件
    - 无异常
    """
    acting_fn = _make_full_config_acting_fn()

    events = []
    async for e in run_loop(
        agent_id="agent-full",
        conv_id="conv-full",
        input_={"prompt": "Run full config test", "session_id": "s1"},
        state_store=store,
        thinking_fn=_make_thinking_full_config(),
        acting_fn=acting_fn,
        max_steps=10,
    ):
        events.append(e)

    # 检查事件类型
    states = [e.state for e in events]

    # 应有 INIT、THINKING、ACTING（tool_call）、OBSERVING（tool_result）、DONE
    assert StepState.INIT in states
    assert StepState.THINKING in states
    assert StepState.DONE in states

    # 4 种工具都被调用
    tool_call_events = [e for e in events if e.event_type == "tool_call"]
    tool_names = [e.input.get("tool") for e in tool_call_events]
    assert "list_skills" in tool_names
    assert "execute_sql" in tool_names
    assert "knowledge_search" in tool_names
    assert "bash" in tool_names

    # 每种工具都有对应的 tool_result（至少 4 个）
    tool_result_events = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_result_events) >= 4
    for result_event in tool_result_events[:4]:
        assert result_event.output.get("is_exe_success") is True


async def test_full_config_with_hook_manager(store):
    """满配 + HookManager：验证 pre/post_tool_use 和 turn_complete 触发。

    注意: run_loop 不直接触发 pre/post_tool_use —— 这些由 default_acting_fn
    内部触发。turn_complete 由 run_loop 在 turn 结束时触发。
    """
    hook_manager = MagicMock()
    hook_manager.trigger = AsyncMock()
    # pre_tool_use 使用 trigger_blocking
    decision = MagicMock()
    decision.action = "CONTINUE"
    hook_manager.trigger_blocking = AsyncMock(return_value=decision)

    acting_fn = _make_full_config_acting_fn(hook_manager=hook_manager)

    async for _ in run_loop(
        agent_id="agent-full",
        conv_id="conv-full",
        input_={"prompt": "Run with hooks", "session_id": "s1"},
        state_store=store,
        thinking_fn=_make_thinking_full_config(),
        acting_fn=acting_fn,
        hook_manager=hook_manager,
        max_steps=10,
    ):
        pass

    # turn_complete 应被触发
    turn_complete_calls = [
        c for c in hook_manager.trigger.call_args_list
        if c.args[0] == "turn_complete"
    ]
    assert len(turn_complete_calls) == 1

    # pre_tool_use 应被触发至少 4 次（每个工具一次）
    pre_tool_calls = [
        c for c in hook_manager.trigger_blocking.call_args_list
        if c.args[0] == "pre_tool_use"
    ]
    assert len(pre_tool_calls) >= 4

    # post_tool_use 应被触发至少 4 次（每个工具一次）
    post_tool_calls = [
        c for c in hook_manager.trigger.call_args_list
        if c.args[0] == "post_tool_use"
    ]
    assert len(post_tool_calls) >= 4


async def test_conversation_complete_hook_fires(store):
    """验证 conversation_complete hook 通过 trigger_conversation_complete 触发。"""
    hook_manager = MagicMock()
    hook_manager.trigger = AsyncMock()

    await trigger_conversation_complete(
        hook_manager=hook_manager,
        conv_id="conv-full",
        agent_id="agent-full",
        user_id="user-1",
        total_rounds=3,
    )

    hook_manager.trigger.assert_called_once()
    call_args = hook_manager.trigger.call_args
    assert call_args.args[0] == "conversation_complete"
    context = call_args.args[1]
    assert context["conv_id"] == "conv-full"
    assert context["agent_id"] == "agent-full"
    assert context["total_rounds"] == 3


async def test_full_config_tool_context_resources(store, mock_tool_context):
    """验证满配 ToolContext 中所有资源类型正确设置。"""
    # DB resource
    db_res = mock_tool_context.get_resource("db_resource")
    assert db_res is not None
    assert db_res._datasource_id == 42

    # Knowledge retriever
    retriever = mock_tool_context.get_resource("knowledge_retriever")
    assert retriever is not None

    # Sandbox client
    sandbox = mock_tool_context.get_resource("sandbox_client")
    assert sandbox is not None
    assert sandbox.work_dir == "/home/ubuntu"

    # Skill fields
    assert mock_tool_context.skill_dir == "/skills"
    assert "sql_review" in mock_tool_context.available_skills

    # Scene info
    assert mock_tool_context.scene == "data_analyst"
    assert mock_tool_context.scenario_id == "scenario-001"


async def test_tool_resolver_returns_correct_tools():
    """验证满配 ToolResolver 能正确解析所有工具类型。"""
    resolver = _make_full_config_tool_resolver()

    skill_tool = resolver.resolve("list_skills")
    assert skill_tool is not None
    assert isinstance(skill_tool, FakeSkillTool)

    db_tool = resolver.resolve("execute_sql")
    assert db_tool is not None
    assert isinstance(db_tool, FakeDBTool)

    knowledge_tool = resolver.resolve("knowledge_search")
    assert knowledge_tool is not None
    assert isinstance(knowledge_tool, FakeKnowledgeTool)

    sandbox_tool = resolver.resolve("bash")
    assert sandbox_tool is not None
    assert isinstance(sandbox_tool, FakeSandboxTool)

    unknown = resolver.resolve("nonexistent")
    assert unknown is None


async def test_full_config_with_mcp_resource_pack(mock_tool_context):
    """验证 ToolResolver 通过 _find_tool_in_pack 递归解析 MCP resource pack 工具。"""
    # 内层 pack：包含真正的 MCP 工具
    class InnerPack:
        is_pack = True

    # 外层 pack：_resources 包含内层 pack
    class OuterPack:
        pass

    outer_pack = OuterPack()
    inner_pack = InnerPack()

    class FakeMCPTool:
        name = "mcp_weather"

        async def execute(self, args, context=None):
            return V2ToolResult.ok(
                output="weather: sunny",
                tool_name="mcp_weather",
            )

    inner_pack._resources = {"mcp_weather": FakeMCPTool()}
    outer_pack._resources = {"weather_pack": inner_pack}

    # 构造 ToolResolver：仅 resource_pack，无 system_tools 包含该工具
    resolver = ToolResolver(
        system_tools={
            "list_skills": FakeSkillTool(),
        },
        resource_pack=outer_pack,
    )

    # 验证 resolve 通过递归查找返回工具
    tool = resolver.resolve("mcp_weather")
    assert tool is not None
    assert isinstance(tool, FakeMCPTool)

    # 验证工具执行
    result = await tool.execute(args={}, context=mock_tool_context)
    assert result.output == "weather: sunny"
    assert result.tool_name == "mcp_weather"


async def test_baize_vs_v2_same_prompt_both_run(store):
    """V2 跑通端到端 + BAIZE 代码路径仍存在；两者是不同内核，不对比行为等价性（spec §1）。"""
    # V2 端到端：同一 prompt 运行
    acting_fn = _make_full_config_acting_fn()
    events = []
    async for e in run_loop(
        agent_id="agent-full",
        conv_id="conv-full",
        input_={"prompt": "hello", "session_id": "s1"},
        state_store=store,
        thinking_fn=_make_thinking_full_config(),
        acting_fn=acting_fn,
        max_steps=10,
    ):
        events.append(e)

    # V2 路径正常完成
    states = [e.state for e in events]
    assert StepState.DONE in states

    # 4 工具都被调用
    tool_call_events = [e for e in events if e.event_type == "tool_call"]
    tool_names = [e.input.get("tool") for e in tool_call_events]
    for expected in ("list_skills", "execute_sql", "knowledge_search", "bash"):
        assert expected in tool_names

    # BAIZE 代码路径仍存在（结构对比，不跑完整 BAIZE）
    assert hasattr(Agent, "generate_reply"), "BAIZE entry method generate_reply missing"


# =============================================================================
# Cross-reference: 以下维度由先前 Task 的专项测试覆盖（路径相对于 packages/derisk-core/）
# =============================================================================
#
# 维度                           | 覆盖测试
# -------------------------------+---------------------------------------------------------
# sub-agent shared_conv 模式     | tests/agent/core/v2/test_subagent_shared_conv.py（Task 14）
# memory tier1/2/3 hooks 注册    | tests/agent/core/v2/test_memory_hook_setup.py（Task 11）
# pre/post_tool_use hooks 详细   | tests/agent/core/v2/test_default_acting.py（Task 10）
# turn_complete hook 详细        | tests/agent/core/v2/test_run_loop.py（Task 15/16）
# ToolFailureTracker             | tests/agent/core/v2/test_tool_failure_tracker.py（Task 4）
# retrying_thinking              | tests/agent/core/v2/test_retrying_thinking.py（Task 5）
# ToolResolver                   | tests/agent/core/v2/test_tool_resolver.py（Task 8）
# ToolContextFactory             | tests/agent/core/v2/test_tool_context_factory.py（Task 7）
# default_thinking_fn            | tests/agent/core/v2/test_default_thinking.py（Task 12）
# Skill 工具 V2 签名             | tests/agent/tools/test_skill_tool_v2.py（Task 18）
# 沙箱工具 V2 迁移               | tests/agent/tools/test_sandbox_tool_v2.py（Task 19）
# DB/Knowledge/AgentStart V2     | tests/agent/tools/test_db_knowledge_agent_tools_v2.py（Task 20）
# run_loop 多轮                  | tests/agent/core/v2/test_run_loop.py（Task 15/16）
# V2 runtime 兼容 deprecation    | tests/agent/core/v2/test_v2_runtime_with_deprecation.py（Task 3）
