"""Media Generation Tools module.

Provides tools for AI-powered image and video generation:
- generate_image: Generate images using DALL-E, Wan (万相), Stable Diffusion, etc.
- generate_video: Generate videos using Sora, Seedance (火山引擎), etc.
- analyze_image: Analyze image quality using multimodal LLM
- composite_video: Composite multiple video segments using FFmpeg
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_media_gen_tools(registry: "ToolRegistry") -> None:
    """Register media generation tools."""
    from .media_gen_tools import GenerateImageTool, GenerateVideoTool
    from .analyze_image_tool import AnalyzeImageTool
    from .composite_video_tool import CompositeVideoTool

    registry.register(GenerateImageTool())
    registry.register(GenerateVideoTool())
    registry.register(AnalyzeImageTool())
    registry.register(CompositeVideoTool())
