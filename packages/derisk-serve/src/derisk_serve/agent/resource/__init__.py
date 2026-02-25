"""Agent resource module."""

from .derisk_skill import (
    DeriskSkillResource,
    DeriskSkillResourceParameters,
    register_derisk_skill_resource,
)

__all__ = [
    "DeriskSkillResource",
    "DeriskSkillResourceParameters",
    "register_derisk_skill_resource",
]