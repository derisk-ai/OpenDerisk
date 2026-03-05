"""
Agent Skill System - Inspired by opencode skill patterns.

This module provides:
- Skill: Base class for agent skills
- SkillRegistry: Central registry for skills
- SkillManager: Skill lifecycle management
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union

logger = logging.getLogger(__name__)


class SkillType(str, Enum):
    """Skill type classification."""

    BUILTIN = "builtin"
    CUSTOM = "custom"
    EXTERNAL = "external"
    PLUGIN = "plugin"


class SkillStatus(str, Enum):
    """Skill status."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    LOADING = "loading"
    ERROR = "error"


@dataclass
class SkillMetadata:
    """Metadata for a skill."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    skill_type: SkillType = SkillType.CUSTOM
    priority: int = 0
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "skill_type": self.skill_type.value,
            "priority": self.priority,
            "enabled": self.enabled,
        }


class Skill(ABC):
    """
    Base class for agent skills.

    Skills are modular capabilities that can be added to agents.
    Inspired by opencode's skill system.
    """

    def __init__(self, metadata: Optional[SkillMetadata] = None):
        self._metadata = metadata or SkillMetadata(
            name=self.__class__.__name__,
            description=self.__doc__ or "",
        )
        self._status = SkillStatus.DISABLED
        self._context: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        """Get skill name."""
        return self._metadata.name

    @property
    def description(self) -> str:
        """Get skill description."""
        return self._metadata.description

    @property
    def metadata(self) -> SkillMetadata:
        """Get skill metadata."""
        return self._metadata

    @property
    def status(self) -> SkillStatus:
        """Get skill status."""
        return self._status

    @property
    def is_enabled(self) -> bool:
        """Check if skill is enabled."""
        return self._status == SkillStatus.ENABLED

    def set_context(self, key: str, value: Any) -> None:
        """Set context value."""
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get context value."""
        return self._context.get(key, default)

    async def initialize(self) -> bool:
        """
        Initialize the skill.

        Returns:
            True if initialization succeeded
        """
        self._status = SkillStatus.LOADING
        try:
            success = await self._do_initialize()
            self._status = SkillStatus.ENABLED if success else SkillStatus.ERROR
            return success
        except Exception as e:
            logger.error(f"Skill {self.name} initialization failed: {e}")
            self._status = SkillStatus.ERROR
            return False

    async def shutdown(self) -> None:
        """Shutdown the skill."""
        try:
            await self._do_shutdown()
        except Exception as e:
            logger.error(f"Skill {self.name} shutdown failed: {e}")
        finally:
            self._status = SkillStatus.DISABLED

    @abstractmethod
    async def _do_initialize(self) -> bool:
        """Implementation of initialization."""
        return True

    async def _do_shutdown(self) -> None:
        """Implementation of shutdown."""
        pass

    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any:
        """Execute the skill."""
        pass

    def __repr__(self) -> str:
        return f"Skill(name={self.name}, status={self.status.value})"


class FunctionSkill(Skill):
    """
    A skill that wraps a simple function.

    Example:
        @skill("calculate")
        async def calculate(expression: str) -> float:
            return eval(expression)
    """

    def __init__(
        self,
        func: Callable,
        name: str,
        description: str = "",
        metadata: Optional[SkillMetadata] = None,
    ):
        super().__init__(
            metadata
            or SkillMetadata(
                name=name,
                description=description or func.__doc__ or "",
            )
        )
        self._func = func

    async def _do_initialize(self) -> bool:
        return True

    async def execute(self, *args, **kwargs) -> Any:
        """Execute the wrapped function."""
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(self._func):
            return await self._func(*args, **kwargs)
        else:
            return self._func(*args, **kwargs)


class SkillRegistry:
    """
    Central registry for skills.

    Manages skill registration, discovery, and lifecycle.
    """

    _instance: Optional["SkillRegistry"] = None
    _skills: Dict[str, Skill] = {}
    _metadata: Dict[str, SkillMetadata] = {}

    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills = {}
            cls._instance._metadata = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> "SkillRegistry":
        """Get singleton instance."""
        return cls()

    def register(
        self,
        skill: Union[Skill, Type[Skill], Callable],
        name: Optional[str] = None,
        description: str = "",
        metadata: Optional[SkillMetadata] = None,
    ) -> "SkillRegistry":
        """Register a skill."""
        if callable(skill) and not isinstance(skill, type):
            if name is None:
                name = skill.__name__
            skill = FunctionSkill(skill, name, description, metadata)
        elif isinstance(skill, type):
            skill = skill(metadata)

        self._skills[skill.name] = skill
        self._metadata[skill.name] = skill.metadata
        logger.debug(f"Registered skill: {skill.name}")
        return self

    def unregister(self, name: str) -> "SkillRegistry":
        """Unregister a skill."""
        if name in self._skills:
            del self._skills[name]
            del self._metadata[name]
            logger.debug(f"Unregistered skill: {name}")
        return self

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)

    def get_metadata(self, name: str) -> Optional[SkillMetadata]:
        """Get skill metadata by name."""
        return self._metadata.get(name)

    def list(
        self,
        skill_type: Optional[SkillType] = None,
        enabled_only: bool = True,
    ) -> List[Skill]:
        """List registered skills."""
        results = []
        for skill in self._skills.values():
            if enabled_only and not skill.is_enabled:
                continue
            if skill_type and skill.metadata.skill_type != skill_type:
                continue
            results.append(skill)
        return sorted(results, key=lambda s: s.metadata.priority)

    def list_metadata(
        self,
        skill_type: Optional[SkillType] = None,
    ) -> List[SkillMetadata]:
        """List skill metadata."""
        skills = self.list(skill_type=skill_type, enabled_only=False)
        return [s.metadata for s in skills]

    async def initialize_all(self) -> Dict[str, bool]:
        """Initialize all registered skills."""
        results = {}
        for name, skill in self._skills.items():
            results[name] = await skill.initialize()
        return results

    async def shutdown_all(self) -> None:
        """Shutdown all skills."""
        for skill in self._skills.values():
            await skill.shutdown()

    async def execute(self, name: str, *args, **kwargs) -> Any:
        """Execute a skill by name."""
        skill = self.get(name)
        if skill is None:
            raise ValueError(f"Skill not found: {name}")
        if not skill.is_enabled:
            raise RuntimeError(f"Skill is not enabled: {name}")
        return await skill.execute(*args, **kwargs)


def skill(
    name: Optional[str] = None,
    description: str = "",
    metadata: Optional[SkillMetadata] = None,
):
    """
    Decorator to register a function as a skill.

    Usage:
        @skill("search")
        async def search_web(query: str) -> List[str]:
            return ["result1", "result2"]
    """

    def decorator(func: Callable) -> Callable:
        skill_name = name or func.__name__
        registry = SkillRegistry.get_instance()
        registry.register(func, skill_name, description, metadata)
        func._skill_name = skill_name
        return func

    if callable(name):
        func = name
        name = func.__name__
        return decorator(func)

    return decorator


class SkillManager:
    """
    Skill lifecycle manager.

    Provides high-level skill management operations.
    """

    def __init__(self, registry: Optional[SkillRegistry] = None):
        self._registry = registry or SkillRegistry.get_instance()

    @property
    def registry(self) -> SkillRegistry:
        """Get the skill registry."""
        return self._registry

    async def load_skill(
        self,
        skill_path: str,
        name: Optional[str] = None,
    ) -> Optional[Skill]:
        """
        Load a skill from a module path.

        Args:
            skill_path: Module path (e.g., "mypackage.skills.search")
            name: Optional skill name override

        Returns:
            Loaded skill or None if loading failed
        """
        try:
            import importlib

            module = importlib.import_module(skill_path)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Skill)
                    and attr is not Skill
                ):
                    skill_instance = attr()
                    self._registry.register(skill_instance)
                    return skill_instance

            logger.warning(f"No Skill class found in {skill_path}")
            return None

        except Exception as e:
            logger.error(f"Failed to load skill from {skill_path}: {e}")
            return None

    async def load_skills_from_config(
        self,
        config: Dict[str, Any],
    ) -> Dict[str, bool]:
        """
        Load skills from configuration.

        Args:
            config: Configuration dict with skill definitions

        Returns:
            Dict mapping skill names to initialization status
        """
        results = {}

        skills_config = config.get("skills", {})
        for skill_name, skill_config in skills_config.items():
            if isinstance(skill_config, str):
                skill_path = skill_config
                skill_kwargs = {}
            else:
                skill_path = skill_config.get("path", "")
                skill_kwargs = {k: v for k, v in skill_config.items() if k != "path"}

            if skill_path:
                skill = await self.load_skill(skill_path, skill_name)
                if skill:
                    results[skill_name] = await skill.initialize()
                else:
                    results[skill_name] = False

        return results

    def create_skill_from_function(
        self,
        func: Callable,
        name: str,
        description: str = "",
        **metadata_kwargs,
    ) -> Skill:
        """Create a skill from a function."""
        metadata = SkillMetadata(
            name=name,
            description=description or func.__doc__ or "",
            **metadata_kwargs,
        )
        skill = FunctionSkill(func, name, description, metadata)
        self._registry.register(skill)
        return skill


def create_skill_registry() -> SkillRegistry:
    """Factory function to create a skill registry."""
    return SkillRegistry.get_instance()


def create_skill_manager(registry: Optional[SkillRegistry] = None) -> SkillManager:
    """Factory function to create a skill manager."""
    return SkillManager(registry)
