"""Segmenter 测试。"""

from derisk.agent.expand.react_master_agent.context_engine.assembler import (
    TimelineAssembler,
)
from derisk.agent.expand.react_master_agent.context_engine.segmenter import Segmenter

from .conftest import FakeMsg


def test_segment_by_conv_id():
    msgs = [
        FakeMsg("c1", "human", "m1", content="q1", rounds=1, created_at=1.0),
        FakeMsg("c1", "ai", "m2", content="a1", rounds=1, created_at=2.0),
        FakeMsg("c2", "human", "m3", content="q2", rounds=2, created_at=3.0),
    ]
    tl = TimelineAssembler().assemble(msgs, {"c1": [], "c2": []}, "c2", "s")
    segs = Segmenter().segment(tl)
    assert [s.conv_id for s in segs] == ["c1", "c2"]
    assert len(segs[0].units) == 2
    assert len(segs[1].units) == 1


def test_current_conv_segment_last():
    # c2 较早出现但 c1 是 current → c1 段应排最后
    msgs = [
        FakeMsg("c2", "human", "m1", content="q2", rounds=1, created_at=1.0),
        FakeMsg("c1", "human", "m2", content="q1", rounds=2, created_at=2.0),
    ]
    tl = TimelineAssembler().assemble(msgs, {"c1": [], "c2": []}, "c1", "s")
    segs = Segmenter().segment(tl)
    assert segs[-1].conv_id == "c1"


def test_flatten_roundtrip():
    msgs = [
        FakeMsg("c1", "human", "m1", content="q1", rounds=1, created_at=1.0),
        FakeMsg("c2", "human", "m2", content="q2", rounds=2, created_at=2.0),
    ]
    tl = TimelineAssembler().assemble(msgs, {"c1": [], "c2": []}, "c2", "s")
    segs = Segmenter().segment(tl)
    flat = Segmenter.flatten(segs)
    assert len(flat) == 2
