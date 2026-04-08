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


def validate_tool_call_pairs(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Pre-flight validator: ensures every assistant message with tool_calls is
    followed by matching tool messages, and every tool message references a
    valid tool_call_id from a preceding assistant message.

    Repairs silently when possible:
      - Orphan tool messages (no matching assistant tool_calls) → removed
      - Assistant with tool_calls but missing tool responses → tool_calls stripped,
        demoted to plain assistant message

    Returns the (possibly repaired) message list.
    """
    # Build a set of valid tool_call_ids from assistant messages
    valid_tc_ids: set = set()
    for msg in messages:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id:
                    valid_tc_ids.add(tc_id)

    # Pass 1: Remove orphan tool messages (tool_call_id not in any assistant's tool_calls)
    cleaned: List[Dict[str, Any]] = []
    removed_tool_ids: set = set()
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id and tc_id not in valid_tc_ids:
                logger.warning(
                    f"[validate_tool_call_pairs] Removing orphan tool message "
                    f"with tool_call_id={tc_id} (no matching assistant tool_calls)"
                )
                removed_tool_ids.add(tc_id)
                continue
        cleaned.append(msg)

    # Pass 2: For each assistant with tool_calls, verify that ALL referenced
    # tool_call_ids have a subsequent tool message.  If any are missing,
    # strip tool_calls to avoid OpenAI 400 errors.
    present_tool_ids: set = set()
    for msg in cleaned:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            present_tool_ids.add(msg["tool_call_id"])

    result: List[Dict[str, Any]] = []
    for msg in cleaned:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            tc_ids_in_msg = []
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id:
                    tc_ids_in_msg.append(tc_id)
            missing = [tid for tid in tc_ids_in_msg if tid not in present_tool_ids]
            if missing:
                logger.warning(
                    f"[validate_tool_call_pairs] Assistant message has tool_calls "
                    f"with ids {tc_ids_in_msg} but tool responses missing for {missing}. "
                    f"Stripping tool_calls to avoid OpenAI error."
                )
                repaired = {k: v for k, v in msg.items() if k != "tool_calls"}
                if not repaired.get("content"):
                    repaired["content"] = "[tool call result unavailable — context was compacted]"
                result.append(repaired)
                continue
        result.append(msg)

    if len(result) != len(messages):
        logger.warning(
            f"[validate_tool_call_pairs] Repaired message list: "
            f"{len(messages)} → {len(result)} messages"
        )

    return result


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
                import httpx
                
                timeout = httpx.Timeout(
                    connect=10.0,
                    read=self.config.timeout,
                    write=30.0,
                    pool=10.0
                )
                
                self._client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.api_base,
                    timeout=timeout
                )
                logger.info(f"[OpenAIAdapter] 客户端初始化完成, base_url={self.config.api_base}")
            except ImportError:
                raise ImportError("请安装openai: pip install openai")
    
    async def generate(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> LLMResponse:
        import sys
        await self._init_client()
        
        start_time = time.time()
        self._call_count += 1
        
        try:
            params = {
                "model": self.config.model,
                "messages": [m if isinstance(m, dict) else m.dict(exclude_none=True) for m in messages],
                "temperature": kwargs.get("temperature", self.config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
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
            
            # Pre-flight: validate tool-call pair integrity
            params["messages"] = validate_tool_call_pairs(params["messages"])
            
            logger.info(f"[OpenAIAdapter] ========== 开始调用模型 ==========")
            logger.info(f"[OpenAIAdapter] 模型: {self.config.model}")
            logger.info(f"[OpenAIAdapter] 请求参数: temperature={params.get('temperature')}, max_tokens={params.get('max_tokens')}")
            msg_list = [msg if isinstance(msg, dict) else msg.dict(exclude_none=True) for msg in messages]
            logger.info(f"[OpenAIAdapter] 消息数量: {len(messages)}, 消息列表: {json.dumps(msg_list, ensure_ascii=False)}")
            if params.get("tools"):
                tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in params['tools']]
                logger.info(f"[OpenAIAdapter] 工具数量: {len(params['tools'])}, 工具列表: {tool_names}")
            
            response = await self._client.chat.completions.create(**params)
            
            logger.info(f"[OpenAIAdapter] ========== 模型返回成功 ==========")
            logger.info(f"[OpenAIAdapter] 响应延迟: {time.time() - start_time:.2f}s")
            
            latency = time.time() - start_time
            self._total_latency += latency
            
            choice = response.choices[0]
            
            usage = LLMUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            )
            self._total_tokens += usage.total_tokens
            
            logger.info(f"[OpenAIAdapter] Token使用: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
            logger.info(f"[OpenAIAdapter] 结束原因: {choice.finish_reason}")
            
            tool_calls = None
            if choice.message.tool_calls:
                logger.info(f"[OpenAIAdapter] 返回工具调用数量: {len(choice.message.tool_calls)}")
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in choice.message.tool_calls
                ]
                for i, tc in enumerate(choice.message.tool_calls):
                    logger.info(f"[OpenAIAdapter] 工具调用[{i}]: {tc.function.name}, 参数={tc.function.arguments}")
            
            function_call = None
            if choice.message.function_call:
                function_call = {
                    "name": choice.message.function_call.name,
                    "arguments": choice.message.function_call.arguments
                }
                logger.info(f"[OpenAIAdapter] 函数调用: {function_call['name']}, 参数={function_call['arguments']}")
            
            content = choice.message.content or ""
            if content:
                logger.info(f"[OpenAIAdapter] 返回内容: {content}")
            
            logger.info(f"[OpenAIAdapter] ========== 模型调用结束 ==========")
            
            return LLMResponse(
                content=content,
                model=response.model,
                provider="openai",
                usage=usage,
                finish_reason=choice.finish_reason,
                function_call=function_call,
                tool_calls=tool_calls,
                latency=latency
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"[OpenAIAdapter] ========== 模型调用失败 ==========")
            logger.error(f"[OpenAIAdapter] 错误: {e}", exc_info=True)
            raise
    
    async def stream(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> AsyncIterator[str]:
        await self._init_client()
        
        self._call_count += 1
        
        try:
            params = {
                "model": self.config.model,
                "messages": [m if isinstance(m, dict) else m.dict(exclude_none=True) for m in messages],
                "temperature": kwargs.get("temperature", self.config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            }
            
            logger.info(f"[OpenAIAdapter] ========== 开始流式调用模型 ==========")
            logger.info(f"[OpenAIAdapter] 模型: {self.config.model}")
            logger.info(f"[OpenAIAdapter] 消息数量: {len(messages)}, 请求参数: {json.dumps(params, ensure_ascii=False, default=str)}")

            response = await self._client.chat.completions.create(**params)
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            logger.info(f"[OpenAIAdapter] ========== 流式调用结束 ==========")
                    
        except Exception as e:
            self._error_count += 1
            logger.error(f"[OpenAIAdapter] ========== 流式调用失败 ==========")
            logger.error(f"[OpenAIAdapter] 错误: {e}", exc_info=True)
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
            
            logger.info(f"[AnthropicAdapter] ========== 开始调用模型 ==========")
            logger.info(f"[AnthropicAdapter] 模型: {self.config.model}")
            logger.info(f"[AnthropicAdapter] 请求参数: {json.dumps(params, ensure_ascii=False, default=str)}")
            logger.info(f"[AnthropicAdapter] 消息数量: {len(messages)}")
            for i, msg in enumerate(messages):
                logger.info(f"[AnthropicAdapter] 消息[{i}]: role={msg.role}, content={msg.content}")
            if system_msg:
                logger.info(f"[AnthropicAdapter] System提示: {system_msg}")
            
            response = await self._client.messages.create(**params)
            
            logger.info(f"[AnthropicAdapter] ========== 模型返回成功 ==========")
            logger.info(f"[AnthropicAdapter] 响应延迟: {time.time() - start_time:.2f}s")
            
            latency = time.time() - start_time
            self._total_latency += latency
            
            usage = LLMUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens
            )
            self._total_tokens += usage.total_tokens
            
            logger.info(f"[AnthropicAdapter] Token使用: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
            logger.info(f"[AnthropicAdapter] 结束原因: {response.stop_reason}")
            
            content = response.content[0].text if response.content else ""
            if content:
                logger.info(f"[AnthropicAdapter] 返回内容: {content}")
            
            logger.info(f"[AnthropicAdapter] ========== 模型调用结束 ==========")
            
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
            logger.error(f"[AnthropicAdapter] ========== 模型调用失败 ==========")
            logger.error(f"[AnthropicAdapter] 错误: {e}", exc_info=True)
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
        
        logger.info(f"[AnthropicAdapter] ========== 开始流式调用模型 ==========")
        logger.info(f"[AnthropicAdapter] 模型: {self.config.model}")
        logger.info(f"[AnthropicAdapter] 消息数量: {len(messages)}")
        
        try:
            async with self._client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text
            logger.info(f"[AnthropicAdapter] ========== 流式调用结束 ==========")
                    
        except Exception as e:
            self._error_count += 1
            logger.error(f"[AnthropicAdapter] ========== 流式调用失败 ==========")
            logger.error(f"[AnthropicAdapter] 错误: {e}", exc_info=True)
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