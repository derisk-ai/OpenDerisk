"""
Kanban 管理器 - 从 PDCAAgent 迁移并优化

支持结构化的任务规划、阶段管理和交付物验证。
作为 ReActMasterAgent 的可选模块，通过 enable_kanban=True 启用。

核心功能：
1. 创建和管理看板（Kanban）
2. 阶段状态管理（Stage: working/completed/failed）
3. 交付物 Schema 验证
4. 探索限制机制（防止过度探索）
5. 与 Memory 体系集成
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.memory.gpts.file_base import KanbanStorage
    from ...core.file_system.agent_file_system import AgentFileSystem

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """阶段状态"""

    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkEntry:
    """工作日志条目"""

    timestamp: float = field(default_factory=time.time)
    tool: str = ""
    summary: str = ""
    result: str = ""
    archives: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "tool": self.tool,
            "summary": self.summary,
            "result": self.result,
            "archives": self.archives,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WorkEntry":
        return cls(
            timestamp=data.get("timestamp", time.time()),
            tool=data.get("tool", ""),
            summary=data.get("summary", ""),
            result=data.get("result", ""),
            archives=data.get("archives"),
        )


@dataclass
class Stage:
    """阶段：看板的核心单元"""

    stage_id: str
    description: str
    status: str = StageStatus.WORKING.value
    deliverable_type: str = ""
    deliverable_schema: Dict = field(default_factory=dict)
    deliverable_file: str = ""
    work_log: List[WorkEntry] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0
    depends_on: List[str] = field(default_factory=list)
    reflection: str = ""

    def to_dict(self) -> Dict:
        return {
            "stage_id": self.stage_id,
            "description": self.description,
            "status": self.status,
            "deliverable_type": self.deliverable_type,
            "deliverable_schema": self.deliverable_schema,
            "deliverable_file": self.deliverable_file,
            "work_log": [e.to_dict() for e in self.work_log],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "depends_on": self.depends_on,
            "reflection": self.reflection,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Stage":
        work_log = [WorkEntry.from_dict(e) for e in data.pop("work_log", [])]
        return cls(work_log=work_log, **data)

    def is_completed(self) -> bool:
        return self.status == StageStatus.COMPLETED.value

    def is_working(self) -> bool:
        return self.status == StageStatus.WORKING.value


@dataclass
class Kanban:
    """看板：线性Stage序列"""

    kanban_id: str
    mission: str
    stages: List[Stage] = field(default_factory=list)
    current_stage_index: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "kanban_id": self.kanban_id,
            "mission": self.mission,
            "stages": [s.to_dict() for s in self.stages],
            "current_stage_index": self.current_stage_index,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Kanban":
        stages = [Stage.from_dict(s) for s in data.pop("stages", [])]
        return cls(stages=stages, **data)

    def get_current_stage(self) -> Optional[Stage]:
        if 0 <= self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def get_stage_by_id(self, stage_id: str) -> Optional[Stage]:
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    def get_completed_stages(self) -> List[Stage]:
        return [s for s in self.stages if s.is_completed()]

    def is_all_completed(self) -> bool:
        return all(s.is_completed() for s in self.stages)

    def advance_to_next_stage(self) -> bool:
        if self.current_stage_index < len(self.stages) - 1:
            self.current_stage_index += 1
            next_stage = self.get_current_stage()
            if next_stage:
                next_stage.status = StageStatus.WORKING.value
                next_stage.started_at = time.time()
            return True
        return False

    def generate_overview(self) -> str:
        lines = [f"# Kanban Overview", f"Mission: {self.mission}", "", "## Progress"]
        icons = []
        for i, stage in enumerate(self.stages):
            if stage.is_completed():
                icon = "✅"
            elif i == self.current_stage_index:
                icon = "🔄"
            else:
                icon = "⏳"
            icons.append(f"[{icon} {stage.stage_id}]")
        lines.append(" -> ".join(icons))
        lines.append("")

        completed = self.get_completed_stages()
        if completed:
            lines.append("## Completed Stages")
            for stage in completed:
                lines.append(f"- **{stage.stage_id}**: {stage.description}")
            lines.append("")

        current = self.get_current_stage()
        if current and not current.is_completed():
            lines.extend(
                [
                    "## Current Stage",
                    f"**{current.stage_id}**: {current.description}",
                    f"Status: {current.status}",
                    "",
                ]
            )

        return "\n".join(lines)

    def generate_current_stage_detail(self) -> str:
        current = self.get_current_stage()
        if not current:
            return "No active stage."

        lines = [
            f"### Current Stage: {current.stage_id}",
            "",
            f"**Description**: {current.description}",
            f"**Status**: {current.status}",
            f"**Deliverable Type**: {current.deliverable_type}",
            "",
        ]

        if current.deliverable_schema:
            lines.extend(
                [
                    "#### Expected Deliverable Schema",
                    "```json",
                    json.dumps(current.deliverable_schema, indent=2, ensure_ascii=False),
                    "```",
                    "",
                ]
            )

        if current.work_log:
            lines.append("#### Work Log")
            for i, entry in enumerate(current.work_log, 1):
                t_str = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
                summary = (
                    entry.summary[:200] + "..."
                    if len(entry.summary) > 200
                    else entry.summary
                )
                lines.append(f"{i}. [{t_str}] `{entry.tool}`: {summary}")
            lines.append("")

        return "\n".join(lines)


class KanbanManager:
    """
    看板管理器

    支持两种存储模式：
    1. kanban_storage: 集成到 Memory 体系（推荐）
    2. agent_file_system: 独立文件存储（兼容模式）
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        agent_file_system: Optional["AgentFileSystem"] = None,
        kanban_storage: Optional["KanbanStorage"] = None,
        exploration_limit: int = 2,
    ):
        self.agent_id = agent_id
        self.session_id = session_id
        self._afs = agent_file_system
        self._kanban_storage = kanban_storage
        self.exploration_limit = exploration_limit

        self.kanban: Optional[Kanban] = None
        self.pre_kanban_logs: List[WorkEntry] = []
        self._deliverables: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    @property
    def storage_mode(self) -> str:
        if self._kanban_storage:
            return "kanban_storage"
        elif self._afs:
            return "agent_file_system"
        else:
            return "memory_only"

    async def load(self):
        async with self._lock:
            if self._loaded:
                return

            if self._kanban_storage:
                await self._load_from_storage()
            elif self._afs:
                await self._load_from_afs()

            self._loaded = True

    async def _load_from_storage(self):
        if not self._kanban_storage:
            return
        try:
            kanban_data = await self._kanban_storage.get_kanban(self.session_id)
            if kanban_data:
                if isinstance(kanban_data, dict):
                    self.kanban = Kanban.from_dict(kanban_data)
                else:
                    self.kanban = Kanban.from_dict(kanban_data.to_dict())

            pre_logs = await self._kanban_storage.get_pre_kanban_logs(self.session_id)
            self.pre_kanban_logs = []
            for log in pre_logs:
                if isinstance(log, dict):
                    self.pre_kanban_logs.append(WorkEntry.from_dict(log))
                else:
                    self.pre_kanban_logs.append(WorkEntry.from_dict(log.to_dict()))

            self._deliverables = await self._kanban_storage.get_all_deliverables(
                self.session_id
            )
            logger.info(f"Loaded from KanbanStorage: kanban={self.kanban is not None}")
        except Exception as e:
            logger.error(f"Load from KanbanStorage failed: {e}")

    async def _load_from_afs(self):
        if not self._afs:
            return
        try:
            kanban_key = f"{self.agent_id}_{self.session_id}_kanban"
            content = await self._afs.read_file(kanban_key)
            if content:
                data = json.loads(content)
                self.kanban = Kanban.from_dict(data)
                logger.info(f"Loaded kanban from AFS")

            logs_key = f"{self.agent_id}_{self.session_id}_pre_kanban_logs"
            logs_content = await self._afs.read_file(logs_key)
            if logs_content:
                logs_data = json.loads(logs_content)
                self.pre_kanban_logs = [WorkEntry.from_dict(e) for e in logs_data]
        except Exception as e:
            logger.debug(f"Load from AFS: {e}")

    async def save(self):
        if not self.kanban:
            return

        if self._kanban_storage:
            from ...core.memory.gpts.file_base import Kanban as StorageKanban

            storage_kanban = StorageKanban.from_dict(self.kanban.to_dict())
            await self._kanban_storage.save_kanban(self.session_id, storage_kanban)
        elif self._afs:
            kanban_key = f"{self.agent_id}_{self.session_id}_kanban"
            await self._afs.save_file(
                file_key=kanban_key,
                data=json.dumps(self.kanban.to_dict(), ensure_ascii=False),
                file_type="kanban",
                extension="json",
            )

    async def create_kanban(self, mission: str, stages: List[Dict]) -> Dict[str, Any]:
        async with self._lock:
            if not self._loaded:
                await self._load_from_storage() if self._kanban_storage else await self._load_from_afs()

            if self.kanban is not None:
                return {
                    "status": "error",
                    "message": "Kanban already exists. Cannot create a new one.",
                }

            if not stages:
                return {"status": "error", "message": "Stages list cannot be empty."}

            kanban_id = f"{self.agent_id}_{self.session_id}"
            self.kanban = Kanban(
                kanban_id=kanban_id, mission=mission, stages=[], current_stage_index=0
            )

            for i, stage_spec in enumerate(stages):
                stage = Stage(
                    stage_id=stage_spec.get("stage_id", f"stage_{i+1}"),
                    description=stage_spec.get("description", ""),
                    deliverable_type=stage_spec.get("deliverable_type", ""),
                    deliverable_schema=stage_spec.get("deliverable_schema", {}),
                    depends_on=stage_spec.get("depends_on", []),
                )

                if i == 0:
                    stage.status = StageStatus.WORKING.value
                    stage.started_at = time.time()

                self.kanban.stages.append(stage)

            await self.save()

            self.pre_kanban_logs = []
            logger.info(f"Kanban created with {len(stages)} stages")

            current_stage = self.kanban.get_current_stage()
            return {
                "status": "success",
                "message": f"Kanban created with {len(stages)} stages. Now working on: {current_stage.stage_id}",
                "current_stage": {
                    "stage_id": current_stage.stage_id,
                    "description": current_stage.description,
                    "deliverable_type": current_stage.deliverable_type,
                    "deliverable_schema": current_stage.deliverable_schema,
                },
            }

    async def submit_deliverable(
        self, stage_id: str, deliverable: Dict[str, Any], reflection: str = ""
    ) -> Dict[str, Any]:
        async with self._lock:
            if not self._loaded:
                await self._load_from_storage() if self._kanban_storage else await self._load_from_afs()

            if not self.kanban:
                return {"status": "error", "message": "No kanban exists."}

            stage = self.kanban.get_stage_by_id(stage_id)
            if not stage:
                return {"status": "error", "message": f"Stage '{stage_id}' not found."}

            current_stage = self.kanban.get_current_stage()
            if current_stage.stage_id != stage_id:
                return {
                    "status": "error",
                    "message": f"Current stage is '{current_stage.stage_id}', not '{stage_id}'.",
                }

            if stage.deliverable_schema:
                valid, error_msg = validate_deliverable_schema(
                    deliverable, stage.deliverable_schema
                )
                if not valid:
                    stage.status = StageStatus.FAILED.value
                    stage.completed_at = time.time()
                    stage.reflection = f"Validation failed: {error_msg}"
                    await self.save()
                    return {
                        "status": "error",
                        "message": f"Deliverable validation failed: {error_msg}",
                    }

            deliverable_key = f"{self.agent_id}_{self.session_id}_deliverable_{stage_id}"
            if self._afs:
                await self._afs.save_file(
                    file_key=deliverable_key,
                    data=json.dumps(deliverable, ensure_ascii=False),
                    file_type="deliverable",
                    extension="json",
                )

            stage.status = StageStatus.COMPLETED.value
            stage.deliverable_file = deliverable_key
            stage.completed_at = time.time()
            stage.reflection = reflection

            has_next = self.kanban.advance_to_next_stage()
            await self.save()

            result = {
                "status": "success",
                "message": f"Stage '{stage_id}' completed. Deliverable saved.",
            }

            if has_next:
                next_stage = self.kanban.get_current_stage()
                result["next_stage"] = {
                    "stage_id": next_stage.stage_id,
                    "description": next_stage.description,
                    "deliverable_type": next_stage.deliverable_type,
                }
            else:
                result["all_completed"] = True
                result["message"] += " All stages completed!"

            return result

    async def read_deliverable(self, stage_id: str) -> Dict[str, Any]:
        async with self._lock:
            if not self._loaded:
                await self._load_from_storage() if self._kanban_storage else await self._load_from_afs()

            if not self.kanban:
                return {"status": "error", "message": "No kanban exists."}

            stage = self.kanban.get_stage_by_id(stage_id)
            if not stage:
                return {"status": "error", "message": f"Stage '{stage_id}' not found."}

            if not stage.deliverable_file:
                return {"status": "error", "message": f"Stage '{stage_id}' has no deliverable."}

        deliverable_key = stage.deliverable_file

        if self._kanban_storage:
            deliverable = await self._kanban_storage.get_deliverable(
                self.session_id, stage_id
            )
            if deliverable:
                return {
                    "status": "success",
                    "stage_id": stage_id,
                    "deliverable_type": stage.deliverable_type,
                    "deliverable": deliverable,
                }
        elif self._afs:
            content = await self._afs.read_file(deliverable_key)
            if content:
                try:
                    deliverable_data = json.loads(content)
                    return {
                        "status": "success",
                        "stage_id": stage_id,
                        "deliverable_type": stage.deliverable_type,
                        "deliverable": deliverable_data,
                    }
                except json.JSONDecodeError as e:
                    return {"status": "error", "message": f"JSON parse error: {e}"}

        return {"status": "error", "message": "Failed to read deliverable."}

    async def record_work(
        self,
        tool: str,
        args: Optional[Any] = None,
        summary: Optional[str] = None,
    ):
        async with self._lock:
            if not self._loaded:
                await self._load_from_storage() if self._kanban_storage else await self._load_from_afs()

            if not self.kanban:
                work_entry = WorkEntry(
                    timestamp=time.time(),
                    tool=tool,
                    summary=summary or "",
                )
                self.pre_kanban_logs.append(work_entry)

                if self._afs:
                    logs_key = f"{self.agent_id}_{self.session_id}_pre_kanban_logs"
                    logs_data = [e.to_dict() for e in self.pre_kanban_logs]
                    await self._afs.save_file(
                        file_key=logs_key,
                        data=json.dumps(logs_data, ensure_ascii=False),
                        file_type="logs",
                        extension="json",
                    )
                return

            stage = self.kanban.get_current_stage()
            if stage:
                work_entry = WorkEntry(
                    timestamp=time.time(),
                    tool=tool,
                    summary=summary or "",
                )
                stage.work_log.append(work_entry)
                await self.save()

    def get_exploration_count(self) -> int:
        exploration_tools = {"view", "read_file", "read_deliverable", "browse", "search"}
        count = 0
        for entry in self.pre_kanban_logs:
            if entry.tool in exploration_tools:
                count += 1
        return count

    def is_exploration_limit_reached(self) -> bool:
        return self.get_exploration_count() >= self.exploration_limit

    async def get_kanban_status(self) -> str:
        if not self._loaded:
            await self.load()

        if not self.kanban:
            exploration_count = self.get_exploration_count()
            if self.pre_kanban_logs:
                lines = ["### Pre-Kanban Actions (Exploration Phase)"]
                lines.append(
                    f"Exploration count: {exploration_count}/{self.exploration_limit}"
                )

                if self.is_exploration_limit_reached():
                    lines.append(
                        f"\n⚠️ **Exploration limit reached ({self.exploration_limit}).** "
                        f"You MUST call `create_kanban` now."
                    )
                else:
                    remaining = self.exploration_limit - exploration_count
                    lines.append(f"\n**Remaining exploration rounds: {remaining}**")

                return "\n".join(lines)
            return "No kanban initialized. Use `create_kanban` tool to start."

        return self.kanban.generate_overview()

    async def get_current_stage_detail(self) -> str:
        if not self._loaded:
            await self.load()

        if not self.kanban:
            return await self.get_kanban_status()

        return self.kanban.generate_current_stage_detail()

    async def get_todolist_data(self) -> Optional[Dict[str, Any]]:
        if not self._loaded:
            await self.load()

        if not self.kanban:
            return None

        status_map = {
            StageStatus.WORKING.value: "working",
            StageStatus.COMPLETED.value: "completed",
            StageStatus.FAILED.value: "failed",
        }

        current_index = 0
        for i, stage in enumerate(self.kanban.stages):
            if stage.status == StageStatus.WORKING.value:
                current_index = i
                break

        items = []
        for i, stage in enumerate(self.kanban.stages):
            items.append(
                {
                    "id": stage.stage_id,
                    "title": stage.description,
                    "status": status_map.get(stage.status, "pending"),
                    "index": i,
                }
            )

        return {
            "uid": f"{self.agent_id}_todolist",
            "type": "all",
            "mission": self.kanban.mission,
            "items": items,
            "current_index": current_index,
        }


def validate_deliverable_schema(deliverable: Dict, schema: Dict) -> tuple:
    """验证交付物是否符合 Schema"""
    try:
        from jsonschema import validate, ValidationError

        validate(instance=deliverable, schema=schema)
        return True, "Valid"
    except ValidationError as e:
        return False, str(e)
    except ImportError:
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in deliverable:
                return False, f"Missing required field: {field}"
        return True, "Valid (basic validation)"


async def create_kanban_manager(
    agent_id: str,
    session_id: str,
    agent_file_system: Optional["AgentFileSystem"] = None,
    kanban_storage: Optional["KanbanStorage"] = None,
    exploration_limit: int = 2,
) -> KanbanManager:
    """创建并初始化 KanbanManager"""
    manager = KanbanManager(
        agent_id=agent_id,
        session_id=session_id,
        agent_file_system=agent_file_system,
        kanban_storage=kanban_storage,
        exploration_limit=exploration_limit,
    )
    await manager.load()
    return manager


__all__ = [
    "KanbanManager",
    "Kanban",
    "Stage",
    "StageStatus",
    "WorkEntry",
    "validate_deliverable_schema",
    "create_kanban_manager",
]