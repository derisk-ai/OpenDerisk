"""
ModelProvider - 模型供应商抽象层

实现统一的LLM调用接口
支持多Provider、负载均衡、自动降级
"""

from typing import List, Optional, Dict, Any, AsyncIterator, Callable, Union, Literal
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
import json
import uuid
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class ModelCapability(str, Enum):
    """模型能力"""

    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    VISION = "vision"
    FUNCTION_CALLING = "function_calling"
    STREAMING = "streaming"


class ModelMessage(BaseModel):
    """消息模型"""

    role: Literal["system", "user", "assistant", "function"]
    content: str
    name: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None


class ModelUsage(BaseModel):
    """Token使用统计"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelResponse(BaseModel):
    """模型响应"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    content: str
    model: str
    provider: str
    usage: ModelUsage = Field(default_factory=ModelUsage)
    finish_reason: Optional[str] = None

    function_call: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    created_at: datetime = Field(default_factory=datetime.now)
    latency: float = 0.0

    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class StreamChunk(BaseModel):
    """流式响应块"""

    id: str
    content: str
    delta: str
    finish_reason: Optional[str] = None
    usage: Optional[ModelUsage] = None


class ModelConfig(BaseModel):
    """模型配置"""

    model_id: str
    model_name: str
    provider: str
    capabilities: List[ModelCapability] = Field(default_factory=list)

    is_multimodal: bool = False

    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0

    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0

    cost_per_1k_prompt_tokens: float = 0.0
    cost_per_1k_completion_tokens: float = 0.0

    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class CallOptions(BaseModel):
    """调用选项"""

    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[List[str]] = None

    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    functions: Optional[List[Dict[str, Any]]] = None
    function_call: Optional[Union[str, Dict[str, Any]]] = None

    response_format: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelProvider(ABC):
    """
    模型供应商抽象基类

    示例:
        class OpenAIProvider(ModelProvider):
            async def generate(self, messages: List[ModelMessage], **kwargs) -> ModelResponse:
                response = await self.client.chat.completions.create(
                    model=self.config.model_name,
                    messages=[m.dict() for m in messages],
                    **kwargs
                )
                return ModelResponse(content=response.choices[0].message.content, ...)
    """

    def __init__(self, config: ModelConfig, api_key: Optional[str] = None, **kwargs):
        self.config = config
        self.api_key = api_key
        self._client: Any = None
        self._kwargs = kwargs

        self._call_count = 0
        self._error_count = 0
        self._total_latency = 0.0
        self._total_tokens = 0

    @abstractmethod
    async def _init_client(self):
        """初始化客户端"""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> ModelResponse:
        """
        生成响应

        Args:
            messages: 消息列表
            options: 调用选项
            **kwargs: 其他参数

        Returns:
            ModelResponse: 模型响应
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """
        流式生成响应

        Args:
            messages: 消息列表
            options: 调用选项
            **kwargs: 其他参数

        Yields:
            StreamChunk: 流式响应块
        """
        pass

    async def _ensure_client(self):
        """确保客户端已初始化"""
        if self._client is None:
            await self._init_client()

    def calculate_cost(self, usage: ModelUsage) -> float:
        """计算调用成本"""
        prompt_cost = (
            usage.prompt_tokens / 1000
        ) * self.config.cost_per_1k_prompt_tokens
        completion_cost = (
            usage.completion_tokens / 1000
        ) * self.config.cost_per_1k_completion_tokens
        return prompt_cost + completion_cost

    def supports_capability(self, capability: ModelCapability) -> bool:
        """是否支持该能力"""
        return capability in self.config.capabilities

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self._ensure_client()
            response = await self.generate(
                messages=[ModelMessage(role="user", content="ping")],
                options=CallOptions(max_tokens=5),
            )
            return bool(response.content)
        except Exception as e:
            logger.error(f"[{self.config.provider}] Health check failed: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        avg_latency = (
            self._total_latency / self._call_count if self._call_count > 0 else 0
        )
        error_rate = self._error_count / self._call_count if self._call_count > 0 else 0

        return {
            "provider": self.config.provider,
            "model": self.config.model_name,
            "call_count": self._call_count,
            "error_count": self._error_count,
            "error_rate": error_rate,
            "avg_latency": avg_latency,
            "total_tokens": self._total_tokens,
        }


class OpenAIProvider(ModelProvider):
    """OpenAI Provider实现"""

    async def _init_client(self):
        """初始化OpenAI客户端"""
        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self.api_key, **self._kwargs)
            logger.info(f"[OpenAIProvider] 客户端初始化成功: {self.config.model_name}")
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

    async def generate(
        self,
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> ModelResponse:
        """生成响应"""
        await self._ensure_client()

        start_time = time.time()
        self._call_count += 1

        try:
            call_params = self._build_call_params(messages, options, kwargs)

            logger.debug(
                f"[OpenAIProvider] generate request params: "
                f"{json.dumps(call_params, ensure_ascii=False, default=str)}"
            )

            response = await self._client.chat.completions.create(**call_params)

            latency = time.time() - start_time
            self._total_latency += latency

            choice = response.choices[0]

            usage = ModelUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )
            self._total_tokens += usage.total_tokens

            return ModelResponse(
                content=choice.message.content or "",
                model=response.model,
                provider="openai",
                usage=usage,
                finish_reason=choice.finish_reason,
                function_call=choice.message.function_call,
                tool_calls=choice.message.tool_calls,
                latency=latency,
            )

        except Exception as e:
            self._error_count += 1
            logger.error(f"[OpenAIProvider] 生成失败: {e}")
            raise

    async def stream(
        self,
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """流式生成"""
        await self._ensure_client()

        self._call_count += 1
        call_params = self._build_call_params(messages, options, kwargs)
        call_params["stream"] = True

        logger.debug(
            f"[OpenAIProvider] stream request params: "
            f"{json.dumps(call_params, ensure_ascii=False, default=str)}"
        )

        try:
            response_id = str(uuid.uuid4().hex)

            async for chunk in await self._client.chat.completions.create(
                **call_params
            ):
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    yield StreamChunk(
                        id=response_id,
                        content=delta.content or "",
                        delta=delta.content or "",
                        finish_reason=chunk.choices[0].finish_reason,
                    )

        except Exception as e:
            self._error_count += 1
            logger.error(f"[OpenAIProvider] 流式生成失败: {e}")
            raise

    def _build_call_params(
        self, messages: List[ModelMessage], options: Optional[CallOptions], kwargs: Dict
    ) -> Dict[str, Any]:
        """构建调用参数"""
        params = {
            "model": self.config.model_name,
            "messages": [m.dict(exclude_none=True) for m in messages],
        }

        if self.config.max_tokens:
            params["max_tokens"] = self.config.max_tokens
        if self.config.temperature is not None:
            params["temperature"] = self.config.temperature
        if self.config.top_p is not None:
            params["top_p"] = self.config.top_p
        if self.config.presence_penalty:
            params["presence_penalty"] = self.config.presence_penalty
        if self.config.frequency_penalty:
            params["frequency_penalty"] = self.config.frequency_penalty

        if options:
            if options.temperature is not None:
                params["temperature"] = options.temperature
            if options.top_p is not None:
                params["top_p"] = options.top_p
            if options.max_tokens is not None:
                params["max_tokens"] = options.max_tokens
            if options.presence_penalty is not None:
                params["presence_penalty"] = options.presence_penalty
            if options.frequency_penalty is not None:
                params["frequency_penalty"] = options.frequency_penalty
            if options.stop:
                params["stop"] = options.stop
            if options.tools:
                params["tools"] = options.tools
            if options.tool_choice:
                params["tool_choice"] = options.tool_choice
            if options.functions:
                params["functions"] = options.functions
            if options.function_call:
                params["function_call"] = options.function_call
            if options.response_format:
                params["response_format"] = options.response_format
            if options.seed is not None:
                params["seed"] = options.seed

        params.update(kwargs)
        return params


class AnthropicProvider(ModelProvider):
    """Anthropic Provider实现"""

    async def _init_client(self):
        """初始化Anthropic客户端"""
        try:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self.api_key, **self._kwargs)
            logger.info(
                f"[AnthropicProvider] 客户端初始化成功: {self.config.model_name}"
            )
        except ImportError:
            raise ImportError("Please install anthropic: pip install anthropic")

    async def generate(
        self,
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> ModelResponse:
        """生成响应"""
        await self._ensure_client()

        start_time = time.time()
        self._call_count += 1

        try:
            system_msg = ""
            chat_messages = []

            for msg in messages:
                if msg.role == "system":
                    system_msg = msg.content
                else:
                    chat_messages.append({"role": msg.role, "content": msg.content})

            call_params = {
                "model": self.config.model_name,
                "messages": chat_messages,
                "max_tokens": options.max_tokens if options else self.config.max_tokens,
            }

            if system_msg:
                call_params["system"] = system_msg

            logger.debug(
                f"[AnthropicProvider] generate request params: "
                f"{json.dumps(call_params, ensure_ascii=False, default=str)}"
            )

            response = await self._client.messages.create(**call_params)

            latency = time.time() - start_time
            self._total_latency += latency

            usage = ModelUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            )
            self._total_tokens += usage.total_tokens

            content = response.content[0].text if response.content else ""

            return ModelResponse(
                content=content,
                model=response.model,
                provider="anthropic",
                usage=usage,
                finish_reason=response.stop_reason,
                latency=latency,
            )

        except Exception as e:
            self._error_count += 1
            logger.error(f"[AnthropicProvider] 生成失败: {e}")
            raise

    async def stream(
        self,
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """流式生成"""
        await self._ensure_client()

        self._call_count += 1

        try:
            system_msg = ""
            chat_messages = []

            for msg in messages:
                if msg.role == "system":
                    system_msg = msg.content
                else:
                    chat_messages.append({"role": msg.role, "content": msg.content})

            call_params = {
                "model": self.config.model_name,
                "messages": chat_messages,
                "max_tokens": options.max_tokens if options else self.config.max_tokens,
            }

            if system_msg:
                call_params["system"] = system_msg

            response_id = str(uuid.uuid4().hex)

            logger.debug(
                f"[AnthropicProvider] stream request params: "
                f"{json.dumps(call_params, ensure_ascii=False, default=str)}"
            )

            async with self._client.messages.stream(**call_params) as stream:
                async for text in stream.text_stream:
                    yield StreamChunk(
                        id=response_id,
                        content=text,
                        delta=text,
                    )

        except Exception as e:
            self._error_count += 1
            logger.error(f"[AnthropicProvider] 流式生成失败: {e}")
            raise


class ModelRegistry:
    """
    模型注册中心

    职责:
    1. 管理多个Provider
    2. 支持负载均衡
    3. 自动降级和重试
    4. 成本追踪

    示例:
        registry = ModelRegistry()

        registry.register_provider(OpenAIProvider(openai_config, api_key="..."))
        registry.register_provider(AnthropicProvider(anthropic_config, api_key="..."))

        response = await registry.generate(
            model_ids=["gpt-4", "claude-3-opus"],
            messages=[ModelMessage(role="user", content="Hello")]
        )
    """

    def __init__(self):
        self._providers: Dict[str, ModelProvider] = {}
        self._model_aliases: Dict[str, str] = {}
        self._fallback_chains: Dict[str, List[str]] = {}
        self._call_count = 0
        self._total_cost = 0.0

    def register_provider(
        self, provider: ModelProvider, aliases: Optional[List[str]] = None
    ):
        """注册Provider"""
        model_id = provider.config.model_id
        self._providers[model_id] = provider

        if aliases:
            for alias in aliases:
                self._model_aliases[alias] = model_id

        logger.info(
            f"[ModelRegistry] 注册Provider: {model_id} ({provider.config.provider})"
        )

    def set_fallback_chain(self, primary_model: str, fallback_models: List[str]):
        """设置降级链"""
        self._fallback_chains[primary_model] = fallback_models
        logger.info(f"[ModelRegistry] 设置降级链: {primary_model} -> {fallback_models}")

    def get_provider(self, model_id: str) -> Optional[ModelProvider]:
        """获取Provider"""
        resolved_id = self._model_aliases.get(model_id, model_id)
        return self._providers.get(resolved_id)

    async def generate(
        self,
        model_ids: List[str],
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        fallback: bool = True,
        **kwargs,
    ) -> ModelResponse:
        """
        生成响应（支持多模型降级）

        Args:
            model_ids: 模型ID列表（按优先级排序）
            messages: 消息列表
            options: 调用选项
            fallback: 是否启用降级
            **kwargs: 其他参数

        Returns:
            ModelResponse: 模型响应
        """
        self._call_count += 1

        models_to_try = model_ids.copy()

        if fallback and len(model_ids) == 1:
            fallback_models = self._fallback_chains.get(model_ids[0], [])
            models_to_try.extend(fallback_models)

        last_error = None

        for model_id in models_to_try:
            provider = self.get_provider(model_id)

            if not provider:
                logger.warning(f"[ModelRegistry] Provider not found: {model_id}")
                continue

            try:
                response = await provider.generate(messages, options, **kwargs)
                cost = provider.calculate_cost(response.usage)
                self._total_cost += cost

                logger.info(
                    f"[ModelRegistry] 调用成功: {model_id}, "
                    f"tokens={response.usage.total_tokens}, cost=${cost:.4f}"
                )

                return response

            except Exception as e:
                logger.warning(f"[ModelRegistry] Provider {model_id} failed: {e}")
                last_error = e
                continue

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def stream(
        self,
        model_id: str,
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """流式生成"""
        provider = self.get_provider(model_id)

        if not provider:
            raise ValueError(f"Provider not found: {model_id}")

        self._call_count += 1

        async for chunk in provider.stream(messages, options, **kwargs):
            yield chunk

    async def generate_with_retry(
        self,
        model_ids: List[str],
        messages: List[ModelMessage],
        options: Optional[CallOptions] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs,
    ) -> ModelResponse:
        """带重试的生成"""
        last_error = None

        for attempt in range(max_retries):
            try:
                return await self.generate(model_ids, messages, options, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))

        raise RuntimeError(f"Failed after {max_retries} retries: {last_error}")

    def list_providers(self) -> List[str]:
        """列出所有Provider"""
        return list(self._providers.keys())

    def get_provider_capabilities(self, model_id: str) -> List[ModelCapability]:
        """获取Provider能力"""
        provider = self.get_provider(model_id)
        if provider:
            return provider.config.capabilities
        return []

    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有Provider健康状态"""
        results = {}

        for model_id, provider in self._providers.items():
            results[model_id] = await provider.health_check()

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        provider_stats = {
            model_id: provider.get_statistics()
            for model_id, provider in self._providers.items()
        }

        return {
            "total_calls": self._call_count,
            "total_cost": self._total_cost,
            "providers": provider_stats,
            "registered_models": len(self._providers),
            "aliases": len(self._model_aliases),
            "fallback_chains": len(self._fallback_chains),
        }


class ModelClient:
    """
    高层模型客户端

    提供简化的API调用接口

    示例:
        client = ModelClient()
        client.add_openai("gpt-4", api_key="...")
        client.add_anthropic("claude-3-opus", api_key="...")

        response = await client.chat("gpt-4", "Hello!")
        async for chunk in client.stream("claude-3-opus", "Tell me a story"):
            print(chunk.content)
    """

    def __init__(self):
        self.registry = ModelRegistry()

    def add_openai(
        self, model_id: str, model_name: str = None, api_key: str = None, **kwargs
    ):
        """添加OpenAI模型"""
        config = ModelConfig(
            model_id=model_id,
            model_name=model_name or model_id,
            provider="openai",
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.STREAMING,
            ],
            **kwargs,
        )
        provider = OpenAIProvider(config, api_key)
        self.registry.register_provider(provider)

    def add_anthropic(
        self, model_id: str, model_name: str = None, api_key: str = None, **kwargs
    ):
        """添加Anthropic模型"""
        config = ModelConfig(
            model_id=model_id,
            model_name=model_name or model_id,
            provider="anthropic",
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.STREAMING,
            ],
            **kwargs,
        )
        provider = AnthropicProvider(config, api_key)
        self.registry.register_provider(provider)

    async def chat(
        self,
        model_id: str,
        message: str,
        system: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> ModelResponse:
        """聊天"""
        messages = []

        if system:
            messages.append(ModelMessage(role="system", content=system))

        if history:
            for msg in history:
                messages.append(
                    ModelMessage(
                        role=msg.get("role", "user"), content=msg.get("content", "")
                    )
                )

        messages.append(ModelMessage(role="user", content=message))

        return await self.registry.generate([model_id], messages, options, **kwargs)

    async def stream(
        self,
        model_id: str,
        message: str,
        system: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        options: Optional[CallOptions] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """流式聊天"""
        messages = []

        if system:
            messages.append(ModelMessage(role="system", content=system))

        if history:
            for msg in history:
                messages.append(
                    ModelMessage(
                        role=msg.get("role", "user"), content=msg.get("content", "")
                    )
                )

        messages.append(ModelMessage(role="user", content=message))

        async for chunk in self.registry.stream(model_id, messages, options, **kwargs):
            yield chunk

    async def function_call(
        self,
        model_id: str,
        message: str,
        functions: List[Dict[str, Any]],
        system: Optional[str] = None,
        **kwargs,
    ) -> ModelResponse:
        """函数调用"""
        options = CallOptions(functions=functions)
        return await self.chat(model_id, message, system, options=options, **kwargs)

    async def tool_call(
        self,
        model_id: str,
        message: str,
        tools: List[Dict[str, Any]],
        tool_choice: Optional[Union[str, Dict]] = None,
        system: Optional[str] = None,
        **kwargs,
    ) -> ModelResponse:
        """工具调用"""
        options = CallOptions(tools=tools, tool_choice=tool_choice)
        return await self.chat(model_id, message, system, options=options, **kwargs)


model_registry = ModelRegistry()
