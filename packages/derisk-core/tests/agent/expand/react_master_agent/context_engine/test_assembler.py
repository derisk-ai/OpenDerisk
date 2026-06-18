"""TimelineAssembler 测试 —— 唯一 join + 唯一排序。"""

from derisk.agent.expand.react_master_agent.context_engine.assembler import (
    TimelineAssembler,
)
from derisk.agent.expand.react_master_agent.context_engine.timeline import (
    ResultStatus,
    UnitKind,
)

from .conftest import FakeMsg, FakeWE, ai_tool_call


def _assemble(msgs, wls, current="c1", subagent=None):
    return TimelineAssembler().assemble(
        messages=msgs,
        work_logs_by_conv=wls,
        current_conv_id=current,
        session_id="s",
        subagent_goal_id=subagent,
    )


def test_single_join_by_tool_call_id():
    msgs = [
        FakeMsg("c1", "ai", "m1", content="", tool_calls=[ai_tool_call("tc1", "fa")]),
    ]
    wls = {"c1": [FakeWE("fa", "tc1", result="RES", message_id="m1")]}
    tl = _assemble(msgs, wls)
    call = [u for u in tl.units if u.kind == UnitKind.CALL][0]
    assert call.calls[0].result_status == ResultStatus.OK
    assert call.calls[0].result_text == "RES"


def test_join_fallback_by_message_id_and_name():
    # WorkEntry 无 tool_call_id，但有 message_id + tool 名匹配
    msgs = [
        FakeMsg("c1", "ai", "m1", content="", tool_calls=[ai_tool_call("tc1", "fa")]),
    ]
    wls = {"c1": [FakeWE("fa", "", result="RES", message_id="m1")]}
    tl = _assemble(msgs, wls)
    call = [u for u in tl.units if u.kind == UnitKind.CALL][0]
    assert call.calls[0].result_text == "RES"


def test_join_fallback_positional_by_tool_name():
    # 既无 tool_call_id 也无 message_id，按工具名顺序定位
    msgs = [
        FakeMsg("c1", "ai", "m1", content="", tool_calls=[ai_tool_call("tc1", "fa")]),
    ]
    wls = {"c1": [FakeWE("fa", "", result="RES", message_id="")]}
    tl = _assemble(msgs, wls)
    call = [u for u in tl.units if u.kind == UnitKind.CALL][0]
    assert call.calls[0].result_text == "RES"


def test_missing_result_marked_missing():
    msgs = [
        FakeMsg("c1", "ai", "m1", content="", tool_calls=[ai_tool_call("tcX", "fa")]),
    ]
    wls = {"c1": []}
    tl = _assemble(msgs, wls)
    call = [u for u in tl.units if u.kind == UnitKind.CALL][0]
    assert call.calls[0].result_status == ResultStatus.MISSING
    assert not call.calls[0].is_renderable


def test_multi_toolcall_message_atomic():
    msgs = [
        FakeMsg(
            "c1",
            "ai",
            "m1",
            content="",
            tool_calls=[ai_tool_call("tc1", "fa"), ai_tool_call("tc2", "fb")],
        ),
    ]
    wls = {
        "c1": [
            FakeWE("fa", "tc1", result="A", message_id="m1"),
            FakeWE("fb", "tc2", result="B", message_id="m1"),
        ]
    }
    tl = _assemble(msgs, wls)
    call = [u for u in tl.units if u.kind == UnitKind.CALL][0]
    assert len(call.calls) == 2
    by_id = {b.tool_call_id: b.result_text for b in call.calls}
    assert by_id == {"tc1": "A", "tc2": "B"}


def test_single_sort_rounds_then_created_at():
    # 乱序输入，应按 (rounds, created_at) 排序
    msgs = [
        FakeMsg("c1", "ai", "m3", content="third", rounds=2, created_at=1.0),
        FakeMsg("c1", "human", "m1", content="first", rounds=1, created_at=1.0),
        FakeMsg("c1", "ai", "m2", content="second", rounds=1, created_at=2.0),
    ]
    tl = _assemble(msgs, {"c1": []})
    texts = [
        u.user_content if u.kind == UnitKind.USER else u.ai_text for u in tl.units
    ]
    assert texts == ["first", "second", "third"]


def test_error_status_when_not_success():
    msgs = [
        FakeMsg("c1", "ai", "m1", content="", tool_calls=[ai_tool_call("tc1", "fa")]),
    ]
    wls = {"c1": [FakeWE("fa", "tc1", result="boom", message_id="m1", success=False)]}
    tl = _assemble(msgs, wls)
    call = [u for u in tl.units if u.kind == UnitKind.CALL][0]
    assert call.calls[0].result_status == ResultStatus.ERROR


def test_system_and_tool_messages_skipped():
    msgs = [
        FakeMsg("c1", "system", "m0", content="sys"),
        FakeMsg("c1", "tool", "m1", content="toolres"),
        FakeMsg("c1", "human", "m2", content="hi"),
    ]
    tl = _assemble(msgs, {"c1": []})
    assert len(tl.units) == 1
    assert tl.units[0].kind == UnitKind.USER


def test_subagent_goal_filter():
    msgs = [
        FakeMsg("c1", "human", "m1", content="主输入", rounds=1),
        FakeMsg("c1", "ai", "m2", content="goalA", rounds=1, goal_id="A"),
        FakeMsg("c1", "ai", "m3", content="goalB", rounds=1, goal_id="B"),
    ]
    tl = _assemble(msgs, {"c1": []}, subagent="A")
    texts = [u.ai_text for u in tl.units if u.kind == UnitKind.AI_TEXT]
    assert "goalA" in texts
    assert "goalB" not in texts


def test_subagent_filter_falls_back_when_empties_user():
    # 过滤后无 USER 单元 → 回退不过滤
    msgs = [
        FakeMsg("c1", "human", "m1", content="输入", rounds=1, goal_id="Z"),
        FakeMsg("c1", "ai", "m2", content="goalA", rounds=1, goal_id="A"),
    ]
    # 用一个不存在的 goal，过滤后 user(goal=Z) 也被排除 → 无 USER → 回退
    tl = _assemble(msgs, {"c1": []}, subagent="NOPE")
    # 回退后两条都在
    assert len(tl.units) == 2
