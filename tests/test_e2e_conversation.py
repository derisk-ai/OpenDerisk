#!/usr/bin/env python3
"""
End-to-end test simulating complete Agent conversation flow.
This validates the full chain:
User Message -> Agent -> AIWrapper -> Provider -> LLM Response
"""

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from typing import AsyncIterator, List, Dict, Any, Optional

# Setup paths
derisk_core_path = Path(__file__).parent / "packages" / "derisk-core" / "src"
if str(derisk_core_path) not in sys.path:
    sys.path.insert(0, str(derisk_core_path))

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
from derisk.core.interface.message import ModelMessage, HumanMessage, SystemMessage
from derisk.util.error_types import LLMChatError


class ConversationSimulator:
    """Simulates a complete conversation flow"""

    def __init__(self):
        self.conversation_history = []
        self.provider_calls = []

    def simulate_user_message(self, content: str) -> Dict:
        """Simulate a user message"""
        return {"role": "user", "content": content, "message_id": str(uuid.uuid4())}

    def simulate_assistant_message(self, content: str) -> Dict:
        """Simulate an assistant message"""
        return {
            "role": "assistant",
            "content": content,
            "message_id": str(uuid.uuid4()),
        }


class ValidatingProvider(LLMProvider):
    """
    Provider that validates request format and simulates responses.
    This helps verify the complete conversation chain.
    """

    def __init__(
        self,
        responses: List[str] = None,
        api_key: str = "",
        base_url: Optional[str] = None,
        **kwargs,
    ):
        self.responses = responses or ["I understand. Let me help you with that."]
        self.response_index = 0
        self.call_history: List[Dict] = []
        self.api_key = api_key
        self.base_url = base_url

    def _validate_request(self, request: ModelRequest) -> List[str]:
        """Validate the request format and return any errors"""
        errors = []

        # Check model is specified
        if not request.model:
            errors.append("Model name is required")

        # Check messages are present and valid
        if not request.messages:
            errors.append("Messages are required")
        else:
            for i, msg in enumerate(request.messages):
                if isinstance(msg, dict):
                    if "role" not in msg:
                        errors.append(f"Message {i} missing 'role' field")
                    if "content" not in msg:
                        errors.append(f"Message {i} missing 'content' field")
                elif hasattr(msg, "role") and hasattr(msg, "content"):
                    # It's a ModelMessage object
                    pass
                else:
                    errors.append(f"Message {i} has invalid format: {type(msg)}")

        # Check temperature is in valid range
        if request.temperature is not None:
            if not (0 <= request.temperature <= 2):
                errors.append(f"Temperature {request.temperature} out of range [0, 2]")

        # Check max_new_tokens is positive
        if request.max_new_tokens is not None:
            if request.max_new_tokens <= 0:
                errors.append(
                    f"max_new_tokens must be positive, got {request.max_new_tokens}"
                )

        return errors

    async def generate(self, request: ModelRequest) -> ModelOutput:
        """Generate a non-streaming response"""
        errors = self._validate_request(request)

        self.call_history.append(
            {"method": "generate", "request": request, "errors": errors}
        )

        if errors:
            return ModelOutput(
                error_code=1, text=f"Validation errors: {'; '.join(errors)}"
            )

        response_text = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1

        return ModelOutput(
            error_code=0,
            text=response_text,
            finish_reason="stop",
            usage={
                "prompt_tokens": sum(
                    len(
                        str(
                            m.get("content", m.content if hasattr(m, "content") else "")
                        )
                    )
                    for m in request.messages
                )
                // 4,
                "completion_tokens": len(response_text) // 4,
                "total_tokens": 0,
            },
        )

    def generate_stream(self, request: ModelRequest) -> AsyncIterator[ModelOutput]:
        """Generate a streaming response"""
        errors = self._validate_request(request)

        self.call_history.append(
            {"method": "generate_stream", "request": request, "errors": errors}
        )

        async def stream():
            if errors:
                yield ModelOutput(
                    error_code=1, text=f"Validation errors: {'; '.join(errors)}"
                )
                return

            response_text = self.responses[self.response_index % len(self.responses)]
            self.response_index += 1

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
        return [ModelMetadata(model="gpt-4"), ModelMetadata(model="gpt-3.5-turbo")]

    async def count_token(self, model: str, prompt: str) -> int:
        return len(prompt) // 4


@pytest.mark.asyncio
class TestEndToEndConversation:
    """Test complete end-to-end conversation flow"""

    async def test_simple_conversation_flow(self):
        """Test a simple conversation: User asks, Agent responds"""
        simulator = ConversationSimulator()
        provider = ValidatingProvider(responses=["Hello! How can I help you today?"])

        config = AgentLLMConfig(
            model="gpt-4",
            provider="openai",
            api_key="sk-test-key",
            temperature=0.7,
            max_new_tokens=1024,
        )

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            # Simulate user message
            user_msg = simulator.simulate_user_message("Hello!")
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_msg["content"]},
            ]

            # Generate response
            collected_content = []
            async for output in wrapper.create(
                messages=messages, stream_out=True, temperature=0.7, max_new_tokens=1024
            ):
                if output.content:
                    collected_content.append(output.content)

            # Verify response
            full_response = "".join(collected_content)
            assert "Hello! How can I help you today?" in full_response

            # Verify provider was called with correct parameters
            assert len(provider.call_history) == 1
            request = provider.call_history[0]["request"]
            assert request.model == "gpt-4"
            assert request.temperature == 0.7
            assert request.max_new_tokens == 1024
            assert len(request.messages) == 2

            # Verify no validation errors
            assert len(provider.call_history[0]["errors"]) == 0

    async def test_multi_turn_conversation(self):
        """Test a multi-turn conversation - verify full context is passed"""
        simulator = ConversationSimulator()
        final_response = "Is there anything else I can help with?"
        provider = ValidatingProvider(responses=[final_response])

        config = AgentLLMConfig(
            model="gpt-4", provider="openai", api_key="sk-test", temperature=0.5
        )

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            # Simulate a full conversation history
            conversation = [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "I have a problem"},
                {"role": "assistant", "content": "I can help you with that!"},
                {"role": "user", "content": "Can you solve it?"},
                {"role": "assistant", "content": "Here's the solution you requested."},
                {"role": "user", "content": "Thank you!"},
            ]

            # Generate final response
            outputs = []
            async for output in wrapper.create(messages=conversation, stream_out=False):
                outputs.append(output)

            # Verify we got a response
            assert len(outputs) == 1
            assert final_response in outputs[0].content

            # Verify full conversation context was passed to provider
            assert len(provider.call_history) == 1
            request = provider.call_history[0]["request"]
            assert len(request.messages) == 6  # Full conversation context
            # Verify no validation errors
            assert len(provider.call_history[0]["errors"]) == 0

    async def test_conversation_with_tools(self):
        """Test conversation that includes tool calls"""
        provider = ValidatingProvider(
            responses=['{"action": "search", "query": "weather"}']
        )

        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [
                {"role": "system", "content": "You can use tools."},
                {"role": "user", "content": "What's the weather?"},
            ]

            async for output in wrapper.create(messages=messages, stream_out=False):
                # Verify tool call structure
                assert output.content is not None
                assert "search" in output.content or "weather" in output.content

    async def test_conversation_error_recovery(self):
        """Test conversation error handling and recovery"""
        error_response = [None]  # Use mutable to track state

        class ErrorThenSuccessProvider(ValidatingProvider):
            async def generate(self, request: ModelRequest) -> ModelOutput:
                if error_response[0] is None:
                    error_response[0] = True
                    return ModelOutput(error_code=1, text="Temporary error")
                return await super().generate(request)

            def generate_stream(
                self, request: ModelRequest
            ) -> AsyncIterator[ModelOutput]:
                if error_response[0] is None:
                    error_response[0] = True

                    async def error_stream():
                        yield ModelOutput(error_code=1, text="Temporary error")

                    return error_stream()
                return super().generate_stream(request)

        provider = ErrorThenSuccessProvider(responses=["Success!"])

        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "Hello"}]

            # First attempt should fail
            try:
                async for output in wrapper.create(messages=messages, stream_out=False):
                    pass
                assert False, "Should have raised LLMChatError"
            except LLMChatError:
                pass  # Expected

            # Second attempt should succeed (after retry logic in Agent)
            # Note: In real scenario, Agent would handle retry

    async def test_conversation_with_thinking_content(self):
        """Test conversation that includes thinking/reasoning content"""

        class ThinkingProvider(ValidatingProvider):
            async def generate(self, request: ModelRequest) -> ModelOutput:
                result = await super().generate(request)
                # Simulate thinking content
                return result

            def generate_stream(
                self, request: ModelRequest
            ) -> AsyncIterator[ModelOutput]:
                async def stream_with_thinking():
                    # Simulate thinking phase
                    yield ModelOutput(error_code=0, text="", incremental=True)

                    # Then actual response
                    words = self.responses[0].split()
                    for i, word in enumerate(words):
                        yield ModelOutput(
                            error_code=0,
                            text=word + (" " if i < len(words) - 1 else ""),
                            incremental=True,
                            finish_reason="stop" if i == len(words) - 1 else None,
                        )

                return stream_with_thinking()

        provider = ThinkingProvider(responses=["The answer is 42."])

        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "What is 6 times 7?"}]

            collected = []
            async for output in wrapper.create(messages=messages, stream_out=True):
                if output.content:
                    collected.append(output.content)

            full_text = "".join(collected)
            assert "42" in full_text


def run_tests():
    """Run all e2e tests"""
    print("=" * 70)
    print("End-to-End Conversation Flow Tests")
    print("=" * 70)
    print("Testing complete chain: User -> Agent -> AIWrapper -> Provider -> LLM")
    print("=" * 70)

    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    return exit_code


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
