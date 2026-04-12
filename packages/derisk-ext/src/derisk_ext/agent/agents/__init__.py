"""专业 Agent 模块.

提供特定领域的专业 Agent 实现:
- FrameGenAgent: 首帧图片生成 Agent
- VideoGenAgent: 视频生成 Agent
"""

from .frame_gen_agent import FrameGenAgent
from .video_gen_agent import VideoGenAgent

__all__ = [
    "FrameGenAgent",
    "VideoGenAgent",
]