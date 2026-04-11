"""Aliyun Wan (万相) Image Generation Provider.

Supports wan2.7-image-pro and wan2.7-image models from Aliyun Bailian (阿里云百炼).

Features:
- Text-to-image generation
- Image editing (图生图, 多图参考)
- Sequential image generation (组图生成)
- Interactive editing with bbox
- Custom color palette
- Thinking mode for quality enhancement

API Reference: https://help.aliyun.com/zh/model-studio/wan-image-generation-api-reference
"""

import asyncio
import base64
import logging
import mimetypes
import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import httpx

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)

# Region-specific endpoints
ALIYUN_ENDPOINTS = {
    "beijing": "https://dashscope.aliyuncs.com/api/v1",
    "singapore": "https://dashscope-intl.aliyuncs.com/api/v1",
}


@MediaGenProviderRegistry.register(name="aliyun_wan", env_key="DASHSCOPE_API_KEY")
class AliyunWanProvider(MediaGenProvider):
    """Aliyun Wan (万相) image generation provider.

    Supports:
    - wan2.7-image-pro: Professional version with 4K support
    - wan2.7-image: Faster generation, max 2K
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: Optional[str] = None,
        region: str = "beijing",
        **kwargs: Any,
    ):
        """Initialize Aliyun Wan provider.

        Args:
            api_key: Bailian API key (DASHSCOPE_API_KEY)
            base_url: Custom endpoint (optional)
            region: Region for endpoint selection ("beijing" or "singapore")
            **kwargs: Additional configuration
        """
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = ALIYUN_ENDPOINTS.get(region, ALIYUN_ENDPOINTS["beijing"])

        super().__init__(api_key=api_key, base_url=self.base_url, **kwargs)
        self._http_client: Optional[httpx.AsyncClient] = None

    def supported_image_models(self) -> List[str]:
        """List supported image generation models."""
        return ["wan2.7-image-pro", "wan2.7-image"]

    def supported_video_models(self) -> List[str]:
        """Wan does not support video generation."""
        return []

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=120)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def generate_image(
        self,
        prompt: str,
        model: str = "wan2.7-image-pro",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate an image using Aliyun Wan API.

        Args:
            prompt: Text description of the image (supports Chinese and English)
            model: Model name (wan2.7-image-pro or wan2.7-image)
            **kwargs: Additional parameters:
                - images: List[str] - Reference image URLs for editing
                - bbox_list: List[List[List[int]]] - Bounding boxes for interactive editing
                - enable_sequential: bool - Enable sequential mode for group images
                - n: int - Number of images to generate (1-4 for normal, 1-12 for sequential)
                - size: str - Resolution (1K, 2K, 4K) or pixel dimensions
                - watermark: bool - Add AI watermark
                - thinking_mode: bool - Enable thinking mode for better quality
                - color_palette: List[Dict] - Custom color palette
                - seed: int - Random seed for reproducibility
                - async_mode: bool - Use async API (for long tasks)
                - timeout: int - Max wait time for async mode

        Returns:
            MediaGenResult containing the generated image data
        """
        # Validate model
        if model not in self.supported_image_models():
            logger.warning(f"Model {model} not in supported list, using wan2.7-image-pro")
            model = "wan2.7-image-pro"

        # Extract parameters
        images = kwargs.get("images", [])
        bbox_list = kwargs.get("bbox_list")
        enable_sequential = kwargs.get("enable_sequential", False)
        n = kwargs.get("n", 1)
        size = kwargs.get("size", "2K")
        watermark = kwargs.get("watermark", False)
        thinking_mode = kwargs.get("thinking_mode", True)
        color_palette = kwargs.get("color_palette")
        seed = kwargs.get("seed")

        # Build message content
        content: List[Dict[str, Any]] = [{"text": prompt}]

        # Add reference images
        for img_url in images:
            content.append({"image": img_url})

        # Build parameters
        parameters: Dict[str, Any] = {
            "size": size,
            "n": n,
            "watermark": watermark,
        }

        if thinking_mode and not images and not enable_sequential:
            # Thinking mode only for text-to-image without sequential
            parameters["thinking_mode"] = True

        if enable_sequential:
            parameters["enable_sequential"] = True

        if bbox_list:
            parameters["bbox_list"] = bbox_list

        if color_palette:
            parameters["color_palette"] = color_palette

        if seed:
            parameters["seed"] = seed

        # Choose sync or async mode
        async_mode = kwargs.get("async_mode", False)
        timeout = kwargs.get("timeout", 120)

        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            if async_mode:
                return await self._async_generate(
                    client, headers, model, content, parameters, timeout
                )
            else:
                return await self._sync_generate(
                    client, headers, model, content, parameters, timeout
                )
        except Exception as e:
            logger.error(f"[AliyunWanProvider] Generation failed: {e}", exc_info=True)
            raise

    async def _sync_generate(
        self,
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        model: str,
        content: List[Dict],
        parameters: Dict[str, Any],
        timeout: int,
    ) -> MediaGenResult:
        """Synchronous generation (returns immediately or within timeout)."""
        url = f"{self.base_url}/services/aigc/multimodal-generation/generation"

        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }

        logger.info(f"[AliyunWanProvider] Sync generation request: model={model}")

        response = await client.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()

        # Parse response
        output = result.get("output", {})
        choices = output.get("choices", [])

        if not choices:
            raise ValueError(f"No choices in response: {result}")

        # Extract first image
        image_urls = []
        revised_prompt = None
        for choice in choices:
            message = choice.get("message", {})
            for item in message.get("content", []):
                if item.get("type") == "image":
                    image_urls.append(item.get("image", ""))
                if item.get("text"):
                    revised_prompt = item.get("text")

        if not image_urls:
            raise ValueError(f"No images in response: {result}")

        # Download first image
        first_image_url = image_urls[0]
        logger.info(f"[AliyunWanProvider] Downloading image from {first_image_url}")

        img_response = await client.get(first_image_url, timeout=30)
        img_response.raise_for_status()
        image_data = img_response.content

        # Parse size from usage
        usage = result.get("usage", {})
        size_str = usage.get("size", "")

        return MediaGenResult(
            data=image_data,
            format="png",
            mime_type="image/png",
            metadata={
                "model": model,
                "prompt": parameters.get("prompt", ""),
                "revised_prompt": revised_prompt,
                "image_urls": image_urls,
                "n": len(image_urls),
                "size": size_str,
                "request_id": result.get("request_id"),
            },
        )

    async def _async_generate(
        self,
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        model: str,
        content: List[Dict],
        parameters: Dict[str, Any],
        timeout: int,
    ) -> MediaGenResult:
        """Asynchronous generation (submit task, poll for result)."""
        # Add async header
        async_headers = {**headers, "X-DashScope-Async": "enable"}
        url = f"{self.base_url}/services/aigc/image-generation/generation"

        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }

        # Step 1: Submit task
        logger.info(f"[AliyunWanProvider] Submitting async task: model={model}")

        response = await client.post(url, headers=async_headers, json=payload, timeout=30)
        response.raise_for_status()
        task_result = response.json()

        task_id = task_result.get("output", {}).get("task_id")
        if not task_id:
            raise ValueError(f"No task_id in response: {task_result}")

        logger.info(f"[AliyunWanProvider] Task submitted: task_id={task_id}")

        # Step 2: Poll for completion
        poll_url = f"{self.base_url}/tasks/{task_id}"
        poll_interval = 5
        elapsed = 0

        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_response = await client.get(poll_url, headers=headers, timeout=30)
            status_response.raise_for_status()
            status = status_response.json()

            task_status = status.get("output", {}).get("task_status", "UNKNOWN")
            logger.debug(f"[AliyunWanProvider] Polling: status={task_status}, elapsed={elapsed}s")

            if task_status == "SUCCEEDED":
                # Extract results
                output = status.get("output", {})
                choices = output.get("choices", [])

                image_urls = []
                revised_prompt = None
                for choice in choices:
                    message = choice.get("message", {})
                    for item in message.get("content", []):
                        if item.get("type") == "image":
                            image_urls.append(item.get("image", ""))
                        if item.get("text"):
                            revised_prompt = item.get("text")

                if not image_urls:
                    raise ValueError(f"No images in completed task: {status}")

                # Download first image
                first_image_url = image_urls[0]
                img_response = await client.get(first_image_url, timeout=30)
                img_response.raise_for_status()
                image_data = img_response.content

                usage = status.get("usage", {})
                size_str = usage.get("size", "")

                return MediaGenResult(
                    data=image_data,
                    format="png",
                    mime_type="image/png",
                    metadata={
                        "model": model,
                        "task_id": task_id,
                        "revised_prompt": revised_prompt,
                        "image_urls": image_urls,
                        "n": len(image_urls),
                        "size": size_str,
                        "request_id": status.get("request_id"),
                    },
                )

            elif task_status == "FAILED":
                error_msg = status.get("output", {}).get("error", "Unknown error")
                raise RuntimeError(f"Async generation failed: {error_msg}")

            elif task_status in ("PENDING", "RUNNING"):
                continue

            else:
                logger.warning(f"[AliyunWanProvider] Unknown status: {task_status}")

        raise TimeoutError(f"Async generation timed out after {timeout}s (task_id={task_id})")

    async def generate_video(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Wan does not support video generation."""
        raise NotImplementedError("Aliyun Wan provider does not support video generation")


__all__ = ["AliyunWanProvider", "ALIYUN_ENDPOINTS"]