"""RFC-005 结构验证:capability 自管目录扩展性。

验证:新建一个 capability 目录(mock/)→ CapabilityRegistry.discover() 自动发现
并注册,零改其它代码。证明"一个资源一个扩展目录"的扩展模型成立。
"""

from derisk.agent.capabilities.registry import CapabilityRegistry


def test_discover_finds_sandbox_and_mock_capabilities():
    """discover() 扫描 agent.capabilities 子包,自动注册各 capability。"""
    reg = CapabilityRegistry()
    reg.discover()
    ids = set(reg.capability_ids())
    # sandbox 注册的是占位(register() pass,无实例)→ 不一定在 ids
    # mock 注册了实例 → 必在
    assert "mock" in ids


def test_mock_capability_declares_contribution():
    """新建的 mock capability 能正确 declare,无需改 facade/registry 等任何代码。"""
    reg = CapabilityRegistry()
    reg.discover()
    mock = reg.get("mock")
    assert mock is not None
    contribs = mock.declare(None)
    assert len(contribs) == 1
    assert contribs[0].capability_id == "mock"
    assert contribs[0].slot.value == "system"


def test_new_capability_does_not_affect_others():
    """新增 mock 不影响 capabilities 包其它导入。"""
    from derisk.agent.capabilities import ResourceFacade
    from derisk.agent.capabilities.sandbox import SandboxResource, SANDBOX_DELEGATED_TOOLS
    assert ResourceFacade is not None
    assert SandboxResource is not None
    assert SANDBOX_DELEGATED_TOOLS  # 仍导出(兼容)