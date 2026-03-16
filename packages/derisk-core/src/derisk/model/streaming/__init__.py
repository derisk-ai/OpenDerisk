"""
Streaming Function Call Module

This module provides incremental parsing and streaming capabilities for
LLM function calls, enabling real-time parameter visualization.
"""

from .incremental_parser import (
    IncrementalFunctionCallParser,
    ParseState,
    StreamingFunctionCall,
    ParseEvent,
)
from .streaming_processor import StreamingFunctionCallProcessor
from .chunk_strategies import (
    IChunkStrategy,
    LineBasedChunkStrategy,
    SemanticChunkStrategy,
    AdaptiveChunkStrategy,
    ChunkStrategy,
    ChunkMetadata,
    ParamChunk,
)
from .config_loader import StreamingConfigLoader

__all__ = [
    # Parser
    "IncrementalFunctionCallParser",
    "ParseState",
    "StreamingFunctionCall",
    "ParseEvent",
    # Processor
    "StreamingFunctionCallProcessor",
    # Chunk Strategies
    "IChunkStrategy",
    "LineBasedChunkStrategy",
    "SemanticChunkStrategy",
    "AdaptiveChunkStrategy",
    "ChunkStrategy",
    "ChunkMetadata",
    "ParamChunk",
    # Config
    "StreamingConfigLoader",
]
