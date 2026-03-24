"""OpenAI Video Generation Provider (Sora).

Implements video generation via the OpenAI API.
Video generation uses an async job pattern: submit -> poll -> download.
"""

import asyncio
import logging
from typing import Any, List, Optional

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)


@MediaGenProviderRegistry.register(name="openai_video", env_key="OPENAI_API_KEY")
class OpenAIVideoProvider(MediaGenProvider):
    """OpenAI Sora video generation provider."""

    def supported_image_models(self) -> List[str]:
        return []

    def supported_video_models(self) -> List[str]:
        return ["sora"]

    async def generate_image(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        raise NotImplementedError("OpenAI video provider does not support image generation")

    async def generate_video(
        self,
        prompt: str,
        model: str = "sora",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate a video using OpenAI Sora API.

        Args:
            prompt: Text description of the video.
            model: Model to use (default "sora").
            **kwargs: Additional params:
                - duration: Duration in seconds (default 5).
                - resolution: "720p", "1080p" (default "1080p").
                - aspect_ratio: "16:9", "9:16", "1:1" (default "16:9").
                - timeout: Max wait time in seconds (default 300).
        """
        try:
            import httpx
        except ImportError:
            raise ImportError(
                "httpx package is required for video generation. "
                "Install with: pip install httpx"
            )

        duration = kwargs.get("duration", 5)
        resolution = kwargs.get("resolution", "1080p")
        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        timeout = kwargs.get("timeout", 300)

        base_url = self.base_url or "https://api.openai.com/v1"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Step 1: Submit generation job
        logger.info(
            f"[OpenAIVideoProvider] Submitting video job: model={model}, "
            f"duration={duration}s, resolution={resolution}"
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            submit_resp = await client.post(
                f"{base_url}/videos/generations",
                headers=headers,
                json={
                    "model": model,
                    "prompt": prompt,
                    "duration": duration,
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio,
                },
            )
            submit_resp.raise_for_status()
            job = submit_resp.json()
            job_id = job.get("id")
            if not job_id:
                raise ValueError(f"Video generation API returned no job ID: {job}")

            # Step 2: Poll until complete
            logger.info(f"[OpenAIVideoProvider] Polling job {job_id}...")
            poll_interval = 5
            elapsed = 0

            while elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                status_resp = await client.get(
                    f"{base_url}/videos/generations/{job_id}",
                    headers=headers,
                )
                status_resp.raise_for_status()
                status = status_resp.json()

                state = status.get("status", "")
                if state == "completed":
                    video_url = status.get("url") or status.get("output", {}).get("url")
                    if not video_url:
                        raise ValueError(f"Job completed but no video URL: {status}")

                    # Step 3: Download video
                    logger.info(f"[OpenAIVideoProvider] Downloading video from {video_url}")
                    dl_resp = await client.get(video_url)
                    dl_resp.raise_for_status()

                    return MediaGenResult(
                        data=dl_resp.content,
                        format="mp4",
                        mime_type="video/mp4",
                        duration_seconds=float(duration),
                        metadata={
                            "model": model,
                            "resolution": resolution,
                            "aspect_ratio": aspect_ratio,
                            "job_id": job_id,
                        },
                    )
                elif state in ("failed", "cancelled"):
                    error = status.get("error", "Unknown error")
                    raise RuntimeError(f"Video generation failed: {error}")

                logger.debug(
                    f"[OpenAIVideoProvider] Job {job_id} status: {state} ({elapsed}s elapsed)"
                )

            raise TimeoutError(
                f"Video generation timed out after {timeout}s (job_id={job_id})"
            )
