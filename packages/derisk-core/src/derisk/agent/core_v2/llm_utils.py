"""
LLM调用工具类 - 为 core_v2 架构提供统一的 LLM 调用接口

支持:
1. LLMConfig (derisk.agent.util.llm.llm.LLMConfig) - 包含策略和模型选择
2. LLMAdapter (core_v2.llm_adapter) - 新架构的 LLM 适配器
3. LLMProvider (derisk.agent.util.llm.provider.base.LLMProvider) - Core 架构的模型提供者
4. DefaultLLMClient - 原始 LLM 客户端
"""

import logging
import json
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


async def call_llm(
    model_provider: Any,
    message: str,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs
) -> Optional[str]:
    """
    统一的 LLM 调用接口
    
    支持:
    1. LLMConfig (derisk.agent.util.llm.llm.LLMConfig) - 包含策略和模型选择
    2. LLMAdapter (core_v2.llm_adapter.LLMAdapter) - 新架构的 LLM 适配器
    3. LLMProvider (derisk.agent.util.llm.provider.base.LLMProvider) - Core 架构的模型提供者
    4. DefaultLLMClient - 原始 LLM 客户端
    
    Args:
        model_provider: LLM 配置/客户端
        message: 用户消息
        system_prompt: 系统提示
        history: 对话历史
        temperature: 温度参数
        max_tokens: 最大 token 数
        **kwargs: 其他参数
        
    Returns:
        Optional[str]: 生成的回复内容，失败返回 None
    """
    if not model_provider:
        logger.warning("model_provider 为空，无法调用 LLM")
        return None
    
    try:
        from derisk.agent.util.llm.llm import LLMConfig
        if isinstance(model_provider, LLMConfig):
            return await _call_with_llm_config(
                model_provider, message, system_prompt, history, 
                temperature, max_tokens, **kwargs
            )
    except ImportError:
        pass
    
    try:
        from .llm_adapter import LLMAdapter
        if isinstance(model_provider, LLMAdapter):
            return await _call_with_llm_adapter(
                model_provider, message, system_prompt, history,
                temperature, max_tokens, **kwargs
            )
    except ImportError:
        pass
    
    try:
        from derisk.agent.util.llm.provider.base import LLMProvider
        if isinstance(model_provider, LLMProvider):
            return await _call_with_llm_provider(
                model_provider, message, system_prompt, history,
                temperature, max_tokens, **kwargs
            )
    except ImportError:
        pass
    
    if hasattr(model_provider, 'generate') or hasattr(model_provider, 'chat'):
        return await _call_with_generic_client(
            model_provider, message, system_prompt, history,
            temperature, max_tokens, **kwargs
        )
    
    logger.error(f"不支持的 model_provider 类型: {type(model_provider)}")
    return None


async def _call_with_llm_provider(
    llm_provider: Any,
    message: str,
    system_prompt: Optional[str],
    history: Optional[List[Dict[str, str]]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    **kwargs
) -> Optional[str]:
    """使用 LLMProvider (Core 架构) 调用 LLM"""
    try:
        from derisk.core import ModelRequest
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": message})
        
        model_name = kwargs.get("model", "default")
        
        request = ModelRequest.build_request(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_new_tokens=max_tokens,
        )
        
        response = await llm_provider.generate(request)
        
        if response:
            if hasattr(response, 'text') and response.text:
                return response.text
            elif hasattr(response, 'content') and response.content:
                return response.content
            elif isinstance(response, str):
                return response
            elif hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content
        
        logger.warning(f"LLMProvider 返回空响应: {response}")
        return None
        
    except Exception as e:
        logger.error(f"LLMProvider 调用失败: {e}", exc_info=True)
        return None


async def _call_with_llm_config(
    llm_config: Any,
    message: str,
    system_prompt: Optional[str],
    history: Optional[List[Dict[str, str]]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    **kwargs
) -> Optional[str]:
    """使用 LLMConfig 调用 LLM"""
    try:
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache
        from derisk.agent.util.llm.llm_client import AIWrapper
        from derisk.agent.core.llm_config import AgentLLMConfig
        
        strategy_context = llm_config.strategy_context
        model_list = []
        
        if strategy_context:
            if isinstance(strategy_context, list):
                model_list = strategy_context
            elif isinstance(strategy_context, str):
                try:
                    model_list = json.loads(strategy_context)
                except:
                    model_list = [strategy_context]
        
        if not model_list:
            all_models = ModelConfigCache.get_all_models()
            model_list = all_models if all_models else []
        
        model_name = model_list[0] if model_list else None
        
        if not model_name:
            logger.warning("没有可用的模型")
            return None
        
        logger.info(f"[LLMUtils] 使用模型: {model_name}")
        
        model_config = ModelConfigCache.get_config(model_name)
        agent_llm_config = None
        if model_config:
            try:
                agent_llm_config = AgentLLMConfig.from_dict(model_config)
            except Exception as e:
                logger.warning(f"解析模型配置失败: {e}")
        
        ai_wrapper = AIWrapper(llm_config=agent_llm_config)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": message})
        
        model_param = llm_config.llm_param.get(model_name) if llm_config.llm_param else None
        
        gen_kwargs = {
            "messages": messages,
            "llm_model": model_name,
            "temperature": temperature or (model_param.get("temperature") if model_param else None),
            "max_new_tokens": max_tokens or (model_param.get("max_new_tokens") if model_param else None),
            "stream_out": False,
        }
        
        gen_kwargs = {k: v for k, v in gen_kwargs.items() if v is not None}
        
        async for result in ai_wrapper.create(**gen_kwargs):
            if result and result.content:
                return result.content
        
        return None
        
    except Exception as e:
        logger.error(f"LLMConfig 调用失败: {e}", exc_info=True)
        return None


async def _call_with_llm_adapter(
    llm_adapter: Any,
    message: str,
    system_prompt: Optional[str],
    history: Optional[List[Dict[str, str]]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    **kwargs
) -> Optional[str]:
    """使用 LLMAdapter 调用 LLM"""
    try:
        from .llm_adapter import LLMMessage
        
        messages = []
        
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        
        if history:
            for msg in history:
                messages.append(LLMMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", "")
                ))
        
        messages.append(LLMMessage(role="user", content=message))
        
        response = await llm_adapter.generate(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return response.content
        
    except Exception as e:
        logger.error(f"LLMAdapter 调用失败: {e}", exc_info=True)
        return None


async def _call_with_generic_client(
    client: Any,
    message: str,
    system_prompt: Optional[str],
    history: Optional[List[Dict[str, str]]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    **kwargs
) -> Optional[str]:
    """使用通用客户端调用 LLM"""
    try:
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": message})
        
        response = None
        
        if hasattr(client, 'generate'):
            if hasattr(client, '__call__'):
                response = await client.generate(messages)
            else:
                response = await client.generate(message)
        elif hasattr(client, 'chat'):
            response = await client.chat(messages)
        elif hasattr(client, 'acompletion'):
            response = await client.acompletion(messages)
        
        if response:
            if hasattr(response, "content"):
                return response.content
            elif hasattr(response, "choices"):
                return response.choices[0].message.content
            elif isinstance(response, str):
                return response
        
        logger.error(f"无法解析响应: {response}")
        return None
        
    except Exception as e:
        logger.error(f"通用客户端调用失败: {e}", exc_info=True)
        return None


class LLMCaller:
    """
    LLM 调用器 - 封装 LLM 调用逻辑
    
    使用示例:
        caller = LLMCaller(model_provider)
        response = await caller.call("你好")
    """
    
    def __init__(self, model_provider: Any):
        self.model_provider = model_provider
    
    async def call(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> Optional[str]:
        """调用 LLM"""
        return await call_llm(
            self.model_provider,
            message,
            system_prompt,
            history,
            **kwargs
        )
    
    async def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> Optional[str]:
        """聊天接口 (call 的别名)"""
        return await self.call(message, system_prompt, history, **kwargs)