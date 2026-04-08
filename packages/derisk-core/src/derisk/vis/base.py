"""Base class for vis protocol module."""

import json
import logging
from typing import Any, Dict, Optional, Type

import orjson

from derisk.util.json_utils import serialize

logger = logging.getLogger(__name__)


class Vis:
    """Vis protocol base class."""

    # Class-level registry for vis components
    _registry: Dict[str, "Vis"] = {}

    def __init__(self, **kwargs):
        """
        vis init
        Args:
            **kwargs:
        """

    def render_prompt(self) -> Optional[str]:
        """Return the prompt for the vis protocol."""
        return None

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the vis protocol.

        Display corresponding content using vis protocol

        Args:
            **kwargs:

        Returns:
        vis protocol text
        """
        return kwargs["content"]

    async def generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the vis protocol.

        Display corresponding content using vis protocol
        Args:
            **kwargs:

        Returns:
        vis protocol text
        """
        return self.sync_generate_param(**kwargs)

    def sync_display(self, **kwargs) -> Optional[str]:
        """Display the content using the vis protocol."""
        # content = json.dumps(
        #     self.sync_generate_param(**kwargs), default=serialize, ensure_ascii=False
        # )
        content = orjson.dumps(
            self.sync_generate_param(**kwargs), default=serialize
        ).decode()
        return f"```{self.vis_tag()}\n{content}\n```"

    async def display(self, **kwargs) -> Optional[str]:
        """Display the content using the vis protocol."""
        return self.sync_display(**kwargs)

    @classmethod
    def vis_tag(cls) -> str:
        """Return current vis protocol module tag name."""
        return ""

    @classmethod
    def of(cls, vis_type: str) -> Optional["Vis"]:
        """
        Factory method to get a vis component by type.

        Args:
            vis_type: The type of vis component (e.g., 'code', 'text', 'chart')

        Returns:
            Vis instance or None if not found
        """
        # First check the registry
        if vis_type in cls._registry:
            return cls._registry[vis_type]

        # Try to import and register from derisk_ext.vis
        try:
            from derisk_ext.vis.derisk.derisk_vis_manage import VisManager

            vis_manager = VisManager()
            vis_class = vis_manager.get_vis_class(vis_type)
            if vis_class:
                instance = vis_class()
                cls._registry[vis_type] = instance
                return instance
        except ImportError:
            pass

        # Try common vis types by direct import
        vis_map = {
            "code": ("derisk_ext.vis.common.tags.derisk_code", "CodeSpace"),
            "text": ("derisk_ext.vis.derisk.tags.drsk_content", "DrskContent"),
            "chart": ("derisk_ext.vis.gptvis.tags.vis_chart", "VisChart"),
            "thinking": (
                "derisk_ext.vis.common.tags.derisk_thinking",
                "DeriskThinking",
            ),
            "plan": ("derisk_ext.vis.common.tags.derisk_plan", "AgentPlan"),
            "todo_list": ("derisk_ext.vis.common.tags.derisk_todo_list", "TodoList"),
            "d-attach": ("derisk_ext.vis.common.tags.derisk_attach", "DeriskAttach"),
            "d-sql-query": ("derisk_ext.vis.common.tags.derisk_sql_query", "DeriskSqlQuery"),
        }

        if vis_type in vis_map:
            try:
                module_path, class_name = vis_map[vis_type]
                module = __import__(module_path, fromlist=[class_name])
                vis_class = getattr(module, class_name)
                instance = vis_class()
                cls._registry[vis_type] = instance
                return instance
            except (ImportError, AttributeError) as e:
                logger.warning(f"Failed to load vis component '{vis_type}': {e}")

        return None

    @classmethod
    def register(cls, vis_type: str, instance: "Vis") -> None:
        """
        Register a vis component.

        Args:
            vis_type: The type identifier
            instance: The Vis instance
        """
        cls._registry[vis_type] = instance
