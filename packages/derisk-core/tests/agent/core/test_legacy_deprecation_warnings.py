"""P4 Task 3: legacy APIs emit DeprecationWarning pointing to V2 replacements."""
import asyncio
import warnings
from unittest.mock import MagicMock, AsyncMock

import pytest


def test_push_context_event_emits_deprecation():
    """ConversableAgent.push_context_event emits DeprecationWarning."""
    from derisk.agent.core.base_agent import ConversableAgent

    mock_agent = MagicMock()
    mock_agent.role = "test_role"
    mock_agent.name = "test_name"

    with pytest.warns(DeprecationWarning, match="BAIZESubsystemAdapter"):
        coro = ConversableAgent.push_context_event(mock_agent, MagicMock(), MagicMock(), "")
        asyncio.run(coro)


def test_push_message_emits_deprecation():
    """GptsMemory.push_message emits DeprecationWarning."""
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

    mock_mem = MagicMock(spec=GptsMemory)
    mock_mem._get_cache = AsyncMock(return_value=None)

    with pytest.warns(DeprecationWarning, match="EventStream"):
        coro = GptsMemory.push_message(mock_mem, "test_conv_id")
        asyncio.run(coro)


def test_queue_iterator_emits_deprecation():
    """GptsMemory.queue_iterator emits DeprecationWarning."""
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

    mock_mem = MagicMock(spec=GptsMemory)
    mock_mem._get_cache = AsyncMock(return_value=None)

    with pytest.warns(DeprecationWarning, match="EventStream"):
        coro = GptsMemory.queue_iterator(mock_mem, "test_conv_id")
        asyncio.run(coro)


def test_action_output_ask_user_emits_deprecation():
    """ActionOutput.ask_user emits DeprecationWarning on access."""
    from derisk.agent.core.action.base import ActionOutput

    ao = ActionOutput(content="test", ask_user=True)
    with pytest.warns(DeprecationWarning, match="AskUserAdapter"):
        _ = ao.ask_user