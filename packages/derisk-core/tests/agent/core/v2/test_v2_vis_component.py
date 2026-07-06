from derisk.agent.core.v2.v2_vis_component import (
    SimplifiedVisComponent,
    VisComponentTag,
    VisOperationType,
    make_vis_delete,
    make_vis_incr,
    make_vis_replace,
)


def test_simplified_vis_component_incr():
    """测试incr操作组件"""
    component = SimplifiedVisComponent(
        type=VisOperationType.INCR,
        uid="s1-thinking-0",
        tag=VisComponentTag.THINKING,
        content="分析中",
        meta={"state": "streaming"},
    )
    assert component.type == VisOperationType.INCR
    assert component.uid == "s1-thinking-0"
    assert component.tag == VisComponentTag.THINKING
    assert component.content == "分析中"
    assert component.meta["state"] == "streaming"


def test_simplified_vis_component_replace():
    """测试replace操作组件"""
    component = SimplifiedVisComponent(
        type=VisOperationType.REPLACE,
        uid="s1-step_status-0",
        tag=VisComponentTag.STEP_STATUS,
        content="",
        meta={"state": "ACTING", "step_id": "s1"},
    )
    assert component.type == VisOperationType.REPLACE
    assert component.meta["state"] == "ACTING"


def test_simplified_vis_component_delete():
    """测试delete操作组件"""
    component = SimplifiedVisComponent(
        type=VisOperationType.DELETE,
        uid="s1-temp-0",
        tag=VisComponentTag.MESSAGE,
        content="",
    )
    assert component.type == VisOperationType.DELETE


def test_vis_operation_type_values():
    """测试操作类型枚举值"""
    assert VisOperationType.INCR.value == "incr"
    assert VisOperationType.REPLACE.value == "replace"
    assert VisOperationType.DELETE.value == "delete"


def test_to_dict_from_dict_roundtrip():
    component = SimplifiedVisComponent(
        type=VisOperationType.INCR,
        uid="s1-thinking-0",
        tag=VisComponentTag.THINKING,
        content="test",
        meta={"key": "val"},
    )
    restored = SimplifiedVisComponent.from_dict(component.to_dict())
    assert restored.type == component.type
    assert restored.uid == component.uid
    assert restored.tag == component.tag
    assert restored.content == component.content
    assert restored.meta == component.meta


def test_make_vis_helpers():
    incr = make_vis_incr("uid-1", VisComponentTag.THINKING, "content")
    assert incr.type == VisOperationType.INCR

    replace = make_vis_replace("uid-2", VisComponentTag.STEP_STATUS, "", {"state": "INIT"})
    assert replace.type == VisOperationType.REPLACE

    delete = make_vis_delete("uid-3")
    assert delete.type == VisOperationType.DELETE
