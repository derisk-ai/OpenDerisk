"""
Recovery Coordinator - 恢复协调器

统一管理 Core V1 和 Core V2 的中断恢复
支持任意点中断恢复、Todo/Kanban 续接
"""

from typing import Dict, List, Optional, Any, Union, TYPE_CHECKING
from datetime import datetime
import asyncio
import json
import logging
import os

from .interaction_protocol import (
    InteractionRequest,
    InteractionResponse,
    InteractionStatus,
    TodoItem,
    InterruptPoint,
    RecoveryState,
    RecoveryResult,
    ResumeResult,
    RecoveryError,
)
from .interaction_gateway import StateStore, MemoryStateStore

if TYPE_CHECKING:
    from derisk.agent.core import ConversableAgent
    from derisk.agent.core_v2 import SimpleAgent

logger = logging.getLogger(__name__)


class RecoveryCoordinator:
    """
    恢复协调器
    
    职责：
    1. 在交互点创建快照
    2. 持久化恢复状态
    3. 协调恢复流程
    4. 管理 Todo 列表
    """
    
    def __init__(
        self,
        state_store: Optional[StateStore] = None,
        checkpoint_interval: int = 5,
    ):
        self.state_store = state_store or MemoryStateStore()
        self.checkpoint_interval = checkpoint_interval
        
        self._recovery_states: Dict[str, RecoveryState] = {}
        self._interrupt_points: Dict[str, InterruptPoint] = {}
        self._todos: Dict[str, Dict[str, TodoItem]] = {}
    
    async def create_checkpoint(
        self,
        session_id: str,
        execution_id: str,
        step_index: int,
        phase: str,
        context: Dict[str, Any],
        agent: Union["ConversableAgent", "SimpleAgent"],
    ) -> str:
        """
        创建检查点
        """
        from datetime import datetime
        checkpoint_id = f"cp_{session_id}_{step_index}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        snapshot_data = await self._collect_snapshot_data(agent)
        
        interrupt_point = InterruptPoint(
            session_id=session_id,
            execution_id=execution_id,
            step_index=step_index,
            phase=phase,
            reason="checkpoint",
        )
        
        recovery_state = RecoveryState(
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            interrupt_point=interrupt_point,
            conversation_history=snapshot_data.get("conversation_history", []),
            tool_execution_history=snapshot_data.get("tool_execution_history", []),
            decision_history=snapshot_data.get("decision_history", []),
            pending_actions=snapshot_data.get("pending_actions", []),
            files_created=snapshot_data.get("files_created", []),
            files_modified=snapshot_data.get("files_modified", []),
            variables=snapshot_data.get("variables", {}),
            todo_list=snapshot_data.get("todo_list", []),
            completed_subtasks=snapshot_data.get("completed_subtasks", []),
            pending_subtasks=snapshot_data.get("pending_subtasks", []),
            original_goal=snapshot_data.get("original_goal", ""),
            current_subgoal=snapshot_data.get("current_subgoal"),
        )
        
        recovery_state.snapshot_size = len(json.dumps(recovery_state.to_dict()))
        
        await self.state_store.set(
            f"checkpoint:{session_id}:{checkpoint_id}",
            recovery_state.to_dict()
        )
        
        await self.state_store.set(
            f"latest_checkpoint:{session_id}",
            {"checkpoint_id": checkpoint_id, "timestamp": datetime.now().isoformat()}
        )
        
        self._recovery_states[session_id] = recovery_state
        self._interrupt_points[interrupt_point.interrupt_id] = interrupt_point
        
        logger.info(f"[RecoveryCoordinator] Created checkpoint {checkpoint_id}")
        return checkpoint_id
    
    async def create_interaction_checkpoint(
        self,
        session_id: str,
        execution_id: str,
        interaction_request: InteractionRequest,
        agent: Union["ConversableAgent", "SimpleAgent"],
    ) -> str:
        """在交互请求发起时创建检查点"""
        checkpoint_id = await self.create_checkpoint(
            session_id=session_id,
            execution_id=execution_id,
            step_index=interaction_request.step_index,
            phase="waiting_interaction",
            context=interaction_request.context,
            agent=agent,
        )
        
        if session_id in self._recovery_states:
            self._recovery_states[session_id].pending_interactions.append(interaction_request)
            await self._persist_recovery_state(session_id)
        
        logger.info(f"[RecoveryCoordinator] Created interaction checkpoint {checkpoint_id}")
        return checkpoint_id
    
    async def has_recovery_state(self, session_id: str) -> bool:
        """检查是否有恢复状态"""
        latest = await self.state_store.get(f"latest_checkpoint:{session_id}")
        return latest is not None
    
    async def get_latest_recovery_state(self, session_id: str) -> Optional[RecoveryState]:
        """获取最新的恢复状态"""
        latest = await self.state_store.get(f"latest_checkpoint:{session_id}")
        if not latest:
            return None
        
        checkpoint_id = latest.get("checkpoint_id")
        data = await self.state_store.get(f"checkpoint:{session_id}:{checkpoint_id}")
        if data:
            return RecoveryState.from_dict(data)
        return None
    
    async def recover(
        self,
        session_id: str,
        checkpoint_id: Optional[str] = None,
        resume_mode: str = "continue",
    ) -> RecoveryResult:
        """
        恢复执行
        
        Args:
            session_id: 会话ID
            checkpoint_id: 检查点ID（可选，默认使用最新）
            resume_mode: 恢复模式 (continue/skip/restart)
        """
        if checkpoint_id:
            data = await self.state_store.get(f"checkpoint:{session_id}:{checkpoint_id}")
            if data:
                recovery_state = RecoveryState.from_dict(data)
            else:
                return RecoveryResult(success=False, error="Checkpoint not found")
        else:
            recovery_state = await self.get_latest_recovery_state(session_id)
        
        if not recovery_state:
            return RecoveryResult(success=False, error="No recovery state found")
        
        validation = await self._validate_recovery_state(recovery_state)
        if not validation.get("valid", False):
            return RecoveryResult(success=False, error=validation.get("error", "Validation failed"))
        
        await self._restore_files(recovery_state)
        
        return RecoveryResult(
            success=True,
            recovery_context=recovery_state,
            pending_interaction=recovery_state.pending_interactions[0] if recovery_state.pending_interactions else None,
            pending_todos=[t for t in recovery_state.todo_list if t.status != "completed"],
            summary=recovery_state.get_progress_summary(),
        )
    
    async def resume_from_interaction(
        self,
        session_id: str,
        interaction_response: InteractionResponse,
    ) -> ResumeResult:
        """从交互响应恢复执行"""
        recovery_state = self._recovery_states.get(session_id)
        if not recovery_state:
            recovery_state = await self.get_latest_recovery_state(session_id)
        
        if not recovery_state:
            return ResumeResult(success=False, error="No recovery state")
        
        recovery_state.pending_interactions = [
            r for r in recovery_state.pending_interactions
            if r.request_id != interaction_response.request_id
        ]
        
        return ResumeResult(
            success=True,
            checkpoint_id=recovery_state.checkpoint_id,
            step_index=recovery_state.interrupt_point.step_index,
            conversation_history=recovery_state.conversation_history,
            variables=recovery_state.variables,
            todo_list=recovery_state.todo_list,
            response=interaction_response,
        )
    
    async def create_todo(
        self,
        session_id: str,
        content: str,
        priority: int = 0,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """创建 Todo"""
        if session_id not in self._todos:
            self._todos[session_id] = {}
        
        todo = TodoItem(
            content=content,
            priority=priority,
            dependencies=dependencies or [],
        )
        
        self._todos[session_id][todo.id] = todo
        await self._persist_todos(session_id)
        
        logger.info(f"[RecoveryCoordinator] Created todo {todo.id}: {content}")
        return todo.id
    
    async def update_todo(
        self,
        session_id: str,
        todo_id: str,
        status: Optional[str] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """更新 Todo 状态"""
        if session_id not in self._todos or todo_id not in self._todos[session_id]:
            return
        
        todo = self._todos[session_id][todo_id]
        
        if status:
            todo.status = status
            if status == "in_progress":
                todo.started_at = datetime.now()
            elif status in ["completed", "failed"]:
                todo.completed_at = datetime.now()
        
        if result:
            todo.result = result
        if error:
            todo.error = error
        
        await self._persist_todos(session_id)
    
    def get_todos(self, session_id: str) -> List[TodoItem]:
        """获取 Todo 列表"""
        return list(self._todos.get(session_id, {}).values())
    
    def get_todo(self, session_id: str, todo_id: str) -> Optional[TodoItem]:
        """获取单个 Todo"""
        return self._todos.get(session_id, {}).get(todo_id)
    
    def get_next_todo(self, session_id: str) -> Optional[TodoItem]:
        """获取下一个可执行的 Todo"""
        todos = self._todos.get(session_id, {})
        for todo_id, todo in todos.items():
            if todo.status == "pending":
                if self._dependencies_met(session_id, todo):
                    return todo
        return None
    
    def get_progress(self, session_id: str) -> tuple:
        """获取进度"""
        todos = list(self._todos.get(session_id, {}).values())
        total = len(todos)
        completed = len([t for t in todos if t.status == "completed"])
        return completed, total
    
    def clear_session(self, session_id: str):
        """清除会话状态"""
        self._todos.pop(session_id, None)
        self._recovery_states.pop(session_id, None)
    
    async def _collect_snapshot_data(
        self,
        agent: Union["ConversableAgent", "SimpleAgent"],
    ) -> Dict[str, Any]:
        """收集快照数据"""
        data = {
            "conversation_history": [],
            "tool_execution_history": [],
            "decision_history": [],
            "pending_actions": [],
            "files_created": [],
            "files_modified": [],
            "variables": {},
            "todo_list": [],
            "completed_subtasks": [],
            "pending_subtasks": [],
            "original_goal": "",
            "current_subgoal": None,
        }
        
        if hasattr(agent, "agent_context"):
            if agent.memory and hasattr(agent.memory, "get_context_window"):
                try:
                    data["conversation_history"] = await agent.memory.get_context_window(max_tokens=100000)
                except:
                    pass
            
            if hasattr(agent, "variables"):
                data["variables"] = dict(getattr(agent, "variables", {}))
            
            data["todo_list"] = list(self._todos.get(
                getattr(agent.agent_context, "conv_session_id", "default"),
                {}
            ).values())
        
        elif hasattr(agent, "_messages"):
            data["conversation_history"] = getattr(agent, "_messages", [])
            data["variables"] = getattr(agent, "_variables", {})
        
        return data
    
    async def _validate_recovery_state(self, recovery_state: RecoveryState) -> Dict[str, Any]:
        """验证恢复状态"""
        if not recovery_state.session_id:
            return {"valid": False, "error": "Missing session_id"}
        if not recovery_state.checkpoint_id:
            return {"valid": False, "error": "Missing checkpoint_id"}
        return {"valid": True}
    
    async def _restore_files(self, recovery_state: RecoveryState):
        """恢复文件状态"""
        for file_info in recovery_state.files_created + recovery_state.files_modified:
            path = file_info.get("path") if isinstance(file_info, dict) else getattr(file_info, "path", None)
            if path and not os.path.exists(path):
                logger.warning(f"[RecoveryCoordinator] File not found: {path}")
    
    async def _persist_recovery_state(self, session_id: str):
        """持久化恢复状态"""
        if session_id in self._recovery_states:
            state = self._recovery_states[session_id]
            await self.state_store.set(
                f"checkpoint:{session_id}:{state.checkpoint_id}",
                state.to_dict()
            )
    
    async def _persist_todos(self, session_id: str):
        """持久化 Todo 列表"""
        todos = self._todos.get(session_id, {})
        data = {
            "session_id": session_id,
            "todos": [t.to_dict() for t in todos.values()],
        }
        await self.state_store.set(f"todos:{session_id}", data)
    
    async def _load_todos(self, session_id: str):
        """加载 Todo 列表"""
        data = await self.state_store.get(f"todos:{session_id}")
        if data:
            self._todos[session_id] = {
                t.get("id"): TodoItem.from_dict(t)
                for t in data.get("todos", [])
            }
    
    def _dependencies_met(self, session_id: str, todo: TodoItem) -> bool:
        """检查依赖是否满足"""
        todos = self._todos.get(session_id, {})
        for dep_id in todo.dependencies:
            if dep_id in todos:
                if todos[dep_id].status != "completed":
                    return False
        return True


_coordinator_instance: Optional[RecoveryCoordinator] = None


def get_recovery_coordinator() -> RecoveryCoordinator:
    """获取全局恢复协调器实例"""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = RecoveryCoordinator()
    return _coordinator_instance


def set_recovery_coordinator(coordinator: RecoveryCoordinator):
    """设置全局恢复协调器实例"""
    global _coordinator_instance
    _coordinator_instance = coordinator


__all__ = [
    "RecoveryCoordinator",
    "get_recovery_coordinator",
    "set_recovery_coordinator",
]