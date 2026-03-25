"""Media Generation configuration model."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MediaGenConfig(BaseModel):
    """Configuration for media generation providers."""

    provider: str = Field(default="openai", description="Default provider name")
    api_key: Optional[str] = Field(default=None, description="Provider API key")
    base_url: Optional[str] = Field(default=None, description="Custom API endpoint")
    default_image_model: str = Field(default="dall-e-3", description="Default image model")
    default_video_model: str = Field(default="sora", description="Default video model")
    max_concurrent_requests: int = Field(default=3, description="Max concurrent generation requests")
    extra_kwargs: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific kwargs")
