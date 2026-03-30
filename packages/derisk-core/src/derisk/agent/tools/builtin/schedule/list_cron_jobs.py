"""
ListCronJobs Tool - 列出定时任务工具
"""

import logging
from typing import Any, Dict, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


class ListCronJobsTool(ToolBase):
    """列出定时任务工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_cron_jobs",
            display_name="List Scheduled Tasks",
            description="List all scheduled tasks (cron jobs)",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["schedule", "cron", "list"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled_only": {
                    "type": "boolean",
                    "description": "Only show enabled tasks",
                    "default": False,
                }
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """列出定时任务"""
        try:
            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                return ToolResult.fail(error="SystemApp not initialized", tool_name=self.name)

            from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
            from derisk_serve.cron.service.service import Service

            service = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
            if not service:
                return ToolResult.fail(error="Cron service not initialized", tool_name=self.name)

            enabled_only = args.get("enabled_only", False)
            jobs = await service.list_jobs()

            if enabled_only:
                jobs = [job for job in jobs if job.enabled]

            if not jobs:
                return ToolResult.ok(
                    output="No scheduled tasks found",
                    tool_name=self.name,
                    metadata={"total": 0}
                )

            lines = [f"Found {len(jobs)} scheduled tasks:\n"]
            for job in jobs:
                status = "Enabled" if job.enabled else "Disabled"
                lines.append(f"  - [{job.id}] {job.name}: {status}")
                if job.description:
                    lines.append(f"    Description: {job.description}")
                lines.append(f"    Schedule: {job.schedule.kind.value}")

            return ToolResult.ok(
                output="\n".join(lines),
                tool_name=self.name,
                metadata={"total": len(jobs)}
            )

        except Exception as e:
            logger.error(f"[ListCronJobsTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)