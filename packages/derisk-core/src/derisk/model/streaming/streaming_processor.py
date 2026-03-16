"""
Streaming Function Call Processor

Integrates the incremental parser with SSE streaming to provide
real-time parameter visualization during LLM function calls.

This is the main integration point for enabling streaming parameters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Set,
)

from .incremental_parser import (
    IncrementalFunctionCallParser,
    ParseEvent,
    ParseState,
)
from .chunk_strategies import (
    AdaptiveChunkStrategy,
    ChunkMetadata,
    ChunkStrategy,
    IChunkStrategy,
    ParamChunk,
    get_strategy,
)

if TYPE_CHECKING:
    from derisk.agent.interaction.sse_stream_manager import SSEStreamManager

logger = logging.getLogger(__name__)


@dataclass
class StreamingConfig:
    """Configuration for streaming behavior"""

    streaming_threshold: int = 256  # Characters
    chunk_strategy: ChunkStrategy = ChunkStrategy.ADAPTIVE
    chunk_size: int = 100  # Characters per chunk
    chunk_by_line: bool = True
    streaming_params: Dict[str, Set[str]] = field(default_factory=dict)


class StreamingFunctionCallProcessor:
    """
    Processor for streaming function call parameters.

    This class integrates with LLM output streams and SSE managers
    to enable real-time parameter visualization.

    Architecture:
    ┌─────────────────┐
    │   LLM Stream    │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────────────────────────┐
    │ StreamingFunctionCallProcessor      │
    │                                     │
    │  ┌───────────────────────────────┐  │
    │  │ IncrementalFunctionCallParser │  │
    │  └───────────────────────────────┘  │
    │                                     │
    │  ┌───────────────────────────────┐  │
    │  │ Chunk Strategy                │  │
    │  └───────────────────────────────┘  │
    └────────────────┬────────────────────┘
                     │
                     ▼
    ┌─────────────────────────────────────┐
    │       SSE Stream Manager            │
    │                                     │
    │  Events:                            │
    │  - tool_call_start                  │
    │  - tool_param_start                 │
    │  - tool_param_chunk                 │
    │  - tool_param_end                   │
    │  - tool_call_end                    │
    └─────────────────────────────────────┘
                     │
                     ▼
    ┌─────────────────────────────────────┐
    │          Frontend                   │
    │                                     │
    │  - Real-time rendering              │
    │  - Progress indicators              │
    │  - Typewriter effect                │
    └─────────────────────────────────────┘

    Usage:
        processor = StreamingFunctionCallProcessor(
            sse_manager=sse_manager,
            config=StreamingConfig()
        )

        # Process LLM stream
        async for token in processor.process_llm_stream(
            session_id="session_123",
            llm_stream=llm_api_stream()
        ):
            # Token is passed through unchanged
            # Streaming events are sent via SSE automatically
            yield token

    Integration with existing code:
        # In your chat/agent handler:

        async def chat_handler(request):
            processor = StreamingFunctionCallProcessor(sse_manager)

            async for token in processor.process_llm_stream(
                session_id=request.session_id,
                llm_stream=llm_client.stream(prompt)
            ):
                # Your existing token handling
                yield token
    """

    # Default streaming parameters configuration
    DEFAULT_STREAMING_PARAMS: Dict[str, Set[str]] = {
        "write": {"content"},
        "edit": {"newString", "oldString"},
        "bash": {"command"},
        "execute_code": {"code"},
        "create_file": {"content"},
        "apply_patch": {"patch"},
        "update_file": {"content"},
        "run_code": {"code"},
    }

    def __init__(
        self,
        sse_manager: Optional["SSEStreamManager"] = None,
        config: Optional[StreamingConfig] = None,
        on_event: Optional[Callable[[ParseEvent], None]] = None,
    ):
        """
        Initialize the streaming processor.

        Args:
            sse_manager: SSE stream manager for sending events
            config: Streaming configuration
            on_event: Optional callback for custom event handling
        """
        self.sse_manager = sse_manager
        self.config = config or StreamingConfig()
        self.on_event = on_event

        # Initialize parser
        self._parser = IncrementalFunctionCallParser(
            streaming_threshold=self.config.streaming_threshold,
            chunk_size=self.config.chunk_size,
            chunk_by_line=self.config.chunk_by_line,
        )

        # Merge streaming params config
        self._streaming_params = {
            **self.DEFAULT_STREAMING_PARAMS,
            **self.config.streaming_params,
        }

        # Current session
        self._session_id: Optional[str] = None

        # Track active function calls
        self._active_calls: Dict[str, Dict[str, Any]] = {}

    async def process_llm_stream(
        self,
        session_id: str,
        llm_stream: AsyncGenerator[str, None],
    ) -> AsyncGenerator[str, None]:
        """
        Process an LLM stream with streaming parameter extraction.

        This is the main entry point. Feed an LLM token stream and
        get back the same tokens while streaming events are sent.

        Args:
            session_id: Session identifier for SSE events
            llm_stream: Async generator of LLM output tokens

        Yields:
            The original tokens (passthrough)
        """
        self._session_id = session_id
        self._parser.reset()
        self._active_calls.clear()

        try:
            async for token in llm_stream:
                # 1. Yield the token (passthrough for downstream processing)
                yield token

                # 2. Process token for function call extraction
                async for event in self._parser.parse_token(token):
                    await self._handle_parse_event(event)

        finally:
            # Cleanup
            self._active_calls.clear()

    async def _handle_parse_event(self, event: ParseEvent) -> None:
        """
        Handle a parse event and send SSE notifications.

        Args:
            event: The parse event from the incremental parser
        """
        # Call custom handler if provided
        if self.on_event:
            self.on_event(event)

        # Send SSE event if manager is available
        if not self.sse_manager:
            return

        if event.event_type == "tool_start":
            await self._handle_tool_start(event)

        elif event.event_type == "param_start":
            await self._handle_param_start(event)

        elif event.event_type == "param_chunk":
            await self._handle_param_chunk(event)

        elif event.event_type == "param_end":
            await self._handle_param_end(event)

        elif event.event_type == "tool_end":
            await self._handle_tool_end(event)

    async def _handle_tool_start(self, event: ParseEvent) -> None:
        """Handle tool call start"""
        call_id = event.call_id
        tool_name = event.tool_name or "unknown"

        # Track this call
        self._active_calls[call_id] = {
            "tool_name": tool_name,
            "params": {},
            "streaming_params": set(),
        }

        # Send SSE event
        await self.sse_manager.send_sse_event(
            self._session_id,
            "tool_call_start",
            {
                "call_id": call_id,
                "tool_name": tool_name,
            },
        )

        logger.debug(f"[StreamingProcessor] Tool start: {tool_name} ({call_id})")

    async def _handle_param_start(self, event: ParseEvent) -> None:
        """Handle parameter start"""
        call_id = event.call_id
        param_name = event.param_name

        if not param_name:
            return

        tool_name = event.tool_name or "unknown"

        # Check if this param should be streamed
        should_stream = self._should_stream_param(tool_name, param_name)

        if should_stream and call_id in self._active_calls:
            self._active_calls[call_id]["streaming_params"].add(param_name)

        # Send SSE event
        await self.sse_manager.send_sse_event(
            self._session_id,
            "tool_param_start",
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "param_name": param_name,
                "streaming": should_stream,
            },
        )

        logger.debug(
            f"[StreamingProcessor] Param start: {param_name} (streaming={should_stream})"
        )

    async def _handle_param_chunk(self, event: ParseEvent) -> None:
        """Handle parameter chunk"""
        call_id = event.call_id
        param_name = event.param_name
        chunk_data = event.data

        if not param_name or not chunk_data:
            return

        tool_name = event.tool_name or "unknown"

        # Send SSE event
        await self.sse_manager.send_sse_event(
            self._session_id,
            "tool_param_chunk",
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "param_name": param_name,
                "chunk_data": chunk_data,
                "is_delta": True,
            },
        )

    async def _handle_param_end(self, event: ParseEvent) -> None:
        """Handle parameter end"""
        call_id = event.call_id
        param_name = event.param_name
        value = event.data

        if not param_name:
            return

        tool_name = event.tool_name or "unknown"

        # Store in active call
        if call_id in self._active_calls:
            self._active_calls[call_id]["params"][param_name] = value

        # Send SSE event
        await self.sse_manager.send_sse_event(
            self._session_id,
            "tool_param_end",
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "param_name": param_name,
                "length": len(value) if value else 0,
            },
        )

        logger.debug(
            f"[StreamingProcessor] Param end: {param_name} ({len(value) if value else 0} chars)"
        )

    async def _handle_tool_end(self, event: ParseEvent) -> None:
        """Handle tool call end"""
        call_id = event.call_id
        tool_name = event.tool_name or "unknown"
        params = event.data or {}

        # Send SSE event
        await self.sse_manager.send_sse_event(
            self._session_id,
            "tool_call_end",
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "params": params,
            },
        )

        # Cleanup
        if call_id in self._active_calls:
            del self._active_calls[call_id]

        logger.debug(f"[StreamingProcessor] Tool end: {tool_name} ({call_id})")

    def _should_stream_param(self, tool_name: str, param_name: str) -> bool:
        """
        Check if a parameter should be streamed.

        Args:
            tool_name: Name of the tool
            param_name: Name of the parameter

        Returns:
            True if the parameter should be streamed
        """
        streaming_params = self._streaming_params.get(tool_name, set())
        return param_name in streaming_params

    def reset(self) -> None:
        """Reset the processor state"""
        self._parser.reset()
        self._active_calls.clear()

    def get_active_calls(self) -> Dict[str, Dict[str, Any]]:
        """Get currently active function calls"""
        return self._active_calls.copy()


def create_streaming_processor(
    sse_manager: Optional["SSEStreamManager"] = None,
    streaming_threshold: int = 256,
    chunk_strategy: ChunkStrategy = ChunkStrategy.ADAPTIVE,
    streaming_params: Optional[Dict[str, Set[str]]] = None,
) -> StreamingFunctionCallProcessor:
    """
    Factory function to create a streaming processor.

    Args:
        sse_manager: SSE stream manager
        streaming_threshold: Character threshold for streaming
        chunk_strategy: Strategy for chunking large parameters
        streaming_params: Custom streaming parameter configuration

    Returns:
        Configured StreamingFunctionCallProcessor
    """
    config = StreamingConfig(
        streaming_threshold=streaming_threshold,
        chunk_strategy=chunk_strategy,
        streaming_params=streaming_params or {},
    )

    return StreamingFunctionCallProcessor(
        sse_manager=sse_manager,
        config=config,
    )
