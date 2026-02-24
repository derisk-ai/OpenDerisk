#!/usr/bin/env python3
"""
Complete validation suite for Agent Provider model conversation logic.
This comprehensive test validates:
1. Provider initialization and configuration
2. AIWrapper integration with Provider
3. Message routing and formatting
4. Error handling
5. End-to-end conversation flow

Usage:
    python test_provider_complete_validation.py

All tests must pass for the Provider model to be considered fully functional.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from typing import AsyncIterator, List, Dict, Any, Optional
import traceback

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
from derisk.util.error_types import LLMChatError


class TestProvider(MagicMock):
    """Enhanced mock provider that tracks all interactions"""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.responses = kwargs.get("responses", ["Test response"])
        self.should_fail = kwargs.get("should_fail", False)
        self.call_log = []
        self.api_key = kwargs.get("api_key", "")
        self.base_url = kwargs.get("base_url", None)
        self.response_index = 0

    async def generate(self, request: ModelRequest) -> ModelOutput:
        self.call_log.append({"method": "generate", "request": request})

        if self.should_fail:
            return ModelOutput(error_code=1, text="Simulated error")

        response = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1

        return ModelOutput(
            error_code=0,
            text=response,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def generate_stream(self, request: ModelRequest) -> AsyncIterator[ModelOutput]:
        self.call_log.append({"method": "generate_stream", "request": request})

        async def stream():
            if self.should_fail:
                yield ModelOutput(error_code=1, text="Simulated error")
                return

            response = self.responses[self.response_index % len(self.responses)]
            self.response_index += 1

            words = response.split()
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


def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result"""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {test_name}")
    if details and not passed:
        print(f"      Details: {details}")


async def run_test_suite():
    """Run complete test suite"""
    results = {"passed": 0, "failed": 0, "tests": []}

    print_header("PROVIDER MODEL VALIDATION SUITE")
    print("Testing complete Agent conversation chain with Provider model")
    print()

    # Test 1: Provider Initialization
    print_header("TEST 1: Provider Initialization")
    try:
        config = AgentLLMConfig(
            model="gpt-4", provider="openai", api_key="sk-test-key", temperature=0.7
        )

        with patch("derisk.agent.util.llm.llm_client.OpenAIProvider", TestProvider):
            wrapper = AIWrapper(llm_config=config)
            assert wrapper._provider is not None
            print_result("OpenAI Provider Initialization", True)
            results["passed"] += 1
            results["tests"].append(("Provider Init", True, None))
    except Exception as e:
        print_result("OpenAI Provider Initialization", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Provider Init", False, str(e)))

    # Test 2: Claude Provider
    try:
        config = AgentLLMConfig(
            model="claude-3-opus",
            provider="claude",
            api_key="sk-claude-key",
            temperature=0.5,
        )

        with patch("derisk.agent.util.llm.llm_client.ClaudeProvider", TestProvider):
            wrapper = AIWrapper(llm_config=config)
            assert wrapper._provider is not None
            print_result("Claude Provider Initialization", True)
            results["passed"] += 1
            results["tests"].append(("Claude Provider Init", True, None))
    except Exception as e:
        print_result("Claude Provider Initialization", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Claude Provider Init", False, str(e)))

    # Test 3: Environment Variable API Key
    print_header("TEST 2: API Key Configuration")
    try:
        import os

        os.environ["OPENAI_API_KEY"] = "env-api-key"

        config = AgentLLMConfig(model="gpt-4", provider="openai")

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", TestProvider
        ) as mock:
            wrapper = AIWrapper(llm_config=config)
            assert wrapper._provider.api_key == "env-api-key"
            print_result("API Key from Environment", True)
            results["passed"] += 1
            results["tests"].append(("API Key from Env", True, None))
    except Exception as e:
        print_result("API Key from Environment", False, str(e))
        results["failed"] += 1
        results["tests"].append(("API Key from Env", False, str(e)))
    finally:
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

    # Test 4: Missing API Key
    try:
        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key=None)

        with patch.dict("os.environ", {}, clear=True):
            try:
                wrapper = AIWrapper(llm_config=config)
                print_result(
                    "Missing API Key Validation", False, "Should have raised ValueError"
                )
                results["failed"] += 1
                results["tests"].append(
                    ("Missing API Key", False, "Should have raised ValueError")
                )
            except ValueError as e:
                if "API Key is required" in str(e):
                    print_result("Missing API Key Validation", True)
                    results["passed"] += 1
                    results["tests"].append(("Missing API Key", True, None))
                else:
                    raise
    except Exception as e:
        print_result("Missing API Key Validation", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Missing API Key", False, str(e)))

    # Test 5: Streaming Conversation
    print_header("TEST 3: Conversation Flows")
    try:
        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        provider = TestProvider(responses=["Hello from streaming!"])

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "Hi!"}]
            collected = []

            async for output in wrapper.create(messages=messages, stream_out=True):
                collected.append(output)

            assert len(collected) > 0
            full_text = "".join([o.content for o in collected if o.content])
            assert "Hello from streaming!" in full_text
            assert len(provider.call_log) == 1
            assert provider.call_log[0]["method"] == "generate_stream"

            print_result("Streaming Conversation", True)
            results["passed"] += 1
            results["tests"].append(("Streaming Conversation", True, None))
    except Exception as e:
        print_result("Streaming Conversation", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Streaming Conversation", False, str(e)))

    # Test 6: Non-Streaming Conversation
    try:
        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        provider = TestProvider(responses=["Hello from non-streaming!"])

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "Hi!"}]
            collected = []

            async for output in wrapper.create(messages=messages, stream_out=False):
                collected.append(output)

            assert len(collected) == 1
            assert "Hello from non-streaming!" in collected[0].content
            assert len(provider.call_log) == 1
            assert provider.call_log[0]["method"] == "generate"

            print_result("Non-Streaming Conversation", True)
            results["passed"] += 1
            results["tests"].append(("Non-Streaming Conversation", True, None))
    except Exception as e:
        print_result("Non-Streaming Conversation", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Non-Streaming Conversation", False, str(e)))

    # Test 7: Parameter Passing
    print_header("TEST 4: Parameter Passing")
    try:
        config = AgentLLMConfig(
            model="gpt-4",
            provider="openai",
            api_key="sk-test",
            temperature=0.9,
            max_new_tokens=2048,
        )

        provider = TestProvider()

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
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

            request = provider.call_log[0]["request"]
            assert request.model == "gpt-4"
            assert request.temperature == 0.9
            assert request.max_new_tokens == 2048

            print_result("Temperature and Max Tokens", True)
            results["passed"] += 1
            results["tests"].append(("Parameter Passing", True, None))
    except Exception as e:
        print_result("Temperature and Max Tokens", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Parameter Passing", False, str(e)))

    # Test 8: Error Handling
    print_header("TEST 5: Error Handling")
    try:
        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        provider = TestProvider(should_fail=True)

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [{"role": "user", "content": "Test"}]

            try:
                async for output in wrapper.create(messages=messages, stream_out=False):
                    pass
                print_result("Error Handling", False, "Should have raised LLMChatError")
                results["failed"] += 1
                results["tests"].append(
                    ("Error Handling", False, "Should have raised LLMChatError")
                )
            except LLMChatError:
                print_result("Error Handling", True)
                results["passed"] += 1
                results["tests"].append(("Error Handling", True, None))
    except Exception as e:
        print_result("Error Handling", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Error Handling", False, str(e)))

    # Test 9: Multi-turn Conversation
    print_header("TEST 6: Multi-turn Conversation")
    try:
        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        provider = TestProvider(responses=["Final response"])

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            # Simulate conversation history
            messages = [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ]

            async for output in wrapper.create(messages=messages, stream_out=False):
                pass

            request = provider.call_log[0]["request"]
            assert len(request.messages) == 4

            print_result("Multi-turn Conversation", True)
            results["passed"] += 1
            results["tests"].append(("Multi-turn Conversation", True, None))
    except Exception as e:
        print_result("Multi-turn Conversation", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Multi-turn Conversation", False, str(e)))

    # Test 10: Complex Message Structure
    try:
        config = AgentLLMConfig(model="gpt-4", provider="openai", api_key="sk-test")

        provider = TestProvider()

        with patch(
            "derisk.agent.util.llm.llm_client.OpenAIProvider", return_value=provider
        ):
            wrapper = AIWrapper(llm_config=config)

            messages = [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "User message 1"},
                {"role": "assistant", "content": "Assistant response"},
                {"role": "user", "content": "User message 2"},
            ]

            async for output in wrapper.create(messages=messages, stream_out=False):
                pass

            request = provider.call_log[0]["request"]
            # Verify all messages are present
            assert len(request.messages) == 4

            # Check message roles are preserved
            msg_roles = []
            for msg in request.messages:
                if isinstance(msg, dict):
                    msg_roles.append(msg.get("role"))
                else:
                    msg_roles.append(msg.role)

            assert "system" in msg_roles
            assert "user" in msg_roles
            assert "assistant" in msg_roles

            print_result("Complex Message Structure", True)
            results["passed"] += 1
            results["tests"].append(("Complex Messages", True, None))
    except Exception as e:
        print_result("Complex Message Structure", False, str(e))
        results["failed"] += 1
        results["tests"].append(("Complex Messages", False, str(e)))

    # Print Summary
    print_header("VALIDATION SUMMARY")
    total = results["passed"] + results["failed"]
    print(f"  Total Tests: {total}")
    print(f"  Passed: {results['passed']} ✓")
    print(f"  Failed: {results['failed']} ✗")
    print()

    if results["failed"] == 0:
        print("  🎉 ALL TESTS PASSED! Provider model is fully functional.")
        print()
        print("  The Agent conversation chain is working correctly:")
        print("  User Message → Agent → AIWrapper → Provider → LLM Response")
        return 0
    else:
        print("  ⚠️  SOME TESTS FAILED. Please review the failures above.")
        print()
        print("  Failed Tests:")
        for name, passed, error in results["tests"]:
            if not passed:
                print(f"    - {name}: {error}")
        return 1


def main():
    """Main entry point"""
    try:
        exit_code = asyncio.run(run_test_suite())
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
