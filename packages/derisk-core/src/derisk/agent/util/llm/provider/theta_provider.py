import os
import json
import logging
import random
from typing import Dict, Any, AsyncIterator, List, Optional

from derisk.core.interface.llm import (
    ModelRequest,
    ModelOutput,
    ModelMetadata,
)
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.agent.util.llm.provider.tool_call_compat import (
    is_model_without_native_fc,
    inject_tool_prompt_to_messages,
    extract_tool_calls_from_content,
)
from derisk.util.error_types import LLMChatError
from derisk.agent.util.llm.provider.provider_registry import ProviderRegistry
import cachetools
from cachetools import cached

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "theta/QwQ-32B"
_DEFAULT_API_BASE = "https://xxxx/v1"


@cached(cachetools.TTLCache(maxsize=100, ttl=1800))
def llm_quota(mist_key: str) -> dict[str, int]:
    from derisk_serve.config.service.service import get_config_by_key
    config = get_config_by_key("theta_quota_" + mist_key)
    return json.loads(config) if config else {}


async def select_key(model_name: str, mist_keys: list[str]) -> Optional[str]:
    if not mist_keys:
        return None
    if len(mist_keys) == 1:
        return mist_keys[0]
    
    quotas = [(llm_quota(mist_key)).get(model_name, 60) for mist_key in mist_keys]
    mist_key = random.choices(mist_keys, weights=quotas)[0]
    logger.info(f"[DEBUG][LLM]select_key: model[{model_name}], selected[{mist_key}], from[{mist_keys}]:[{quotas}]")
    return mist_key


@ProviderRegistry.register("theta", env_key="THETA_API_KEY")
class ThetaProvider(LLMProvider):
    """Theta LLM provider with tool call compatibility support."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ):
        from openai import AsyncOpenAI

        real_key = api_key or os.getenv("THETA_API_KEY")
        self._configured_model = model or _DEFAULT_MODEL
        self._api_keys = real_key.split(",") if real_key else []
        
        self.client = AsyncOpenAI(
            api_key=self._api_keys[0] if self._api_keys else "",
            base_url=base_url or os.getenv("THETA_API_BASE") or _DEFAULT_API_BASE,
            **kwargs
        )

    def _get_model_name(self, model: Optional[str]) -> str:
        model_name = (model or self._configured_model).strip()
        return model_name.split("/", 1)[1] if model_name.startswith("theta/") else model_name

    async def _resolve_api_key(self, model_name: str) -> str:
        from derisk.agent.util.llm.llm_util import is_mist_api_key, api_key_mist_pwd
        use_key = await select_key(model_name, self._api_keys)
        if is_mist_api_key(use_key):
            use_key = api_key_mist_pwd(use_key)
        if not use_key:
            raise ValueError("Missing API key for Theta!")
        return use_key

    async def generate(self, request: ModelRequest) -> ModelOutput:
        try:
            model_name = self._get_model_name(request.model)
            api_key = await self._resolve_api_key(model_name)
            
            openai_messages = request.to_common_messages(support_system_role=True)
            params = {
                "model": model_name,
                "messages": openai_messages,
                "temperature": request.temperature,
            }
            if request.max_new_tokens and request.max_new_tokens > 0:
                params["max_tokens"] = max(32768, request.max_new_tokens)
            else:
                params["max_tokens"] = 32768

            use_compat_fc = False
            if request.tools:
                if is_model_without_native_fc(model_name):
                    use_compat_fc = True
                    messages = params["messages"]
                    params["messages"] = inject_tool_prompt_to_messages(messages, request.tools)
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"ThetaProvider: Using compat tool call mode for model {model_name}, tools={tool_names}")
                else:
                    params["tools"] = request.tools
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"ThetaProvider: tools count={len(request.tools)}, names={tool_names}")
            if request.tool_choice and not use_compat_fc:
                params["tool_choice"] = request.tool_choice
            if request.parallel_tool_calls is not None and not use_compat_fc:
                params["parallel_tool_calls"] = request.parallel_tool_calls

            self.client.api_key = api_key
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
                    logger.info(f"ThetaProvider: Extracted tool_calls from compat mode: {tool_names}")

            if tool_calls:
                if hasattr(tool_calls[0], 'model_dump'):
                    tc_output = [tc.model_dump() for tc in tool_calls]
                else:
                    tc_output = list(tool_calls)
                tc_summary = [{"id": tc.get("id"), "name": tc.get("function", {}).get("name")} for tc in tc_output]
                logger.info(f"ThetaProvider: tool_calls output={json.dumps(tc_summary)}")
            else:
                logger.info(f"ThetaProvider: no tool_calls in response, finish_reason={choice.finish_reason}")

            return ModelOutput(
                error_code=0,
                text=content,
                tool_calls=tc_output if tool_calls else None,
                finish_reason=choice.finish_reason,
                usage=response.usage.model_dump() if response.usage else None,
            )
        except Exception as e:
            logger.exception(f"Theta generate error: {e}")
            return ModelOutput(error_code=1, text=str(e))

    async def generate_stream(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelOutput]:
        try:
            model_name = self._get_model_name(request.model)
            api_key = await self._resolve_api_key(model_name)
            
            openai_messages = request.to_common_messages(support_system_role=True)
            params = {
                "model": model_name,
                "messages": openai_messages,
                "temperature": request.temperature,
                "stream": True,
            }
            if request.max_new_tokens and request.max_new_tokens > 0:
                params["max_tokens"] = max(32768, request.max_new_tokens)
            else:
                params["max_tokens"] = 32768

            use_compat_fc = False
            if request.tools:
                if is_model_without_native_fc(model_name):
                    use_compat_fc = True
                    messages = params["messages"]
                    params["messages"] = inject_tool_prompt_to_messages(messages, request.tools)
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"ThetaProvider stream: Using compat tool call mode for model {model_name}, tools={tool_names}")
                else:
                    params["tools"] = request.tools
                    tool_names = [t.get("function", {}).get("name") for t in request.tools]
                    logger.info(f"ThetaProvider stream: tools count={len(request.tools)}, names={tool_names}")
            if request.tool_choice and not use_compat_fc:
                params["tool_choice"] = request.tool_choice
            if request.parallel_tool_calls is not None and not use_compat_fc:
                params["parallel_tool_calls"] = request.parallel_tool_calls

            self.client.api_key = api_key
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
                    logger.info(f"ThetaProvider stream: finish_reason={choice.finish_reason}")
                    if use_compat_fc and not output_tool_calls and accumulated_content:
                        compat_tool_calls, cleaned_content = extract_tool_calls_from_content(accumulated_content)
                        if compat_tool_calls:
                            output_tool_calls = compat_tool_calls
                            content = cleaned_content
                            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in compat_tool_calls]
                            logger.info(f"ThetaProvider stream: Extracted tool_calls from compat mode: {tool_names}")
                    
                    if output_tool_calls:
                        tool_names = [tc.get("function", {}).get("name", "unknown") for tc in output_tool_calls]
                        logger.info(f"ThetaProvider stream: tool_calls output count={len(output_tool_calls)}, names={tool_names}")

                yield ModelOutput(
                    error_code=0,
                    text=content or "",
                    tool_calls=output_tool_calls,
                    finish_reason=choice.finish_reason,
                    incremental=True,
                )
        except Exception as e:
            logger.exception(f"Theta stream error: {e}")
            yield ModelOutput(error_code=1, text=str(e))

    async def models(self) -> List[ModelMetadata]:
        result = []
        if self._configured_model:
            result.append(
                ModelMetadata(model=self._configured_model, context_length=128000)
            )
        return result

    async def count_token(self, model: str, prompt: str) -> int:
        return len(prompt) // 4