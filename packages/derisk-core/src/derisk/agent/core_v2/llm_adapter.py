"""
LLMAdapter - 统一LLM调用适配层

提供统一的LLM调用接口，支持多种后端：
- OpenAI
- Azure OpenAI
- Anthropic Claude
- 本地模型
- 自定义API
"""

from typing import Dict, Any, List, Optional, AsyncIterator, Union
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
import asyncio
import logging
import json
import time

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """LLM提供商"""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    CUSTOM = "custom"


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


class LLMMessage(BaseModel):
    """LLM消息"""
    role: str
    content: str
    name: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class LLMUsage(BaseModel):
    """Token使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """LLM响应"""
    content: str
    model: str
    provider: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    finish_reason: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    latency: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMConfig(BaseModel):
    """LLM配置"""
    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4"
    
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    
    stream: bool = True
    
    class Config:
        use_enum_values = True


class LLMAdapter(ABC):
    """
    LLM适配器基类
    
    所有LLM后端都需要实现此接口
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._call_count = 0
        self._error_count = 0
        self._total_latency = 0.0
        self._total_tokens = 0
    
    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> LLMResponse:
        """生成响应"""
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> AsyncIterator[str]:
        """流式生成"""
        pass
    
    async def chat(
        self,
        message: str,
        system: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> LLMResponse:
        """简化聊天接口"""
        messages = []
        
        if system:
            messages.append(LLMMessage(role="system", content=system))
        
        if history:
            for msg in history:
                messages.append(LLMMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", "")
                ))
        
        messages.append(LLMMessage(role="user", content=message))
        
        return await self.generate(messages, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "call_count": self._call_count,
            "error_count": self._error_count,
            "total_tokens": self._total_tokens,
            "avg_latency": self._total_latency / max(1, self._call_count),
        }


class OpenAIAdapter(LLMAdapter):
    """OpenAI适配器"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
    
    async def _init_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.api_base,
                    timeout=self.config.timeout
                )
            except ImportError:
                raise ImportError("请安装openai: pip install openai")
    
    async def generate(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> LLMResponse:
        await self._init_client()
        
        start_time = time.time()
        self._call_count += 1
        
        try:
            params = {
                "model": self.config.model,
                "messages": [m.dict(exclude_none=True) for m in messages],
                "temperature": kwargs.get("temperature", self.config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "top_p": kwargs.get("top_p", self.config.top_p),
            }
            
            if kwargs.get("tools"):
                params["tools"] = kwargs["tools"]
            if kwargs.get("tool_choice"):
                params["tool_choice"] = kwargs["tool_choice"]
            if kwargs.get("functions"):
                params["functions"] = kwargs["functions"]
            if kwargs.get("function_call"):
                params["function_call"] = kwargs["function_call"]
            if kwargs.get("response_format"):
                params["response_format"] = kwargs["response_format"]
            
            response = await self._client.chat.completions.create(**params)
            
            latency = time.time() - start_time
            self._total_latency += latency
            
            choice = response.choices[0]
            
            usage = LLMUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            )
            self._total_tokens += usage.total_tokens
            
            return LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                provider="openai",
                usage=usage,
                finish_reason=choice.finish_reason,
                function_call=choice.message.function_call,
                tool_calls=choice.message.tool_calls,
                latency=latency
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"[OpenAIAdapter] 生成失败: {e}")
            raise
    
    async def stream(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> AsyncIterator[str]:
        await self._init_client()
        
        self._call_count += 1
        
        params = {
            "model": self.config.model,
            "messages": [m.dict(exclude_none=True) for m in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": True,
        }
        
        try:
            response = await self._client.chat.completions.create(**params)
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            self._error_count += 1
            logger.error(f"[OpenAIAdapter] 流式生成失败: {e}")
            raise


class AnthropicAdapter(LLMAdapter):
    """Anthropic适配器"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
    
    async def _init_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(
                    api_key=self.config.api_key,
                    timeout=self.config.timeout
                )
            except ImportError:
                raise ImportError("请安装anthropic: pip install anthropic")
    
    async def generate(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> LLMResponse:
        await self._init_client()
        
        start_time = time.time()
        self._call_count += 1
        
        try:
            system_msg = ""
            chat_messages = []
            
            for msg in messages:
                if msg.role == "system":
                    system_msg = msg.content
                else:
                    chat_messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
            
            params = {
                "model": self.config.model,
                "messages": chat_messages,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            }
            
            if system_msg:
                params["system"] = system_msg
            
            response = await self._client.messages.create(**params)
            
            latency = time.time() - start_time
            self._total_latency += latency
            
            usage = LLMUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens
            )
            self._total_tokens += usage.total_tokens
            
            content = response.content[0].text if response.content else ""
            
            return LLMResponse(
                content=content,
                model=response.model,
                provider="anthropic",
                usage=usage,
                finish_reason=response.stop_reason,
                latency=latency
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"[AnthropicAdapter] 生成失败: {e}")
            raise
    
    async def stream(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> AsyncIterator[str]:
        await self._init_client()
        
        self._call_count += 1
        
        system_msg = ""
        chat_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system_msg = msg.content
            else:
                chat_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        params = {
            "model": self.config.model,
            "messages": chat_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        
        if system_msg:
            params["system"] = system_msg
        
        try:
            async with self._client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text
                    
        except Exception as e:
            self._error_count += 1
            logger.error(f"[AnthropicAdapter] 流式生成失败: {e}")
            raise


class LLMFactory:
    """
    LLM工厂类
    
    示例:
        config = LLMConfig(provider="openai", model="gpt-4", api_key="sk-xxx")
        llm = LLMFactory.create(config)
        
        response = await llm.chat("你好")
        print(response.content)
    """
    
    @staticmethod
    def create(config: LLMConfig) -> LLMAdapter:
        """创建LLM适配器"""
        if config.provider == LLMProvider.OPENAI:
            return OpenAIAdapter(config)
        elif config.provider == LLMProvider.ANTHROPIC:
            return AnthropicAdapter(config)
        else:
            raise ValueError(f"不支持的Provider: {config.provider}")
    
    @staticmethod
    def create_from_env(provider: str = "openai") -> LLMAdapter:
        """从环境变量创建"""
        import os
        
        if provider == "openai":
            config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model=os.getenv("OPENAI_MODEL", "gpt-4"),
                api_key=os.getenv("OPENAI_API_KEY"),
                api_base=os.getenv("OPENAI_API_BASE"),
            )
        elif provider == "anthropic":
            config = LLMConfig(
                provider=LLMProvider.ANTHROPIC,
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-opus-20240229"),
                api_key=os.getenv("ANTHROPIC_API_KEY"),
            )
        else:
            raise ValueError(f"不支持的Provider: {provider}")
        
        return LLMFactory.create(config)


llm_factory = LLMFactory()