import os
import json
import logging
from typing import Dict, Any, AsyncIterator, List, Optional

from derisk.core.interface.llm import (
    ModelRequest,
    ModelOutput,
    ModelMetadata,
    ModelInferenceMetrics,
)
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.agent.util.llm.provider.tool_call_compat import (
    is_model_without_native_fc,
    inject_tool_prompt_to_messages,
    extract_tool_calls_from_content,
)
from derisk.util.error_types import LLMChatError
from derisk.agent.util.llm.provider.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


@ProviderRegistry.register("openai", env_key="OPENAI_API_KEY")
class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ):
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

            use_compat_fc = False
            if request.tools:
                if is_model_without_native_fc(request.model):
                    use_compat_fc = True
                    messages = params["messages"]
                    params["messages"] = inject_tool_prompt_to_messages(messages, request.tools)
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"OpenAIProvider: Using compat tool call mode for model {request.model}, tools={tool_names}")
                else:
                    params["tools"] = request.tools
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"OpenAIProvider: tools count={len(request.tools)}, names={tool_names}")
            if request.tool_choice and not use_compat_fc:
                params["tool_choice"] = request.tool_choice
                logger.info(f"OpenAIProvider: tool_choice={request.tool_choice}")
            if request.parallel_tool_calls is not None and not use_compat_fc:
                params["parallel_tool_calls"] = request.parallel_tool_calls

            response = await self.client.chat.completions.create(**params)

            choice = response.choices[0]
            content = choice.message.content
            tool_calls = choice.message.tool_calls

            if use_compat_fc and not tool_calls and content:
                compat_tool_calls, cleaned_content = extract_tool_calls_from_content(content)
                if compat_tool_calls:
                    tool_calls = compat_tool_calls
                    content = cleaned_content
                    tool_names = [tc.get("function", {}).get("name", "unknown") for tc in compat_tool_calls]
                    logger.info(f"OpenAIProvider: Extracted tool_calls from compat mode: {tool_names}")

            tc_output = None
            if tool_calls:
                if hasattr(tool_calls[0], 'model_dump'):
                    tc_output = [tc.model_dump() for tc in tool_calls]
                else:
                    tc_output = list(tool_calls)
                tc_summary = [{"id": tc.get("id"), "name": tc.get("function", {}).get("name")} for tc in tc_output]
                logger.info(f"OpenAIProvider: tool_calls output={json.dumps(tc_summary)}")
            else:
                logger.info(f"OpenAIProvider: no tool_calls in response, finish_reason={choice.finish_reason}")

            return ModelOutput(
                error_code=0,
                text=content,
                tool_calls=tc_output,
                finish_reason=choice.finish_reason,
                usage=response.usage.model_dump() if response.usage else None,
            )
        except Exception as e:
            logger.exception(f"OpenAI generate error: {e}")
            return ModelOutput(error_code=1, text=str(e))

    async def generate_stream(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelOutput]:
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

            use_compat_fc = False
            if request.tools:
                if is_model_without_native_fc(request.model):
                    use_compat_fc = True
                    messages = params["messages"]
                    params["messages"] = inject_tool_prompt_to_messages(messages, request.tools)
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"OpenAIProvider stream: Using compat tool call mode for model {request.model}, tools={tool_names}")
                else:
                    params["tools"] = request.tools
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"OpenAIProvider stream: tools count={len(request.tools)}, names={tool_names}")
            if request.tool_choice and not use_compat_fc:
                params["tool_choice"] = request.tool_choice
                logger.info(f"OpenAIProvider stream: tool_choice={request.tool_choice}")
            if request.parallel_tool_calls is not None and not use_compat_fc:
                params["parallel_tool_calls"] = request.parallel_tool_calls

            stream = await self.client.chat.completions.create(**params)

            accumulated_tool_calls = {}
            accumulated_content = ""

            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                content = delta.content if delta else None
                tool_calls = delta.tool_calls if delta else None

                if content:
                    accumulated_content += content

                if tool_calls:
                    for tc in tool_calls:
                        idx = tc.index if hasattr(tc, "index") else 0
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": tc.id if hasattr(tc, "id") else None,
                                "type": tc.type if hasattr(tc, "type") else "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if hasattr(tc, "id") and tc.id:
                            accumulated_tool_calls[idx]["id"] = tc.id
                        if hasattr(tc, "type") and tc.type:
                            accumulated_tool_calls[idx]["type"] = tc.type
                        if hasattr(tc, "function") and tc.function:
                            if tc.function.name:
                                accumulated_tool_calls[idx]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                accumulated_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

                output_tool_calls = (
                    list(accumulated_tool_calls.values())
                    if accumulated_tool_calls
                    else None
                )

                if choice.finish_reason:
                    logger.info(f"OpenAIProvider stream: finish_reason={choice.finish_reason}")
                    if use_compat_fc and not output_tool_calls and accumulated_content:
                        compat_tool_calls, cleaned_content = extract_tool_calls_from_content(accumulated_content)
                        if compat_tool_calls:
                            output_tool_calls = compat_tool_calls
                            content = cleaned_content
                            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in compat_tool_calls]
                            logger.info(f"OpenAIProvider stream: Extracted tool_calls from compat mode: {tool_names}")
                    
                    if output_tool_calls:
                        tool_names = [tc.get("function", {}).get("name", "unknown") for tc in output_tool_calls]
                        logger.info(f"OpenAIProvider stream: tool_calls output count={len(output_tool_calls)}, names={tool_names}")

                yield ModelOutput(
                    error_code=0,
                    text=content or "",
                    tool_calls=output_tool_calls,
                    finish_reason=choice.finish_reason,
                    incremental=True,
                )
        except Exception as e:
            logger.exception(f"OpenAI stream error: {e}")
            yield ModelOutput(error_code=1, text=str(e))

    async def models(self) -> List[ModelMetadata]:
        """List available models."""
        result = []
        if self._configured_model:
            result.append(
                ModelMetadata(model=self._configured_model, context_length=128000)
            )
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
