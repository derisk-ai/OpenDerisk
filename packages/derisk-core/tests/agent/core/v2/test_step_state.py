import pytest
from derisk.agent.core.v2.step_state import (
    StepState,
    validate_transition,
    IllegalTransitionError,
)


def test_step_state_members():
    assert StepState.INIT.value == "init"
    assert StepState.THINKING.value == "thinking"
    assert StepState.ACTING.value == "acting"
    assert StepState.OBSERVING.value == "observing"
    assert StepState.AWAITING_USER.value == "awaiting_user"
    assert StepState.AWAITING_TOOL_PERMISSION.value == "awaiting_tool_permission"
    assert StepState.AWAITING_SUB_AGENT.value == "awaiting_sub_agent"
    assert StepState.DONE.value == "done"
    assert StepState.FAILED.value == "failed"


def test_legal_transitions():
    assert validate_transition(StepState.INIT, StepState.THINKING) is True
    assert validate_transition(StepState.THINKING, StepState.ACTING) is True
    assert validate_transition(StepState.ACTING, StepState.OBSERVING) is True
    assert validate_transition(StepState.OBSERVING, StepState.THINKING) is True
    assert validate_transition(StepState.THINKING, StepState.AWAITING_USER) is True
    assert validate_transition(StepState.ACTING, StepState.AWAITING_USER) is True
    assert validate_transition(StepState.AWAITING_USER, StepState.THINKING) is True
    assert validate_transition(StepState.ACTING, StepState.AWAITING_TOOL_PERMISSION) is True
    assert validate_transition(StepState.AWAITING_TOOL_PERMISSION, StepState.ACTING) is True
    assert validate_transition(StepState.ACTING, StepState.AWAITING_SUB_AGENT) is True
    assert validate_transition(StepState.AWAITING_SUB_AGENT, StepState.OBSERVING) is True
    assert validate_transition(StepState.THINKING, StepState.DONE) is True
    assert validate_transition(StepState.ACTING, StepState.FAILED) is True


def test_illegal_transitions():
    assert validate_transition(StepState.INIT, StepState.DONE) is False
    assert validate_transition(StepState.DONE, StepState.THINKING) is False
    assert validate_transition(StepState.AWAITING_USER, StepState.DONE) is False
    assert validate_transition(StepState.FAILED, StepState.THINKING) is False


def test_awaiting_states_reachable_from_thinking_or_acting():
    # 所有 AWAITING_* 必须从 THINKING 或 ACTING 可达
    for awaiting in [
        StepState.AWAITING_USER,
        StepState.AWAITING_TOOL_PERMISSION,
        StepState.AWAITING_SUB_AGENT,
    ]:
        assert validate_transition(StepState.THINKING, awaiting) is True or \
               validate_transition(StepState.ACTING, awaiting) is True


def test_init_can_transition_to_awaiting_user():
    """P1 follow-up: thinking_fn can request user input before any token."""
    assert validate_transition(StepState.INIT, StepState.AWAITING_USER)


def test_acting_can_transition_to_done():
    """P1 follow-up: permission-denial path skips OBSERVING, goes straight to DONE."""
    assert validate_transition(StepState.ACTING, StepState.DONE)


def test_runtime_extra_no_longer_needed():
    """The runtime_extra workaround in runtime.py should be removed after folding."""
    import derisk.agent.core.v2.runtime as runtime_mod
    src = open(runtime_mod.__file__).read()
    assert "runtime_extra" not in src, (
        "runtime_extra workaround should be removed — transitions folded into VALID_TRANSITIONS"
    )
