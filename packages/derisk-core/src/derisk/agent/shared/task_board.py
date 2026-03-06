"""
TaskBoardManager - 统一任务看板管理器

实现 Todo 列表和 Kanban 看板的统一管理，支持长复杂任务的规划与追踪。
作为共享基础设施，可供 Core V1 和 Core V2 共同使用。

核心能力：
1. Todo 列表管理（简单任务模式）
2. Kanban 看板管理（阶段化任务模式）
3. 任务依赖关系处理
4. 与 AgentFileSystem 集成持久化
5. 推理过程按需创建任务

设计原则：
- 统一资源管理：所有任务数据通过 AgentFileSystem 管理
- 双模式支持：同时支持简单的 Todo 和复杂的 Kanban
- 状态可追踪：提供清晰的任务进度视图
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

if TYPE_CHECKING:
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem
    from derisk.agent.core.memory.gpts.file_base import KanbanStorage

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TaskPriority(str, Enum):
    """任务优先级"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StageStatus(str, Enum):
    """看板阶段状态"""
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskItem:
    """任务项"""
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: List[str] = field(default_factory=list)
    assignee: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    progress: float = 0.0
    estimated_tokens: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "assignee": self.assignee,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": self.progress,
            "estimated_tokens": self.estimated_tokens,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskItem":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", "medium")),
            dependencies=data.get("dependencies", []),
            assignee=data.get("assignee"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            progress=data.get("progress", 0.0),
            estimated_tokens=data.get("estimated_tokens", 0),
        )


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
    """看板阶段"""
    stage_id: str
    description: str
    status: StageStatus = StageStatus.WORKING
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
            "status": self.status.value,
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
        return cls(
            work_log=work_log,
            status=StageStatus(data.get("status", "working")),
            **{k: v for k, v in data.items() if k != "status"},
        )
    
    def is_completed(self) -> bool:
        return self.status == StageStatus.COMPLETED
    
    def is_working(self) -> bool:
        return self.status == StageStatus.WORKING


@dataclass
class Kanban:
    """看板"""
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
                next_stage.status = StageStatus.WORKING
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
            lines.extend([
                "## Current Stage",
                f"**{current.stage_id}**: {current.description}",
                f"Status: {current.status.value}",
                "",
            ])
        
        return "\n".join(lines)


class TaskBoardManager:
    """
    统一任务看板管理器
    
    支持：
    1. Todo列表模式（简单任务快速管理）
    2. Kanban看板模式（复杂阶段化任务）
    3. 任务依赖关系处理
    4. 与 AgentFileSystem 集成持久化
    
    使用示例：
        # 创建管理器
        manager = TaskBoardManager(
            session_id="session_001",
            agent_id="agent_001",
            file_system=afs,
        )
        await manager.load()
        
        # Todo 模式
        todo = await manager.create_todo("分析数据文件")
        await manager.update_todo_status(todo.id, TaskStatus.WORKING)
        await manager.update_todo_status(todo.id, TaskStatus.COMPLETED)
        
        # Kanban 模式
        result = await manager.create_kanban(
            mission="完成数据分析报告",
            stages=[
                {"stage_id": "collect", "description": "收集数据"},
                {"stage_id": "analyze", "description": "分析数据"},
                {"stage_id": "report", "description": "生成报告"},
            ]
        )
    
    设计原则：
    - 统一存储：所有数据通过 AgentFileSystem 管理
    - 模式分离：Todo简单、Kanban复杂，按需选择
    - 状态可追踪：提供清晰进度视图
    """
    
    def __init__(
        self,
        session_id: str,
        agent_id: str,
        file_system: Optional["AgentFileSystem"] = None,
        kanban_storage: Optional["KanbanStorage"] = None,
        exploration_limit: int = 3,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self._file_system = file_system
        self._kanban_storage = kanban_storage
        self.exploration_limit = exploration_limit
        
        self._todos: Dict[str, TaskItem] = {}
        self._kanban: Optional[Kanban] = None
        self._pre_kanban_logs: List[WorkEntry] = []
        self._deliverables: Dict[str, Dict[str, Any]] = {}
        
        self._lock = asyncio.Lock()
        self._loaded = False
    
    @property
    def storage_mode(self) -> str:
        if self._kanban_storage:
            return "kanban_storage"
        elif self._file_system:
            return "agent_file_system"
        else:
            return "memory_only"
    
    async def load(self):
        async with self._lock:
            if self._loaded:
                return
            
            if self._kanban_storage:
                await self._load_from_kanban_storage()
            elif self._file_system:
                await self._load_from_file_system()
            
            self._loaded = True
            logger.info(f"[TaskBoard] Loaded, mode={self.storage_mode}, todos={len(self._todos)}")
    
    async def _load_from_kanban_storage(self):
        if not self._kanban_storage:
            return
        try:
            kanban_data = await self._kanban_storage.get_kanban(self.session_id)
            if kanban_data:
                if isinstance(kanban_data, dict):
                    self._kanban = Kanban.from_dict(kanban_data)
                else:
                    self._kanban = Kanban.from_dict(kanban_data.to_dict())
            
            self._deliverables = await self._kanban_storage.get_all_deliverables(self.session_id)
        except Exception as e:
            logger.error(f"[TaskBoard] Load from KanbanStorage failed: {e}")
    
    async def _load_from_file_system(self):
        if not self._file_system:
            return
        try:
            kanban_key = f"{self.agent_id}_kanban"
            content = await self._file_system.read_file(kanban_key)
            if content:
                data = json.loads(content)
                self._kanban = Kanban.from_dict(data)
            
            todos_key = f"{self.agent_id}_todos"
            todos_content = await self._file_system.read_file(todos_key)
            if todos_content:
                todos_data = json.loads(todos_content)
                self._todos = {
                    tid: TaskItem.from_dict(t) for tid, t in todos_data.items()
                }
            
            logs_key = f"{self.agent_id}_pre_kanban_logs"
            logs_content = await self._file_system.read_file(logs_key)
            if logs_content:
                logs_data = json.loads(logs_content)
                self._pre_kanban_logs = [WorkEntry.from_dict(e) for e in logs_data]
        except Exception as e:
            logger.debug(f"[TaskBoard] Load from file system: {e}")
    
    async def save(self):
        if self._kanban_storage and self._kanban:
            from derisk.agent.core.memory.gpts.file_base import Kanban as StorageKanban
            
            storage_kanban = StorageKanban.from_dict(self._kanban.to_dict())
            await self._kanban_storage.save_kanban(self.session_id, storage_kanban)
        
        if self._file_system:
            await self._save_to_file_system()
    
    async def _save_to_file_system(self):
        if not self._file_system:
            return
        
        from derisk.agent.core.memory.gpts import FileType
        
        try:
            if self._kanban:
                kanban_key = f"{self.agent_id}_kanban"
                await self._file_system.save_file(
                    file_key=kanban_key,
                    data=json.dumps(self._kanban.to_dict(), ensure_ascii=False),
                    file_type=FileType.KANBAN,
                    extension="json",
                )
            
            if self._todos:
                todos_key = f"{self.agent_id}_todos"
                todos_data = {tid: t.to_dict() for tid, t in self._todos.items()}
                await self._file_system.save_file(
                    file_key=todos_key,
                    data=json.dumps(todos_data, ensure_ascii=False),
                    file_type=FileType.KANBAN,
                    extension="json",
                )
            
            if self._pre_kanban_logs:
                logs_key = f"{self.agent_id}_pre_kanban_logs"
                logs_data = [e.to_dict() for e in self._pre_kanban_logs]
                await self._file_system.save_file(
                    file_key=logs_key,
                    data=json.dumps(logs_data, ensure_ascii=False),
                    file_type=FileType.KANBAN,
                    extension="json",
                )
        except Exception as e:
            logger.error(f"[TaskBoard] Save failed: {e}")
    
    # ==================== Todo 模式 ====================
    
    async def create_todo(
        self,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskItem:
        """创建 Todo 项"""
        async with self._lock:
            if not self._loaded:
                await self._ensure_loaded()
            
            task_id = f"todo_{int(time.time()*1000)}_{len(self._todos)}"
            
            task = TaskItem(
                id=task_id,
                title=title,
                description=description,
                status=TaskStatus.PENDING,
                priority=priority,
                dependencies=dependencies or [],
                metadata=metadata or {},
            )
            
            self._todos[task_id] = task
            await self._save_to_file_system()
            
            logger.info(f"[TaskBoard] Created todo: {task_id} - {title}")
            return task
    
    async def update_todo_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[float] = None,
    ) -> Optional[TaskItem]:
        """更新 Todo 状态"""
        async with self._lock:
            if not self._loaded:
                await self._ensure_loaded()
            
            if task_id not in self._todos:
                logger.warning(f"[TaskBoard] Todo not found: {task_id}")
                return None
            
            task = self._todos[task_id]
            task.status = status
            task.updated_at = time.time()
            
            if status == TaskStatus.WORKING and task.started_at is None:
                task.started_at = time.time()
            
            if status == TaskStatus.COMPLETED:
                task.completed_at = time.time()
                task.progress = 1.0
            
            if progress is not None:
                task.progress = progress
            
            await self._save_to_file_system()
            return task
    
    async def get_todo(self, task_id: str) -> Optional[TaskItem]:
        """获取单个 Todo"""
        if not self._loaded:
            await self._ensure_loaded()
        return self._todos.get(task_id)
    
    async def list_todos(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
    ) -> List[TaskItem]:
        """列出 Todo"""
        if not self._loaded:
            await self._ensure_loaded()
        
        todos = list(self._todos.values())
        
        if status:
            todos = [t for t in todos if t.status == status]
        
        if priority:
            todos = [t for t in todos if t.priority == priority]
        
        return sorted(todos, key=lambda t: (t.priority.value, t.created_at))
    
    async def delete_todo(self, task_id: str) -> bool:
        """删除 Todo"""
        async with self._lock:
            if task_id in self._todos:
                del self._todos[task_id]
                await self._save_to_file_system()
                return True
            return False
    
    async def get_next_pending_todo(self) -> Optional[TaskItem]:
        """获取下一个待处理的 Todo（考虑依赖关系）"""
        if not self._loaded:
            await self._ensure_loaded()
        
        pending_todos = sorted(
            [t for t in self._todos.values() if t.status == TaskStatus.PENDING],
            key=lambda t: t.priority.value,
        )
        
        for task in pending_todos:
            all_deps_met = True
            for dep_id in task.dependencies:
                dep_task = self._todos.get(dep_id)
                if dep_task and dep_task.status != TaskStatus.COMPLETED:
                    all_deps_met = False
                    break
            
            if all_deps_met:
                return task
        
        return None
    
    # ==================== Kanban 模式 ====================
    
    async def create_kanban(
        self,
        mission: str,
        stages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """创建 Kanban 看板"""
        async with self._lock:
            if not self._loaded:
                await self._ensure_loaded()
            
            if self._kanban is not None:
                return {
                    "status": "error",
                    "message": "Kanban already exists. Cannot create a new one.",
                }
            
            if not stages:
                return {"status": "error", "message": "Stages list cannot be empty."}
            
            kanban_id = f"{self.agent_id}_{self.session_id}"
            self._kanban = Kanban(
                kanban_id=kanban_id,
                mission=mission,
                stages=[],
                current_stage_index=0,
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
                    stage.status = StageStatus.WORKING
                    stage.started_at = time.time()
                
                self._kanban.stages.append(stage)
            
            await self.save()
            
            self._pre_kanban_logs = []
            logger.info(f"[TaskBoard] Created kanban with {len(stages)} stages")
            
            current_stage = self._kanban.get_current_stage()
            return {
                "status": "success",
                "message": f"Kanban created with {len(stages)} stages.",
                "kanban_id": self._kanban.kanban_id,
                "current_stage": {
                    "stage_id": current_stage.stage_id,
                    "description": current_stage.description,
                    "deliverable_type": current_stage.deliverable_type,
                } if current_stage else None,
            }
    
    async def get_kanban(self) -> Optional[Kanban]:
        """获取当前 Kanban"""
        if not self._loaded:
            await self._ensure_loaded()
        return self._kanban
    
    async def get_current_stage(self) -> Optional[Stage]:
        """获取当前阶段"""
        if not self._loaded:
            await self._ensure_loaded()
        
        if self._kanban:
            return self._kanban.get_current_stage()
        return None
    
    async def submit_deliverable(
        self,
        stage_id: str,
        deliverable: Dict[str, Any],
        reflection: str = "",
    ) -> Dict[str, Any]:
        """提交阶段交付物"""
        async with self._lock:
            if not self._loaded:
                await self._ensure_loaded()
            
            if not self._kanban:
                return {"status": "error", "message": "No kanban exists."}
            
            stage = self._kanban.get_stage_by_id(stage_id)
            if not stage:
                return {"status": "error", "message": f"Stage '{stage_id}' not found."}
            
            current_stage = self._kanban.get_current_stage()
            if current_stage and current_stage.stage_id != stage_id:
                return {
                    "status": "error",
                    "message": f"Current stage is '{current_stage.stage_id}', not '{stage_id}'.",
                }
            
            if stage.deliverable_schema:
                valid, error_msg = self._validate_deliverable(deliverable, stage.deliverable_schema)
                if not valid:
                    stage.status = StageStatus.FAILED
                    stage.completed_at = time.time()
                    stage.reflection = f"Validation failed: {error_msg}"
                    await self.save()
                    return {
                        "status": "error",
                        "message": f"Deliverable validation failed: {error_msg}",
                    }
            
            deliverable_key = f"{self.agent_id}_deliverable_{stage_id}"
            if self._file_system:
                from derisk.agent.core.memory.gpts import FileType
                
                await self._file_system.save_file(
                    file_key=deliverable_key,
                    data=json.dumps(deliverable, ensure_ascii=False),
                    file_type=FileType.DELIVERABLE,
                    extension="json",
                )
            
            self._deliverables[stage_id] = deliverable
            stage.status = StageStatus.COMPLETED
            stage.deliverable_file = deliverable_key
            stage.completed_at = time.time()
            stage.reflection = reflection
            
            has_next = self._kanban.advance_to_next_stage()
            await self.save()
            
            result = {
                "status": "success",
                "message": f"Stage '{stage_id}' completed.",
            }
            
            if has_next:
                next_stage = self._kanban.get_current_stage()
                result["next_stage"] = {
                    "stage_id": next_stage.stage_id,
                    "description": next_stage.description,
                    "deliverable_type": next_stage.deliverable_type,
                }
            else:
                result["all_completed"] = True
                result["message"] += " All stages completed!"
            
            return result
    
    def _validate_deliverable(
        self,
        deliverable: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> tuple:
        """验证交付物"""
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
    
    async def read_deliverable(self, stage_id: str) -> Dict[str, Any]:
        """读取阶段交付物"""
        async with self._lock:
            if not self._loaded:
                await self._ensure_loaded()
            
            if not self._kanban:
                return {"status": "error", "message": "No kanban exists."}
            
            stage = self._kanban.get_stage_by_id(stage_id)
            if not stage:
                return {"status": "error", "message": f"Stage '{stage_id}' not found."}
            
            if not stage.deliverable_file:
                return {"status": "error", "message": f"Stage '{stage_id}' has no deliverable."}
            
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
            
            if self._file_system:
                content = await self._file_system.read_file(stage.deliverable_file)
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
        """记录工作日志"""
        async with self._lock:
            if not self._loaded:
                await self._ensure_loaded()
            
            entry = WorkEntry(
                timestamp=time.time(),
                tool=tool,
                summary=summary or "",
            )
            
            if not self._kanban:
                self._pre_kanban_logs.append(entry)
            else:
                stage = self._kanban.get_current_stage()
                if stage:
                    stage.work_log.append(entry)
                    await self.save()
    
    # ==================== 状态报告 ====================
    
    async def get_status_report(self) -> str:
        """获取状态报告"""
        if not self._loaded:
            await self._ensure_loaded()
        
        lines = ["## 任务状态概览", ""]
        
        pending = [t for t in self._todos.values() if t.status == TaskStatus.PENDING]
        working = [t for t in self._todos.values() if t.status == TaskStatus.WORKING]
        completed = [t for t in self._todos.values() if t.status == TaskStatus.COMPLETED]
        failed = [t for t in self._todos.values() if t.status == TaskStatus.FAILED]
        
        lines.append(f"### Todo 列表状态")
        lines.append(f"- 待处理: {len(pending)}")
        lines.append(f"- 进行中: {len(working)}")
        lines.append(f"- 已完成: {len(completed)}")
        lines.append(f"- 失败: {len(failed)}")
        lines.append("")
        
        if working:
            lines.append("### 当前进行中")
            for task in working:
                lines.append(f"- [{task.id}] {task.title} ({task.progress*100:.0f}%)")
            lines.append("")
        
        if self._kanban:
            lines.append("### Kanban 看板")
            lines.append(self._kanban.generate_overview())
        else:
            exploration_count = len(self._pre_kanban_logs)
            lines.append("### 探索阶段")
            lines.append(f"探索次数: {exploration_count}/{self.exploration_limit}")
            if self.is_exploration_limit_reached():
                lines.append("⚠️ **探索限制已达，请创建 Kanban**")
        
        return "\n".join(lines)
    
    def get_exploration_count(self) -> int:
        return len(self._pre_kanban_logs)
    
    def is_exploration_limit_reached(self) -> bool:
        return self.get_exploration_count() >= self.exploration_limit
    
    async def get_todolist_data(self) -> Optional[Dict[str, Any]]:
        """获取 Todo 列表可视化数据"""
        if not self._loaded:
            await self._ensure_loaded()
        
        status_map = {
            TaskStatus.PENDING: "pending",
            TaskStatus.WORKING: "working",
            TaskStatus.COMPLETED: "completed",
            TaskStatus.FAILED: "failed",
            TaskStatus.BLOCKED: "blocked",
            TaskStatus.SKIPPED: "skipped",
        }
        
        items = []
        for i, task in enumerate(sorted(self._todos.values(), key=lambda t: t.created_at)):
            items.append({
                "id": task.id,
                "title": task.title,
                "status": status_map.get(task.status, "pending"),
                "priority": task.priority.value,
                "progress": task.progress,
                "index": i,
            })
        
        current_index = 0
        for i, item in enumerate(items):
            if item["status"] == "working":
                current_index = i
                break
        
        mission = self._kanban.mission if self._kanban else "任务管理"
        
        return {
            "uid": f"{self.agent_id}_todolist",
            "type": "all",
            "mission": mission,
            "items": items,
            "current_index": current_index,
        }
    
    async def close(self):
        await self.save()
    
    async def _ensure_loaded(self):
        if not self._loaded:
            await self.load()


async def create_task_board_manager(
    session_id: str,
    agent_id: str,
    file_system: Optional["AgentFileSystem"] = None,
    kanban_storage: Optional["KanbanStorage"] = None,
    exploration_limit: int = 3,
) -> TaskBoardManager:
    manager = TaskBoardManager(
        session_id=session_id,
        agent_id=agent_id,
        file_system=file_system,
        kanban_storage=kanban_storage,
        exploration_limit=exploration_limit,
    )
    await manager.load()
    return manager


__all__ = [
    "TaskBoardManager",
    "TaskItem",
    "TaskStatus",
    "TaskPriority",
    "Kanban",
    "Stage",
    "StageStatus",
    "WorkEntry",
    "create_task_board_manager",
]