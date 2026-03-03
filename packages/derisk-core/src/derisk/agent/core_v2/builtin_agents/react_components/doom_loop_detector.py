"""
末日循环检测器 - 检测重复工具调用

参考ReActMasterAgent的DoomLoopDetector实现
"""

import hashlib
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DoomLoopAction(str, Enum):
    """Doom Loop处理动作"""
    ALLOW = "allow"
    BLOCK = "block"
    ASK_USER = "ask_user"


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    args: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    call_hash: str = field(default="")
    
    def __post_init__(self):
        if not self.call_hash:
            self.call_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """计算调用的唯一哈希值"""
        normalized_args = json.dumps(self.args, sort_keys=True, ensure_ascii=False)
        content = f"{self.tool_name}:{normalized_args}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    
    def matches(self, other: "ToolCallRecord") -> bool:
        """检查两个调用是否匹配"""
        return self.call_hash == other.call_hash


@dataclass
class DoomLoopCheckResult:
    """Doom Loop检查结果"""
    is_doom_loop: bool
    consecutive_count: int
    action: DoomLoopAction
    message: str
    detected_pattern: Optional[List[ToolCallRecord]] = None


class DoomLoopDetector:
    """
    末日循环检测器
    
    检测Agent是否陷入重复调用同一工具的无限循环中。
    当检测到连续多次相同参数的工具调用时，触发警告。
    """
    
    def __init__(
        self,
        threshold: int = 3,
        max_history: int = 100,
        expiry_seconds: float = 300,
    ):
        """
        初始化检测器
        
        Args:
            threshold: 触发检测的连续相同调用次数阈值
            max_history: 历史记录最大保留数量
            expiry_seconds: 调用记录过期时间（秒）
        """
        self.threshold = threshold
        self.max_history = max_history
        self.expiry_seconds = expiry_seconds
        self._call_history: deque = deque(maxlen=max_history)
    
    def record_call(self, tool_name: str, args: Dict[str, Any]) -> ToolCallRecord:
        """记录一次工具调用"""
        record = ToolCallRecord(tool_name=tool_name, args=args)
        self._call_history.append(record)
        self._cleanup_expired_records()
        
        logger.debug(f"[DoomLoop] 记录工具调用: {tool_name}, hash: {record.call_hash[:8]}")
        return record
    
    def check_doom_loop(self) -> DoomLoopCheckResult:
        """
        检查是否存在末日循环
        
        Returns:
            DoomLoopCheckResult: 检查结果
        """
        if len(self._call_history) < self.threshold:
            return DoomLoopCheckResult(
                is_doom_loop=False,
                consecutive_count=0,
                action=DoomLoopAction.ALLOW,
                message="历史记录不足，无需检测"
            )
        
        recent_calls = list(self._call_history)[-self.threshold * 2:]
        
        for i in range(len(recent_calls) - self.threshold + 1):
            window = recent_calls[i:i + self.threshold]
            
            if all(call.matches(window[0]) for call in window):
                message = self._generate_warning_message(window)
                
                return DoomLoopCheckResult(
                    is_doom_loop=True,
                    consecutive_count=self.threshold,
                    action=DoomLoopAction.ASK_USER,
                    message=message,
                    detected_pattern=window
                )
        
        return DoomLoopCheckResult(
            is_doom_loop=False,
            consecutive_count=0,
            action=DoomLoopAction.ALLOW,
            message="未检测到末日循环"
        )
    
    def _generate_warning_message(self, pattern: List[ToolCallRecord]) -> str:
        """生成警告消息"""
        tool_name = pattern[0].tool_name
        args = pattern[0].args
        count = len(pattern)
        
        return f"""
⚠️ 检测到可能的无限循环

发现连续 {count} 次调用相同的工具：
- 工具名称: {tool_name}
- 调用参数: {json.dumps(args, ensure_ascii=False, indent=2)}

这通常表明Agent陷入了重复执行模式。
建议检查任务逻辑或尝试不同的方法。
"""
    
    def _cleanup_expired_records(self):
        """清理过期的调用记录"""
        current_time = time.time()
        
        while self._call_history:
            oldest = self._call_history[0]
            if current_time - oldest.timestamp > self.expiry_seconds:
                self._call_history.popleft()
            else:
                break
    
    def reset(self):
        """重置检测器"""
        self._call_history.clear()
        logger.info("[DoomLoop] 检测器已重置")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_calls": len(self._call_history),
            "threshold": self.threshold,
            "max_history": self.max_history,
        }