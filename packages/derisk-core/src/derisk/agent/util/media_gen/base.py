"""Media Generation Provider base classes.

Provides abstract interfaces for image/video generation providers
(DALL-E, Stable Diffusion, Sora, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MediaGenResult:
    """Result of a media generation call."""

    data: bytes
    format: str  # "png", "jpg", "mp4", "webm"
    mime_type: str  # "image/png", "video/mp4"
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None  # for video
    metadata: Dict[str, Any] = field(default_factory=dict)


class MediaGenProvider(ABC):
    """Abstract base class for media generation providers."""

    def __init__(
        self,
        api_key: str = "",
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.extra_kwargs = kwargs

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        model: str,
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate an image from a text prompt."""

    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        model: str,
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate a video from a text prompt."""

    @abstractmethod
    def supported_image_models(self) -> List[str]:
        """List supported image generation models."""

    @abstractmethod
    def supported_video_models(self) -> List[str]:
        """List supported video generation models."""
