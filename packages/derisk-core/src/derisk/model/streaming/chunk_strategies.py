"""
Chunk Strategies for Streaming Parameters

Provides different strategies for chunking large parameter values
into smaller pieces for incremental transmission.

Design Pattern: Strategy Pattern
- Each strategy is encapsulated in a class
- Strategies are interchangeable
- Easy to add new strategies
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Type


class ChunkStrategy(Enum):
    """Available chunk strategies"""

    FIXED_SIZE = "fixed_size"
    LINE_BASED = "line_based"
    SEMANTIC = "semantic"
    ADAPTIVE = "adaptive"


@dataclass
class ChunkMetadata:
    """Metadata for a parameter chunk"""

    chunk_index: int
    total_chunks: Optional[int] = None
    bytes_in_chunk: int = 0
    bytes_total: Optional[int] = None
    lines_in_chunk: int = 0
    lines_total: Optional[int] = None
    is_final: bool = False


@dataclass
class ParamChunk:
    """A single chunk of a streaming parameter"""

    call_id: str
    tool_name: str
    param_name: str
    chunk_data: str
    metadata: ChunkMetadata


class IChunkStrategy(ABC):
    """
    Interface for chunk strategies.

    Implementations define how to split content into chunks.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name"""
        pass

    @abstractmethod
    async def chunk(
        self, content: str, options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate chunks from content.

        Args:
            content: The content to chunk
            options: Optional strategy-specific options

        Yields:
            Chunks of content
        """
        pass

    @abstractmethod
    def estimate_chunks(self, content: str) -> Optional[int]:
        """
        Estimate the number of chunks.

        Args:
            content: The content to chunk

        Returns:
            Estimated chunk count, or None if cannot estimate
        """
        pass


class FixedSizeChunkStrategy(IChunkStrategy):
    """
    Fixed-size chunking strategy.

    Splits content into chunks of a fixed byte/character size.
    Simple but may split in the middle of lines/words.
    """

    def __init__(self, chunk_size: int = 1024):
        """
        Initialize with chunk size.

        Args:
            chunk_size: Size of each chunk in characters
        """
        self.chunk_size = chunk_size

    @property
    def name(self) -> str:
        return "fixed_size"

    async def chunk(
        self, content: str, options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Generate fixed-size chunks"""
        for i in range(0, len(content), self.chunk_size):
            yield content[i : i + self.chunk_size]

    def estimate_chunks(self, content: str) -> Optional[int]:
        """Estimate chunk count"""
        if not content:
            return 0
        return (len(content) + self.chunk_size - 1) // self.chunk_size


class LineBasedChunkStrategy(IChunkStrategy):
    """
    Line-based chunking strategy.

    Splits content at line boundaries, grouping multiple lines
    per chunk. Ideal for code content.

    This is the recommended strategy for code parameters.
    """

    def __init__(self, lines_per_chunk: int = 50):
        """
        Initialize with lines per chunk.

        Args:
            lines_per_chunk: Number of lines per chunk
        """
        self.lines_per_chunk = lines_per_chunk

    @property
    def name(self) -> str:
        return "line_based"

    async def chunk(
        self, content: str, options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Generate line-based chunks"""
        lines = content.split("\n")

        for i in range(0, len(lines), self.lines_per_chunk):
            chunk_lines = lines[i : i + self.lines_per_chunk]
            chunk = "\n".join(chunk_lines)

            # Add trailing newline if not the last chunk
            if i + self.lines_per_chunk < len(lines):
                chunk += "\n"

            yield chunk

    def estimate_chunks(self, content: str) -> Optional[int]:
        """Estimate chunk count based on lines"""
        if not content:
            return 0
        lines = content.split("\n")
        return (len(lines) + self.lines_per_chunk - 1) // self.lines_per_chunk


class SemanticChunkStrategy(IChunkStrategy):
    """
    Semantic chunking strategy.

    Splits content at semantic boundaries (functions, classes, etc.)
    for code content. Provides more meaningful chunks.

    Best for large code files where you want each chunk to be
    a complete semantic unit.
    """

    # Patterns for semantic boundaries in various languages
    BOUNDARY_PATTERNS = {
        "python": [
            r"^\s*(def |class |async def )",
            r"^\s*@\w+",  # Decorators
            r"^if __name__",
        ],
        "javascript": [
            r"^\s*(function |const |let |var |async function |class )",
            r"^\s*export\s+(function|const|class)",
            r"^\s*@\w+",  # Decorators
        ],
        "typescript": [
            r"^\s*(function |const |let |var |async function |class |interface |type )",
            r"^\s*export\s+(function|const|class|interface|type)",
            r"^\s*@\w+",
        ],
        "default": [
            r"^\s*(function |def |class |const |let |var |async )",
        ],
    }

    def __init__(self, min_chunk_lines: int = 10):
        """
        Initialize with minimum chunk size.

        Args:
            min_chunk_lines: Minimum lines before allowing a split
        """
        self.min_chunk_lines = min_chunk_lines

    @property
    def name(self) -> str:
        return "semantic"

    async def chunk(
        self, content: str, options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Generate semantic chunks"""
        language = options.get("language", "default") if options else "default"
        patterns = self.BOUNDARY_PATTERNS.get(
            language, self.BOUNDARY_PATTERNS["default"]
        )

        lines = content.split("\n")
        current_chunk_lines: List[str] = []
        current_line_count = 0

        for line in lines:
            # Check if this line is a semantic boundary
            is_boundary = any(re.match(pattern, line) for pattern in patterns)

            # Start a new chunk if we hit a boundary and have enough lines
            if (
                is_boundary
                and current_line_count >= self.min_chunk_lines
                and current_chunk_lines
            ):
                yield "\n".join(current_chunk_lines) + "\n"
                current_chunk_lines = []
                current_line_count = 0

            current_chunk_lines.append(line)
            current_line_count += 1

        # Yield remaining lines
        if current_chunk_lines:
            yield "\n".join(current_chunk_lines)

    def estimate_chunks(self, content: str) -> Optional[int]:
        """Semantic chunks are hard to estimate"""
        return None


class AdaptiveChunkStrategy(IChunkStrategy):
    """
    Adaptive chunking strategy.

    Automatically selects the best strategy based on content type
    and characteristics. This is the recommended default strategy.
    """

    def __init__(
        self,
        default_chunk_size: int = 1024,
        default_lines_per_chunk: int = 50,
    ):
        """
        Initialize adaptive strategy.

        Args:
            default_chunk_size: Default chunk size for fixed strategy
            default_lines_per_chunk: Default lines for line-based strategy
        """
        self.default_chunk_size = default_chunk_size
        self.default_lines_per_chunk = default_lines_per_chunk

        # Internal strategies
        self._fixed_strategy = FixedSizeChunkStrategy(default_chunk_size)
        self._line_strategy = LineBasedChunkStrategy(default_lines_per_chunk)
        self._semantic_strategy = SemanticChunkStrategy()

    @property
    def name(self) -> str:
        return "adaptive"

    async def chunk(
        self, content: str, options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate chunks using the best strategy for the content.

        Automatically detects content type and selects appropriate strategy.
        """
        content_type = self._detect_content_type(content)

        if content_type == "code":
            # Use line-based for code
            async for chunk in self._line_strategy.chunk(content, options):
                yield chunk
        elif content_type == "data":
            # Use fixed-size for structured data
            async for chunk in self._fixed_strategy.chunk(content, options):
                yield chunk
        else:
            # Use line-based for text
            async for chunk in self._line_strategy.chunk(content, options):
                yield chunk

    def estimate_chunks(self, content: str) -> Optional[int]:
        """Estimate using the selected strategy"""
        content_type = self._detect_content_type(content)

        if content_type == "code":
            return self._line_strategy.estimate_chunks(content)
        elif content_type == "data":
            return self._fixed_strategy.estimate_chunks(content)
        else:
            return self._line_strategy.estimate_chunks(content)

    def _detect_content_type(self, content: str) -> str:
        """
        Detect content type from content.

        Returns:
            'code', 'data', or 'text'
        """
        # Code indicators
        code_patterns = [
            r"\bdef\s+\w+\s*\(",  # Python functions
            r"\bfunction\s+\w+\s*\(",  # JS functions
            r"\bclass\s+\w+",  # Class definitions
            r"\bimport\s+",  # Import statements
            r"\bfrom\s+\w+\s+import",  # Python imports
            r"\bconst\s+\w+\s*=",  # JS const
            r"\blet\s+\w+\s*=",  # JS let
            r"\bexport\s+(default\s+)?",  # JS exports
            r"\basync\s+(function|def)",  # Async functions
            r"=>\s*\{",  # Arrow functions
            r'\{\s*\n\s*".+":\s*"',  # Could be JSON, check further
        ]

        code_matches = sum(
            1 for pattern in code_patterns if re.search(pattern, content)
        )

        # Data indicators (JSON, YAML, etc.)
        data_patterns = [
            r"^\s*\{.*\}\s*$",  # JSON object
            r"^\s*\[.*\]\s*$",  # JSON array
            r"^\s*-+\s*$",  # YAML document start
            r"^\w+:\s+",  # YAML key-value
        ]

        data_matches = sum(
            1 for pattern in data_patterns if re.search(pattern, content, re.MULTILINE)
        )

        if code_matches > 2:
            return "code"
        elif data_matches > 1:
            return "data"
        else:
            return "text"


# Strategy registry for dynamic lookup
STRATEGY_REGISTRY: Dict[ChunkStrategy, Type[IChunkStrategy]] = {
    ChunkStrategy.FIXED_SIZE: FixedSizeChunkStrategy,
    ChunkStrategy.LINE_BASED: LineBasedChunkStrategy,
    ChunkStrategy.SEMANTIC: SemanticChunkStrategy,
    ChunkStrategy.ADAPTIVE: AdaptiveChunkStrategy,
}


def get_strategy(strategy: ChunkStrategy, **kwargs) -> IChunkStrategy:
    """
    Get a chunk strategy instance.

    Args:
        strategy: The strategy type
        **kwargs: Arguments to pass to the strategy constructor

    Returns:
        Strategy instance
    """
    strategy_class = STRATEGY_REGISTRY.get(strategy, AdaptiveChunkStrategy)
    return strategy_class(**kwargs)
