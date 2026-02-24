import os
from typing import Dict, Any, AsyncIterator, List, Optional
import logging

from derisk.core.interface.llm import ModelRequest, ModelOutput, ModelMetadata, ModelInferenceMetrics
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.util.error_types import LLMChatError

logger = logging.getLogger(__name__)

class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None, **kwargs):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, **kwargs)
        self._configured_model = model

    async def generate(self, request: ModelRequest) -> ModelOutput:
        """Generate a response from the model."""
        try:
            openai_messages = request.to_common_messages(support_system_role=True)
            params = {
                "model": request.model,
                "messages": openai_messages,
                "temperature": request.temperature,
            }
            if request.max_new_tokens and request.max_new_tokens > 0:
                params["max_tokens"] = request.max_new_tokens
            
            response = await self.client.chat.completions.create(**params)
            
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
            params = {
                "model": request.model,
                "messages": openai_messages,
                "temperature": request.temperature,
                "stream": True,
            }
            if request.max_new_tokens and request.max_new_tokens > 0:
                params["max_tokens"] = request.max_new_tokens
            
            stream = await self.client.chat.completions.create(**params)
            
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                content = delta.content if delta else None
                tool_calls = delta.tool_calls if delta else None
                
                yield ModelOutput(
                    error_code=0,
                    text=content or "",
                    tool_calls=[tc.model_dump() for tc in tool_calls] if tool_calls else None,
                    finish_reason=choice.finish_reason,
                    incremental=True
                )
        except Exception as e:
            logger.exception(f"OpenAI stream error: {e}")
            yield ModelOutput(error_code=1, text=str(e))

    async def models(self) -> List[ModelMetadata]:
        """List available models."""
        result = []
        if self._configured_model:
            result.append(ModelMetadata(model=self._configured_model, context_length=128000))
        try:
            models = await self.client.models.list()
            remote_models = [ModelMetadata(model=m.id) for m in models.data]
            existing_ids = {m.model for m in result}
            for m in remote_models:
                if m.model not in existing_ids:
                    result.append(m)
        except Exception as e:
            logger.warning(f"OpenAI models API error: {e}, using configured model only")
        return result

    async def count_token(self, model: str, prompt: str) -> int:
        """Count tokens in a prompt."""
        # Simple estimation or use tiktoken if available
        return len(prompt) // 4
