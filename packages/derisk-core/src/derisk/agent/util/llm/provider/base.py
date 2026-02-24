from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncIterator, List, Optional
from derisk.core.interface.llm import ModelRequest, ModelOutput, ModelMetadata

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelOutput:
        """Generate a response from the model."""
        pass

    @abstractmethod
    def generate_stream(self, request: ModelRequest) -> AsyncIterator[ModelOutput]:
        """Generate a streaming response from the model."""
        pass

    @abstractmethod
    async def models(self) -> List[ModelMetadata]:
        """List available models."""
        pass

    @abstractmethod
    async def count_token(self, model: str, prompt: str) -> int:
        """Count tokens in a prompt."""
        pass
