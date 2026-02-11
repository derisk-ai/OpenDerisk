import logging
import os
from typing import Any, Dict, List, Optional, Union

from derisk._private.pydantic import BaseModel, model_to_dict
from derisk.agent.core.llm_config import AgentLLMConfig
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.agent.util.llm.provider.claude_provider import ClaudeProvider
from derisk.agent.util.llm.provider.openai_provider import OpenAIProvider
from derisk.core import (
    LLMClient,
    ModelInferenceMetrics,
    ModelOutput,
    ModelRequest,
    ModelRequestContext,
)
from derisk.core.interface.output_parser import BaseOutputParser
from derisk.util.error_types import LLMChatError
from derisk.util.tracer import root_tracer

logger = logging.getLogger(__name__)


class AgentLLMOut(BaseModel):
    llm_name: Optional[str] = None
    llm_context: Optional[dict] = None
    in_messages: Optional[List[Dict]] = None
    thinking_content: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[Union[str, List[Dict[str, Any]]]] = None
    metrics: Optional[ModelInferenceMetrics] = None
    extra: Optional[Dict[str, Any]] = None
    ttft: int = 0

    def to_dict(self):
        dict_value = model_to_dict(self, exclude={"metrics"})
        if self.metrics:
            dict_value['metrics'] = self.metrics.to_dict()
        return dict_value


class AIWrapper:
    """AIWrapper for LLM."""

    cache_path_root: str = ".cache"
    extra_kwargs = {
        "cache_seed",
        "filter_func",
        "allow_format_str_template",
        "context",
        "llm_model",
        "llm_context",
        "memory",
        "conv_id",
        "sender",
        "stream_out",
        "incremental",
    }

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        llm_config: Optional[AgentLLMConfig] = None,
        output_parser: Optional[BaseOutputParser] = None,
    ):
        """Create an AIWrapper instance.

        Args:
            llm_client: Deprecated. The legacy LLM client.
            llm_config: The new AgentLLMConfig.
            output_parser: The output parser.
        """
        self.llm_echo = False
        self.model_cache_enable = False
        self._llm_client = llm_client
        self._llm_config = llm_config
        self._provider: Optional[LLMProvider] = None
        self._output_parser = output_parser or BaseOutputParser(is_stream_out=False)

        if self._llm_config:
            self._init_provider()

    def _init_provider(self):
        if not self._llm_config:
            return

        provider_name = self._llm_config.provider.lower()
        api_key = self._llm_config.api_key
        base_url = self._llm_config.base_url

        # If API key is not provided in config, try to get from env
        if not api_key:
             if provider_name == "openai":
                 api_key = os.getenv("OPENAI_API_KEY")
             elif provider_name == "claude":
                 api_key = os.getenv("ANTHROPIC_API_KEY")

        final_api_key: str = ""
        if api_key:
            final_api_key = api_key
        else:
             # Fallback or error handling if key is missing?
             # For now, we assume it might work without key (e.g. local models) or fail later
             # But providers expect string, so we ensure it is at least an empty string or raise error if critical
             # For OpenAI/Claude, key is usually required.
             if provider_name in ["openai", "claude"]:
                 raise ValueError(f"API Key is required for provider {provider_name}")
             final_api_key = "" # Default to empty string for other providers/local

        kwargs = self._llm_config.extra_kwargs.copy()

        if provider_name == "openai":
            self._provider = OpenAIProvider(api_key=final_api_key, base_url=base_url, **kwargs)
        elif provider_name == "claude":
            self._provider = ClaudeProvider(api_key=final_api_key, base_url=base_url, **kwargs)
        else:
            logger.warning(f"Unknown provider: {provider_name}, falling back to legacy LLMClient if available")

    def _construct_create_params(self, create_config: Dict, extra_kwargs: Dict) -> Dict:
        """Prime the create_config with additional_kwargs."""
        # Validate the config
        prompt = create_config.get("prompt")
        messages = create_config.get("messages")
        if prompt is None and messages is None:
            raise ValueError(
                "Either prompt or messages should be in create config but not both."
            )

        context = extra_kwargs.get("context")
        if context is None:
            # No need to instantiate if no context is provided.
            return create_config
        # Instantiate the prompt or messages
        extra_kwargs.get("allow_format_str_template", False)
        # Make a copy of the config
        params = create_config.copy()
        params["context"] = context

        return params

    def _separate_create_config(self, config):
        """Separate the config into create_config and extra_kwargs."""
        create_config = {k: v for k, v in config.items() if k not in self.extra_kwargs}
        extra_kwargs = {k: v for k, v in config.items() if k in self.extra_kwargs}
        return create_config, extra_kwargs

    async def create(self, **config):
        # merge the input config with the i-th config in the config list
        full_config = {**config}
        # separate the config into create_config and extra_kwargs
        create_config, extra_kwargs = self._separate_create_config(full_config)
        params = self._construct_create_params(create_config, extra_kwargs)

        # Use config from parameter or self._llm_config
        llm_model = extra_kwargs.get("llm_model")
        if self._llm_config:
             llm_model = self._llm_config.model

        # Ensure llm_model is a string
        final_llm_model: str = str(llm_model) if llm_model else "default"

        llm_context = extra_kwargs.get("llm_context")
        stream_out = extra_kwargs.get("stream_out", True)
        function_calling_context: Optional[Dict] = params.get("function_calling_context", None)

        # Prepare request payload/ModelRequest
        messages = params["messages"]

        # Resolve temperature
        temp_val = params.get("temperature")
        if temp_val is None and self._llm_config:
            temp_val = self._llm_config.temperature
        if temp_val is None:
            temp_val = 0.5
        temperature = float(temp_val)

        # Resolve max_new_tokens
        max_tokens_val = params.get("max_new_tokens")
        if max_tokens_val is None and self._llm_config:
            max_tokens_val = self._llm_config.max_new_tokens
        if max_tokens_val is None:
            max_tokens_val = 2048
        max_new_tokens = int(max_tokens_val)

        # Create ModelRequest
        request = ModelRequest.build_request(
             model=final_llm_model,
             messages=messages,
             stream=stream_out,
             echo=self.llm_echo,
             temperature=temperature,
             max_new_tokens=max_new_tokens,
             # Add other parameters from config if needed
        )
        if self._llm_config and self._llm_config.stop:
            request.stop = self._llm_config.stop

        if self._llm_config and self._llm_config.top_p:
            request.top_p = self._llm_config.top_p


        payload = {
            "model": llm_model,
            "prompt": params.get("prompt"),
            "messages": params["messages"],
            "temperature": temperature,
            "max_new_tokens": max_new_tokens,
            "echo": self.llm_echo,
            "trace_id": params.get("trace_id", None),
            "rpc_id": params.get("rpc_id", None),
            "incremental": params.get("incremental", False),
        }

        logger.info(f"Model Request:{llm_model}")

        span = root_tracer.start_span(
            "Agent.llm_client.no_streaming_call",
            metadata=self._get_span_metadata(payload),
        )
        payload["span_id"] = span.span_id
        payload["model_cache_enable"] = self.model_cache_enable
        extra = {}
        if llm_context:
            extra.update(llm_context)

        mist_keys = params.get("mist_keys")
        if mist_keys:
            # 存在独立配置的mist key
            extra["mist_keys"] = mist_keys

        # 调用模型的用户信息
        user = params.get("staff_no")
        if user:
            extra['user'] = user

        request.context = ModelRequestContext(extra=extra,
                                             trace_id=params.get("trace_id", None),
                                             rpc_id=params.get("rpc_id", None))

        if function_calling_context:
            # This logic needs to be adapted for ModelRequest if specific params are needed
            # For now, assuming tools are passed in messages or handled by caller adding to messages
            pass

        try:

            # Choose client: self._provider or self._llm_client (legacy)
            if self._provider:
                 client = self._provider
            elif self._llm_client:
                 client = self._llm_client
            else:
                 raise ValueError("No LLM provider or client configured.")

            if stream_out:
                # Type ignore: client can be LLMProvider (async gen) or LLMClient (async gen but typed as Coroutine in some contexts)
                # We verified both have generate_stream returning AsyncIterator
                async for output in client.generate_stream(request):  # type: ignore
                    model_output: ModelOutput = output
                    # 恢复模型调用异常，触发后续的模型兜底策略
                    if model_output.error_code != 0:
                        raise LLMChatError(model_output.text, original_exception=model_output.error_code)

                    thinking_text, content_text = model_output.gen_text_and_thinking()

                    think_blank = not thinking_text or len(thinking_text) <= 0
                    content_blank = not content_text or len(content_text) <= 0
                    if think_blank and content_blank and not model_output.tool_calls:
                        continue

                    yield AgentLLMOut(thinking_content=thinking_text, content=content_text,
                                      metrics=model_output.metrics, llm_name=llm_model, llm_context=llm_context,
                                      tool_calls=model_output.tool_calls, in_messages=params["messages"])
            else:
                model_output = await client.generate(request)
                # 恢复模型调用异常，触发后续的模型兜底策略
                if model_output.error_code != 0:
                    raise LLMChatError(model_output.text, original_exception=model_output.error_code)
                thinking_text, content_text = model_output.gen_text_and_thinking()

                yield AgentLLMOut(thinking_content=thinking_text, content=content_text, metrics=model_output.metrics,
                                  llm_name=llm_model, llm_context=llm_context, tool_calls=model_output.tool_calls,
                                  in_messages=params["messages"])
        except LLMChatError as e:
            logger.exception(f"LLM  Chat error, detail: {str(e)}")
            raise
        except Exception as e:
            logger.exception(f"Call LLMClient error, detail: {str(e)}")
            raise ValueError(f"LLM Request Exception!{str(e)}")
        finally:
            span.end()

    def _get_span_metadata(self, payload: Dict) -> Dict:
        metadata = {k: v for k, v in payload.items()}

        metadata["messages"] = list(
            map(lambda m: m if isinstance(m, dict) else m.dict(), metadata["messages"])
        )
        return metadata
