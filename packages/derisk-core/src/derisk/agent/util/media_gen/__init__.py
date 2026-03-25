"""Media Generation Provider module.

Provides pluggable providers for image/video generation (DALL-E, Stable Diffusion, Sora, etc.).
"""

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.config import MediaGenConfig
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

# Auto-register built-in providers on import
from derisk.agent.util.media_gen import openai_image_provider  # noqa: F401
from derisk.agent.util.media_gen import openai_video_provider  # noqa: F401

__all__ = [
    "MediaGenProvider",
    "MediaGenResult",
    "MediaGenConfig",
    "MediaGenProviderRegistry",
]
