"""
优化后的KanbanManager - 集成 Memory 体系
核心改进：
1. 支持通过 KanbanStorage 接口统一集成到 Memory 体系
2. 兼容旧版 FileSystem 直接存储模式
3. 保留简化的状态管理和交付物机制
"""

import asyncio
import json
import logging
import time
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from .plan_models import (
    Kanban,
    StageStatus,
    WorkEntry,
    create_stage_from_spec,
    validate_deliverable_schema,
)
from ...core.file_system.file_system import FileSystem

if TYPE_CHECKING:
    from ...core.memory.gpts.file_base import KanbanStorage

logger = logging.getLogger(__name__)


class AsyncKanbanManager:
    """
    异步看板管理器 (集成 Memory 体系)

    职责：
    1. 创建和管理看板
    2. 提交和验证交付物
    3. 读取前置交付物
    4. 生成Prompt上下文

    存储策略：
    - 优先使用 kanban_storage（推荐，集成到 Memory 体系）
    - 回退使用 file_system（向后兼容）
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        file_system: Optional[FileSystem] = None,
        kanban_storage: Optional["KanbanStorage"] = None,
    ):
        """
        初始化看板管理器

        Args:
            agent_id: Agent ID
            session_id: Session ID
            file_system: FileSystem 实例（向后兼容）
            kanban_storage: KanbanStorage 实例（推荐，集成到 Memory）
        """
        self.agent_id = agent_id
        self.session_id = session_id
        self.fs = file_system
        self._kanban_storage = kanban_storage

        # 定义在文件系统中的 Key (兼容模式使用)
        self.kanban_file = f"{agent_id}_{session_id}_kanban"
        self.kanban_view_file = f"{agent_id}_{session_id}_kanban_view"
        self.pre_kanban_logs_file = f"{agent_id}_{session_id}_pre_kanban_logs"

        # 交付物使用统一前缀
        self.deliverable_prefix = f"{agent_id}_{session_id}_deliverable"

        # 内存状态
        self.kanban: Optional[Kanban] = None
        self.pre_kanban_logs: List[WorkEntry] = []  # 记录 Kanban 创建前的预研日志
        self._deliverables: Dict[str, Dict[str, Any]] = {}  # stage_id -> deliverable
        self._lock = asyncio.Lock()
        self._loaded = False

        # 记录存储模式
        if kanban_storage:
            logger.info(f"KanbanManager 初始化: 使用 KanbanStorage 模式")
        elif file_system:
            logger.info(f"KanbanManager 初始化: 使用 FileSystem 模式（兼容）")
        else:
            logger.info(f"KanbanManager 初始化: 仅内存模式")

    @property
    def storage_mode(self) -> str:
        """获取当前存储模式"""
        if self._kanban_storage:
            return "kanban_storage"
        elif self.fs:
            return "file_system"
        else:
            return "memory_only"

    async def _load_unlocked(self):
        """内部方法：不获取锁的加载逻辑"""
        if self._loaded:
            return

        # 优先从 KanbanStorage 加载
        if self._kanban_storage:
            await self._load_from_storage()
        else:
            await self._load_from_filesystem()

        self._loaded = True

    async def _load_from_storage(self):
        """从 KanbanStorage 加载看板"""
        if self._kanban_storage is None:
            return

        try:
            # 获取看板数据并转换为本地 Kanban 类型
            kanban_data = await self._kanban_storage.get_kanban(self.session_id)
            if kanban_data:
                # 如果是字典，需要转换
                if isinstance(kanban_data, dict):
                    self.kanban = Kanban.from_dict(kanban_data)
                else:
                    # 尝试使用 to_dict 转换
                    self.kanban = Kanban.from_dict(kanban_data.to_dict())

            # 获取预研日志
            pre_logs = await self._kanban_storage.get_pre_kanban_logs(self.session_id)
            self.pre_kanban_logs = []
            for log in pre_logs:
                # 转换为本地 WorkEntry 类型
                if isinstance(log, dict):
                    self.pre_kanban_logs.append(WorkEntry.from_dict(log))
                else:
                    self.pre_kanban_logs.append(WorkEntry.from_dict(log.to_dict()))

            # 获取交付物
            self._deliverables = await self._kanban_storage.get_all_deliverables(
                self.session_id
            )

            logger.info(
                f"📚 从 KanbanStorage 加载: kanban={self.kanban is not None}, "
                f"pre_logs={len(self.pre_kanban_logs)}, deliverables={len(self._deliverables)}"
            )
        except Exception as e:
            logger.error(f"从 KanbanStorage 加载失败: {e}")

    async def _load_from_filesystem(self):
        """从文件系统加载历史日志"""
        if self.fs is None:
            return

        try:
            # 加载看板
            content = await self.fs.read_file(self.kanban_file)
            if content:
                data = json.loads(content)
                self.kanban = Kanban.from_dict(data)
                logger.info(f"📚 加载了看板: {self.kanban_file}")

            # 加载预研日志
            logs_content = await self.fs.read_file(self.pre_kanban_logs_file)
            if logs_content:
                logs_data = json.loads(logs_content)
                self.pre_kanban_logs = [
                    WorkEntry.from_dict(entry) for entry in logs_data
                ]
                logger.info(f"📚 加载了 {len(self.pre_kanban_logs)} 条预研日志")

        except Exception as e:
            logger.error(f"加载历史日志失败: {e}")

    async def load(self):
        """加载看板状态"""
        async with self._lock:
            await self._load_unlocked()

    async def save(self):
        """保存看板状态"""
        if not self.kanban:
            return

        # 优先保存到 KanbanStorage
        if self._kanban_storage:
            # 将本地 Kanban 转换为字典存储
            from ...core.memory.gpts.file_base import Kanban as StorageKanban

            storage_kanban = StorageKanban.from_dict(self.kanban.to_dict())
            await self._kanban_storage.save_kanban(self.session_id, storage_kanban)
            logger.debug(f"💾 保存看板到 KanbanStorage")
        else:
            await self._save_to_filesystem()

    async def _save_to_filesystem(self):
        """保存到文件系统（兼容模式）"""
        if self.fs is None:
            return

        try:
            # 准备数据
            kanban_data = self.kanban.to_dict()
            kanban_view = self._generate_kanban_markdown()

            # 通过 FileSystem 并发保存 JSON 和 Markdown
            await asyncio.gather(
                self.fs.save_file(self.kanban_file, kanban_data, "json"),
                self.fs.save_file(self.kanban_view_file, kanban_view, "md"),
            )

            logger.info(f"💾 已保存 Kanban 到 FileSystem: {self.kanban_file}")

        except Exception as e:
            logger.error(f"保存看板失败: {e}")

    def _generate_kanban_markdown(self) -> str:
        """生成Markdown格式的看板视图"""
        if not self.kanban:
            return "# No Kanban\n\nKanban not initialized yet."

        lines = [
            f"# Kanban: {self.agent_id}",
            f"Session: {self.session_id}",
            f"Last Update: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Mission",
            self.kanban.mission,
            "",
            "## Stages",
        ]

        for i, stage in enumerate(self.kanban.stages):
            status_icon = {
                StageStatus.COMPLETED.value: "✅",
                StageStatus.WORKING.value: "🔄",
                StageStatus.FAILED.value: "❌",
            }.get(stage.status, "⏳")

            is_current = i == self.kanban.current_stage_index
            current_marker = " **[CURRENT]**" if is_current else ""

            lines.append(f"### {status_icon} {stage.stage_id}{current_marker}")
            lines.append(f"**Description**: {stage.description}")
            lines.append(f"**Status**: {stage.status}")
            lines.append(f"**Deliverable Type**: {stage.deliverable_type}")

            if stage.deliverable_file:
                lines.append(f"**Deliverable File**: `{stage.deliverable_file}`")

            if stage.depends_on:
                lines.append(f"**Depends On**: {', '.join(stage.depends_on)}")

            if stage.reflection:
                lines.append(f"**Reflection**: {stage.reflection}")

            if stage.work_log:
                lines.append(f"**Work Log**: {len(stage.work_log)} entries")

            lines.append("")

        return "\n".join(lines)

    # ==================== 核心操作 ====================

    async def create_kanban(self, mission: str, stages: List[Dict]) -> Dict[str, Any]:
        """
        创建看板

        Args:
            mission: 任务描述
            stages: 阶段规格列表

        Returns:
            操作结果
        """
        async with self._lock:
            if not self._loaded:
                await self._load_unlocked()

            if self.kanban is not None:
                return {
                    "status": "error",
                    "message": "Kanban already exists. Cannot create a new one.",
                }

            if not stages:
                return {"status": "error", "message": "Stages list cannot be empty."}

            # 创建看板
            kanban_id = f"{self.agent_id}_{self.session_id}"
            self.kanban = Kanban(
                kanban_id=kanban_id, mission=mission, stages=[], current_stage_index=0
            )

            # 创建所有阶段
            for i, stage_spec in enumerate(stages):
                stage_spec["is_first"] = i == 0  # 标记第一个阶段
                stage = create_stage_from_spec(stage_spec)

                # 第一个阶段自动进入working状态
                if i == 0:
                    stage.status = StageStatus.WORKING.value
                    stage.started_at = time.time()

                self.kanban.stages.append(stage)

            # 保存
            await self.save()

            # [Clean] 清除 pre_kanban_logs，释放上下文空间
            self.pre_kanban_logs = []
            # 清除 pre_kanban_logs 文件
            await self.fs.save_file(self.pre_kanban_logs_file, [], "json")
            logger.info("💾 已清除 pre_kanban_logs 文件")

            current_stage = self.kanban.get_current_stage()
            return {
                "status": "success",
                "message": (
                    f"Kanban created with {len(stages)} stages. "
                    f"Now working on: {current_stage.stage_id}"
                ),
                "current_stage": {
                    "stage_id": current_stage.stage_id,
                    "description": current_stage.description,
                    "deliverable_type": current_stage.deliverable_type,
                    "expected_schema": current_stage.deliverable_schema,
                },
            }

    async def submit_deliverable(
        self, stage_id: str, deliverable: Dict[str, Any], reflection: str = ""
    ) -> Dict[str, Any]:
        """
        提交当前阶段的交付物

        Args:
            stage_id: 阶段ID
            deliverable: 交付物数据（结构化对象）
            reflection: Agent的自我评估

        Returns:
            操作结果
        """
        async with self._lock:
            if not self._loaded:
                await self._load_unlocked()

            if not self.kanban:
                return {
                    "status": "error",
                    "message": "No kanban exists. Please create one first.",
                }

            # 查找阶段
            stage = self.kanban.get_stage_by_id(stage_id)
            if not stage:
                return {"status": "error", "message": f"Stage '{stage_id}' not found."}

            # 检查是否是当前阶段
            current_stage = self.kanban.get_current_stage()
            if current_stage.stage_id != stage_id:
                return {
                    "status": "error",
                    "message": (
                        f"Cannot submit deliverable for '{stage_id}'. "
                        f"Current stage is '{current_stage.stage_id}'."
                    ),
                }

            # 验证Schema
            valid, error_msg = validate_deliverable_schema(
                deliverable, stage.deliverable_schema
            )
            if not valid:
                # 标记为失败状态
                stage.status = StageStatus.FAILED.value
                stage.completed_at = time.time()
                stage.reflection = f"Validation failed: {error_msg}"
                await self.save()

                return {
                    "status": "error",
                    "message": f"Deliverable validation failed: {error_msg}",
                    "hint": "Stage marked as FAILED. Please review and retry.",
                }

            # 通过 FileSystem 保存交付物
            try:
                # 通过 FileSystem 保存交付物
                deliverable_key = f"{self.deliverable_prefix}_{stage_id}"
                _ = await self.fs.save_file(deliverable_key, deliverable, "json")
            except Exception as e:
                # 标记为失败状态
                stage.status = StageStatus.FAILED.value
                stage.completed_at = time.time()
                stage.reflection = f"File system error: {str(e)}"
                await self.save()

                return {
                    "status": "error",
                    "message": f"Failed to save deliverable: {str(e)}",
                }

            # 更新阶段状态
            stage.status = StageStatus.COMPLETED.value
            stage.deliverable_file = deliverable_key  # 存储 key 而非路径
            stage.completed_at = time.time()
            stage.reflection = reflection

            # 推进到下一阶段
            has_next = self.kanban.advance_to_next_stage()

            # 保存看板
            await self.save()

            # 构造返回结果
            result = {
                "status": "success",
                "message": (
                    f"Stage '{stage_id}' completed. "
                    f"Deliverable saved to AFS: {deliverable_key}"
                ),
                "validation": {
                    "schema_valid": True,
                    "message": "Deliverable matches expected schema",
                },
            }

            if has_next:
                next_stage = self.kanban.get_current_stage()
                available_deliverables = [
                    {
                        "stage_id": s.stage_id,
                        "file_key": s.deliverable_file,  # 返回 key
                        "type": s.deliverable_type,
                    }
                    for s in self.kanban.get_completed_stages()
                ]

                result["next_stage"] = {
                    "stage_id": next_stage.stage_id,
                    "description": next_stage.description,
                    "deliverable_type": next_stage.deliverable_type,
                    "available_deliverables": available_deliverables,
                }
            else:
                result["message"] += " All stages completed!"
                result["all_completed"] = True

            return result

    async def read_deliverable(self, stage_id: str) -> Dict[str, Any]:
        """
        读取指定阶段的交付物

        Args:
            stage_id: 阶段ID

        Returns:
            交付物内容
        """
        logger.info(f"read_deliverable:{stage_id}")
        async with self._lock:
            if not self._loaded:
                await self._load_unlocked()

            if not self.kanban:
                return {"status": "error", "message": "No kanban exists."}

            # 查找阶段
            stage = self.kanban.get_stage_by_id(stage_id)
            if not stage:
                return {"status": "error", "message": f"Stage '{stage_id}' not found."}

            if not stage.deliverable_file:
                return {
                    "status": "error",
                    "message": f"Stage '{stage_id}' has no deliverable yet.",
                }

        # 通过 FileSystem 读取交付物 (释放锁后进行 I/O)
        deliverable_key = stage.deliverable_file
        content = await self.fs.read_file(deliverable_key)

        if not content:
            return {
                "status": "error",
                "message": f"Failed to read deliverable for stage '{stage_id}'.",
            }

        try:
            deliverable_data = json.loads(content)
            return {
                "status": "success",
                "stage_id": stage_id,
                "deliverable_type": stage.deliverable_type,
                "deliverable": deliverable_data,
            }
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "message": f"Failed to parse deliverable JSON: {e}",
            }

    async def get_current_stage_context(self) -> Dict[str, Any]:
        """
        获取当前阶段的上下文信息
        用于生成 Prompt

        Returns:
            当前阶段的上下文
        """
        async with self._lock:
            if not self._loaded:
                await self._load_unlocked()

            if not self.kanban:
                return {"status": "error", "message": "No kanban exists."}

            current_stage = self.kanban.get_current_stage()
            completed_stages = self.kanban.get_completed_stages()

        # 构建上下文
        context = {
            "status": "success",
            "mission": self.kanban.mission,
            "current_stage": {
                "stage_id": current_stage.stage_id,
                "description": current_stage.description,
                "deliverable_type": current_stage.deliverable_type,
                "deliverable_schema": current_stage.deliverable_schema,
                "depends_on": current_stage.depends_on,
            },
            "completed_stages": [
                {
                    "stage_id": s.stage_id,
                    "description": s.description,
                    "deliverable_type": s.deliverable_type,
                    "deliverable_key": s.deliverable_file,
                    "reflection": s.reflection,
                }
                for s in completed_stages
            ],
            "progress": {
                "current_index": self.kanban.current_stage_index,
                "total_stages": len(self.kanban.stages),
                "completion_rate": "{:.1f}%".format(
                    self.kanban.current_stage_index / len(self.kanban.stages) * 100
                ),
            },
        }

        return context

    async def get_kanban_overview(self) -> Dict[str, Any]:
        """
        获取看板全局概览

        Returns:
            看板概览信息
        """
        async with self._lock:
            if not self._loaded:
                await self._load_unlocked()

            if not self.kanban:
                return {"status": "error", "message": "No kanban exists."}

            stages_info = []
            for i, stage in enumerate(self.kanban.stages):
                stage_info = {
                    "stage_id": stage.stage_id,
                    "description": stage.description,
                    "status": stage.status,
                    "deliverable_type": stage.deliverable_type,
                    "is_current": (i == self.kanban.current_stage_index),
                    "has_deliverable": bool(stage.deliverable_file),
                }
                stages_info.append(stage_info)

            return {
                "status": "success",
                "kanban_id": self.kanban.kanban_id,
                "mission": self.kanban.mission,
                "current_stage_index": self.kanban.current_stage_index,
                "total_stages": len(self.kanban.stages),
                "stages": stages_info,
            }

    async def record_work(
        self,
        tool: str,
        args: Optional[Any] = None,
        summary: Optional[str] = None,
        result: Optional[str] = "",
    ) -> Dict[str, Any]:
        """
        简化的工作日志记录方法（自动记录到当前阶段）

        Args:
            tool: 工具名称
            summary: 工作摘要
            result: 执行结果（可选）

        Returns:
            操作结果
        """
        return await self.add_work_log(
            entry={"action": tool, "args": args, "summary": summary, "result": result}
        )

    async def add_work_log(
        self, entry: Dict[str, Any], stage_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        添加工作日志到指定阶段（默认为当前阶段）

        Args:
            entry: 日志条目，包含 action, details, result 等字段
            stage_id: 阶段ID（可选，默认为当前阶段）

        Returns:
            操作结果
        """
        async with self._lock:
            if not self._loaded:
                await self._load_unlocked()

            if not self.kanban:
                # [FIX] 如果看板未初始化，记录到 pre_kanban_logs，
                # 允许 Agent 在创建看板前执行预研动作
                logger.info("Recording work log to pre-kanban history.")
                work_entry = WorkEntry(
                    timestamp=time.time(),
                    tool=entry.get("action", ""),
                    summary=entry.get("summary", ""),
                    archives=entry.get("archives"),
                    result=entry.get("result", ""),
                )
                self.pre_kanban_logs.append(work_entry)

                # 保存 pre_kanban_logs 到文件系统
                logs_data = [entry.to_dict() for entry in self.pre_kanban_logs]
                await self.fs.save_file(self.pre_kanban_logs_file, logs_data, "json")
                logger.info(
                    f"💾 已保存 pre_kanban_logs 到 AFS，共 {len(self.pre_kanban_logs)} 条记录"
                )

                return {
                    "status": "success",
                    "message": "Work log added to pre-kanban history. "
                    "Please create kanban when ready.",
                }

            # 如果未指定 stage_id，使用当前阶段
            if stage_id is None:
                stage = self.kanban.get_current_stage()
                if not stage:
                    return {"status": "error", "message": "No current stage available."}
            else:
                stage = self.kanban.get_stage_by_id(stage_id)
                if not stage:
                    return {
                        "status": "error",
                        "message": f"Stage '{stage_id}' not found.",
                    }

            # 创建工作日志条目
            work_entry = WorkEntry(
                timestamp=time.time(),
                tool=entry.get("action", ""),
                summary=entry.get("summary", ""),
                archives=entry.get("archives"),
                result=entry.get("result", ""),
            )

            stage.work_log.append(work_entry)
            await self.save()

            return {
                "status": "success",
                "message": f"Work log added to stage '{stage.stage_id}'.",
            }

    async def get_archived_deliverable(self, archive_key: str) -> Optional[str]:
        """
        读取归档的交付物内容
        用于读取大型交付物或历史数据

        Args:
            archive_key: 归档键

        Returns:
            归档内容
        """
        try:
            content = await self.fs.read_file(archive_key)
            return content
        except Exception as e:
            logger.error(f"Failed to read archived deliverable {archive_key}: {e}")
            return None

    # ==================== Prompt 上下文生成 ====================

    async def get_kanban_status(self) -> str:
        """
        获取看板状态（用于Prompt注入）
        返回格式化的看板概览文本

        Returns:
            看板状态的 Markdown 格式文本
        """
        if not self._loaded:
            await self.load()

        if not self.kanban:
            return (
                "No kanban initialized. Please create one using `create_kanban` tool."
            )

        return self.kanban.generate_overview()

    async def get_current_stage_detail(self) -> str:
        """
        获取当前阶段详情（用于Prompt注入）
        返回当前阶段的详细信息

        Returns:
            当前阶段详情的 Markdown 格式文本
        """
        if not self._loaded:
            await self.load()

        if not self.kanban:
            exploration_count = self.get_exploration_count()
            if self.pre_kanban_logs:
                lines = ["### Pre-Kanban Actions (Information Gathering)"]
                lines.append(
                    "You are currently in the pre-planning phase. "
                    "You have performed the following actions:"
                )
                lines.append("")

                for i, entry in enumerate(self.pre_kanban_logs, 1):
                    t_str = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
                    # 限制 summary 长度，避免 Prompt 过长
                    summary_preview = entry.summary
                    if summary_preview and len(summary_preview) > 500:
                        summary_preview = summary_preview[:500] + "... (truncated)"
                    lines.append(f"{i}. [{t_str}] `{entry.tool}`: {summary_preview}")

                lines.append("")
                # 添加探索计数和强制约束提醒
                lines.append(f"**Exploration Count**: {exploration_count}/2")
                if exploration_count >= 2:
                    lines.append(
                        "⚠️ **STOP**: You have reached the exploration limit (2 rounds). "
                        "**You MUST call `create_kanban` NOW.** Do NOT use view/read tools."
                    )
                else:
                    remaining = 2 - exploration_count
                    lines.append(
                        f"**Remaining Exploration**: {remaining} round(s). "
                        f"If you have enough information, call `create_kanban` immediately."
                    )
                lines.append("")
                return "\n".join(lines)

            return "No kanban initialized. No actions taken yet."

        return self.kanban.generate_current_stage_detail()

    async def get_available_deliverables(self) -> str:
        """
        获取可用交付物列表（用于Prompt注入）
        返回所有已完成阶段的交付物信息

        Returns:
            可用交付物列表的 Markdown 格式文本
        """
        if not self._loaded:
            await self.load()

        if not self.kanban:
            return "No deliverables available."

        return self.kanban.generate_available_deliverables()

    async def is_all_completed(self) -> bool:
        """
        检查是否所有阶段都已完成

        Returns:
            True 如果所有阶段完成，否则 False
        """
        if not self._loaded:
            await self.load()

        if not self.kanban:
            return False

        return self.kanban.is_all_completed()

    # ==================== 调试与监控 ====================

    async def get_full_state(self) -> Dict[str, Any]:
        """
        获取完整的看板状态（用于调试）

        Returns:
            完整的看板状态字典
        """
        if not self._loaded:
            await self.load()

        if not self.kanban:
            return {"status": "no_kanban"}

        return self.kanban.to_dict()

    async def export_all_deliverables(self) -> Dict[str, Any]:
        """
        导出所有交付物（用于最终报告生成）

        Returns:
            所有交付物的字典，key 为 stage_id，value 为交付物内容
        """
        if not self._loaded:
            await self.load()

        if not self.kanban:
            return {}

        deliverables = {}
        for stage in self.kanban.get_completed_stages():
            result = await self.read_deliverable(stage.stage_id)
            if result["status"] == "success":
                deliverables[stage.stage_id] = result["deliverable"]

        return deliverables

    async def get_todolist_data(self) -> Optional[Dict[str, Any]]:
        """
        获取TodoList数据（用于前端todollist可视化）

        Returns:
            TodoList数据字典，如果没有kanban则返回None
        """
        if not self._loaded:
            await self.load()

        # 状态映射：StageStatus -> Todo status
        # StageStatus只有: WORKING="working", COMPLETED="completed", FAILED="failed"
        status_map = {
            StageStatus.WORKING.value: "working",
            StageStatus.COMPLETED.value: "completed",
            StageStatus.FAILED.value: "failed",
        }

        # 获取当前阶段的索引（working状态）
        todo_items = []
        current_index = 0
        if self.kanban:
            for i, stage in enumerate(self.kanban.stages):
                if stage.status == StageStatus.WORKING.value:
                    current_index = i
                    break

            # 构建todo items - 简化版，只包含checkbox和标题
            for i, stage in enumerate(self.kanban.stages):
                todo_status = status_map.get(stage.status, "pending")
                todo_items.append(
                    {
                        "id": stage.stage_id,
                        "title": stage.description,
                        "status": todo_status,
                        "index": i,
                    }
                )

        return {
            "uid": f"{self.agent_id}_todolist",
            "type": "all",
            "mission": self.kanban.mission if self.kanban else "",
            "items": todo_items,
            "current_index": current_index,
        }

    def get_exploration_count(self) -> int:
        """
        获取探索计数（看板创建前已使用的 view/read_file 类工具次数）
        用于限制过度探索，强制 Agent 及时创建看板

        Returns:
            已使用的探索工具次数
        """
        exploration_tools = {"view", "read_file", "read_deliverable"}
        count = 0
        for entry in self.pre_kanban_logs:
            if entry.tool in exploration_tools:
                count += 1
        return count


# ==================== 工具函数 ====================


async def create_kanban_manager(
    agent_id: str,
    session_id: str,
    file_system: Optional[FileSystem] = None,
    kanban_storage: Optional["KanbanStorage"] = None,
) -> AsyncKanbanManager:
    """
    创建并初始化 KanbanManager

    Args:
        agent_id: Agent ID
        session_id: Session ID
        file_system: FileSystem 实例（向后兼容）
        kanban_storage: KanbanStorage 实例（推荐，集成到 Memory）

    Returns:
        已初始化的 AsyncKanbanManager 实例
    """
    manager = AsyncKanbanManager(
        agent_id=agent_id,
        session_id=session_id,
        file_system=file_system,
        kanban_storage=kanban_storage,
    )
    await manager.load()
    return manager
