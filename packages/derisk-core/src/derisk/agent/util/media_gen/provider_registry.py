"""Media Generation Provider Registry.

Singleton registry for media generation providers, following the same pattern
as derisk.agent.util.llm.provider.provider_registry.ProviderRegistry.
"""

import logging
from typing import Any, Callable, Dict, Optional, Type

from derisk.agent.util.media_gen.base import MediaGenProvider

logger = logging.getLogger(__name__)

MediaGenProviderFactory = Callable[..., MediaGenProvider]


class MediaGenProviderRegistry:
    """Singleton registry for media generation providers."""

    _instance: Optional["MediaGenProviderRegistry"] = None
    _providers: Dict[str, Type[MediaGenProvider]] = {}
    _factories: Dict[str, MediaGenProviderFactory] = {}
    _env_key_mappings: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        name: str,
        provider_class: Optional[Type[MediaGenProvider]] = None,
        factory: Optional[MediaGenProviderFactory] = None,
        env_key: Optional[str] = None,
    ):
        """Register a media generation provider.

        Can be used as a decorator or called directly.
        """

        def decorator(provider_cls: Type[MediaGenProvider]) -> Type[MediaGenProvider]:
            provider_name = name.lower()
            cls._providers[provider_name] = provider_cls
            if factory:
                cls._factories[provider_name] = factory
            if env_key:
                cls._env_key_mappings[provider_name] = env_key
            logger.info(f"Registered media gen provider: {provider_name}")
            return provider_cls

        if provider_class:
            return decorator(provider_class)
        return decorator

    @classmethod
    def get_provider_class(cls, name: str) -> Optional[Type[MediaGenProvider]]:
        return cls._providers.get(name.lower())

    @classmethod
    def get_env_key(cls, name: str) -> Optional[str]:
        return cls._env_key_mappings.get(name.lower())

    @classmethod
    def create_provider(
        cls,
        name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[MediaGenProvider]:
        """Create a provider instance by name."""
        provider_name = name.lower()

        factory = cls._factories.get(provider_name)
        if factory:
            return factory(api_key=api_key, base_url=base_url, **kwargs)

        provider_class = cls._providers.get(provider_name)
        if provider_class:
            return provider_class(api_key=api_key or "", base_url=base_url, **kwargs)

        return None

    @classmethod
    def list_providers(cls) -> Dict[str, Type[MediaGenProvider]]:
        return cls._providers.copy()

    @classmethod
    def has_provider(cls, name: str) -> bool:
        return name.lower() in cls._providers
