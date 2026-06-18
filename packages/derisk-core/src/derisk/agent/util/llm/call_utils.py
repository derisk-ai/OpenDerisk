"""
LLM 调用工具 - 统一的 LLM 调用入口

支持以下 ``model_provider`` 类型：
1. ``LLMConfig`` (``derisk.agent.util.llm.llm.LLMConfig``) - 包含策略和模型选择
2. ``LLMProvider`` (``derisk.agent.util.llm.provider.base.LLMProvider``) - Core 架构的模型提供者
3. 通用客户端：暴露 ``generate`` / ``chat`` / ``acompletion`` 之一即可
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def call_llm(
    model_provider: Any,
    message: str,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs,
) -> Optional[str]:
    """统一的 LLM 调用接口。失败返回 ``None``。"""
    if not model_provider:
        logger.warning("model_provider is empty, cannot call LLM")
        return None

    try:
        from derisk.agent.util.llm.llm import LLMConfig

        if isinstance(model_provider, LLMConfig):
            return await _call_with_llm_config(
                model_provider, message, system_prompt, history,
                temperature, max_tokens, **kwargs,
            )
    except ImportError:
        pass

    try:
        from derisk.agent.util.llm.provider.base import LLMProvider

        if isinstance(model_provider, LLMProvider):
            return await _call_with_llm_provider(
                model_provider, message, system_prompt, history,
                temperature, max_tokens, **kwargs,
            )
    except ImportError:
        pass

    if hasattr(model_provider, "generate") or hasattr(model_provider, "chat"):
        return await _call_with_generic_client(
            model_provider, message, system_prompt, history,
            temperature, max_tokens, **kwargs,
        )

    logger.error(f"Unsupported model_provider type: {type(model_provider)}")
    return None


async def _call_with_llm_provider(
    llm_provider: Any,
    message: str,
    system_prompt: Optional[str],
    history: Optional[List[Dict[str, str]]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    **kwargs,
) -> Optional[str]:
    try:
        from derisk.core import ModelRequest

        messages: List[Dict[str, str]] = []
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
            if hasattr(response, "text") and response.text:
                return response.text
            if hasattr(response, "content") and response.content:
                return response.content
            if isinstance(response, str):
                return response
            if hasattr(response, "choices") and response.choices:
                return response.choices[0].message.content

        logger.warning(f"LLMProvider returned empty response: {response}")
        return None
    except Exception as e:
        logger.error(f"LLMProvider call failed: {e}", exc_info=True)
        return None


async def _call_with_llm_config(
    llm_config: Any,
    message: str,
    system_prompt: Optional[str],
    history: Optional[List[Dict[str, str]]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    **kwargs,
) -> Optional[str]:
    try:
        from derisk.agent.core.llm_config import AgentLLMConfig
        from derisk.agent.util.llm.llm_client import AIWrapper
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache

        strategy_context = llm_config.strategy_context
        model_list: List[str] = []
        if strategy_context:
            if isinstance(strategy_context, list):
                model_list = strategy_context
            elif isinstance(strategy_context, str):
                try:
                    model_list = json.loads(strategy_context)
                except Exception:
                    model_list = [strategy_context]

        if not model_list:
            all_models = ModelConfigCache.get_all_models()
            model_list = all_models if all_models else []

        model_name = model_list[0] if model_list else None
        if not model_name:
            logger.warning("No usable model")
            return None

        logger.info(f"[call_llm] Using model: {model_name}")

        model_config = ModelConfigCache.get_config(model_name)
        agent_llm_config = None
        if model_config:
            try:
                agent_llm_config = AgentLLMConfig.from_dict(model_config)
            except Exception as e:
                logger.warning(f"Parse model config failed: {e}")

        ai_wrapper = AIWrapper(llm_config=agent_llm_config)

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        model_param = (
            llm_config.llm_param.get(model_name) if llm_config.llm_param else None
        )
        gen_kwargs = {
            "messages": messages,
            "llm_model": model_name,
            "temperature": temperature
            or (model_param.get("temperature") if model_param else None),
            "max_new_tokens": max_tokens
            or (model_param.get("max_new_tokens") if model_param else None),
            "stream_out": False,
        }
        gen_kwargs = {k: v for k, v in gen_kwargs.items() if v is not None}

        async for result in ai_wrapper.create(**gen_kwargs):
            if result and result.content:
                return result.content
        return None
    except Exception as e:
        logger.error(f"LLMConfig call failed: {e}", exc_info=True)
        return None


async def _call_with_generic_client(
    client: Any,
    message: str,
    system_prompt: Optional[str],
    history: Optional[List[Dict[str, str]]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    **kwargs,
) -> Optional[str]:
    try:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        response = None
        if hasattr(client, "generate"):
            try:
                response = await client.generate(messages)
            except TypeError:
                response = await client.generate(message)
        elif hasattr(client, "chat"):
            response = await client.chat(messages)
        elif hasattr(client, "acompletion"):
            response = await client.acompletion(messages)

        if response:
            if hasattr(response, "content"):
                return response.content
            if hasattr(response, "choices"):
                return response.choices[0].message.content
            if isinstance(response, str):
                return response

        logger.error(f"Cannot parse response: {response}")
        return None
    except Exception as e:
        logger.error(f"Generic client call failed: {e}", exc_info=True)
        return None


__all__ = ["call_llm"]
