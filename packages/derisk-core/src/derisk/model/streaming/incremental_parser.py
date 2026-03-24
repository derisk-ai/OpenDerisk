"""
Incremental Function Call Parser

Parses LLM function call output incrementally, enabling real-time
parameter extraction and streaming without waiting for complete JSON.

This is the core component that intercepts LLM token stream and
extracts parameter values as they are generated.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ParseState(Enum):
    """Parser state machine states"""

    IDLE = "idle"
    IN_TOOL_CALLS_ARRAY = "in_tool_calls_array"
    IN_TOOL_CALL_OBJECT = "in_tool_call_object"
    IN_FUNCTION_OBJECT = "in_function_object"
    IN_ARGUMENTS_OBJECT = "in_arguments_object"
    IN_PARAM_KEY = "in_param_key"
    IN_PARAM_VALUE = "in_param_value"
    IN_STRING_VALUE = "in_string_value"
    COMPLETE = "complete"


@dataclass
class StreamingFunctionCall:
    """
    Represents a function call being streamed.

    Tracks the state of a single function call as it's being parsed
    from the LLM output stream.
    """

    call_id: str
    tool_name: str = ""
    arguments_buffer: str = ""

    # Current parsing state
    current_param_name: Optional[str] = None
    current_param_value: str = ""

    # Completed parameters
    completed_params: Dict[str, Any] = field(default_factory=dict)

    # Streaming params tracking (params that are large enough to stream)
    streaming_params: Set[str] = field(default_factory=set)

    # Chunk tracking for streaming params
    param_chunks: Dict[str, List[str]] = field(default_factory=dict)

    # Metadata
    start_time: float = 0.0
    state: ParseState = ParseState.IDLE


@dataclass
class ParseEvent:
    """
    Event emitted during incremental parsing.

    These events are sent to the frontend via SSE for real-time updates.
    """

    event_type: (
        str  # 'tool_start', 'param_start', 'param_chunk', 'param_end', 'tool_end'
    )
    call_id: str
    tool_name: Optional[str] = None
    param_name: Optional[str] = None
    data: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IncrementalFunctionCallParser:
    """
    Incremental parser for LLM function call output.

    This parser processes the raw token stream from LLM and extracts
    function call parameters in real-time, enabling:

    1. Immediate visualization of large parameters (code, file content)
    2. Progress indication during parameter generation
    3. Early validation and feedback

    Key Features:
    - Token-by-token parsing without buffering entire JSON
    - State machine for tracking JSON structure
    - Automatic detection of large parameters for streaming
    - Support for nested JSON in parameter values

    Usage:
        parser = IncrementalFunctionCallParser()

        async for token in llm_stream:
            async for event in parser.parse_token(token):
                # Handle events in real-time
                await send_sse_event(event)

    Example LLM output flow:
        Token 1: {"tool_calls": [{"id": "call_123", "function":...
        Token 2: "arguments": "{\\"content\\": \\"def hello():\\n...
        Token 3:     print('world')\\n...
        ...

    Parser emits:
        - tool_start when tool_calls array is detected
        - param_start when a large parameter key is detected
        - param_chunk for each line/chunk of the parameter value
        - param_end when the parameter value is complete
        - tool_end when the entire function call is complete
    """

    # Default threshold for considering a parameter as "large" (in characters)
    DEFAULT_STREAMING_THRESHOLD = 256

    # Known streaming parameter configurations
    # These tools have parameters that should be streamed
    STREAMING_PARAMS_CONFIG: Dict[str, Set[str]] = {
        "write": {"content"},
        "edit": {"newString", "oldString"},
        "bash": {"command"},
        "execute_code": {"code"},
        "create_file": {"content"},
        "apply_patch": {"patch"},
    }

    def __init__(
        self,
        streaming_threshold: int = DEFAULT_STREAMING_THRESHOLD,
        chunk_size: int = 100,  # Characters per chunk for streaming params
        chunk_by_line: bool = True,  # Prefer line boundaries for chunks
    ):
        """
        Initialize the incremental parser.

        Args:
            streaming_threshold: Minimum character count to consider streaming
            chunk_size: Target size for each chunk
            chunk_by_line: If True, chunk at line boundaries when possible
        """
        self.streaming_threshold = streaming_threshold
        self.chunk_size = chunk_size
        self.chunk_by_line = chunk_by_line

        # Parser state
        self._state = ParseState.IDLE
        self._buffer = ""
        self._position = 0

        # Current function call being parsed
        self._current_call: Optional[StreamingFunctionCall] = None

        # JSON structure tracking
        self._brace_depth = 0
        self._bracket_depth = 0
        self._in_string = False
        self._escape_next = False

        # Position markers
        self._key_start = -1
        self._value_start = -1
        self._last_chunk_position = 0

        # Pending chunk for streaming
        self._pending_chunk = ""
        self._pending_param_name: Optional[str] = None

    @property
    def state(self) -> ParseState:
        """Current parser state"""
        return self._state

    @property
    def current_call(self) -> Optional[StreamingFunctionCall]:
        """Current function call being parsed"""
        return self._current_call

    async def parse_token(
        self,
        token: str,
    ) -> AsyncGenerator[ParseEvent, None]:
        """
        Parse a single token from LLM output.

        This is the main entry point. Feed tokens from LLM stream
        and receive parse events for real-time updates.

        Args:
            token: A piece of the LLM output (typically 1-10 characters)

        Yields:
            ParseEvent: Events for tool_start, param_start, param_chunk, etc.
        """
        self._buffer += token

        # Process each character
        for char in token:
            async for event in self._process_char(char):
                yield event
            self._position += 1

    async def _process_char(self, char: str) -> AsyncGenerator[ParseEvent, None]:
        """Process a single character and update state machine"""

        # Handle escape sequences in strings
        if self._escape_next:
            self._escape_next = False
            if self._state == ParseState.IN_STRING_VALUE:
                self._current_param_value_add(char)
            return

        if char == "\\" and self._in_string:
            self._escape_next = True
            return

        # Handle string boundaries
        if char == '"':
            if not self._in_string:
                self._in_string = True
                async for event in self._on_string_start():
                    yield event
            else:
                self._in_string = False
                async for event in self._on_string_end():
                    yield event
            return

        # Inside a string, accumulate the character
        if self._in_string:
            if self._state == ParseState.IN_STRING_VALUE:
                self._current_param_value_add(char)
            return

        # Handle JSON structure (outside strings)
        if char == "{":
            self._brace_depth += 1
            async for event in self._on_object_start():
                yield event

        elif char == "}":
            async for event in self._on_object_end():
                yield event
            self._brace_depth -= 1

        elif char == "[":
            self._bracket_depth += 1
            async for event in self._on_array_start():
                yield event

        elif char == "]":
            async for event in self._on_array_end():
                yield event
            self._bracket_depth -= 1

        elif char == ":":
            async for event in self._on_colon():
                yield event

        elif char == ",":
            async for event in self._on_comma():
                yield event

    def _current_param_value_add(self, char: str):
        """Add character to current parameter value"""
        if self._current_call and self._current_call.current_param_name:
            self._current_call.current_param_value += char

            # Track for potential streaming
            if (
                self._current_call.current_param_name
                in self._current_call.streaming_params
            ):
                self._pending_chunk += char

                # Check if we should emit a chunk
                if self._should_emit_chunk(char):
                    self._pending_param_name = self._current_call.current_param_name

    def _should_emit_chunk(self, last_char: str) -> bool:
        """Determine if we should emit a chunk now"""
        if not self._pending_chunk:
            return False

        if self.chunk_by_line and last_char == "\n":
            return True

        if len(self._pending_chunk) >= self.chunk_size:
            return True

        return False

    async def _on_string_start(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle string start"""
        if self._state == ParseState.IN_ARGUMENTS_OBJECT:
            # This is a parameter key
            self._state = ParseState.IN_PARAM_KEY
            self._key_start = self._position

    async def _on_string_end(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle string end"""
        if self._state == ParseState.IN_PARAM_KEY:
            # Extract the parameter name
            param_name = self._extract_string(self._key_start, self._position)
            if self._current_call:
                self._current_call.current_param_name = param_name
                self._key_start = -1
            self._state = ParseState.IN_ARGUMENTS_OBJECT

        elif self._state == ParseState.IN_STRING_VALUE:
            # Parameter value string complete
            if self._current_call and self._current_call.current_param_name:
                # Emit any pending chunk first
                if self._pending_chunk:
                    yield ParseEvent(
                        event_type="param_chunk",
                        call_id=self._current_call.call_id,
                        tool_name=self._current_call.tool_name,
                        param_name=self._current_call.current_param_name,
                        data=self._pending_chunk,
                        metadata={"is_final_chunk": False},
                    )
                    self._pending_chunk = ""

                # Emit param_end
                final_value = self._current_call.current_param_value
                yield ParseEvent(
                    event_type="param_end",
                    call_id=self._current_call.call_id,
                    tool_name=self._current_call.tool_name,
                    param_name=self._current_call.current_param_name,
                    data=final_value,
                    metadata={"length": len(final_value)},
                )

                # Store completed param
                self._current_call.completed_params[
                    self._current_call.current_param_name
                ] = final_value
                self._current_call.current_param_name = None
                self._current_call.current_param_value = ""

            self._state = ParseState.IN_ARGUMENTS_OBJECT

    async def _on_object_start(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle object start"""

        # Check if entering tool_calls array element
        if self._state == ParseState.IN_TOOL_CALLS_ARRAY and self._brace_depth == 1:
            self._state = ParseState.IN_TOOL_CALL_OBJECT

            # Create new function call
            call_id = f"call_{self._position}"
            self._current_call = StreamingFunctionCall(
                call_id=call_id, state=self._state
            )

        # Check if entering function object
        elif (
            self._state == ParseState.IN_TOOL_CALL_OBJECT
            and "function" in self._buffer[max(0, self._position - 20) : self._position]
        ):
            self._state = ParseState.IN_FUNCTION_OBJECT

        # Check if entering arguments object
        elif (
            self._state == ParseState.IN_FUNCTION_OBJECT
            and "arguments"
            in self._buffer[max(0, self._position - 20) : self._position]
        ):
            self._state = ParseState.IN_ARGUMENTS_OBJECT

            # Emit tool_start event
            if self._current_call:
                yield ParseEvent(
                    event_type="tool_start",
                    call_id=self._current_call.call_id,
                    tool_name=self._current_call.tool_name,
                    metadata={},
                )

    async def _on_object_end(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle object end"""

        if self._state == ParseState.IN_ARGUMENTS_OBJECT and self._brace_depth == 2:
            # Arguments object complete
            if self._current_call:
                yield ParseEvent(
                    event_type="tool_end",
                    call_id=self._current_call.call_id,
                    tool_name=self._current_call.tool_name,
                    data=self._current_call.completed_params,
                    metadata={},
                )
            self._state = ParseState.IN_FUNCTION_OBJECT

        elif self._state == ParseState.IN_TOOL_CALL_OBJECT and self._brace_depth == 0:
            # Tool call object complete
            self._state = ParseState.IN_TOOL_CALLS_ARRAY

    async def _on_array_start(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle array start"""
        # Check if this is the tool_calls array
        if "tool_calls" in self._buffer[max(0, self._position - 30) : self._position]:
            self._state = ParseState.IN_TOOL_CALLS_ARRAY

    async def _on_array_end(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle array end"""
        if self._state == ParseState.IN_TOOL_CALLS_ARRAY and self._bracket_depth == 0:
            self._state = ParseState.COMPLETE

    async def _on_colon(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle colon (key-value separator)"""
        if self._state == ParseState.IN_ARGUMENTS_OBJECT:
            # Value starts now
            self._value_start = self._position + 1

    async def _on_comma(self) -> AsyncGenerator[ParseEvent, None]:
        """Handle comma (element separator)"""
        # Could be used to detect end of non-string values
        pass

    def _extract_string(self, start: int, end: int) -> str:
        """
        Extract a string value from buffer.

        Handles escape sequences properly.
        """
        if start < 0 or end < start:
            return ""

        raw = self._buffer[start + 1 : end]  # Skip quotes

        # Process escape sequences
        try:
            return json.loads('"' + raw + '"')
        except json.JSONDecodeError:
            # Fallback: return as-is
            return raw

    def _is_streaming_param(self, param_name: str) -> bool:
        """Check if a parameter should be streamed"""
        if not self._current_call:
            return False

        tool_name = self._current_call.tool_name
        streaming_params = self.STREAMING_PARAMS_CONFIG.get(tool_name, set())
        return param_name in streaming_params

    def reset(self):
        """Reset parser state for a new parse session"""
        self._state = ParseState.IDLE
        self._buffer = ""
        self._position = 0
        self._current_call = None
        self._brace_depth = 0
        self._bracket_depth = 0
        self._in_string = False
        self._escape_next = False
        self._key_start = -1
        self._value_start = -1
        self._last_chunk_position = 0
        self._pending_chunk = ""
        self._pending_param_name = None

    def get_buffer_preview(self, length: int = 100) -> str:
        """Get a preview of the current buffer (for debugging)"""
        if len(self._buffer) <= length:
            return self._buffer
        return "..." + self._buffer[-length:]
