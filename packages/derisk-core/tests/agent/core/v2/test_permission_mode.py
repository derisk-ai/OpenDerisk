from derisk.agent.core.v2.permission_mode import PermissionMode


def test_permission_mode_values():
    assert PermissionMode.DEFAULT.value == "default"
    assert PermissionMode.PLAN.value == "plan"
    assert PermissionMode.AUTO.value == "auto"
    assert PermissionMode.BYPASS.value == "bypass"


def test_permission_mode_from_string():
    assert PermissionMode("default") is PermissionMode.DEFAULT
    assert PermissionMode("plan") is PermissionMode.PLAN
    assert PermissionMode("auto") is PermissionMode.AUTO
    assert PermissionMode("bypass") is PermissionMode.BYPASS
