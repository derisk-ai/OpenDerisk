"""Skills - 技能系统

可扩展的技能模块，支持技能注册、发现和执行
"""

from .skill_base import (
    SkillBase,
    SkillMetadata,
    SkillContext,
    SkillResult,
    SkillRegistry,
    skill_registry,
    SummarySkill,
    CodeAnalysisSkill,
)
from .video_creation_skill import VideoCreationSkill, VIDEO_CREATION_SKILL_CONTENT

# 注册视频创作技能
skill_registry.register(VideoCreationSkill())

__all__ = [
    "SkillBase",
    "SkillMetadata",
    "SkillContext",
    "SkillResult",
    "SkillRegistry",
    "skill_registry",
    "SummarySkill",
    "CodeAnalysisSkill",
    "VideoCreationSkill",
    "VIDEO_CREATION_SKILL_CONTENT",
]