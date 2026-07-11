"""RFC-005 S20/Step4 沙箱委托类工具归属验证。

工具自声明 capability_id(ToolMetadata.capability_id="sandbox"),
SandboxResource.declare_tools 据此归类,不再靠工具名白名单。
有沙箱时:bash/read/write/edit/deliver_file/download_file 归 sandbox。
无沙箱时:它们是本地默认工具,走 builtin。
executor_id 始终 builtin(工具执行体自处理沙箱/本地切换,选B)。
"""

from derisk.agent.capabilities.sandbox import SandboxResource
from derisk.core.interface.resource.tool_entry import BUILTIN_EXECUTOR_ID


class _FakeSandboxClient:
    provider = staticmethod(lambda: "local")
    skill_dir = "/s"


class _FakeMeta:
    """模拟 ToolMetadata 的 register 必需字段(category/source/capability_id)。"""

    def __init__(self, name, capability_id=None):
        self.name = name
        self.category = "UTILITY"
        self.source = "SYSTEM"
        self.capability_id = capability_id
        self.risk_level = "LOW"
        self.tags = []
        self.description = "d"


class _FakeTool:
    def __init__(self, name, capability_id=None, description="d"):
        self.name = name
        self.description = description
        self.metadata = _FakeMeta(name, capability_id)


def _bash_tool():
    return _FakeTool("bash", capability_id="sandbox")


def _spawn_tool():
    return _FakeTool("spawn_agent_task")  # 无 capability_id → builtin


# --------------------------------------------------------------------------- #
# declare_tools 归属 sandbox(读 metadata.capability_id)
# --------------------------------------------------------------------------- #
def test_declare_tools_marks_sandbox_capability_as_sandbox():
    res = SandboxResource(_FakeSandboxClient())
    tools = {"bash": _bash_tool(), "spawn_agent_task": _spawn_tool()}
    entries = res.declare_tools(tools)
    by_name = {e.tool_name: e for e in entries}
    assert "bash" in by_name
    assert by_name["bash"].capability_id == "sandbox"
    assert "spawn_agent_task" not in by_name


def test_declare_tools_executor_id_stays_builtin():
    """选B:沙箱工具 executor_id 仍 builtin(执行复用,不建 SandboxExecutor)。"""
    res = SandboxResource(_FakeSandboxClient())
    entries = res.declare_tools({"bash": _bash_tool()})
    assert all(e.executor_id == BUILTIN_EXECUTOR_ID for e in entries)


def test_declare_tools_covers_all_sandbox_capability_tools():
    """所有自声明 capability_id=sandbox 的工具都归 sandbox。"""
    res = SandboxResource(_FakeSandboxClient())
    names = ["bash", "read", "write", "edit", "deliver_file", "download_file"]
    tools = {n: _FakeTool(n, capability_id="sandbox") for n in names}
    entries = res.declare_tools(tools)
    assert {e.tool_name for e in entries} == set(names)
    assert all(e.capability_id == "sandbox" for e in entries)


def test_declare_tools_empty_when_none_sandbox():
    res = SandboxResource(_FakeSandboxClient())
    entries = res.declare_tools({"spawn_agent_task": _spawn_tool()})
    assert entries == []


# --------------------------------------------------------------------------- #
# v1 拆分逻辑模拟:有沙箱 vs 无沙箱
# --------------------------------------------------------------------------- #
def _split_like_v1(has_sandbox: bool, all_tools: dict):
    """模拟 react_master_agent._build_sandbox_capability 的拆分。"""
    if not has_sandbox:
        return [], {}, all_tools  # 全 builtin
    res = SandboxResource(_FakeSandboxClient())
    sandbox_entries = res.declare_tools(all_tools)
    sandbox_names = {e.tool_name for e in sandbox_entries}
    non_sandbox = {k: v for k, v in all_tools.items() if k not in sandbox_names}
    return sandbox_entries, non_sandbox, {}


def test_with_sandbox_bash_splits_to_sandbox_non_sandbox():
    tools = {"bash": _bash_tool(), "spawn_agent_task": _spawn_tool()}
    sandbox_entries, non_sandbox, _ = _split_like_v1(True, tools)
    assert {e.tool_name for e in sandbox_entries} == {"bash"}
    assert set(non_sandbox.keys()) == {"spawn_agent_task"}


def test_without_sandbox_all_stay_builtin():
    tools = {"bash": _bash_tool(), "spawn_agent_task": _spawn_tool()}
    sandbox_entries, _non_sandbox, all_builtin = _split_like_v1(False, tools)
    # 无沙箱:bash 也在 builtin 全集里,不归 sandbox
    assert sandbox_entries == []
    assert set(all_builtin.keys()) == {"bash", "spawn_agent_task"}


# --------------------------------------------------------------------------- #
# 工具自声明 mechanism: ToolRegistry 按 capability_id 索引
# --------------------------------------------------------------------------- #
def test_registry_indexes_by_capability_id():
    """ToolRegistry.get_by_capability 据自声明 capability_id 查询。"""
    from derisk.agent.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(_bash_tool())
    reg.register(_spawn_tool())
    sandbox_tools = reg.get_by_capability("sandbox")
    assert {t.name for t in sandbox_tools} == {"bash"}
    assert "sandbox" in reg.capability_ids()
    assert reg.get_by_capability("agent:builtin") == []  # spawn 未声明 capability_id