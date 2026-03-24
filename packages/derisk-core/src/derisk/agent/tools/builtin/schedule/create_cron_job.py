"""
CreateCronJob Tool - 创建定时任务工具

允许 Agent 创建定时任务（cron job），任务将在指定时间自动执行。
"""

import logging
from typing import Any, Dict, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


class CreateCronJobTool(ToolBase):
    """
    创建定时任务工具

    支持三种调度类型：
    - 'cron': 标准 cron 表达式 (e.g., '0 9 * * *' 表示每天 9 点)
    - 'every': 固定间隔（分钟）(e.g., every 60 分钟)
    - 'at': 指定时间执行一次 (ISO 格式)
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="create_cron_job",
            display_name="Create Scheduled Task",
            description="""Create a scheduled task (cron job) that will be executed automatically at specified times.

This tool allows you to set up recurring or one-time tasks for the user.

Schedule types:
- 'cron': Standard cron expression (e.g., '0 9 * * *' for every day at 9 AM)
- 'every': Fixed interval in minutes (e.g., every 60 minutes)
- 'at': One-time execution at a specific datetime (ISO format)

Session modes:
- 'isolated': Each execution creates a new isolated session (default)
- 'shared': Use a shared session across all executions

IMPORTANT: The 'message' parameter is the instruction/command that will be sent to the Agent when the task triggers. The Agent will receive this message and act on it. This is NOT a template - variables like {{now}} or {{date}} are NOT supported. Just write a clear instruction for the Agent to execute.

Examples:
1. Daily reminder: schedule_kind='cron', cron_expr='0 9 * * *', message='Remind the user to do daily check-in'
2. Hourly system check: schedule_kind='every', every_minutes=60, message='Check the system status and report any issues'
3. Current time reminder: schedule_kind='every', every_minutes=1, message='Tell the user the current time'
4. One-time greeting: schedule_kind='at', at_time='2024-12-25T09:00:00', message='Send a Christmas greeting to the user'
""",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["schedule", "cron", "timer", "automation"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the scheduled task.",
                },
                "schedule_kind": {
                    "type": "string",
                    "enum": ["cron", "every", "at"],
                    "description": "Type of schedule ('cron', 'every', or 'at').",
                },
                "message": {
                    "type": "string",
                    "description": "The instruction to send to the Agent when the task triggers. Write a clear command for the Agent to execute.",
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression (e.g., '0 9 * * *') for 'cron' schedule.",
                },
                "every_minutes": {
                    "type": "integer",
                    "description": "Interval in minutes for 'every' schedule.",
                },
                "at_time": {
                    "type": "string",
                    "description": "ISO datetime string for 'at' schedule.",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for the schedule (default: system timezone).",
                },
                "enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether the job is enabled immediately.",
                },
                "session_mode": {
                    "type": "string",
                    "enum": ["isolated", "shared"],
                    "default": "shared",
                    "description": "Session mode for agent execution.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of the job.",
                },
            },
            "required": ["name", "schedule_kind", "message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """执行创建定时任务"""
        try:
            # 获取参数
            name = args.get("name")
            schedule_kind = args.get("schedule_kind")
            message = args.get("message")

            if not name or not schedule_kind or not message:
                return ToolResult.fail(
                    error="Missing required parameters: name, schedule_kind, or message",
                    tool_name=self.name,
                )

            # 获取 cron 服务
            cron_service = self._get_cron_service()
            if not cron_service:
                return ToolResult.fail(
                    error="Cron service not available. Please check system configuration.",
                    tool_name=self.name,
                )

            # 构建任务请求
            job_create = await self._build_job_create(args, context)
            if job_create is None:
                return ToolResult.fail(
                    error="Failed to build job creation request",
                    tool_name=self.name,
                )

            # 创建任务
            job = await cron_service.add_job(job_create)

            return ToolResult.ok(
                output=f"Successfully created scheduled task '{name}' (ID: {job.id}). "
                f"The task will be executed automatically according to the schedule: {schedule_kind}",
                tool_name=self.name,
                metadata={
                    "job_id": job.id,
                    "name": name,
                    "schedule_kind": schedule_kind,
                },
            )

        except Exception as e:
            logger.error(f"Failed to create cron job: {e}")
            return ToolResult.fail(
                error=f"Failed to create scheduled task: {str(e)}",
                tool_name=self.name,
            )

    def _get_cron_service(self):
        """获取 cron 服务实例"""
        try:
            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                return None

            from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
            from derisk_serve.cron.service.service import Service

            return system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
        except Exception as e:
            logger.debug(f"Failed to get cron service: {e}")
            return None

    async def _build_job_create(self, args: Dict[str, Any], context: Optional[Any]):
        """构建任务创建请求"""
        try:
            from derisk.cron import (
                CronJobCreate,
                CronPayload,
                CronSchedule,
                PayloadKind,
                ScheduleKind,
                SessionMode,
            )

            schedule_kind = args.get("schedule_kind")

            # 验证 schedule_kind
            try:
                schedule_kind_enum = ScheduleKind(schedule_kind)
            except ValueError:
                return None

            # 验证 session_mode
            session_mode = args.get("session_mode", "shared")
            try:
                session_mode_enum = SessionMode(session_mode)
            except ValueError:
                session_mode_enum = SessionMode.SHARED

            # 构建调度配置
            schedule = CronSchedule(
                kind=schedule_kind_enum,
                tz=args.get("timezone"),
            )

            if schedule_kind_enum == ScheduleKind.CRON:
                cron_expr = args.get("cron_expr")
                if not cron_expr:
                    return None
                schedule.expr = cron_expr
            elif schedule_kind_enum == ScheduleKind.EVERY:
                every_minutes = args.get("every_minutes")
                if not every_minutes:
                    return None
                schedule.every_ms = every_minutes * 60 * 1000
            elif schedule_kind_enum == ScheduleKind.AT:
                at_time = args.get("at_time")
                if not at_time:
                    return None
                schedule.at = at_time

            # 获取 agent_id 和 conv_session_id（如果可用）
            agent_id = None
            conv_session_id = None
            if context:
                # 从 context 获取相关信息
                if hasattr(context, "agent_context") and context.agent_context:
                    agent_id = getattr(context.agent_context, "agent_app_code", None)
                    conv_session_id = getattr(
                        context.agent_context, "conv_session_id", None
                    )

            # 构建负载
            payload = CronPayload(
                kind=PayloadKind.AGENT_TURN,
                message=args.get("message"),
                agent_id=agent_id,
                session_mode=session_mode_enum,
                conv_session_id=conv_session_id,
            )

            return CronJobCreate(
                name=args.get("name"),
                description=args.get("description"),
                enabled=args.get("enabled", True),
                schedule=schedule,
                payload=payload,
            )

        except ImportError as e:
            logger.error(f"Failed to import cron modules: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to build job create: {e}")
            return None
