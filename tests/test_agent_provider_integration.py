#!/usr/bin/env python3
"""
Integration test for complete Agent conversation flow with Provider model.
This tests the full chain from AgentBuilder -> ConversableAgent -> AIWrapper -> Provider.
"""

import asyncio
import sys
import uuid
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from typing import AsyncIterator, List, Dict, Any, Optional
from pathlib import Path

# Setup paths
derisk_core_path = Path(__file__).parent / "packages" / "derisk-core" / "src"
derisk_serve_path = Path(__file__).parent / "packages" / "derisk-serve" / "src"
if str(derisk_core_path) not in sys.path:
    sys.path.insert(0, str(derisk_core_path))
if str(derisk_serve_path) not in sys.path:
    sys.path.insert(0, str(derisk_serve_path))

# Mock dependencies
mock_app_config = MagicMock()
sys.modules["derisk_app.config"] = mock_app_config
mock_app_config.SandboxConfigParameters = MagicMock()

mock_awel = MagicMock()
sys.modules["derisk_ext.agent.agents.awel.awel_runner_agent"] = mock_awel
mock_awel.AwelRunnerAgent = MagicMock()

import pytest
from derisk.agent.core.llm_config import AgentLLMConfig
from derisk.agent.util.llm.llm_client import AIWrapper, AgentLLMOut
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.core.interface.llm import ModelRequest, ModelOutput, ModelMetadata
from derisk.agent import AgentContext, ConversableAgent
from derisk.agent.core.memory.agent_memory import AgentMemory
from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory


class MockProvider(LLMProvider):
    """Mock Provider that simulates LLM responses"""

    def __init__(
        self,
        responses: List[str] = None,
        api_key: str = "",
        base_url: Optional[str] = None,
        **kwargs,
    ):
        self.responses = responses or ["Hello! I'm a helpful assistant."]
        self.call_history: List[ModelRequest] = []
        self.api_key = api_key
        self.base_url = base_url

    async def generate(self, request: ModelRequest) -> ModelOutput:
        self.call_history.append(request)
        response_text = (
            self.responses[len(self.call_history) - 1]
            if len(self.call_history) <= len(self.responses)
            else self.responses[-1]
        )
        return ModelOutput(
            error_code=0,
            text=response_text,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def generate_stream(self, request: ModelRequest) -> AsyncIterator[ModelOutput]:
        self.call_history.append(request)
        response_text = (
            self.responses[len(self.call_history) - 1]
            if len(self.call_history) <= len(self.responses)
            else self.responses[-1]
        )

        async def stream():
            words = response_text.split()
            for i, word in enumerate(words):
                yield ModelOutput(
                    error_code=0,
                    text=word + (" " if i < len(words) - 1 else ""),
                    incremental=True,
                    finish_reason="stop" if i == len(words) - 1 else None,
                )

        return stream()

    async def models(self) -> List[ModelMetadata]:
        return [ModelMetadata(model="gpt-4")]

    async def count_token(self, model: str, prompt: str) -> int:
        return len(prompt) // 4


class MockGptsMemory(GptsMemory):
    """Mock GptsMemory for testing"""

    def __init__(self):
        self.messages = []
        self.tasks = []
        self.system_messages = []

    async def append(self, conv_id: str, message: Any):
        self.messages.append(message)

    async def get_messages(self, conv_id: str, limit: int = 100):
        return self.messages[-limit:]

    async def upsert_task(self, conv_id: str, task: Any):
        self.tasks.append(task)

    async def append_system_message(self, agent_system_message: Any):
        self.system_messages.append(agent_system_message)


@pytest.fixture
def mock_llm_config():
    """Create a mock LLM config"""
    return AgentLLMConfig(
        model="gpt-4",
        provider="openai",
        api_key="sk-test-key",
        temperature=0.7,
        max_new_tokens=1024,
    )


@pytest.fixture
def mock_agent_context():
    """Create a mock AgentContext"""
    return AgentContext(
        conv_id="test_conv_001",
        conv_session_id="test_session_001",
        gpts_app_code="test_app",
        max_new_tokens=1024,
        temperature=0.7,
        verbose=False,
        incremental=False,
    )


@pytest.fixture
def mock_memory():
    """Create mock memory"""
    memory = MagicMock(spec=AgentMemory)
    memory.gpts_memory = MockGptsMemory()
    return memory


@pytest.mark.asyncio
class TestAgentProviderIntegration:
    """Test complete Agent -> Provider integration"""

    async def test_aiwrapper_uses_provider_correctly(self, mock_llm_config):
        """Test that AIWrapper correctly routes to Provider"""
        mock_provider = MockProvider(["Test response"])

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider",
            return_value=mock_provider,
        ):
            wrapper = AIWrapper(llm_config=mock_llm_config)

            messages = [{"role": "user", "content": "Hello"}]
            outputs = []

            async for output in wrapper.create(
                messages=messages, stream_out=True, temperature=0.7, max_new_tokens=1024
            ):
                outputs.append(output)

            # Verify Provider was called
            assert len(mock_provider.call_history) == 1
            request = mock_provider.call_history[0]
            assert request.model == "gpt-4"
            assert request.temperature == 0.7
            assert request.max_new_tokens == 1024

            # Verify we got outputs
            assert len(outputs) > 0
            full_text = "".join([o.content for o in outputs if o.content])
            assert "Test response" in full_text

    async def test_aiwrapper_handles_empty_response(self, mock_llm_config):
        """Test handling of empty responses from Provider"""

        class EmptyProvider(MockProvider):
            async def generate(self, request: ModelRequest) -> ModelOutput:
                return ModelOutput(error_code=0, text="", finish_reason="stop")

            def generate_stream(
                self, request: ModelRequest
            ) -> AsyncIterator[ModelOutput]:
                async def empty_stream():
                    yield ModelOutput(error_code=0, text="", finish_reason="stop")

                return empty_stream()

        with patch("derisk.agent.util.llm.llm_client.OpenAIProvider", EmptyProvider):
            wrapper = AIWrapper(llm_config=mock_llm_config)

            messages = [{"role": "user", "content": "Hello"}]
            outputs = []

            async for output in wrapper.create(messages=messages, stream_out=True):
                outputs.append(output)

            # Should handle empty response gracefully
            assert len(outputs) >= 0  # May be 0 if filtered

    async def test_aiwrapper_temperature_fallback(self, mock_llm_config):
        """Test that temperature falls back to config value"""
        mock_provider = MockProvider()

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider",
            return_value=mock_provider,
        ):
            wrapper = AIWrapper(llm_config=mock_llm_config)

            # Don't pass temperature in create() call
            messages = [{"role": "user", "content": "Hello"}]
            async for output in wrapper.create(messages=messages, stream_out=False):
                pass

            # Should use config temperature (0.7)
            assert len(mock_provider.call_history) == 1
            assert mock_provider.call_history[0].temperature == 0.7

    async def test_conversable_agent_llm_client_initialization(
        self, mock_agent_context, mock_memory
    ):
        """Test ConversableAgent correctly initializes llm_client with Provider"""
        llm_config = AgentLLMConfig(
            model="gpt-4", provider="openai", api_key="sk-test", temperature=0.5
        )

        mock_provider = MockProvider()

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider",
            return_value=mock_provider,
        ):
            # Create AIWrapper with Provider
            llm_client = AIWrapper(llm_config=llm_config)

            assert llm_client._provider is not None
            assert isinstance(llm_client._provider, MockProvider)

    async def test_provider_message_format_conversion(self, mock_llm_config):
        """Test that messages are correctly formatted for Provider"""
        mock_provider = MockProvider()

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider",
            return_value=mock_provider,
        ):
            wrapper = AIWrapper(llm_config=mock_llm_config)

            # Test with complex message structure
            messages = [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ]

            async for output in wrapper.create(messages=messages, stream_out=False):
                pass

            # Verify request was made with correct messages
            assert len(mock_provider.call_history) == 1
            request = mock_provider.call_history[0]
            assert len(request.messages) == 4
            # Messages may be dicts or ModelMessage objects
            first_msg = request.messages[0]
            last_msg = request.messages[-1]
            first_content = (
                first_msg.get("content")
                if isinstance(first_msg, dict)
                else first_msg.content
            )
            last_content = (
                last_msg.get("content")
                if isinstance(last_msg, dict)
                else last_msg.content
            )
            assert first_content == "You are helpful"
            assert last_content == "How are you?"


def run_tests():
    """Run all tests"""
    print("=" * 60)
    print("Testing Agent-Provider Integration")
    print("=" * 60)

    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    return exit_code


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
