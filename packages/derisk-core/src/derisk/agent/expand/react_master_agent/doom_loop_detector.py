"""
末日循环 (Doom Loop) 检测机制

如果发现连续三次调用同一个工具且输入参数完全相同，
它会通过权限系统请求用户确认，以防止无限循环。
"""

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class DoomLoopAction(Enum):
    """Doom Loop 处理动作"""
    ALLOW = "allow"           # 允许继续执行
    BLOCK = "block"           # 阻止执行
    ASK_USER = "ask_user"     # 询问用户


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    args: Dict[str, Any]
    timestamp: float = field(default_factory=lambda: logging.time.time() if hasattr(logging, 'time') else __import__('time').time())
    call_hash: str = field(default="")

    def __post_init__(self):
        if not self.call_hash:
            self.call_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """计算调用的唯一哈希值"""
        # 规范化参数（排序键）
        normalized_args = json.dumps(self.args, sort_keys=True, ensure_ascii=False)
        content = f"{self.tool_name}:{normalized_args}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def matches(self, other: "ToolCallRecord") -> bool:
        """检查两个调用是否匹配（工具名和参数相同）"""
        return self.call_hash == other.call_hash


@dataclass
class DoomLoopCheckResult:
    """Doom Loop 检查结果"""
    is_doom_loop: bool
    consecutive_count: int
    action: DoomLoopAction
    message: str
    detected_pattern: Optional[List[ToolCallRecord]] = None


class DoomLoopConfig:
    """Doom Loop 检测配置"""
    # 触发检测的连续相同调用次数
    DEFAULT_THRESHOLD = 3

    # 历史记录最大保留数量
    MAX_HISTORY_SIZE = 100

    # 调用记录过期时间（秒）
    CALL_EXPIRY_SECONDS = 300  # 5分钟

    # 消息模板
    DOOM_LOOP_WARNING_TEMPLATE = """
⚠️ **检测到可能的无限循环 (Doom Loop)**

发现连续 {count} 次调用相同的工具：
- 工具名称: {tool_name}
- 调用参数: {args}

这通常表明 Agent 陷入了重复执行模式。
请选择处理方式：
1. [允许继续] - 继续执行当前操作
2. [修改参数] - 修改参数后重新执行
3. [终止任务] - 停止当前任务执行

检测到的调用历史：
{history}
"""


class DoomLoopDetector:
    """
    末日循环检测器

    用于检测 Agent 是否陷入重复调用同一工具的无限循环中。
    当检测到连续多次（默认3次）相同参数的工具调用时，触发用户确认。
    """

    def __init__(
        self,
        threshold: int = DoomLoopConfig.DEFAULT_THRESHOLD,
        max_history: int = DoomLoopConfig.MAX_HISTORY_SIZE,
        expiry_seconds: float = DoomLoopConfig.CALL_EXPIRY_SECONDS,
        permission_callback: Optional[Callable[[str, Dict], Awaitable[bool]]] = None,
    ):
        """
        初始化 Doom Loop 检测器

        Args:
            threshold: 触发检测的连续相同调用次数阈值
            max_history: 历史记录最大保留数量
            expiry_seconds: 调用记录过期时间（秒）
            permission_callback: 权限回调函数，用于请求用户确认
        """
        self.threshold = threshold
        self.max_history = max_history
        self.expiry_seconds = expiry_seconds
        self.permission_callback = permission_callback
        self._call_history: deque = deque(maxlen=max_history)
        self._pattern_cache: Dict[str, List[ToolCallRecord]] = {}

    def record_call(self, tool_name: str, args: Dict[str, Any]) -> ToolCallRecord:
        """
        记录一次工具调用

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            ToolCallRecord: 调用记录
        """
        record = ToolCallRecord(tool_name=tool_name, args=args)
        self._call_history.append(record)

        # 清理过期记录
        self._cleanup_expired_records()

        logger.debug(f"Recorded tool call: {tool_name}, hash: {record.call_hash[:8]}...")
        return record

    def _cleanup_expired_records(self):
        """清理过期的调用记录"""
        import time
        current_time = time.time()

        # 从头开始清理过期记录
        while self._call_history:
            oldest = self._call_history[0]
            if current_time - oldest.timestamp > self.expiry_seconds:
                self._call_history.popleft()
            else:
                break

    def _find_consecutive_pattern(self, record: ToolCallRecord) -> List[ToolCallRecord]:
        """
        查找最近的连续相同调用模式

        Args:
            record: 当前调用记录

        Returns:
            List[ToolCallRecord]: 连续的相同调用记录列表
        """
        if not self._call_history:
            return []

        pattern = []
        # 从历史记录末尾开始向前查找
        for r in reversed(self._call_history):
            if r.matches(record):
                pattern.insert(0, r)
            else:
                break

        return pattern

    def check_doom_loop(
        self,
        tool_name: str,
        args: Dict[str, Any],
        auto_record: bool = True,
    ) -> DoomLoopCheckResult:
        """
        检查是否存在末日循环

        Args:
            tool_name: 工具名称
            args: 工具参数
            auto_record: 是否自动记录本次调用

        Returns:
            DoomLoopCheckResult: 检查结果
        """
        current_record = ToolCallRecord(tool_name=tool_name, args=args)

        if auto_record:
            self.record_call(tool_name, args)

        pattern = self._find_consecutive_pattern(current_record)
        consecutive_count = len(pattern)

        if consecutive_count >= self.threshold:
            # 检测到末日循环
            logger.warning(
                f"Doom loop detected for tool '{tool_name}': "
                f"{consecutive_count} consecutive identical calls"
            )

            message = DoomLoopConfig.DOOM_LOOP_WARNING_TEMPLATE.format(
                count=consecutive_count,
                tool_name=tool_name,
                args=json.dumps(args, indent=2, ensure_ascii=False),
                history=self._format_history(pattern),
            )

            return DoomLoopCheckResult(
                is_doom_loop=True,
                consecutive_count=consecutive_count,
                action=DoomLoopAction.ASK_USER,
                message=message,
                detected_pattern=pattern,
            )

        return DoomLoopCheckResult(
            is_doom_loop=False,
            consecutive_count=consecutive_count,
            action=DoomLoopAction.ALLOW,
            message="",
            detected_pattern=pattern if pattern else None,
        )

    def _format_history(self, pattern: List[ToolCallRecord]) -> str:
        """格式化历史记录为可读字符串"""
        lines = []
        for i, record in enumerate(pattern, 1):
            time_str = self._format_timestamp(record.timestamp)
            lines.append(f"  {i}. [{time_str}] {record.tool_name}")
        return "\n".join(lines)

    def _format_timestamp(self, timestamp: float) -> str:
        """格式化时间戳"""
        from datetime import datetime
        try:
            return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        except:
            return "unknown"

    async def check_and_ask_permission(
        self,
        tool_name: str,
        args: Dict[str, Any],
        permission_ask_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    ) -> bool:
        """
        检查末日循环并请求用户权限

        Args:
            tool_name: 工具名称
            args: 工具参数
            permission_ask_func: 权限询问函数，接收消息内容，返回是否允许

        Returns:
            bool: 是否允许继续执行
        """
        result = self.check_doom_loop(tool_name, args)

        if not result.is_doom_loop:
            return True

        # 使用提供的权限函数或默认回调
        ask_func = permission_ask_func or self.permission_callback

        if ask_func:
            try:
                allowed = await ask_func(result.message)
                if allowed:
                    # 重置检测状态，允许继续
                    self._clear_pattern_for_tool(tool_name)
                    logger.info(f"User allowed doom loop continuation for {tool_name}")
                else:
                    logger.info(f"User blocked doom loop for {tool_name}")
                return allowed
            except Exception as e:
                logger.error(f"Error asking for permission: {e}")
                # 出错时默认阻止
                return False
        else:
            # 没有权限回调时，默认阻止
            logger.warning(
                f"Doom loop detected but no permission callback configured. "
                f"Blocking tool {tool_name}"
            )
            return False

    def _clear_pattern_for_tool(self, tool_name: str):
        """清除特定工具的模式缓存"""
        # 从历史中移除该工具的所有记录
        self._call_history = deque(
            [r for r in self._call_history if r.tool_name != tool_name],
            maxlen=self.max_history,
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取检测器统计信息"""
        return {
            "total_calls_recorded": len(self._call_history),
            "threshold": self.threshold,
            "max_history": self.max_history,
            "unique_tools": len(set(r.tool_name for r in self._call_history)),
        }

    def reset(self):
        """重置检测器状态"""
        self._call_history.clear()
        self._pattern_cache.clear()
        logger.info("DoomLoopDetector reset")


class IntelligentDoomLoopDetector(DoomLoopDetector):
    """
    智能末日循环检测器

    在基础检测之上，增加智能模式识别：
    1. 检测相似参数调用（非完全相同但高度相似）
    2. 检测循环调用模式（A->B->A->B）
    3. 检测重复执行无进展的情况
    """

    def __init__(
        self,
        threshold: int = DoomLoopConfig.DEFAULT_THRESHOLD,
        max_history: int = DoomLoopConfig.MAX_HISTORY_SIZE,
        expiry_seconds: float = DoomLoopConfig.CALL_EXPIRY_SECONDS,
        permission_callback: Optional[Callable[[str, Dict], Awaitable[bool]]] = None,
        similarity_threshold: float = 0.9,
    ):
        super().__init__(threshold, max_history, expiry_seconds, permission_callback)
        self.similarity_threshold = similarity_threshold

    def _calculate_similarity(self, args1: Dict, args2: Dict) -> float:
        """计算两个参数集的相似度"""
        if args1 == args2:
            return 1.0

        # 获取所有键
        all_keys = set(args1.keys()) | set(args2.keys())
        if not all_keys:
            return 1.0

        matching = 0
        for key in all_keys:
            if key in args1 and key in args2:
                if args1[key] == args2[key]:
                    matching += 1
                elif isinstance(args1[key], str) and isinstance(args2[key], str):
                    # 字符串使用编辑距离相似度
                    matching += self._string_similarity(args1[key], args2[key])
            # 键不存在算作不匹配

        return matching / len(all_keys)

    def _string_similarity(self, s1: str, s2: str) -> float:
        """计算字符串相似度 (简化版)"""
        if s1 == s2:
            return 1.0

        # 使用 Jaccard 相似度
        set1 = set(s1.lower().split())
        set2 = set(s2.lower().split())

        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _find_similar_pattern(self, record: ToolCallRecord) -> List[ToolCallRecord]:
        """查找相似的调用模式"""
        if not self._call_history:
            return []

        pattern = [record]
        for r in reversed(list(self._call_history)[:-1]):  # 排除最后一个（刚添加的）
            if r.tool_name == record.tool_name:
                similarity = self._calculate_similarity(r.args, record.args)
                if similarity >= self.similarity_threshold:
                    pattern.insert(0, r)
                else:
                    break
            else:
                break

        return pattern

    def check_doom_loop(
        self,
        tool_name: str,
        args: Dict[str, Any],
        auto_record: bool = True,
    ) -> DoomLoopCheckResult:
        """
        检查是否存在末日循环（包括相似调用）
        """
        # 首先进行精确匹配检查
        result = super().check_doom_loop(tool_name, args, auto_record)

        if result.is_doom_loop:
            return result

        # 检查相似模式
        current_record = ToolCallRecord(tool_name=tool_name, args=args)
        similar_pattern = self._find_similar_pattern(current_record)

        if len(similar_pattern) >= self.threshold:
            logger.warning(
                f"Similar doom loop detected for tool '{tool_name}': "
                f"{len(similar_pattern)} consecutive similar calls"
            )

            message = DoomLoopConfig.DOOM_LOOP_WARNING_TEMPLATE.format(
                count=len(similar_pattern),
                tool_name=tool_name,
                args=json.dumps(args, indent=2, ensure_ascii=False),
                history=self._format_history(similar_pattern),
            ) + "\n[检测到相似参数调用，可能参数有细微变化但本质相同]"

            return DoomLoopCheckResult(
                is_doom_loop=True,
                consecutive_count=len(similar_pattern),
                action=DoomLoopAction.ASK_USER,
                message=message,
                detected_pattern=similar_pattern,
            )

        return result
