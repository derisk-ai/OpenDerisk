#!/usr/bin/env python3
"""
Test file for verifying Agent conversation logic with new Provider model.
This test validates the complete conversation chain with Provider mode.
"""

import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from typing import AsyncIterator, List, Dict, Any, Optional

# Mock dependencies before importing derisk modules
mock_app_config = MagicMock()
sys.modules["derisk_app.config"] = mock_app_config
mock_app_config.SandboxConfigParameters = MagicMock()

mock_awel = MagicMock()
sys.modules["derisk_ext.agent.agents.awel.awel_runner_agent"] = mock_awel
mock_awel.AwelRunnerAgent = MagicMock()

import pytest
import sys
from pathlib import Path

# Add the derisk-core package to path
derisk_core_path = Path(__file__).parent / "packages" / "derisk-core" / "src"
if str(derisk_core_path) not in sys.path:
    sys.path.insert(0, str(derisk_core_path))

from derisk.agent.core.llm_config import AgentLLMConfig
from derisk.agent.util.llm.llm_client import AIWrapper, AgentLLMOut
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.core.interface.llm import (
    ModelRequest,
    ModelOutput,
    ModelMetadata,
    ModelInferenceMetrics,
)
from derisk.util.error_types import LLMChatError


# Mock Provider for testing
class MockOpenAIProvider(LLMProvider):
    """Mock OpenAI Provider for testing"""

    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.kwargs = kwargs
        self.call_count = 0

    async def generate(self, request: ModelRequest) -> ModelOutput:
        """Generate a response from the model."""
        self.call_count += 1
        return ModelOutput(
            error_code=0,
            text="Mock response from OpenAI Provider",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def generate_stream(self, request: ModelRequest) -> AsyncIterator[ModelOutput]:
        """Generate a streaming response from the model."""
        self.call_count += 1

        async def stream_generator():
            chunks = [
                ModelOutput(error_code=0, text="Hello ", incremental=True),
                ModelOutput(error_code=0, text="from ", incremental=True),
                ModelOutput(error_code=0, text="Mock ", incremental=True),
                ModelOutput(
                    error_code=0,
                    text="Provider!",
                    incremental=True,
                    finish_reason="stop",
                ),
            ]
            for chunk in chunks:
                yield chunk

        return stream_generator()

    async def models(self) -> List[ModelMetadata]:
        """List available models."""
        return [ModelMetadata(model="gpt-4")]

    async def count_token(self, model: str, prompt: str) -> int:
        """Count tokens in a prompt."""
        return len(prompt) // 4


class MockClaudeProvider(LLMProvider):
    """Mock Claude Provider for testing"""

    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.kwargs = kwargs
        self.call_count = 0

    async def generate(self, request: ModelRequest) -> ModelOutput:
        """Generate a response from the model."""
        self.call_count += 1
        return ModelOutput(
            error_code=0,
            text="Mock response from Claude Provider",
            finish_reason="stop",
            usage={"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
        )

    def generate_stream(self, request: ModelRequest) -> AsyncIterator[ModelOutput]:
        """Generate a streaming response from the model."""
        self.call_count += 1

        async def stream_generator():
            chunks = [
                ModelOutput(error_code=0, text="Bonjour ", incremental=True),
                ModelOutput(error_code=0, text="from ", incremental=True),
                ModelOutput(error_code=0, text="Claude ", incremental=True),
                ModelOutput(
                    error_code=0,
                    text="Provider!",
                    incremental=True,
                    finish_reason="stop",
                ),
            ]
            for chunk in chunks:
                yield chunk

        return stream_generator()

    async def models(self) -> List[ModelMetadata]:
        """List available models."""
        return [ModelMetadata(model="claude-3-opus")]

    async def count_token(self, model: str, prompt: str) -> int:
        """Count tokens in a prompt."""
        return len(prompt) // 4


class TestProviderInitialization:
    """Test Provider initialization in AIWrapper"""

    def test_openai_provider_initialization(self):
        """Test that OpenAIProvider is correctly initialized"""
        config = AgentLLMConfig(
            model="gpt-4",
            provider="openai",
            api_key="sk-test-key",
            base_url="https://api.openai.com/v1",
            temperature=0.7,
        )

        # Mock the actual provider classes
        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", MockOpenAIProvider
        ):
            wrapper = AIWrapper(llm_config=config)

            assert wrapper._provider is not None
            assert isinstance(wrapper._provider, MockOpenAIProvider)
            assert wrapper._provider.api_key == "sk-test-key"
            assert wrapper._provider.base_url == "https://api.openai.com/v1"

    def test_claude_provider_initialization(self):
        """Test that ClaudeProvider is correctly initialized"""
        config = AgentLLMConfig(
            model="claude-3-opus",
            provider="claude",
            api_key="sk-claude-key",
            base_url="https://api.anthropic.com",
            temperature=0.5,
        )

        with patch(
            "derisk.agent.util.llm.llm_client.ClaudeProvider", MockClaudeProvider
        ):
            wrapper = AIWrapper(llm_config=config)

            assert wrapper._provider is not None
            assert isinstance(wrapper._provider, MockClaudeProvider)
            assert wrapper._provider.api_key == "sk-claude-key"

    def test_provider_api_key_from_env(self, monkeypatch):
        """Test that API key can be loaded from environment"""
        monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")

        config = AgentLLMConfig(
            model="gpt-4",
            provider="openai",
            # No api_key provided
        )

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", MockOpenAIProvider
        ):
            wrapper = AIWrapper(llm_config=config)

            assert wrapper._provider is not None
            assert wrapper._provider.api_key == "env-openai-key"

    def test_provider_missing_api_key_raises_error(self):
        """Test that missing API key raises ValueError for OpenAI/Claude"""
        config = AgentLLMConfig(
            model="gpt-4",
            provider="openai",
            api_key=None,  # No key and no env var
        )

        with patch.dict("os.environ", {}, clear=True):  # Clear env vars
            with pytest.raises(ValueError, match="API Key is required"):
                AIWrapper(llm_config=config)


@pytest.mark.asyncio
class TestProviderConversation:
    """Test complete conversation flow with Provider mode"""

    async def test_streaming_conversation_with_provider(self):
        """Test streaming conversation using Provider mode"""
        config = AgentLLMConfig(
            model="gpt-4",
            provider="openai",
            api_key="sk-test-key",
            temperature=0.7,
            max_new_tokens=1024,
        )

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", MockOpenAIProvider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"},
            ]

            collected_outputs = []
            async for output in wrapper.create(
                messages=messages, llm_model="gpt-4", stream_out=True
            ):
                collected_outputs.append(output)
                assert isinstance(output, AgentLLMOut)

            # Verify we received streaming chunks
            assert len(collected_outputs) > 0
            # Verify content was received
            full_content = "".join([out.content or "" for out in collected_outputs])
            assert len(full_content) > 0
            # Verify provider was called
            assert wrapper._provider.call_count == 1

    async def test_non_streaming_conversation_with_provider(self):
        """Test non-streaming conversation using Provider mode"""
        config = AgentLLMConfig(
            model="claude-3-opus",
            provider="claude",
            api_key="sk-claude-key",
            temperature=0.5,
        )

        with patch(
            "derisk.agent.util.llm.llm_client.ClaudeProvider", MockClaudeProvider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "Say hello"}]

            outputs = []
            async for output in wrapper.create(
                messages=messages, llm_model="claude-3-opus", stream_out=False
            ):
                outputs.append(output)

            assert len(outputs) == 1
            assert "Claude" in outputs[0].content or "Provider" in outputs[0].content
            assert wrapper._provider.call_count == 1

    async def test_provider_error_handling(self):
        """Test error handling when Provider returns error"""
        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test-key")

        # Create a provider that returns an error
        class ErrorProvider(MockOpenAIProvider):
            async def generate(self, request: ModelRequest) -> ModelOutput:
                return ModelOutput(error_code=1, text="API Error: Rate limit exceeded")

            def generate_stream(
                self, request: ModelRequest
            ) -> AsyncIterator[ModelOutput]:
                async def error_stream():
                    yield ModelOutput(
                        error_code=1, text="API Error: Rate limit exceeded"
                    )

                return error_stream()

        with patch("derisk.agent.util.llm.llm_client.OpenAIProvider", ErrorProvider):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "Hello"}]

            with pytest.raises(LLMChatError):
                async for output in wrapper.create(messages=messages, stream_out=False):
                    pass

    async def test_temperature_and_max_tokens_configuration(self):
        """Test that temperature and max_tokens are correctly passed to Provider"""
        config = AgentLLMConfig(
            model="gpt-4",
            provider="openai",
            api_key="sk-test-key",
            temperature=0.9,
            max_new_tokens=2048,
        )

        captured_requests = []

        class CapturingProvider(MockOpenAIProvider):
            async def generate(self, request: ModelRequest) -> ModelOutput:
                captured_requests.append(request)
                return await super().generate(request)

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", CapturingProvider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "Test"}]

            async for output in wrapper.create(
                messages=messages,
                temperature=0.9,
                max_new_tokens=2048,
                stream_out=False,
            ):
                pass

            assert len(captured_requests) == 1
            req = captured_requests[0]
            assert req.temperature == 0.9
            assert req.max_new_tokens == 2048


@pytest.mark.asyncio
class TestProviderModelRequest:
    """Test ModelRequest construction"""

    async def test_model_request_build(self):
        """Test ModelRequest.build_request creates correct request"""
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
        ]

        request = ModelRequest.build_request(
            model="gpt-4",
            messages=messages,
            stream=True,
            temperature=0.7,
            max_new_tokens=1024,
        )

        assert request.model == "gpt-4"
        assert request.temperature == 0.7
        assert request.max_new_tokens == 1024
        assert len(request.messages) == 2


def run_tests():
    """Run all tests"""
    print("=" * 60)
    print("Testing Provider Mode Conversation Logic")
    print("=" * 60)

    # Run pytest
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    return exit_code


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
