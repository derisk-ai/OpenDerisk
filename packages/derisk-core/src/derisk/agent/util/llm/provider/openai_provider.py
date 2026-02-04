import os
from typing import Dict, Any, AsyncIterator, List, Optional
import logging

from derisk.core.interface.llm import ModelRequest, ModelOutput, ModelMetadata, ModelInferenceMetrics
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.util.error_types import LLMChatError

logger = logging.getLogger(__name__)

class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, **kwargs)

    async def generate(self, request: ModelRequest) -> ModelOutput:
        """Generate a response from the model."""
        try:
            openai_messages = request.to_common_messages(support_system_role=True)
            response = await self.client.chat.completions.create(
                model=request.model,
                messages=openai_messages,
                temperature=request.temperature,
                max_tokens=request.max_new_tokens,
                # Add other parameters as needed
            )
            
            choice = response.choices[0]
            content = choice.message.content
            tool_calls = choice.message.tool_calls
            
            return ModelOutput(
                error_code=0,
                text=content,
                tool_calls=[tc.model_dump() for tc in tool_calls] if tool_calls else None,
                finish_reason=choice.finish_reason,
                usage=response.usage.model_dump() if response.usage else None
            )
        except Exception as e:
            logger.exception(f"OpenAI generate error: {e}")
            return ModelOutput(error_code=1, text=str(e))

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[ModelOutput]:
        """Generate a streaming response from the model."""
        try:
            openai_messages = request.to_common_messages(support_system_role=True)
            stream = await self.client.chat.completions.create(
                model=request.model,
                messages=openai_messages,
                temperature=request.temperature,
                max_tokens=request.max_new_tokens,
                stream=True,
                # Add other parameters as needed
            )
            
            async for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta
                content = delta.content
                tool_calls = delta.tool_calls
                
                yield ModelOutput(
                    error_code=0,
                    text=content,
                    tool_calls=[tc.model_dump() for tc in tool_calls] if tool_calls else None,
                    finish_reason=choice.finish_reason,
                    incremental=True
                )
        except Exception as e:
            logger.exception(f"OpenAI stream error: {e}")
            yield ModelOutput(error_code=1, text=str(e))

    async def models(self) -> List[ModelMetadata]:
        """List available models."""
        try:
            models = await self.client.models.list()
            return [ModelMetadata(model=m.id) for m in models.data]
        except Exception as e:
            logger.exception(f"OpenAI models error: {e}")
            return []

    async def count_token(self, model: str, prompt: str) -> int:
        """Count tokens in a prompt."""
        # Simple estimation or use tiktoken if available
        return len(prompt) // 4
