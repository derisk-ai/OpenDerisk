"""ToolResolver 测试。"""
from derisk.agent.core.v2.tool_resolver import ToolResolver


class FakeTool:
    def __init__(self, name):
        self.name = name
        self._tool_base = self  # for UnifiedToolAdapter path

    def to_openai_tool(self):
        return {"type": "function", "function": {"name": self.name, "description": "", "parameters": {}}}


def test_resolve_from_system_tools():
    tool = FakeTool("read_file")
    resolver = ToolResolver(system_tools={"read_file": tool})
    assert resolver.resolve("read_file") is tool


def test_resolve_returns_none_for_unknown():
    resolver = ToolResolver(system_tools={"read_file": FakeTool("read_file")})
    assert resolver.resolve("nonexistent") is None


def test_sandbox_tools_only_injected_if_sandbox_manager():
    """没绑 sandbox_manager 时，sandbox_tool_dict 不注入。"""
    bash = FakeTool("bash")
    resolver = ToolResolver(
        sandbox_tools={"bash": bash},
        sandbox_manager=None,
    )
    assert resolver.resolve("bash") is None


def test_sandbox_tools_injected_when_sandbox_manager():
    bash = FakeTool("bash")
    class FakeSM:
        pass
    resolver = ToolResolver(
        sandbox_tools={"bash": bash},
        sandbox_manager=FakeSM(),
    )
    assert resolver.resolve("bash") is bash


def test_list_tools_for_llm():
    read = FakeTool("read_file")
    write = FakeTool("write_file")
    resolver = ToolResolver(system_tools={"read_file": read, "write_file": write})
    tools = resolver.list_tools_for_llm()
    names = [t["function"]["name"] for t in tools]
    assert set(names) == {"read_file", "write_file"}
