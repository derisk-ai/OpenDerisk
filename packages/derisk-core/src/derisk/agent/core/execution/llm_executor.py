"""
LLM Executor - Simplified LLM invocation and streaming.
Extracted from base_agent.py thinking method.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM configuration for a single call."""

    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    stream: bool = True
    stop: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMOutput:
    """LLM output container."""

    content: str = ""
    thinking_content: Optional[str] = None
    model_name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        if self.usage:
            return self.usage.get("total_tokens", 0)
        return 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "thinking_content": self.thinking_content,
            "model_name": self.model_name,
            "tool_calls": self.tool_calls,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata,
        }


@dataclass
class StreamChunk:
    """A single chunk from LLM streaming output."""

    content_delta: str = ""
    thinking_delta: Optional[str] = None
    is_thinking: bool = False
    is_first: bool = False
    is_last: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMExecutor:
    """
    Simplified LLM executor with streaming support.

    Handles:
    - Model invocation
    - Streaming output
    - Error handling with retry
    - Metrics collection
    """

    def __init__(
        self,
        llm_client: Any,
        on_stream_chunk: Optional[Callable[[StreamChunk], None]] = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ):
        self.llm_client = llm_client
        self.on_stream_chunk = on_stream_chunk
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self._total_calls = 0
        self._total_tokens = 0

    async def invoke(
        self,
        messages: List[Dict[str, Any]],
        config: LLMConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMOutput:
        """
        Invoke LLM with messages.

        Args:
            messages: List of message dicts with role and content
            config: LLM configuration
            context: Additional context for the call

        Returns:
            LLMOutput with generated content
        """
        self._total_calls += 1
        output = LLMOutput(model_name=config.model)

        for attempt in range(self.retry_count):
            try:
                if config.stream:
                    output = await self._invoke_stream(messages, config, context)
                else:
                    output = await self._invoke_once(messages, config, context)

                self._total_tokens += output.total_tokens
                return output

            except Exception as e:
                logger.error(
                    f"LLM invocation failed (attempt {attempt + 1}/{self.retry_count}): {e}"
                )
                if attempt < self.retry_count - 1:
                    import asyncio

                    await asyncio.sleep(self.retry_delay)
                else:
                    raise

        return output

    async def _invoke_once(
        self,
        messages: List[Dict[str, Any]],
        config: LLMConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMOutput:
        """Non-streaming invocation."""
        response = await self.llm_client.create(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            stop=config.stop,
            **context or {},
        )

        output = LLMOutput(model_name=config.model)

        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            output.content = choice.message.content or ""
            if hasattr(choice.message, "tool_calls"):
                output.tool_calls = choice.message.tool_calls
            output.finish_reason = choice.finish_reason

        if hasattr(response, "usage"):
            output.usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return output

    async def _invoke_stream(
        self,
        messages: List[Dict[str, Any]],
        config: LLMConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMOutput:
        """Streaming invocation."""
        output = LLMOutput(model_name=config.model, metadata={"streaming": True})

        stream = await self.llm_client.create(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            stop=config.stop,
            stream=True,
            **context or {},
        )

        full_content = ""
        full_thinking = ""
        chunk_count = 0

        async for chunk in stream:
            chunk_count += 1
            chunk_content = ""
            chunk_thinking = None

            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    chunk_content = delta.content
                    full_content += chunk_content
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    chunk_thinking = delta.reasoning_content
                    full_thinking += chunk_thinking

            stream_chunk = StreamChunk(
                content_delta=chunk_content,
                thinking_delta=chunk_thinking,
                is_thinking=chunk_thinking is not None,
                is_first=chunk_count == 1,
                is_last=hasattr(chunk, "choices")
                and chunk.choices[0].finish_reason is not None,
            )

            if self.on_stream_chunk:
                import asyncio

                if asyncio.iscoroutinefunction(self.on_stream_chunk):
                    await self.on_stream_chunk(stream_chunk)
                elif callable(self.on_stream_chunk):
                    self.on_stream_chunk(stream_chunk)

        output.content = full_content
        output.thinking_content = full_thinking or None

        return output

    @property
    def total_calls(self) -> int:
        """Get total LLM calls made."""
        return self._total_calls

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self._total_tokens


def create_llm_config(
    model: str, temperature: float = 0.7, max_tokens: int = 2048, **kwargs
) -> LLMConfig:
    """Factory function to create LLMConfig."""
    return LLMConfig(
        model=model, temperature=temperature, max_tokens=max_tokens, **kwargs
    )


def create_llm_executor(
    llm_client: Any, on_stream_chunk: Optional[Callable] = None, **kwargs
) -> LLMExecutor:
    """Factory function to create LLMExecutor."""
    return LLMExecutor(llm_client=llm_client, on_stream_chunk=on_stream_chunk, **kwargs)
