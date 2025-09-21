import logging
from typing import Dict, Optional, Any

from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict, Field
from derisk.core import LLMClient, ModelRequestContext, ModelOutput, ModelInferenceMetrics
from derisk.core.interface.output_parser import BaseOutputParser
from derisk.util.error_types import LLMChatError
from derisk.util.tracer import root_tracer

from ..llm.llm import _build_model_request

logger = logging.getLogger(__name__)

class AgentLLMOut(BaseModel):
    llm_name: Optional[str] = None
    thinking_content: Optional[str] = None
    content: Optional[str] = None
    tool_call: Optional[str] = None
    metrics: Optional[ModelInferenceMetrics] = None
    extra: Optional[Dict[str,Any]]= None

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
        llm_client: LLMClient,
        output_parser: Optional[BaseOutputParser] = None,
    ):
        """Create an AIWrapper instance."""
        self.llm_echo = False
        self.model_cache_enable = False
        self._llm_client = llm_client
        self._output_parser = output_parser or BaseOutputParser(is_stream_out=False)


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
        allow_format_str_template = extra_kwargs.get("allow_format_str_template", False)
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
        llm_model = extra_kwargs.get("llm_model")
        llm_context = extra_kwargs.get("llm_context")
        stream_out = extra_kwargs.get("stream_out", True)

        payload = {
            "model": llm_model,
            "prompt": params.get("prompt"),
            "messages": params["messages"],
            "temperature": float(params.get("temperature")),
            "max_new_tokens": int(params.get("max_new_tokens")),
            "echo": self.llm_echo,
            "trace_id": params.get("trace_id", None),
            "rpc_id": params.get("rpc_id", None),
            "incremental": params.get("incremental", False),
        }
        # messages_prompt = '\n'.join(item['content'] for item in payload['messages'])
        # await self._llm_client.count_token(llm_model, messages_prompt)
        logger.info(f"Model Request:{llm_model}")
        # logger.info(f"Request: \n{payload}")
        span = root_tracer.start_span(
            "Agent.llm_client.no_streaming_call",
            metadata=self._get_span_metadata(payload),
        )
        payload["span_id"] = span.span_id
        payload["model_cache_enable"] = self.model_cache_enable
        extra = {}
        if llm_context:
            extra.update(llm_context)
        payload["context"] = ModelRequestContext(extra=extra,
                                                     trace_id=params.get("trace_id", None),
                                                     rpc_id=params.get("rpc_id", None))
        try:
            model_request = _build_model_request(payload)
            from datetime import datetime

            if stream_out:
                async for output in self._llm_client.generate_stream(model_request.copy()):  # type: ignore
                    model_output: ModelOutput = output
                    # 恢复模型调用异常，触发后续的模型兜底策略
                    if model_output.error_code != 0:
                        raise LLMChatError(model_output.text)

                    thinking_text, content_text = model_output.gen_text_and_thinking()

                    think_blank = not thinking_text or len(thinking_text) <= 0
                    content_blank = not content_text or len(content_text) <= 0
                    if think_blank and content_blank:
                        continue

                    yield AgentLLMOut(thinking_content=thinking_text, content=content_text,
                                      metrics=model_output.metrics, llm_name=llm_model)
            else:
                model_output = await self._llm_client.generate(model_request.copy())  # type: ignore
                # 恢复模型调用异常，触发后续的模型兜底策略
                if model_output.error_code != 0:
                    raise LLMChatError(model_output.text)
                thinking_text, content_text = model_output.gen_text_and_thinking()

                yield AgentLLMOut(thinking_content=thinking_text, content=content_text, metrics=model_output.metrics)
        except LLMChatError:
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
