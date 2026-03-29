"""
DeleteCronJob Tool - 删除定时任务工具
"""

import logging
from typing import Any, Dict, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


class DeleteCronJobTool(ToolBase):
    """删除定时任务工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="delete_cron_job",
            display_name="Delete Scheduled Task",
            description="Delete a scheduled task (cron job)",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["schedule", "cron", "delete"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The scheduled task ID to delete",
                }
            },
            "required": ["job_id"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """删除定时任务"""
        try:
            job_id = args.get("job_id")
            if not job_id:
                return ToolResult.fail(error="job_id is required", tool_name=self.name)

            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                return ToolResult.fail(
                    error="SystemApp not initialized", tool_name=self.name
                )

            from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
            from derisk_serve.cron.service.service import Service

            service = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
            if not service:
                return ToolResult.fail(
                    error="Cron service not initialized", tool_name=self.name
                )

            await service.delete_job(job_id)

            return ToolResult.ok(
                output=f"Successfully deleted scheduled task: {job_id}",
                tool_name=self.name,
                metadata={"deleted_job_id": job_id},
            )

        except Exception as e:
            logger.error(f"[DeleteCronJobTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
