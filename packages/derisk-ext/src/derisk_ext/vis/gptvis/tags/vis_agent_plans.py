"""Viss Agent Plans."""

from typing import Optional, Dict, Any

from derisk.vis.base import Vis


class VisAgentPlans(Vis):
    """VisAgentPlans."""

    def sync_display(self, **kwargs) -> str:
        """Display the content using the vis protocol."""
        content = kwargs.get("content")
        from derisk.vis.schema import VisPlansContent

        try:
            tasks = content.get("tasks")
            if tasks:
                return "\n".join(
                    [
                        f"- [{item.get('task_id', '')}]{item.get('task_name', '')}     @{item.get('agent_name', '')}"
                        for item in tasks
                    ]
                )
            return str(content)
        except Exception as e:
            return str(content)

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "agent-plans"
