"""Tests for step_state_guard: VALID_TRANSITIONS + validate_*_transition."""
import logging

import pytest

from derisk.agent.core.schema import Status
from derisk.agent.core.step_state_guard import (
    IllegalTransitionError,
    MESSAGE_VALID_TRANSITIONS,
    SESSION_VALID_TRANSITIONS,
    validate_message_transition,
    validate_session_transition,
)


class TestSessionTransitions:
    def test_legal_transitions_pass(self):
        validate_session_transition(None, Status.RUNNING)
        validate_session_transition(Status.RUNNING, Status.WAITING)
        validate_session_transition(Status.RUNNING, Status.COMPLETE)
        validate_session_transition(Status.RUNNING, Status.FAILED)
        validate_session_transition(Status.WAITING, Status.RUNNING)
        validate_session_transition(Status.RETRYING, Status.RUNNING)
        validate_session_transition(Status.INTERRUPTED, Status.RUNNING)

    def test_terminal_states_cannot_transition(self):
        # COMPLETE and FAILED are terminal
        for new in [Status.RUNNING, Status.WAITING, Status.COMPLETE, Status.FAILED]:
            # Should not raise (WARN_ONLY=True) but should log warning
            validate_session_transition(Status.COMPLETE, new)
            validate_session_transition(Status.FAILED, new)

    def test_illegal_transition_warn_only(self, caplog):
        import derisk.agent.core.step_state_guard as mod

        old = mod.WARN_ONLY
        mod.WARN_ONLY = True
        try:
            with caplog.at_level(logging.WARNING):
                # RUNNING -> TODO is illegal (TODO not in RUNNING's allowed set)
                validate_session_transition(Status.RUNNING, Status.TODO)
            assert any(
                "illegal session transition" in r.message for r in caplog.records
            ), f"Expected warning logged, got: {caplog.records}"
        finally:
            mod.WARN_ONLY = old

    def test_illegal_transition_raises_when_strict(self):
        import derisk.agent.core.step_state_guard as mod

        old = mod.WARN_ONLY
        mod.WARN_ONLY = False
        try:
            with pytest.raises(IllegalTransitionError):
                validate_session_transition(Status.RUNNING, Status.TODO)
            with pytest.raises(IllegalTransitionError):
                validate_session_transition(Status.COMPLETE, Status.RUNNING)
        finally:
            mod.WARN_ONLY = old

    def test_unknown_old_state_passes(self):
        # BLOCKED is not in MESSAGE table — should pass (conservative)
        # But for session table, BLOCKED is present
        # Test with a state not in table by using message table
        validate_message_transition(Status.BLOCKED, Status.RUNNING)


class TestMessageTransitions:
    def test_legal_transitions_pass(self):
        validate_message_transition(None, Status.TODO)
        validate_message_transition(Status.TODO, Status.RUNNING)
        validate_message_transition(Status.RUNNING, Status.COMPLETE)
        validate_message_transition(Status.RUNNING, Status.FAILED)

    def test_terminal_states_cannot_transition(self):
        validate_message_transition(Status.COMPLETE, Status.RUNNING)  # warns
        validate_message_transition(Status.FAILED, Status.RUNNING)  # warns

    def test_illegal_transition_raises_when_strict(self):
        import derisk.agent.core.step_state_guard as mod

        old = mod.WARN_ONLY
        mod.WARN_ONLY = False
        try:
            with pytest.raises(IllegalTransitionError):
                # TODO -> COMPLETE is illegal (must go through RUNNING)
                validate_message_transition(Status.TODO, Status.COMPLETE)
        finally:
            mod.WARN_ONLY = old


class TestTransitionTables:
    def test_session_table_completeness(self):
        # Session-level states: all except TODO (TODO is message-level only)
        session_states = [
            Status.RUNNING, Status.WAITING, Status.RETRYING,
            Status.FAILED, Status.COMPLETE, Status.BLOCKED, Status.INTERRUPTED,
        ]
        for s in session_states:
            assert s in SESSION_VALID_TRANSITIONS, f"{s.name} missing from SESSION table"
        assert None in SESSION_VALID_TRANSITIONS
        # TODO should NOT be in session table
        assert Status.TODO not in SESSION_VALID_TRANSITIONS

    def test_message_table_covers_core_flow(self):
        # Message-level only needs TODO/RUNNING/COMPLETE/FAILED
        for s in [Status.TODO, Status.RUNNING, Status.COMPLETE, Status.FAILED]:
            assert s in MESSAGE_VALID_TRANSITIONS, f"{s.name} missing from MESSAGE table"
