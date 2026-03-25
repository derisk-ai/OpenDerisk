"""OpenAI Image Generation Provider (DALL-E 2/3).

Implements image generation via the OpenAI Images API.
"""

import base64
import logging
from typing import Any, List, Optional

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)


@MediaGenProviderRegistry.register(name="openai", env_key="OPENAI_API_KEY")
class OpenAIImageProvider(MediaGenProvider):
    """DALL-E image generation provider."""

    def supported_image_models(self) -> List[str]:
        return ["dall-e-3", "dall-e-2", "gpt-image-1"]

    def supported_video_models(self) -> List[str]:
        return []

    async def generate_image(
        self,
        prompt: str,
        model: str = "dall-e-3",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate an image using OpenAI DALL-E API.

        Args:
            prompt: Text description of the image.
            model: Model to use ("dall-e-3", "dall-e-2", "gpt-image-1").
            **kwargs: Additional params:
                - size: "1024x1024", "1024x1792", "1792x1024" (dall-e-3)
                - quality: "standard", "hd" (dall-e-3)
                - style: "vivid", "natural" (dall-e-3)
                - n: number of images (only 1 for dall-e-3)
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "openai package is required for DALL-E image generation. "
                "Install with: pip install openai"
            )

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        client = AsyncOpenAI(**client_kwargs)

        size = kwargs.get("size", "1024x1024")
        quality = kwargs.get("quality", "standard")
        style = kwargs.get("style", "vivid")

        gen_kwargs: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": 1,
            "response_format": "b64_json",
        }

        if model == "dall-e-3":
            gen_kwargs["quality"] = quality
            gen_kwargs["style"] = style

        logger.info(f"[OpenAIImageProvider] Generating image: model={model}, size={size}")

        response = await client.images.generate(**gen_kwargs)

        image_data_b64 = response.data[0].b64_json
        if not image_data_b64:
            raise ValueError("OpenAI returned empty image data")

        image_bytes = base64.b64decode(image_data_b64)

        # Parse dimensions from size string
        width, height = None, None
        if "x" in size:
            parts = size.split("x")
            width, height = int(parts[0]), int(parts[1])

        metadata: dict[str, Any] = {
            "model": model,
            "size": size,
            "quality": quality,
        }
        if hasattr(response.data[0], "revised_prompt") and response.data[0].revised_prompt:
            metadata["revised_prompt"] = response.data[0].revised_prompt

        return MediaGenResult(
            data=image_bytes,
            format="png",
            mime_type="image/png",
            width=width,
            height=height,
            metadata=metadata,
        )

    async def generate_video(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        raise NotImplementedError("OpenAI image provider does not support video generation")
