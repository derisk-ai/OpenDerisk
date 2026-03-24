import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

from derisk._private.pydantic import BaseModel, model_to_dict
from derisk.agent.core.llm_config import AgentLLMConfig
from derisk.agent.util.llm.provider.base import LLMProvider
from derisk.agent.util.llm.provider.provider_registry import ProviderRegistry
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


def _get_api_key_from_secrets(provider_name: str, base_url: Optional[str] = None) -> Optional[str]:
    """从加密存储的 secrets 中获取 API Key

    优先级：
    1. 先尝试获取特定于 provider 的 key (如 openai_api_key, dashscope_api_key)
    2. 根据 base_url 判断是否使用特定平台的 key
    3. 如果没有，尝试通用的 llm_api_key

    Args:
        provider_name: Provider 名称 (如 openai, alibaba, anthropic)
        base_url: API base URL，用于判断实际使用的平台

    Returns:
        API Key 或 None
    """
    try:
        from derisk_core.config.encryption import get_secret

        provider_name_lower = provider_name.lower()

        # 首先尝试获取 provider 特定的 key
        provider_specific_keys = {
            "openai": ["openai_api_key"],
            "alibaba": ["dashscope_api_key", "alibaba_api_key"],
            "anthropic": ["anthropic_api_key", "claude_api_key"],
            "dashscope": ["dashscope_api_key"],
            "claude": ["anthropic_api_key", "claude_api_key"],
        }

        # 根据 base_url 判断实际使用的平台（处理 OpenAI 兼容模式）
        base_url_lower = base_url.lower() if base_url else ""
        if "dashscope" in base_url_lower or "aliyun" in base_url_lower:
            # 阿里云 DashScope 使用 OpenAI 兼容 API，但实际 key 是 dashscope_api_key
            keys_to_try = ["dashscope_api_key", "alibaba_api_key", "llm_api_key"]
        elif "anthropic" in base_url_lower or "claude" in base_url_lower:
            keys_to_try = ["anthropic_api_key", "claude_api_key", "llm_api_key"]
        elif "openai" in base_url_lower or "openai.com" in base_url_lower:
            keys_to_try = ["openai_api_key", "llm_api_key"]
        else:
            # 使用默认的 provider 映射
            keys_to_try = provider_specific_keys.get(provider_name_lower, [])
            if provider_name_lower == "openai":
                # openai provider 可能是 OpenAI 也可能是其他 OpenAI 兼容服务
                # 尝试所有可能的 key
                keys_to_try = ["openai_api_key", "dashscope_api_key", "alibaba_api_key", "anthropic_api_key"]

        # 最后添加通用的 llm_api_key
        if "llm_api_key" not in keys_to_try:
            keys_to_try.append("llm_api_key")

        logger.debug(f"Looking for API key: provider={provider_name}, base_url={base_url}, keys_to_try={keys_to_try}")

        for key_name in keys_to_try:
            secret_value = get_secret(key_name)
            if secret_value:
                # 记录找到的 key（只显示部分信息）
                key_preview = f"{secret_value[:8]}...{secret_value[-4:]}" if len(secret_value) > 12 else "***"
                logger.info(
                    f"Found API key from secrets: key_name={key_name}, provider={provider_name}, preview={key_preview}, length={len(secret_value)}")
                return secret_value

        logger.debug(f"No API key found in secrets for provider={provider_name}")
        return None
    except Exception as e:
        logger.warning(f"Failed to get API key from secrets: {e}")
        return None


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
            dict_value["metrics"] = self.metrics.to_dict()
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
        self._provider_cache: Dict[str, LLMProvider] = {}

        if self._llm_config:
            self._init_provider()

    def _init_provider(self):
        if not self._llm_config:
            return

        provider_name = self._llm_config.provider.lower()
        api_key = self._llm_config.api_key
        base_url = self._llm_config.base_url

        # 检查 api_key 是否是占位符（未解析的配置引用或默认值）
        def _is_placeholder_key(key: Optional[str]) -> bool:
            if not key:
                return True
            # 检查是否是 ${env:xxx} 或 ${secrets.xxx} 格式
            if key.startswith("${"):
                return True
            # 检查是否是常见的占位符值
            placeholder_patterns = ["sk-...", "sk-xxxx", "your_api_key", "xxx", "placeholder"]
            key_lower = key.lower()
            if any(pattern in key_lower for pattern in placeholder_patterns):
                return True
            return False

        is_placeholder = _is_placeholder_key(api_key)
        if is_placeholder and api_key:
            logger.debug(f"API key appears to be a placeholder: {api_key[:20]}..., will try to get from secrets")

        # 优先级：系统设置(secrets) > 配置文件 > 环境变量
        if not api_key or is_placeholder:
            # 1. 首先尝试从加密存储的 secrets 中获取
            secrets_key = _get_api_key_from_secrets(provider_name, base_url)
            if secrets_key:
                api_key = secrets_key
                logger.info(f"Using API key from system secrets for provider={provider_name}")

        if not api_key:
            # 2. 然后尝试从环境变量获取
            env_key = ProviderRegistry.get_env_key(provider_name)
            if env_key:
                api_key = os.getenv(env_key)

        final_api_key: str = ""
        if api_key:
            final_api_key = api_key
        else:
            if ProviderRegistry.has_provider(provider_name):
                raise ValueError(f"API Key is required for provider {provider_name}")
            final_api_key = ""

        kwargs = self._llm_config.extra_kwargs.copy()

        provider = ProviderRegistry.create_provider(
            name=provider_name,
            api_key=final_api_key,
            base_url=base_url,
            model=self._llm_config.model,
            **kwargs,
        )

        if provider:
            self._provider = provider
        else:
            logger.warning(
                f"Unknown provider: {provider_name}, falling back to legacy LLMClient if available"
            )

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
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache
        from derisk.agent.core.llm_config import AgentLLMConfig

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

        if llm_model and ModelConfigCache.has_model(llm_model):
            model_config_dict = ModelConfigCache.get_config(llm_model)
            if model_config_dict:
                if llm_model not in self._provider_cache:
                    try:
                        temp_llm_config = AgentLLMConfig.from_dict(model_config_dict)
                        provider_name = temp_llm_config.provider.lower()

                        base_url = temp_llm_config.base_url

                        # 检查 api_key 是否是占位符
                        def _is_placeholder_key(key: Optional[str]) -> bool:
                            if not key:
                                return True
                            if key.startswith("${"):
                                return True
                            placeholder_patterns = ["sk-...", "sk-xxxx", "your_api_key", "xxx", "placeholder"]
                            key_lower = key.lower()
                            if any(pattern in key_lower for pattern in placeholder_patterns):
                                return True
                            return False

                        api_key = temp_llm_config.api_key
                        is_placeholder = _is_placeholder_key(api_key)

                        # 优先级：系统设置(secrets) > 配置文件 > 环境变量
                        if not api_key or is_placeholder:
                            api_key = _get_api_key_from_secrets(provider_name, base_url)
                            if api_key:
                                logger.info(
                                    f"Using API key from system secrets for model={llm_model}, provider={provider_name}")
                        if not api_key:
                            env_key = ProviderRegistry.get_env_key(provider_name)
                            if env_key:
                                api_key = os.getenv(env_key)

                        provider = ProviderRegistry.create_provider(
                            name=provider_name,
                            api_key=api_key or "",
                            base_url=base_url,
                            model=temp_llm_config.model,
                        )
                        if provider:
                            self._provider_cache[llm_model] = provider
                            logger.info(f"Created {provider_name} provider for model={llm_model}")
                    except Exception as e:
                        logger.error(
                            f"Failed to create provider for model {llm_model}: {e}"
                        )

                self._provider = self._provider_cache.get(llm_model)

        llm_context = extra_kwargs.get("llm_context")
        stream_out = extra_kwargs.get("stream_out", True)
        function_calling_context: Optional[Dict] = params.get(
            "function_calling_context", None
        )

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

        # 详细输入日志，方便调试
        if request.messages:
            messages_summary = []
            for msg in request.messages:
                content = msg.content if hasattr(msg, "content") else str(msg)
                if isinstance(content, list):
                    content_str = (
                            "["
                            + ", ".join([f"{c.get('type', 'unknown')}" for c in content])
                            + "]"
                    )
                else:
                    content_str = (
                        str(content)[:500] + "..."
                        if len(str(content)) > 500
                        else str(content)
                    )
                messages_summary.append(
                    {
                        "role": msg.role if hasattr(msg, "role") else "unknown",
                        "content": content_str,
                    }
                )
            logger.info(
                f"Model Input Messages: {json.dumps(messages_summary, ensure_ascii=False, indent=2)}"
            )

        if request.tools:
            tool_names = [
                t.get("function", {}).get("name", "unknown") for t in request.tools
            ]
            logger.info(f"Model Input Tools ({len(request.tools)}): {tool_names}")
            if request.tool_choice:
                logger.info(f"Model Tool Choice: {request.tool_choice}")
            if request.parallel_tool_calls:
                logger.info(f"Model Parallel Tool Calls: {request.parallel_tool_calls}")

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
            extra["user"] = user

        request.context = ModelRequestContext(
            extra=extra,
            trace_id=params.get("trace_id", None),
            rpc_id=params.get("rpc_id", None),
        )

        # Apply function_calling_context to request
        if function_calling_context:
            tools = function_calling_context.get("tools")
            if tools:
                request.tools = tools
                tool_names = [t.get("function", {}).get("name") for t in tools]
                logger.info(f"Tools being sent to LLM: {tool_names}")
            tool_choice = function_calling_context.get("tool_choice")
            if tool_choice:
                request.tool_choice = tool_choice
            parallel_tool_calls = function_calling_context.get("parallel_tool_calls")
            if parallel_tool_calls is not None:
                request.parallel_tool_calls = parallel_tool_calls
            logger.info(
                f"Applied function_calling_context: tools={len(tools) if tools else 0}, "
                f"tool_choice={tool_choice}, parallel_tool_calls={parallel_tool_calls}"
            )
        else:
            logger.warning("No function_calling_context provided to LLM call!")

        try:
            # Choose client: self._provider or self._llm_client (legacy)
            if self._provider:
                client = self._provider
            elif self._llm_client:
                client = self._llm_client
            else:
                raise ValueError("No LLM provider or client configured.")

            if stream_out:
                accumulated_thinking = ""
                accumulated_content = ""
                # 根据 provider 返回的 incremental 属性判断是否需要累积
                need_accumulate = None  # 延迟判断，根据第一个 chunk 确定

                async for output in client.generate_stream(request):  # type: ignore
                    model_output: ModelOutput = output
                    if model_output.error_code != 0:
                        raise LLMChatError(
                            model_output.text,
                            original_exception=model_output.error_code,
                        )

                    thinking_text, content_text = model_output.gen_text_and_thinking()

                    # 根据第一个 chunk 的 incremental 属性确定累积策略
                    if need_accumulate is None:
                        need_accumulate = model_output.incremental

                    # 如果是增量模式，累积内容；否则直接使用
                    if need_accumulate:
                        if thinking_text:
                            accumulated_thinking += thinking_text
                        if content_text:
                            accumulated_content += content_text
                        thinking_text = accumulated_thinking
                        content_text = accumulated_content

                    think_blank = not thinking_text or len(thinking_text) <= 0
                    content_blank = not content_text or len(content_text) <= 0
                    if think_blank and content_blank and not model_output.tool_calls:
                        continue

                    # 详细输出日志：记录 tool_calls
                    if model_output.tool_calls:
                        tool_call_summary = []
                        for tc in model_output.tool_calls:
                            if tc and isinstance(tc, dict):
                                func_info = tc.get("function", {})
                                tool_call_summary.append(
                                    {
                                        "id": tc.get("id"),
                                        "name": func_info.get("name")
                                        if isinstance(func_info, dict)
                                        else None,
                                    }
                                )
                        if tool_call_summary:
                            logger.info(
                                f"Model Output Tool Calls: {json.dumps(tool_call_summary, ensure_ascii=False)}"
                            )

                    yield AgentLLMOut(
                        thinking_content=thinking_text,
                        content=content_text,
                        metrics=model_output.metrics,
                        llm_name=llm_model,
                        llm_context=llm_context,
                        tool_calls=model_output.tool_calls,
                        in_messages=params["messages"],
                    )
            else:
                model_output = await client.generate(request)
                # 恢复模型调用异常，触发后续的模型兜底策略
                if model_output.error_code != 0:
                    raise LLMChatError(
                        model_output.text, original_exception=model_output.error_code
                    )
                thinking_text, content_text = model_output.gen_text_and_thinking()

                # 详细输出日志：记录 tool_calls
                if model_output.tool_calls:
                    tool_call_summary = []
                    for tc in model_output.tool_calls:
                        if tc and isinstance(tc, dict):
                            func_info = tc.get("function", {})
                            tool_call_summary.append(
                                {
                                    "id": tc.get("id"),
                                    "name": func_info.get("name")
                                    if isinstance(func_info, dict)
                                    else None,
                                }
                            )
                    if tool_call_summary:
                        logger.info(
                            f"Model Output Tool Calls: {json.dumps(tool_call_summary, ensure_ascii=False)}"
                        )

                yield AgentLLMOut(
                    thinking_content=thinking_text,
                    content=content_text,
                    metrics=model_output.metrics,
                    llm_name=llm_model,
                    llm_context=llm_context,
                    tool_calls=model_output.tool_calls,
                    in_messages=params["messages"],
                )
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

    async def get_model_metadata(self, model: str) -> "ModelMetadata":
        """Get model metadata from the provider or LLM client."""
        from derisk.core.interface.llm import ModelMetadata

        if self._provider:
            models = await self._provider.models()
            for m in models:
                if m.model == model:
                    return m
            if models:
                return models[0]
            return ModelMetadata(model=model, context_length=128000)

        if self._llm_client:
            return await self._llm_client.get_model_metadata(model)

        return ModelMetadata(model=model, context_length=128000)
