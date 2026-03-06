"""
ExecutionReplay - 执行重放机制

实现完整的执行重放能力：
- 记录执行过程：决策、动作、结果
- 重放执行历史：从任意点重放
- 调试分析：分析执行路径
- 回归测试：验证行为一致性
"""

from typing import Dict, Any, List, Optional, AsyncIterator, Callable, Awaitable
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import asyncio
import json
import logging
import hashlib
from dataclasses import dataclass, field as dataclass_field

logger = logging.getLogger(__name__)


class ReplayEventType(str, Enum):
    """重放事件类型"""
    STEP_START = "step_start"
    STEP_END = "step_end"
    THINKING = "thinking"
    DECISION = "decision"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    CHECKPOINT = "checkpoint"
    STATE_CHANGE = "state_change"
    MESSAGE = "message"


class ReplayMode(str, Enum):
    """重放模式"""
    NORMAL = "normal"
    DEBUG = "debug"
    STEP_BY_STEP = "step_by_step"
    FAST_FORWARD = "fast_forward"


@dataclass
class ReplayEvent:
    """重放事件"""
    event_id: str
    event_type: ReplayEventType
    execution_id: str
    step_index: int
    timestamp: datetime = dataclass_field(default_factory=datetime.now)
    
    data: Dict[str, Any] = dataclass_field(default_factory=dict)
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)
    
    parent_event_id: Optional[str] = None
    
    checksum: Optional[str] = None
    
    def compute_checksum(self) -> str:
        event_data = {
            "event_type": self.event_type.value,
            "step_index": self.step_index,
            "data": self.data
        }
        return hashlib.md5(json.dumps(event_data, sort_keys=True, default=str).encode()).hexdigest()


class ExecutionRecording:
    """
    执行录制器
    
    录制所有执行事件，支持后续重放
    
    示例:
        recorder = ExecutionRecording("exec-1")
        
        # 录制事件
        recorder.record(ReplayEventType.THINKING, {"content": "思考中..."})
        recorder.record(ReplayEventType.DECISION, {"type": "tool_call", "tool": "bash"})
        
        # 导出
        recording = recorder.export()
    """
    
    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        self._events: List[ReplayEvent] = []
        self._event_index: Dict[str, int] = {}
        self._step_events: Dict[int, List[int]] = {}
        
        self._start_time = datetime.now()
        self._end_time: Optional[datetime] = None
    
    @property
    def event_count(self) -> int:
        return len(self._events)
    
    @property
    def step_count(self) -> int:
        return len(self._step_events)
    
    def record(
        self,
        event_type: ReplayEventType,
        data: Dict[str, Any],
        step_index: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        parent_event_id: Optional[str] = None
    ) -> ReplayEvent:
        """录制事件"""
        event_id = f"evt-{len(self._events):08d}"
        
        event = ReplayEvent(
            event_id=event_id,
            event_type=event_type,
            execution_id=self.execution_id,
            step_index=step_index,
            data=data,
            metadata=metadata or {},
            parent_event_id=parent_event_id
        )
        
        event.checksum = event.compute_checksum()
        
        event_index = len(self._events)
        self._events.append(event)
        self._event_index[event_id] = event_index
        
        if step_index not in self._step_events:
            self._step_events[step_index] = []
        self._step_events[step_index].append(event_index)
        
        logger.debug(f"[ExecutionRecording] 录制事件: {event_type.value} @ step {step_index}")
        
        return event
    
    def get_event(self, event_id: str) -> Optional[ReplayEvent]:
        """获取事件"""
        if event_id in self._event_index:
            return self._events[self._event_index[event_id]]
        return None
    
    def get_events_by_step(self, step_index: int) -> List[ReplayEvent]:
        """获取步骤的所有事件"""
        if step_index in self._step_events:
            return [self._events[i] for i in self._step_events[step_index]]
        return []
    
    def get_events_by_type(self, event_type: ReplayEventType) -> List[ReplayEvent]:
        """获取类型的所有事件"""
        return [e for e in self._events if e.event_type == event_type]
    
    def get_event_tree(self) -> Dict[str, Any]:
        """获取事件树结构"""
        tree = {"root": []}
        
        for event in self._events:
            node = {
                "id": event.event_id,
                "type": event.event_type.value,
                "step": event.step_index,
                "timestamp": event.timestamp.isoformat(),
                "data": event.data,
                "children": []
            }
            
            if event.parent_event_id and event.parent_event_id in self._event_index:
                parent_idx = self._event_index[event.parent_event_id]
                if "children" not in self._events[parent_idx].metadata:
                    self._events[parent_idx].metadata["children"] = []
                self._events[parent_idx].metadata["children"].append(node)
            else:
                tree["root"].append(node)
        
        return tree
    
    def export(self) -> Dict[str, Any]:
        """导出录制"""
        return {
            "execution_id": self.execution_id,
            "start_time": self._start_time.isoformat(),
            "end_time": self._end_time.isoformat() if self._end_time else None,
            "event_count": len(self._events),
            "step_count": len(self._step_events),
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value,
                    "step_index": e.step_index,
                    "timestamp": e.timestamp.isoformat(),
                    "data": e.data,
                    "metadata": e.metadata,
                    "parent_event_id": e.parent_event_id,
                    "checksum": e.checksum
                }
                for e in self._events
            ]
        }
    
    @classmethod
    def load(cls, data: Dict[str, Any]) -> "ExecutionRecording":
        """加载录制"""
        recording = cls(data["execution_id"])
        recording._start_time = datetime.fromisoformat(data["start_time"])
        
        if data.get("end_time"):
            recording._end_time = datetime.fromisoformat(data["end_time"])
        
        for event_data in data["events"]:
            event = ReplayEvent(
                event_id=event_data["event_id"],
                event_type=ReplayEventType(event_data["event_type"]),
                execution_id=event_data["execution_id"],
                step_index=event_data["step_index"],
                timestamp=datetime.fromisoformat(event_data["timestamp"]),
                data=event_data["data"],
                metadata=event_data["metadata"],
                parent_event_id=event_data.get("parent_event_id"),
                checksum=event_data.get("checksum")
            )
            
            event_index = len(recording._events)
            recording._events.append(event)
            recording._event_index[event.event_id] = event_index
            
            if event.step_index not in recording._step_events:
                recording._step_events[event.step_index] = []
            recording._step_events[event.step_index].append(event_index)
        
        return recording
    
    def finalize(self):
        """结束录制"""
        self._end_time = datetime.now()


class ExecutionReplayer:
    """
    执行重放器
    
    重放已录制的执行过程
    
    示例:
        replayer = ExecutionReplayer(recording)
        
        # 重放
        async for event in replayer.replay():
            print(f"{event.event_type}: {event.data}")
        
        # 从特定步骤重放
        async for event in replayer.replay_from_step(10):
            process(event)
    """
    
    def __init__(
        self,
        recording: ExecutionRecording,
        mode: ReplayMode = ReplayMode.NORMAL
    ):
        self.recording = recording
        self.mode = mode
        
        self._current_index = 0
        self._breakpoints: set = set()
        self._on_event_handlers: List[Callable] = []
    
    def add_breakpoint(self, step_index: int):
        """添加断点"""
        self._breakpoints.add(step_index)
    
    def remove_breakpoint(self, step_index: int):
        """移除断点"""
        self._breakpoints.discard(step_index)
    
    def on_event(self, handler: Callable[[ReplayEvent], Awaitable[None]]):
        """添加事件处理器"""
        self._on_event_handlers.append(handler)
    
    async def replay(
        self,
        speed: float = 1.0
    ) -> AsyncIterator[ReplayEvent]:
        """重放执行"""
        self._current_index = 0
        
        prev_timestamp = None
        
        for event in self.recording._events:
            if speed < float('inf') and prev_timestamp:
                actual_delay = (event.timestamp - prev_timestamp).total_seconds()
                delay = actual_delay / speed
                if delay > 0:
                    await asyncio.sleep(delay)
            
            if event.step_index in self._breakpoints:
                yield event
                await self._wait_for_continue()
            else:
                yield event
            
            prev_timestamp = event.timestamp
            
            for handler in self._on_event_handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"[ExecutionReplayer] Handler error: {e}")
            
            self._current_index += 1
    
    async def replay_from_step(
        self,
        step_index: int,
        speed: float = 1.0
    ) -> AsyncIterator[ReplayEvent]:
        """从特定步骤重放"""
        if step_index not in self.recording._step_events:
            return
        
        start_event_idx = self.recording._step_events[step_index][0]
        
        self._current_index = start_event_idx
        
        for event in self.recording._events[start_event_idx:]:
            yield event
            self._current_index += 1
    
    async def replay_step(self, step_index: int) -> List[ReplayEvent]:
        """重放特定步骤"""
        return self.recording.get_events_by_step(step_index)
    
    async def _wait_for_continue(self):
        """等待继续"""
        if self.mode == ReplayMode.STEP_BY_STEP:
            await asyncio.sleep(0.1)
    
    def get_current_position(self) -> int:
        """获取当前位置"""
        return self._current_index
    
    def get_progress(self) -> float:
        """获取进度"""
        if len(self.recording._events) == 0:
            return 0.0
        return self._current_index / len(self.recording._events)


class ExecutionAnalyzer:
    """
    执行分析器
    
    分析录制数据，提供洞察
    
    示例:
        analyzer = ExecutionAnalyzer(recording)
        
        # 分析决策路径
        path = analyzer.analyze_decision_path()
        
        # 分析错误
        errors = analyzer.analyze_errors()
        
        # 分析性能
        performance = analyzer.analyze_performance()
    """
    
    def __init__(self, recording: ExecutionRecording):
        self.recording = recording
    
    def analyze_decision_path(self) -> List[Dict[str, Any]]:
        """分析决策路径"""
        decisions = self.recording.get_events_by_type(ReplayEventType.DECISION)
        
        path = []
        for event in decisions:
            path.append({
                "step": event.step_index,
                "decision_type": event.data.get("type"),
                "tool": event.data.get("tool_name"),
                "reasoning": event.data.get("reasoning", "")[:100]
            })
        
        return path
    
    def analyze_errors(self) -> List[Dict[str, Any]]:
        """分析错误"""
        errors = self.recording.get_events_by_type(ReplayEventType.ERROR)
        
        return [
            {
                "step": e.step_index,
                "error_type": e.data.get("error_type"),
                "message": e.data.get("message"),
                "timestamp": e.timestamp.isoformat()
            }
            for e in errors
        ]
    
    def analyze_performance(self) -> Dict[str, Any]:
        """分析性能"""
        step_events = self.recording._step_events
        
        if not step_events:
            return {}
        
        step_durations = []
        for step_idx, event_indices in step_events.items():
            if len(event_indices) >= 2:
                first = self.recording._events[event_indices[0]]
                last = self.recording._events[event_indices[-1]]
                duration = (last.timestamp - first.timestamp).total_seconds()
                step_durations.append(duration)
        
        tool_calls = self.recording.get_events_by_type(ReplayEventType.TOOL_CALL)
        tool_usage = {}
        for event in tool_calls:
            tool = event.data.get("tool_name", "unknown")
            tool_usage[tool] = tool_usage.get(tool, 0) + 1
        
        return {
            "total_steps": len(step_events),
            "total_events": len(self.recording._events),
            "avg_step_duration": sum(step_durations) / len(step_durations) if step_durations else 0,
            "max_step_duration": max(step_durations) if step_durations else 0,
            "tool_usage": tool_usage,
            "total_tool_calls": len(tool_calls)
        }
    
    def get_comparison_checksum(self) -> str:
        """获取比较校验和，用于回归测试"""
        checksums = [e.checksum for e in self.recording._events if e.checksum]
        combined = "".join(checksums)
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def compare_recordings(self, other: ExecutionRecording) -> Dict[str, Any]:
        """比较两个录制"""
        self_checksum = self.get_comparison_checksum()
        other_checksum = ExecutionAnalyzer(other).get_comparison_checksum()
        
        self_events = {(e.event_type, e.step_index): e.data for e in self.recording._events}
        other_events = {(e.event_type, e.step_index): e.data for e in other._events}
        
        self_keys = set(self_events.keys())
        other_keys = set(other_events.keys())
        
        added = other_keys - self_keys
        removed = self_keys - other_keys
        common = self_keys & other_keys
        
        changed = []
        for key in common:
            if self_events[key] != other_events[key]:
                changed.append(key)
        
        return {
            "checksums_match": self_checksum == other_checksum,
            "events_added": len(added),
            "events_removed": len(removed),
            "events_changed": len(changed),
            "details": {
                "added": [{"type": k[0], "step": k[1]} for k in added],
                "removed": [{"type": k[0], "step": k[1]} for k in removed],
                "changed": [{"type": k[0], "step": k[1]} for k in changed]
            }
        }


class ReplayManager:
    """
    重放管理器
    
    统一管理录制和重放
    
    示例:
        manager = ReplayManager()
        
        # 开始录制
        recording = manager.start_recording("exec-1")
        recording.record(ReplayEventType.THINKING, {"content": "..."})
        manager.end_recording("exec-1")
        
        # 重放
        replayer = manager.create_replayer("exec-1")
        async for event in replayer.replay():
            print(event)
    """
    
    def __init__(self, max_recordings: int = 100):
        self._recordings: Dict[str, ExecutionRecording] = {}
        self._max_recordings = max_recordings
        self._recording_counter = 0
    
    def start_recording(self, execution_id: str) -> ExecutionRecording:
        """开始录制"""
        recording = ExecutionRecording(execution_id)
        self._recordings[execution_id] = recording
        self._recording_counter += 1
        
        self._cleanup_old_recordings()
        
        logger.info(f"[ReplayManager] 开始录制: {execution_id}")
        return recording
    
    def get_recording(self, execution_id: str) -> Optional[ExecutionRecording]:
        """获取录制"""
        return self._recordings.get(execution_id)
    
    def end_recording(self, execution_id: str):
        """结束录制"""
        recording = self._recordings.get(execution_id)
        if recording:
            recording.finalize()
            logger.info(f"[ReplayManager] 结束录制: {execution_id}")
    
    def create_replayer(
        self,
        execution_id: str,
        mode: ReplayMode = ReplayMode.NORMAL
    ) -> Optional[ExecutionReplayer]:
        """创建重放器"""
        recording = self._recordings.get(execution_id)
        if recording:
            return ExecutionReplayer(recording, mode)
        return None
    
    def create_analyzer(self, execution_id: str) -> Optional[ExecutionAnalyzer]:
        """创建分析器"""
        recording = self._recordings.get(execution_id)
        if recording:
            return ExecutionAnalyzer(recording)
        return None
    
    def export_recording(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """导出录制"""
        recording = self._recordings.get(execution_id)
        if recording:
            return recording.export()
        return None
    
    def import_recording(self, data: Dict[str, Any]) -> ExecutionRecording:
        """导入录制"""
        recording = ExecutionRecording.load(data)
        self._recordings[recording.execution_id] = recording
        return recording
    
    def list_recordings(self) -> List[Dict[str, Any]]:
        """列出所有录制"""
        return [
            {
                "execution_id": r.execution_id,
                "event_count": r.event_count,
                "step_count": r.step_count,
                "start_time": r._start_time.isoformat(),
                "end_time": r._end_time.isoformat() if r._end_time else None
            }
            for r in self._recordings.values()
        ]
    
    def delete_recording(self, execution_id: str):
        """删除录制"""
        self._recordings.pop(execution_id, None)
    
    def _cleanup_old_recordings(self):
        """清理旧录制"""
        if len(self._recordings) > self._max_recordings:
            sorted_ids = sorted(
                self._recordings.keys(),
                key=lambda x: self._recordings[x]._start_time
            )
            
            for old_id in sorted_ids[:len(self._recordings) - self._max_recordings]:
                del self._recordings[old_id]
                logger.info(f"[ReplayManager] 清理旧录制: {old_id}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "total_recordings": len(self._recordings),
            "total_recordings_created": self._recording_counter,
            "total_events": sum(r.event_count for r in self._recordings.values()),
            "total_steps": sum(r.step_count for r in self._recordings.values())
        }


replay_manager = ReplayManager()