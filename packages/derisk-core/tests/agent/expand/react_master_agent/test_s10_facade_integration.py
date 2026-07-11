"""RFC-005 S10 v1 接入点验证。

验证 react_master_agent.load_thinking_messages 的 system 组装段经 ResourceFacade
产出的正确性,不依赖完整 ReActMasterAgent 实例化(全链路由人工跑)。

覆盖:
- separator_join_system_blocks:块列表按序合并为 str
- v1 system 组装段(identity + control + memory + resources → facade → system str)
  含四层、顺序正确(身份→控制 GLOBAL 在前,记忆→资源 USER 在后)
- tools 来源:facade 快照 tools 槽
"""

from typing import Any, List

import pytest

from derisk.core.interface.resource.bundle import CacheScope, Contribution, Lifetime, Slot, SystemBlock
from derisk.agent.capabilities.facade import ResourceFacade
from derisk.agent.expand.react_master_agent.react_master_agent import (
    separator_join_system_blocks,
)


# --------------------------------------------------------------------------- #
# separator_join_system_blocks
# --------------------------------------------------------------------------- #
def test_separator_join_preserves_order():
    blocks = [
        SystemBlock(text="层1", cache_scope=CacheScope.GLOBAL),
        SystemBlock(text="层2", cache_scope=CacheScope.GLOBAL),
        SystemBlock(text="层3", cache_scope=CacheScope.USER),
    ]
    assert separator_join_system_blocks(blocks, "\n\n---\n\n") == "层1\n\n---\n\n层2\n\n---\n\n层3"


def test_separator_join_skips_empty():
    blocks = [
        SystemBlock(text="", cache_scope=CacheScope.GLOBAL),
        SystemBlock(text="有内容", cache_scope=CacheScope.USER),
    ]
    assert separator_join_system_blocks(blocks) == "有内容"


# --------------------------------------------------------------------------- #
# v1 system 组装段:end-to-end 模拟 load_thinking_messages 的 system 产段
# --------------------------------------------------------------------------- #
class _FakeAgent:
    """模拟 v1 agent 的最小资源面,供 facade 桥接。"""

    def __init__(self):
        self.resource = None
        self.resource_map = {}  # 空:无资源声明(对齐 canvas-agent 仅 memory)
        self.sandbox_manager = None


async def test_v1_system_assembly_contains_identity_and_control():
    """身份层 + 控制层(GLOBAL)进 system 快照,合并后 system 含两者。"""
    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="canvas-agent",
        conv_id="conv-1",
        agent=_FakeAgent(),
        identity="你是 Canvas Agent,负责交付可视化产出。",
        control_block="## 核心工作流\n1. 分析\n2. 执行\n3. 交付",
        memory_static_block=None,
    )
    system_str = separator_join_system_blocks(
        snap.full_system_blocks(), separator="\n\n---\n\n"
    )
    assert "Canvas Agent" in system_str
    assert "核心工作流" in system_str


async def test_v1_system_assembly_includes_memory_block():
    """memory_static_block 进系统 USER 块,出现在 system str。"""
    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="canvas-agent",
        conv_id="conv-1",
        agent=_FakeAgent(),
        identity="身份",
        control_block="控制",
        memory_static_block="## 用户偏好:简洁回复",
    )
    system_str = separator_join_system_blocks(snap.full_system_blocks())
    assert "用户偏好:简洁回复" in system_str


async def test_v1_system_layer_order_global_before_user():
    """GLOBAL(身份+控制)排在 USER(记忆+资源)之前(cache 前缀最大化)。"""
    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="a",
        conv_id="c",
        agent=_FakeAgent(),
        identity="IDENTITY",
        control_block="CONTROL",
        memory_static_block="MEMORY",
    )
    blocks = snap.full_system_blocks()
    texts = [b.text for b in blocks]
    assert texts.index("IDENTITY") < texts.index("CONTROL")
    assert texts.index("CONTROL") < texts.index("MEMORY")


async def test_v1_tools_from_snapshot_when_resource_bound():
    """绑定了工具资源时,facade 快照 tools 槽非空,v1 function_calling_params 取之。

    用 FunctionTool 作资源,经 ToolPack 让 facade 桥接解析。
    """
    from derisk.agent.resource import FunctionTool, ToolPack

    def _fn(**kw):
        return "ok"

    _fn.__doc__ = "执行 SQL"
    tool = FunctionTool(name="execute_sql", func=_fn, description="执行 SQL")
    pack = ToolPack([tool])

    class _AgentWithResource(_FakeAgent):
        def __init__(self):
            super().__init__()
            self.resource = pack

    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="db-agent", conv_id="conv-1", agent=_AgentWithResource(),
    )
    tool_names = {getattr(c.content, "name", None) for c in snap.tools}
    assert "execute_sql" in tool_names


async def test_v1_system_uses_legacy_separator_for_compat():
    """v1 用 section_separator(\\n\\n---\\n\\n)合并,与旧 PromptAssembler 输出对齐。"""
    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="a", conv_id="c", agent=_FakeAgent(),
        identity="身份", control_block="控制",
    )
    legacy = separator_join_system_blocks(snap.full_system_blocks(), "\n\n---\n\n")
    # 含分隔符,字节形态与旧拼装一致
    assert "\n\n---\n\n" in legacy


# --------------------------------------------------------------------------- #
# S14+S15: 沙箱 env + builtin tools 进快照(端到端组装段)
# --------------------------------------------------------------------------- #
class _FakeSandboxClient:
    def __init__(self, provider="local", skill_dir="/sandbox/skills"):
        self.provider = lambda: provider
        self.skill_dir = skill_dir


async def test_sandbox_env_in_system_snapshot():
    """S14: 沙箱 env 作为 Capability 进 system 快照。"""
    from derisk.agent.capabilities.sandbox.resource import SandboxResource

    facade = ResourceFacade()
    sb_res = SandboxResource(_FakeSandboxClient("local"), work_dir="/pilot/data")
    env_contribs = sb_res.declare_env()

    snap = await facade.assemble(
        agent_id="canvas-agent", conv_id="c1", agent=_FakeAgent(),
        identity="身份", control_block="控制",
        extra_static_contribs=env_contribs,
    )
    system_str = separator_join_system_blocks(snap.full_system_blocks())
    assert "环境信息" in system_str
    assert "/pilot/data" in system_str


async def test_builtin_and_sandbox_tools_in_snapshot_all_tools():
    """S15: builtin + 沙箱工具(都在 available_system_tools)进 all_tools。"""
    from derisk.agent.resource import FunctionTool

    def _fn(**kw):
        return "ok"

    _fn.__doc__ = "t"
    spawn_tool = FunctionTool(name="spawn_agent_task", func=_fn, description="spawn")
    run_py = FunctionTool(name="run_python", func=_fn, description="run python")

    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="a", conv_id="c1", agent=_FakeAgent(),
        identity="id", control_block="ctl",
        builtin_tools={"spawn_agent_task": spawn_tool, "run_python": run_py},
    )
    all_entries = snap.all_tools()
    names = {
        getattr(e, "tool_name", None) or getattr(getattr(e, "content", None), "name", None)
        for e in all_entries
    }
    assert {"spawn_agent_task", "run_python"} <= names
    # builtin 标记为 agent:builtin
    for e in snap.builtin_tools:
        assert e.executor_id == "agent:builtin"


async def test_full_system_order_with_sandbox_env():
    """S14: 含沙箱 env 时顺序 GLOBAL(身份/控制)→ USER(记忆)→ ENV(沙箱)。

    USER(记忆,跨会话用户级)优先级高于 ENV(本会话环境),故 USER 在 ENV 前——
    对齐 RFC §3.8 SCOPE_PRIORITY:GLOBAL<USER<ENV<NONE。
    """
    from derisk.core.interface.resource.bundle import CacheScope
    from derisk.agent.capabilities.sandbox.resource import SandboxResource

    facade = ResourceFacade()
    env_contribs = SandboxResource(_FakeSandboxClient("docker"), work_dir="/w").declare_env()
    snap = await facade.assemble(
        agent_id="a", conv_id="c1", agent=_FakeAgent(),
        identity="ID", control_block="CTRL", memory_static_block="MEM",
        extra_static_contribs=env_contribs,
    )
    blocks = snap.full_system_blocks()
    scopes = [b.cache_scope for b in blocks]
    gi = [i for i, s in enumerate(scopes) if s == CacheScope.GLOBAL]
    ei = [i for i, s in enumerate(scopes) if s == CacheScope.ENV]
    ui = [i for i, s in enumerate(scopes) if s == CacheScope.USER]
    assert gi and ei and ui
    assert max(gi) < min(ui) < min(ei)  # GLOBAL → USER → ENV
