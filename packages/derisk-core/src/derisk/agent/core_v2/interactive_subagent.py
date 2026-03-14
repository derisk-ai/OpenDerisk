"""
Interactive Subagent Session - 交互式子Agent会话

支持主Agent与运行中的子Agent进行多次交互：
1. 主Agent发送任务后，子Agent开始运行
2. 主Agent可以随时向子Agent补充信息
3. 子Agent可以向主Agent请求帮助/确认
4. 双向消息传递直到任务完成

此模块实现交互式子Agent功能。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """会话状态"""

    CREATED = "created"  # 已创建
    RUNNING = "running"  # 运行中
    WAITING_INPUT = "waiting_input"  # 等待主Agent输入
    WAITING_CONFIRM = "waiting_confirm"  # 等待主Agent确认
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class MessageType(Enum):
    """消息类型"""

    TASK = "task"  # 任务
    INPUT = "input"  # 补充输入
    FEEDBACK = "feedback"  # 中间反馈
    QUESTION = "question"  # 请求帮助
    CONFIRM_REQUEST = "confirm_request"  # 请求确认
    CONFIRM_RESPONSE = "confirm_response"  # 确认响应
    PROGRESS = "progress"  # 进度更新
    RESULT = "result"  # 最终结果
    ERROR = "error"  # 错误


@dataclass
class SessionMessage:
    """会话消息"""

    message_id: str
    message_type: MessageType
    content: str
    sender: str  # "main_agent" 或 "subagent"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "sender": self.sender,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class InteractiveSessionConfig:
    """交互式会话配置"""

    max_duration: int = 3600  # 最大持续时间(秒)
    max_messages: int = 100  # 最大消息数
    input_timeout: int = 300  # 等待输入超时(秒)
    confirm_timeout: int = 60  # 等待确认超时(秒)
    enable_auto_confirm: bool = False  # 超时自动确认
    auto_confirm_value: bool = True  # 自动确认的值


class InteractiveSubagentSession:
    """
    交互式子Agent会话

    支持：
    1. 主Agent发送任务后持续交互
    2. 子Agent请求帮助/确认
    3. 主Agent补充信息
    4. 进度跟踪

    使用示例：
        # 主Agent端
        session = await manager.create_session("analyzer", "分析日志")

        # 等待子Agent运行
        async for event in session.listen():
            if event.message_type == MessageType.QUESTION:
                # 子Agent请求帮助
                await session.send_input("请关注错误日志")

            elif event.message_type == MessageType.CONFIRM_REQUEST:
                # 子Agent请求确认
                await session.confirm(True)

            elif event.message_type == MessageType.RESULT:
                # 任务完成
                break

        # 子Agent端
        async def run_subagent(session):
            # 执行任务
            await session.send_progress("正在分析...", 30)

            # 需要帮助
            answer = await session.ask_question("需要分析哪些日志级别?")

            # 需要确认
            confirmed = await session.request_confirm("发现5个严重错误，是否继续?")

            # 返回结果
            await session.complete("分析完成")
    """

    def __init__(
        self,
        session_id: str,
        subagent_name: str,
        initial_task: str,
        config: InteractiveSessionConfig = None,
    ):
        self.session_id = session_id
        self.subagent_name = subagent_name
        self.initial_task = initial_task
        self.config = config or InteractiveSessionConfig()

        self.status = SessionStatus.CREATED
        self.messages: List[SessionMessage] = []
        self.metadata: Dict[str, Any] = {}

        # 时间信息
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # 事件通道
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._response_waiters: Dict[str, asyncio.Future] = {}

        # 进度
        self.progress_percent: float = 0.0
        self.progress_message: str = ""

    async def start(self) -> None:
        """启动会话"""
        self.status = SessionStatus.RUNNING
        self.started_at = datetime.now()

        # 记录初始任务消息
        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.TASK,
            content=self.initial_task,
            sender="main_agent",
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        logger.info(
            f"[InteractiveSession] Started session {self.session_id} "
            f"with subagent {self.subagent_name}"
        )

    # =========================================================================
    # 主Agent使用的方法
    # =========================================================================

    async def send_input(self, content: str, metadata: Dict[str, Any] = None) -> bool:
        """
        主Agent向子Agent发送补充输入

        Args:
            content: 输入内容
            metadata: 元数据

        Returns:
            是否成功发送
        """
        if self.status not in [SessionStatus.RUNNING, SessionStatus.WAITING_INPUT]:
            logger.warning(
                f"[InteractiveSession] Cannot send input: status={self.status}"
            )
            return False

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.INPUT,
            content=content,
            sender="main_agent",
            metadata=metadata or {},
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        logger.debug(f"[InteractiveSession] Main agent sent input to {self.session_id}")
        return True

    async def confirm(self, value: bool, reason: str = None) -> bool:
        """
        主Agent响应确认请求

        Args:
            value: 确认值 (True/False)
            reason: 原因说明

        Returns:
            是否成功发送
        """
        if self.status != SessionStatus.WAITING_CONFIRM:
            logger.warning(f"[InteractiveSession] Cannot confirm: status={self.status}")
            return False

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.CONFIRM_RESPONSE,
            content=str(value),
            sender="main_agent",
            metadata={"reason": reason} if reason else {},
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        self.status = SessionStatus.RUNNING

        logger.debug(f"[InteractiveSession] Main agent confirmed: {value}")
        return True

    async def cancel(self, reason: str = None) -> bool:
        """
        主Agent取消会话

        Args:
            reason: 取消原因

        Returns:
            是否成功取消
        """
        self.status = SessionStatus.CANCELLED
        self.completed_at = datetime.now()

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.ERROR,
            content=reason or "Cancelled by main agent",
            sender="main_agent",
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        logger.info(
            f"[InteractiveSession] Session {self.session_id} cancelled: {reason}"
        )
        return True

    async def listen(self):
        """
        监听会话事件

        Yields:
            SessionMessage: 会话消息
        """
        while self.status in [
            SessionStatus.RUNNING,
            SessionStatus.WAITING_INPUT,
            SessionStatus.WAITING_CONFIRM,
        ]:
            try:
                msg = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0,
                )
                yield msg

                # 检查是否完成
                if msg.message_type == MessageType.RESULT:
                    break
                if msg.message_type == MessageType.ERROR:
                    break

            except asyncio.TimeoutError:
                continue

    # =========================================================================
    # 子Agent使用的方法
    # =========================================================================

    async def send_progress(
        self,
        message: str,
        percent: float = None,
    ) -> bool:
        """
        子Agent发送进度更新

        Args:
            message: 进度消息
            percent: 进度百分比 (0-100)

        Returns:
            是否成功发送
        """
        if percent is not None:
            self.progress_percent = percent
        self.progress_message = message

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.PROGRESS,
            content=message,
            sender="subagent",
            metadata={"percent": percent} if percent else {},
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        return True

    async def send_feedback(self, content: str) -> bool:
        """
        子Agent发送中间反馈

        Args:
            content: 反馈内容

        Returns:
            是否成功发送
        """
        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.FEEDBACK,
            content=content,
            sender="subagent",
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        return True

    async def ask_question(
        self,
        question: str,
        timeout: int = None,
    ) -> str:
        """
        子Agent向主Agent提问

        Args:
            question: 问题内容
            timeout: 超时时间(秒)

        Returns:
            主Agent的回答
        """
        self.status = SessionStatus.WAITING_INPUT

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.QUESTION,
            content=question,
            sender="subagent",
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        # 等待回答
        timeout = timeout or self.config.input_timeout
        response = await self._wait_for_response(
            msg.message_id,
            [MessageType.INPUT],
            timeout,
        )

        self.status = SessionStatus.RUNNING
        return response.content if response else ""

    async def request_confirm(
        self,
        prompt: str,
        timeout: int = None,
    ) -> bool:
        """
        子Agent请求主Agent确认

        Args:
            prompt: 确认提示
            timeout: 超时时间(秒)

        Returns:
            确认结果 (True/False)
        """
        self.status = SessionStatus.WAITING_CONFIRM

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.CONFIRM_REQUEST,
            content=prompt,
            sender="subagent",
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        # 等待确认
        timeout = timeout or self.config.confirm_timeout
        response = await self._wait_for_response(
            msg.message_id,
            [MessageType.CONFIRM_RESPONSE],
            timeout,
        )

        self.status = SessionStatus.RUNNING

        if response:
            return response.content.lower() == "true"
        elif self.config.enable_auto_confirm:
            return self.config.auto_confirm_value
        else:
            raise TimeoutError("Confirm timeout")

    async def complete(self, result: str) -> bool:
        """
        子Agent完成任务

        Args:
            result: 最终结果

        Returns:
            是否成功完成
        """
        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.now()

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.RESULT,
            content=result,
            sender="subagent",
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        logger.info(f"[InteractiveSession] Session {self.session_id} completed")
        return True

    async def fail(self, error: str) -> bool:
        """
        子Agent报告失败

        Args:
            error: 错误信息

        Returns:
            是否成功报告
        """
        self.status = SessionStatus.FAILED
        self.completed_at = datetime.now()

        msg = SessionMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            message_type=MessageType.ERROR,
            content=error,
            sender="subagent",
        )
        self.messages.append(msg)
        await self._message_queue.put(msg)

        logger.error(f"[InteractiveSession] Session {self.session_id} failed: {error}")
        return True

    async def _wait_for_response(
        self,
        request_id: str,
        expected_types: List[MessageType],
        timeout: int,
    ) -> Optional[SessionMessage]:
        """等待特定类型的响应"""
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        self._response_waiters[request_id] = future

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return None
        finally:
            self._response_waiters.pop(request_id, None)

    def _handle_incoming_message(self, msg: SessionMessage) -> None:
        """处理传入消息(内部使用)"""
        # 检查是否有等待的请求
        for request_id, future in list(self._response_waiters.items()):
            if not future.done():
                future.set_result(msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "subagent_name": self.subagent_name,
            "status": self.status.value,
            "initial_task": self.initial_task,
            "progress_percent": self.progress_percent,
            "progress_message": self.progress_message,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }


class InteractiveSessionManager:
    """
    交互式会话管理器

    管理所有交互式子Agent会话
    """

    def __init__(self):
        self._sessions: Dict[str, InteractiveSubagentSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        subagent_name: str,
        task: str,
        config: InteractiveSessionConfig = None,
    ) -> InteractiveSubagentSession:
        """
        创建交互式会话

        Args:
            subagent_name: 子Agent名称
            task: 初始任务
            config: 会话配置

        Returns:
            创建的会话
        """
        session_id = f"session_{uuid.uuid4().hex[:12]}"

        session = InteractiveSubagentSession(
            session_id=session_id,
            subagent_name=subagent_name,
            initial_task=task,
            config=config,
        )

        async with self._lock:
            self._sessions[session_id] = session

        await session.start()

        logger.info(
            f"[InteractiveSessionManager] Created session {session_id} "
            f"for subagent {subagent_name}"
        )

        return session

    async def get_session(
        self, session_id: str
    ) -> Optional[InteractiveSubagentSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    async def list_sessions(
        self,
        status: SessionStatus = None,
        subagent_name: str = None,
    ) -> List[InteractiveSubagentSession]:
        """
        列出会话

        Args:
            status: 过滤状态
            subagent_name: 过滤子Agent名称

        Returns:
            会话列表
        """
        sessions = list(self._sessions.values())

        if status:
            sessions = [s for s in sessions if s.status == status]

        if subagent_name:
            sessions = [s for s in sessions if s.subagent_name == subagent_name]

        return sessions

    async def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                await session.cancel("Session closed by manager")
                del self._sessions[session_id]
                return True
        return False

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        sessions = list(self._sessions.values())

        return {
            "total_sessions": len(sessions),
            "running": sum(1 for s in sessions if s.status == SessionStatus.RUNNING),
            "waiting_input": sum(
                1 for s in sessions if s.status == SessionStatus.WAITING_INPUT
            ),
            "waiting_confirm": sum(
                1 for s in sessions if s.status == SessionStatus.WAITING_CONFIRM
            ),
            "completed": sum(
                1 for s in sessions if s.status == SessionStatus.COMPLETED
            ),
            "failed": sum(1 for s in sessions if s.status == SessionStatus.FAILED),
        }


# =============================================================================
# 全局单例
# =============================================================================

_interactive_manager: Optional[InteractiveSessionManager] = None


def get_interactive_manager() -> InteractiveSessionManager:
    """获取全局交互式会话管理器"""
    global _interactive_manager
    if _interactive_manager is None:
        _interactive_manager = InteractiveSessionManager()
    return _interactive_manager


# =============================================================================
# 使用示例
# =============================================================================


async def example_interactive_session():
    """交互式会话示例"""

    manager = get_interactive_manager()

    # 主Agent端：创建会话
    session = await manager.create_session(
        subagent_name="analyzer",
        task="分析系统日志，找出所有错误",
    )

    async def main_agent_handler():
        """主Agent处理逻辑"""
        async for msg in session.listen():
            print(f"[主Agent] 收到消息: {msg.message_type.value} - {msg.content[:50]}")

            if msg.message_type == MessageType.QUESTION:
                # 子Agent请求帮助，提供补充信息
                await session.send_input("请重点关注 ERROR 和 CRITICAL 级别的日志")

            elif msg.message_type == MessageType.CONFIRM_REQUEST:
                # 子Agent请求确认
                await session.confirm(True, "继续分析")

            elif msg.message_type == MessageType.RESULT:
                # 任务完成
                print(f"[主Agent] 最终结果: {msg.content}")
                break

            elif msg.message_type == MessageType.ERROR:
                print(f"[主Agent] 任务失败: {msg.content}")
                break

    async def subagent_handler():
        """子Agent处理逻辑"""
        # 模拟子Agent工作
        await session.send_progress("开始分析日志...", 10)

        # 需要更多信息
        answer = await session.ask_question("需要分析哪些日志级别?")
        print(f"[子Agent] 收到回答: {answer}")

        await session.send_progress("正在扫描日志文件...", 30)
        await session.send_progress("正在解析日志内容...", 50)

        # 发现问题，请求确认
        confirmed = await session.request_confirm(
            "发现 15 个严重错误，是否生成详细报告?"
        )
        print(f"[子Agent] 确认结果: {confirmed}")

        await session.send_progress("生成报告中...", 80)

        if confirmed:
            await session.complete("分析完成: 发现 15 个严重错误，已生成详细报告")
        else:
            await session.complete("分析完成: 发现 15 个严重错误")

    # 并行运行主Agent和子Agent处理
    await asyncio.gather(
        main_agent_handler(),
        subagent_handler(),
    )
