# packages/derisk-core/tests/agent/core/v2/test_package.py
from derisk.agent.core.v2 import (
    StepState,
    StepEvent,
    StateStore,
    DbStateStore,
    EventStream,
    RecoveryCoordinatorV2,
    run_step,
    resume_step,
    validate_transition,
    IllegalTransitionError,
)


def test_all_public_names_importable():
    assert StepState.INIT.value == "init"
    assert callable(run_step)
    assert callable(resume_step)
    assert callable(validate_transition)
    assert issubclass(IllegalTransitionError, Exception)
    assert issubclass(DbStateStore, StateStore)
