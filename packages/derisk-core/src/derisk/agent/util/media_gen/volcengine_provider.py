"""Volcengine (火山引擎) Video Generation Provider.

Supports doubao-seedance models for video generation from text and/or first-frame image.

Features:
- Text-to-video generation
- Image-to-video generation (using first frame)
- Async task polling (create -> poll -> download)
- Duration and camera motion control
- Watermark option

API Reference: https://www.volcengine.com/docs/82379/1521675
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)

# Volcengine endpoints
VOLCENGINE_ENDPOINTS = {
    "beijing": "https://ark.cn-beijing.volces.com/api/v3",
}


@MediaGenProviderRegistry.register(name="volcengine", env_key="ARK_API_KEY")
class VolcengineVideoProvider(MediaGenProvider):
    """Volcengine (火山引擎) video generation provider.

    Supports:
    - doubao-seedance-1-5-pro-251215: Professional video generation model
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: Optional[str] = None,
        region: str = "beijing",
        **kwargs: Any,
    ):
        """Initialize Volcengine provider.

        Args:
            api_key: ARK API key
            base_url: Custom endpoint (optional)
            region: Region for endpoint selection
            **kwargs: Additional configuration
        """
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = VOLCENGINE_ENDPOINTS.get(region, VOLCENGINE_ENDPOINTS["beijing"])

        super().__init__(api_key=api_key, base_url=self.base_url, **kwargs)
        self._http_client: Optional[httpx.AsyncClient] = None

    def supported_image_models(self) -> List[str]:
        """Volcengine does not support image generation."""
        return []

    def supported_video_models(self) -> List[str]:
        """List supported video generation models."""
        return [
            "doubao-seedance-1-5-pro-251215",
            "doubao-seedance-1-5-i2v",  # Image-to-video
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=300)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def generate_image(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Volcengine does not support image generation."""
        raise NotImplementedError("Volcengine provider does not support image generation")

    async def generate_video(
        self,
        prompt: str,
        model: str = "doubao-seedance-1-5-pro-251215",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate a video using Volcengine Seedance API.

        Args:
            prompt: Text description of the video (supports Chinese and English)
            model: Model name
            **kwargs: Additional parameters:
                - first_frame_image_url: str - URL of first frame image (optional)
                - duration: int - Video duration in seconds (default 5)
                - camerafixed: bool - Whether camera is fixed (default False)
                - watermark: bool - Add watermark (default True)
                - timeout: int - Max wait time (default 300)

        Returns:
            MediaGenResult containing the generated video data
        """
        # Validate model
        if model not in self.supported_video_models():
            logger.warning(f"Model {model} not in supported list, using doubao-seedance-1-5-pro")
            model = "doubao-seedance-1-5-pro-251215"

        # Extract parameters
        first_frame_image_url = kwargs.get("first_frame_image_url")
        duration = kwargs.get("duration", 5)
        camerafixed = kwargs.get("camerafixed", False)
        watermark = kwargs.get("watermark", True)
        timeout = kwargs.get("timeout", 300)

        # Build prompt with parameters
        full_prompt = prompt
        if "--duration" not in full_prompt:
            full_prompt = f"{prompt} --duration {duration}"
        if "--camerafixed" not in full_prompt and camerafixed:
            full_prompt = f"{full_prompt} --camerafixed {camerafixed}"
        if "--watermark" not in full_prompt:
            full_prompt = f"{full_prompt} --watermark {watermark}"

        # Build content array
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": full_prompt}
        ]

        # Add first frame image if provided
        if first_frame_image_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": first_frame_image_url}
            })

        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            # Step 1: Submit video generation task
            task_id = await self._submit_task(client, headers, model, content)
            logger.info(f"[VolcengineVideoProvider] Task submitted: task_id={task_id}")

            # Step 2: Poll for completion
            video_url = await self._poll_task(client, headers, task_id, timeout)
            logger.info(f"[VolcengineVideoProvider] Task completed, downloading from {video_url}")

            # Step 3: Download video
            video_data = await self._download_video(client, video_url)

            return MediaGenResult(
                data=video_data,
                format="mp4",
                mime_type="video/mp4",
                duration_seconds=float(duration),
                metadata={
                    "model": model,
                    "task_id": task_id,
                    "prompt": prompt,
                    "first_frame_image_url": first_frame_image_url,
                    "duration": duration,
                },
            )

        except Exception as e:
            logger.error(f"[VolcengineVideoProvider] Generation failed: {e}", exc_info=True)
            raise

    async def _submit_task(
        self,
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        model: str,
        content: List[Dict],
    ) -> str:
        """Submit video generation task and return task_id."""
        url = f"{self.base_url}/content-generation/tasks"

        payload = {
            "model": model,
            "content": content,
        }

        logger.debug(f"[VolcengineVideoProvider] Submitting task: model={model}")

        response = await client.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        task_id = result.get("id")
        if not task_id:
            raise ValueError(f"No task_id in response: {result}")

        return task_id

    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        task_id: str,
        timeout: int,
    ) -> str:
        """Poll task status until completion, return video URL."""
        url = f"{self.base_url}/content-generation/tasks/{task_id}"
        poll_interval = 3
        elapsed = 0

        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            response = await client.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            status = result.get("status", "UNKNOWN")
            logger.debug(f"[VolcengineVideoProvider] Polling: status={status}, elapsed={elapsed}s")

            if status == "succeeded":
                # Extract video URL
                output = result.get("output", {})
                video_url = output.get("video_url")

                # Try alternative paths
                if not video_url:
                    video_url = output.get("url")

                if not video_url:
                    # Check for choices format
                    choices = result.get("choices", [])
                    if choices:
                        for choice in choices:
                            message = choice.get("message", {})
                            for item in message.get("content", []):
                                if item.get("type") == "video":
                                    video_url = item.get("video")
                                    break

                if not video_url:
                    raise ValueError(f"Task succeeded but no video URL: {result}")

                return video_url

            elif status == "failed":
                error = result.get("error", "Unknown error")
                raise RuntimeError(f"Video generation failed: {error}")

            elif status in ("pending", "running", "PENDING", "RUNNING"):
                continue

            else:
                logger.warning(f"[VolcengineVideoProvider] Unknown status: {status}")

        raise TimeoutError(f"Video generation timed out after {timeout}s (task_id={task_id})")

    async def _download_video(
        self,
        client: httpx.AsyncClient,
        video_url: str,
    ) -> bytes:
        """Download video from URL."""
        response = await client.get(video_url, timeout=60)
        response.raise_for_status()
        return response.content


__all__ = ["VolcengineVideoProvider", "VOLCENGINE_ENDPOINTS"]