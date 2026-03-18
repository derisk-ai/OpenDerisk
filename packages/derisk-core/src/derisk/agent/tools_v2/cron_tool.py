"""
Cron Job Tool - 定时任务创建工具

迁移自 derisk-serve/cron/tools/create_cron_job.py
作为统一工具框架的内置工具，允许 Agent 创建定时任务
"""

import logging
from typing import Dict, Any, Optional

from .tool_base import ToolBase, ToolMetadata, ToolResult, ToolCategory, ToolRiskLevel

logger = logging.getLogger(__name__)


class CreateCronJobTool(ToolBase):
    """
    定时任务创建工具

    允许 Agent 在对话过程中创建定时任务，支持多种调度方式：
    - cron: 标准 cron 表达式
    - every: 固定间隔执行
    - at: 一次性定时执行

    示例:
        tool = CreateCronJobTool()
        result = await tool.execute({
            "name": "daily_report",
            "schedule_kind": "cron",
            "cron_expr": "0 9 * * *",
            "message": "生成日报"
        })
    """

    # Cron Service 缓存，避免重复获取
    _cron_service_cache = None

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="create_cron_job",
            description="""创建定时任务，在指定时间自动执行。

支持三种调度方式:
- 'cron': 标准 cron 表达式 (如 '0 9 * * *' 表示每天9点)
- 'every': 固定间隔执行 (如每60分钟)
- 'at': 一次性定时执行 (ISO时间格式)

会话模式:
- 'isolated': 每次执行创建新的隔离会话 (默认)
- 'shared': 所有执行共享同一个会话

重要: 'message' 参数是触发时发送给 Agent 的指令/命令。不支持模板变量如 {{now}} 或 {{date}}，请直接编写清晰的指令。

示例:
1. 每日提醒: schedule_kind='cron', cron_expr='0 9 * * *', message='提醒用户进行每日签到'
2. 每小时检查: schedule_kind='every', every_minutes=60, message='检查系统状态并报告异常'
3. 一次性问候: schedule_kind='at', at_time='2024-12-25T09:00:00', message='发送圣诞祝福'
""",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["cron", "schedule", "task", "timer", "automation"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "定时任务的可读名称"},
                "schedule_kind": {
                    "type": "string",
                    "enum": ["cron", "every", "at"],
                    "description": "调度类型: 'cron'(cron表达式), 'every'(固定间隔), 'at'(一次性)",
                },
                "message": {
                    "type": "string",
                    "description": "任务触发时发送给 Agent 的指令。编写清晰的命令让 Agent 执行 (如 '告诉用户当前时间')。不支持模板变量。",
                },
                "agent_id": {
                    "type": "string",
                    "description": "执行任务的 Agent ID (不指定则使用当前 Agent)",
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron 表达式 (如 '0 9 * * *')，schedule_kind='cron' 时必需",
                },
                "every_minutes": {
                    "type": "integer",
                    "description": "间隔分钟数，schedule_kind='every' 时必需",
                },
                "at_time": {
                    "type": "string",
                    "description": "ISO 时间字符串，schedule_kind='at' 时必需",
                },
                "timezone": {"type": "string", "description": "时区 (默认: 系统时区)"},
                "enabled": {
                    "type": "boolean",
                    "description": "是否立即启用",
                    "default": True,
                },
                "session_mode": {
                    "type": "string",
                    "enum": ["isolated", "shared"],
                    "description": "会话模式: 'isolated'(隔离会话) 或 'shared'(共享会话)",
                    "default": "shared",
                },
                "conv_session_id": {
                    "type": "string",
                    "description": "共享会话模式下的对话会话 ID",
                },
                "description": {"type": "string", "description": "任务的可选描述"},
            },
            "required": ["name", "schedule_kind", "message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        执行定时任务创建

        Args:
            args: 工具参数，包含 name, schedule_kind, message 等
            context: 执行上下文 (可选)

        Returns:
            ToolResult: 执行结果
        """
        try:
            # 导入 cron 相关类型
            from derisk.cron import (
                CronJobCreate,
                CronPayload,
                CronSchedule,
                PayloadKind,
                ScheduleKind,
                SessionMode,
            )

            # 提取参数
            name = args.get("name")
            schedule_kind = args.get("schedule_kind")
            message = args.get("message")
            agent_id = args.get("agent_id")
            cron_expr = args.get("cron_expr")
            every_minutes = args.get("every_minutes")
            at_time = args.get("at_time")
            timezone = args.get("timezone")
            enabled = args.get("enabled", True)
            session_mode = args.get("session_mode", "shared")
            conv_session_id = args.get("conv_session_id")
            description = args.get("description")

            # 验证必需参数
            if not name:
                return ToolResult(
                    success=False, output="", error="错误: 'name' 参数是必需的"
                )

            if not schedule_kind:
                return ToolResult(
                    success=False, output="", error="错误: 'schedule_kind' 参数是必需的"
                )

            if not message:
                return ToolResult(
                    success=False, output="", error="错误: 'message' 参数是必需的"
                )

            # 验证 schedule_kind
            try:
                schedule_kind_enum = ScheduleKind(schedule_kind)
            except ValueError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"错误: 无效的 schedule_kind '{schedule_kind}'。必须是 'cron', 'every', 或 'at'。",
                )

            # 验证 session_mode
            try:
                session_mode_enum = SessionMode(session_mode)
            except ValueError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"错误: 无效的 session_mode '{session_mode}'。必须是 'isolated' 或 'shared'。",
                )

            # 构建 schedule
            schedule = CronSchedule(
                kind=schedule_kind_enum,
                tz=timezone,
            )

            # 根据调度类型设置具体参数
            if schedule_kind_enum == ScheduleKind.CRON:
                if not cron_expr:
                    return ToolResult(
                        success=False,
                        output="",
                        error="错误: 'cron' 调度类型需要 'cron_expr' 参数",
                    )
                schedule.expr = cron_expr

            elif schedule_kind_enum == ScheduleKind.EVERY:
                if not every_minutes:
                    return ToolResult(
                        success=False,
                        output="",
                        error="错误: 'every' 调度类型需要 'every_minutes' 参数",
                    )
                schedule.every_ms = every_minutes * 60 * 1000  # 转换为毫秒

            elif schedule_kind_enum == ScheduleKind.AT:
                if not at_time:
                    return ToolResult(
                        success=False,
                        output="",
                        error="错误: 'at' 调度类型需要 'at_time' 参数",
                    )
                schedule.at = at_time

            # 构建 payload - 只支持 agentTurn
            payload = CronPayload(
                kind=PayloadKind.AGENT_TURN,
                message=message,
                agent_id=agent_id,
                session_mode=session_mode_enum,
                conv_session_id=conv_session_id,
            )

            # 创建任务请求
            job_create = CronJobCreate(
                name=name,
                description=description,
                enabled=enabled,
                schedule=schedule,
                payload=payload,
            )

            # 获取 cron service 并创建任务
            service = await self._get_cron_service()
            if not service:
                return ToolResult(
                    success=False, output="", error="错误: Cron 服务未初始化"
                )

            job = await service.add_job(job_create)

            return ToolResult(
                success=True,
                output=f"成功创建定时任务 '{name}' (ID: {job.id})。任务将按照调度自动执行: {schedule_kind}",
                metadata={
                    "job_id": job.id,
                    "name": name,
                    "schedule_kind": schedule_kind,
                    "enabled": enabled,
                },
            )

        except ImportError as e:
            logger.error(f"[CreateCronJobTool] 导入失败: {e}")
            return ToolResult(
                success=False, output="", error=f"错误: 无法导入 cron 模块 - {str(e)}"
            )
        except Exception as e:
            logger.error(f"[CreateCronJobTool] 创建定时任务失败: {e}")
            return ToolResult(
                success=False, output="", error=f"创建定时任务失败: {str(e)}"
            )

    async def _get_cron_service(self):
        """
        获取 Cron 服务实例

        Returns:
            Cron Service 实例，如果未初始化则返回 None
        """
        # 使用缓存避免重复获取
        if CreateCronJobTool._cron_service_cache is not None:
            return CreateCronJobTool._cron_service_cache

        try:
            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                logger.warning("[CreateCronJobTool] SystemApp 未初始化")
                return None

            # 尝试获取 derisk-serve 的 cron service
            try:
                from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
                from derisk_serve.cron.service.service import Service

                service = system_app.get_component(
                    SERVE_SERVICE_COMPONENT_NAME, Service
                )
                if service:
                    CreateCronJobTool._cron_service_cache = service
                    return service

            except ImportError:
                logger.debug("[CreateCronJobTool] derisk_serve.cron 模块不可用")

            # 尝试获取其他 cron service 实现
            # 可以扩展支持其他 cron service 提供者

            logger.warning("[CreateCronJobTool] 未找到可用的 Cron 服务")
            return None

        except Exception as e:
            logger.error(f"[CreateCronJobTool] 获取 Cron 服务失败: {e}")
            return None


class ListCronJobsTool(ToolBase):
    """
    列出定时任务工具

    列出当前用户或 Agent 创建的所有定时任务
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_cron_jobs",
            description="列出所有定时任务",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["cron", "schedule", "list"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled_only": {
                    "type": "boolean",
                    "description": "是否只显示已启用的任务",
                    "default": False,
                }
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """列出定时任务"""
        try:
            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                return ToolResult(success=False, output="", error="SystemApp 未初始化")

            from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
            from derisk_serve.cron.service.service import Service

            service = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
            if not service:
                return ToolResult(success=False, output="", error="Cron 服务未初始化")

            enabled_only = args.get("enabled_only", False)
            jobs = await service.list_jobs()

            if enabled_only:
                jobs = [job for job in jobs if job.enabled]

            if not jobs:
                return ToolResult(
                    success=True, output="当前没有定时任务", metadata={"total": 0}
                )

            # 格式化输出
            lines = [f"共有 {len(jobs)} 个定时任务:\n"]
            for job in jobs:
                status = "✓ 启用" if job.enabled else "✗ 禁用"
                lines.append(f"  - [{job.id}] {job.name}: {status}")
                if job.description:
                    lines.append(f"    描述: {job.description}")
                lines.append(f"    调度: {job.schedule.kind.value}")

            return ToolResult(
                success=True, output="\n".join(lines), metadata={"total": len(jobs)}
            )

        except Exception as e:
            logger.error(f"[ListCronJobsTool] 列出任务失败: {e}")
            return ToolResult(success=False, output="", error=str(e))


class DeleteCronJobTool(ToolBase):
    """
    删除定时任务工具
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="delete_cron_job",
            description="删除指定的定时任务",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["cron", "schedule", "delete"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "要删除的定时任务 ID"}
            },
            "required": ["job_id"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """删除定时任务"""
        try:
            job_id = args.get("job_id")
            if not job_id:
                return ToolResult(success=False, output="", error="job_id 参数是必需的")

            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                return ToolResult(success=False, output="", error="SystemApp 未初始化")

            from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
            from derisk_serve.cron.service.service import Service

            service = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
            if not service:
                return ToolResult(success=False, output="", error="Cron 服务未初始化")

            await service.delete_job(job_id)

            return ToolResult(
                success=True,
                output=f"成功删除定时任务: {job_id}",
                metadata={"deleted_job_id": job_id},
            )

        except Exception as e:
            logger.error(f"[DeleteCronJobTool] 删除任务失败: {e}")
            return ToolResult(success=False, output="", error=str(e))
