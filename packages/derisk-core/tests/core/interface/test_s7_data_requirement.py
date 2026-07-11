"""RFC-005 S7 data_requirement 契约与大库降级策略单测。"""

from derisk.core.interface.resource.data_requirement import DataRequirement, InjectionMode, SMALL_DB_THRESHOLD, MEDIUM_DB_THRESHOLD, injection_mode_for_table_count
# injection_mode_for_table_count
# --------------------------------------------------------------------------- #
def test_small_db_injects_full():
    assert injection_mode_for_table_count(0) == InjectionMode.SMALL
    assert injection_mode_for_table_count(99) == InjectionMode.SMALL
    assert injection_mode_for_table_count(SMALL_DB_THRESHOLD - 1) == InjectionMode.SMALL


def test_medium_db_compact():
    assert injection_mode_for_table_count(100) == InjectionMode.MEDIUM
    assert injection_mode_for_table_count(250) == InjectionMode.MEDIUM
    assert injection_mode_for_table_count(MEDIUM_DB_THRESHOLD - 1) == InjectionMode.MEDIUM


def test_large_db_no_injection():
    """大库(>=500)→ LARGE,不注入表列表,走按需拉取。"""
    assert injection_mode_for_table_count(500) == InjectionMode.LARGE
    assert injection_mode_for_table_count(5000) == InjectionMode.LARGE


def test_thresholds_overridable():
    """接入层可按 env 覆盖阈值。"""
    # small_threshold=10: 50>=10 且 <500 → MEDIUM
    assert injection_mode_for_table_count(50, small_threshold=10) == InjectionMode.MEDIUM
    # small=10, medium=20: 50>=20 → LARGE
    assert injection_mode_for_table_count(
        50, small_threshold=10, medium_threshold=20
    ) == InjectionMode.LARGE


# --------------------------------------------------------------------------- #
# DataRequirement 契约
# --------------------------------------------------------------------------- #
def test_data_requirement_is_frozen():
    """DataRequirement 不可变(frozen dataclass);params 是 dict 故不参与 hash。

    缓存键依据应取 (executor_id, capability_id, kind) 等标量字段,不含 params。
    """
    req = DataRequirement(
        executor_id="db:conn1",
        capability_id="db",
        kind="db_table_spec",
        params={"datasource_id": "ds1", "mode_hint": "auto"},
    )
    assert req.executor_id == "db:conn1"
    assert req.kind == "db_table_spec"
    assert req.params["datasource_id"] == "ds1"
    # frozen:不可赋值
    import dataclasses
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        req.executor_id = "other"


def test_data_requirement_default_params_empty():
    req = DataRequirement(executor_id="e", capability_id="c", kind="k")
    assert req.params == {}


# --------------------------------------------------------------------------- #
# 语义:LARGE 不注入表列表(declare 应据此决策)
# --------------------------------------------------------------------------- #
def test_large_mode_signals_skip_table_injection():
    """LARGE 模式下,declare 不应把表列表塞进 system(协议约束)。

    这里验证策略函数返回 LARGE;实际 declare 实现见 S13 DB 资源迁移。
    """
    mode = injection_mode_for_table_count(1000)
    assert mode == InjectionMode.LARGE
    # LARGE 的协议语义:不注入表列表,改 data_requirement + 工具按需
    # (DBResource.declare 在 S13 实现时据此分支)