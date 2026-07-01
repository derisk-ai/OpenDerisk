import logging
from typing import Callable, Dict, Optional, Type

from derisk.agent.util.llm.provider.base import LLMProvider

logger = logging.getLogger(__name__)

ProviderFactory = Callable[..., LLMProvider]


class ProviderRegistry:
    _instance: Optional["ProviderRegistry"] = None
    # 注册表 key 为协议名称 (protocol)，如 openai/anthropic/theta
    _providers: Dict[str, Type[LLMProvider]] = {}
    _factories: Dict[str, ProviderFactory] = {}
    _env_key_mappings: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        name: str,
        provider_class: Optional[Type[LLMProvider]] = None,
        factory: Optional[ProviderFactory] = None,
        env_key: Optional[str] = None,
    ):
        def decorator(provider_cls: Type[LLMProvider]) -> Type[LLMProvider]:
            protocol = name.lower()
            cls._providers[protocol] = provider_cls
            if factory:
                cls._factories[protocol] = factory
            if env_key:
                cls._env_key_mappings[protocol] = env_key
            logger.info(f"Registered LLM protocol: {protocol}")
            return provider_cls

        if provider_class:
            return decorator(provider_class)
        return decorator

    @classmethod
    def get_provider_class(cls, name: str) -> Optional[Type[LLMProvider]]:
        return cls._providers.get(name.lower())

    @classmethod
    def get_factory(cls, name: str) -> Optional[ProviderFactory]:
        return cls._factories.get(name.lower())

    @classmethod
    def get_env_key(cls, name: str) -> Optional[str]:
        return cls._env_key_mappings.get(name.lower())

    @classmethod
    def create_provider_by_protocol(
        cls,
        protocol: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[LLMProvider]:
        """根据协议名称创建 provider 实例"""
        protocol = protocol.lower()

        factory = cls._factories.get(protocol)
        if factory:
            return factory(api_key=api_key, base_url=base_url, model=model, **kwargs)

        provider_class = cls._providers.get(protocol)
        if provider_class:
            return provider_class(
                api_key=api_key or "", base_url=base_url, model=model, **kwargs
            )

        return None

    @classmethod
    def create_provider(
        cls,
        name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[LLMProvider]:
        """兼容旧逻辑：name 既可以是 protocol，也可以是 provider 名称

        为了保持兼容性，优先按 protocol 查找，找不到时返回 None。
        调用方应通过 ModelConfigCache 解析出 protocol 后再调用 create_provider_by_protocol。
        """
        return cls.create_provider_by_protocol(
            name, api_key=api_key, base_url=base_url, model=model, **kwargs
        )

    @classmethod
    def list_providers(cls) -> Dict[str, Type[LLMProvider]]:
        return cls._providers.copy()

    @classmethod
    def has_provider(cls, name: str) -> bool:
        return name.lower() in cls._providers