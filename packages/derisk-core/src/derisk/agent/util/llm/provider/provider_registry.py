import logging
from typing import Callable, Dict, Optional, Type

from derisk.agent.util.llm.provider.base import LLMProvider

logger = logging.getLogger(__name__)

ProviderFactory = Callable[..., LLMProvider]


class ProviderRegistry:
    _instance: Optional["ProviderRegistry"] = None
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
            provider_name = name.lower()
            cls._providers[provider_name] = provider_cls
            if factory:
                cls._factories[provider_name] = factory
            if env_key:
                cls._env_key_mappings[provider_name] = env_key
            logger.info(f"Registered LLM provider: {provider_name}")
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
    def create_provider(
        cls,
        name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[LLMProvider]:
        provider_name = name.lower()
        
        factory = cls._factories.get(provider_name)
        if factory:
            return factory(api_key=api_key, base_url=base_url, model=model, **kwargs)
        
        provider_class = cls._providers.get(provider_name)
        if provider_class:
            return provider_class(
                api_key=api_key or "", base_url=base_url, model=model, **kwargs
            )
        
        return None

    @classmethod
    def list_providers(cls) -> Dict[str, Type[LLMProvider]]:
        return cls._providers.copy()

    @classmethod
    def has_provider(cls, name: str) -> bool:
        return name.lower() in cls._providers