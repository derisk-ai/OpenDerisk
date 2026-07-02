"""P4 Task 1: verify the orphan push_context_event wrapper is gone."""
import pytest


def test_orphan_push_context_event_removed():
    """The standalone push_context_event in derisk.context.manager should be removed."""
    from derisk.context import manager
    assert not hasattr(manager, "push_context_event"), (
        "derisk.context.manager.push_context_event should be removed in P4 "
        "(orphan wrapper with 0 production callers)"
    )
