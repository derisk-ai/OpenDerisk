"""Media Generation Tools module.

Provides tools for AI-powered image and video generation:
- generate_image: Generate images using DALL-E, Stable Diffusion, etc.
- generate_video: Generate videos using Sora, Runway, etc.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_media_gen_tools(registry: "ToolRegistry") -> None:
    """Register media generation tools."""
    from .media_gen_tools import GenerateImageTool, GenerateVideoTool

    registry.register(GenerateImageTool())
    registry.register(GenerateVideoTool())
