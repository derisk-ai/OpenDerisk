"""
VISPushManager - VIS 消息推送管理器

将 VIS 推送逻辑从 Agent 中分离，遵循单一职责原则。
支持配置驱动，可通过 AgentInfo 控制推送行为。

设计原则：
1. 配置驱动 - 通过 AgentInfo.enable_vis_push 控制
2. 可选注入 - 没有 GptsMemory 时静默跳过
3. 职责分离 - Agent 专注于业务逻辑，VISPushManager 专注于推送
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


@dataclass
class VISPushConfig:
    """VIS 推送配置"""

    enabled: bool = True
    push_thinking: bool = True
    push_tool_calls: bool = True

    # 推送节流配置
    min_chunk_interval_ms: int = 50  # 最小推送间隔（毫秒）
    batch_size: int = 10  # 批量推送大小

    # 内容截断配置
    max_content_preview: int = 2000  # 内容预览最大长度


@dataclass
class VISPushState:
    """VIS 推送状态"""

    message_id: Optional[str] = None
    accumulated_content: str = ""
    accumulated_thinking: str = ""
    is_first_chunk: bool = True
    current_goal: str = ""
    last_push_time: Optional[datetime] = None
    pending_chunks: List[Dict[str, Any]] = field(default_factory=list)


class VISPushManager:
    """
    VIS 推送管理器

    负责将 Agent 执行过程中的 thinking、content、action_report
    推送到 GptsMemory，供 vis_window3 渲染使用。

    示例：
        manager = VISPushManager(
            gpts_memory=gpts_memory,
            conv_id="conv-123",
            config=VISPushConfig(enabled=True)
        )

        # 初始化新消息
        manager.init_message(goal="用户的问题")

        # 推送 thinking
        await manager.push_thinking("正在思考...")

        # 推送工具调用
        await manager.push_tool_start("bash", {"command": "ls"})
        await manager.push_tool_result("bash", "file1.txt\nfile2.txt", success=True)

        # 推送最终响应
        await manager.push_response("任务完成")
    """

    def __init__(
        self,
        gpts_memory: Optional[Any] = None,
        conv_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_name: str = "agent",
        config: Optional[VISPushConfig] = None,
    ):
        """
        初始化 VIS 推送管理器

        Args:
            gpts_memory: GptsMemory 实例（可选，没有则跳过推送）
            conv_id: 会话 ID
            session_id: 会话 ID
            agent_name: Agent 名称
            config: 推送配置
        """
        self._gpts_memory = gpts_memory
        self._conv_id = conv_id
        self._session_id = session_id
        self._agent_name = agent_name
        self._config = config or VISPushConfig()
        self._state = VISPushState()

    @property
    def enabled(self) -> bool:
        """是否启用推送"""
        return (
            self._config.enabled
            and self._gpts_memory is not None
            and self._conv_id is not None
        )

    @property
    def message_id(self) -> Optional[str]:
        """当前消息 ID"""
        return self._state.message_id

    def set_gpts_memory(self, gpts_memory: Any, conv_id: str) -> None:
        """设置 GptsMemory"""
        self._gpts_memory = gpts_memory
        self._conv_id = conv_id

    def init_message(self, goal: str = "") -> str:
        """
        初始化新消息

        Args:
            goal: 当前目标

        Returns:
            消息 ID
        """
        self._state = VISPushState(
            message_id=str(uuid.uuid4().hex),
            current_goal=goal,
        )
        return self._state.message_id

    async def push_thinking(
        self,
        content: str,
        is_first_chunk: bool = False,
        model: Optional[str] = None,
    ) -> bool:
        """
        推送 thinking 内容

        Args:
            content: thinking 内容
            is_first_chunk: 是否是第一个 chunk
            model: 模型名称

        Returns:
            是否推送成功
        """
        if not self.enabled or not self._config.push_thinking:
            return False

        self._state.accumulated_thinking += content

        return await self._push_message(
            thinking=content,
            is_first_chunk=is_first_chunk or self._state.is_first_chunk,
            model=model,
        )

    async def push_content(
        self,
        content: str,
        is_first_chunk: bool = False,
        status: str = "running",
    ) -> bool:
        """
        推送 content 内容

        Args:
            content: 内容
            is_first_chunk: 是否是第一个 chunk
            status: 状态

        Returns:
            是否推送成功
        """
        if not self.enabled:
            return False

        self._state.accumulated_content += content

        return await self._push_message(
            content=content,
            is_first_chunk=is_first_chunk or self._state.is_first_chunk,
            status=status,
        )

    async def push_tool_start(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        action_id: Optional[str] = None,
        thought: Optional[str] = None,
    ) -> bool:
        """
        推送工具开始执行

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            action_id: 动作 ID
            thought: 思考内容

        Returns:
            是否推送成功
        """
        if not self.enabled or not self._config.push_tool_calls:
            return False

        action_id = action_id or f"call_{tool_name}_{uuid.uuid4().hex[:8]}"

        action_report = self._build_tool_start_action_report(
            tool_name=tool_name,
            tool_args=tool_args,
            action_id=action_id,
            thought=thought,
        )

        return await self._push_message(
            action_report=action_report,
            is_first_chunk=False,
        )

    async def push_tool_result(
        self,
        tool_name: str,
        result_content: str,
        tool_args: Optional[Dict[str, Any]] = None,
        action_id: Optional[str] = None,
        success: bool = True,
        thought: Optional[str] = None,
    ) -> bool:
        """
        推送工具执行结果

        Args:
            tool_name: 工具名称
            result_content: 结果内容
            tool_args: 工具参数
            action_id: 动作 ID
            success: 是否成功
            thought: 思考内容

        Returns:
            是否推送成功
        """
        if not self.enabled or not self._config.push_tool_calls:
            return False

        action_id = action_id or f"call_{tool_name}_{uuid.uuid4().hex[:8]}"

        action_report = self._build_tool_result_action_report(
            tool_name=tool_name,
            tool_args=tool_args or {},
            result_content=result_content,
            action_id=action_id,
            success=success,
            thought=thought,
        )

        return await self._push_message(
            content=result_content,
            action_report=action_report,
            is_first_chunk=False,
        )

    async def push_response(
        self,
        content: str,
        status: str = "complete",
    ) -> bool:
        """
        推送最终响应

        Args:
            content: 响应内容
            status: 状态

        Returns:
            是否推送成功
        """
        if not self.enabled:
            return False

        return await self._push_message(
            content=content,
            status=status,
            is_first_chunk=False,
        )

    async def push_error(
        self,
        error_message: str,
    ) -> bool:
        """
        推送错误消息

        Args:
            error_message: 错误消息

        Returns:
            是否推送成功
        """
        if not self.enabled:
            return False

        return await self._push_message(
            content=error_message,
            status="error",
            is_first_chunk=False,
        )

    async def _push_message(
        self,
        thinking: Optional[str] = None,
        content: Optional[str] = None,
        action_report: Optional[List[Any]] = None,
        is_first_chunk: bool = False,
        model: Optional[str] = None,
        status: str = "running",
        metrics: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        推送消息到 GptsMemory

        Args:
            thinking: thinking 内容
            content: 内容
            action_report: ActionOutput 列表
            is_first_chunk: 是否是第一个 chunk
            model: 模型名称
            status: 状态
            metrics: 指标

        Returns:
            是否推送成功
        """
        if not self._gpts_memory or not self._conv_id:
            return False

        if not self._state.message_id:
            logger.warning("[VISPushManager] message_id 未初始化，跳过推送")
            return False

        stream_msg = {
            "uid": self._state.message_id,
            "type": "incr",
            "message_id": self._state.message_id,
            "conv_id": self._conv_id,
            "conv_session_uid": self._session_id or self._conv_id,
            "goal_id": self._state.message_id,
            "task_goal_id": self._state.message_id,
            "task_goal": self._state.current_goal,
            "app_code": self._agent_name,
            "sender": self._agent_name,
            "sender_name": self._agent_name,
            "sender_role": "assistant",
            "model": model,
            "thinking": thinking,
            "content": content,
            "avatar": None,
            "observation": "",
            "status": status,
            "start_time": datetime.now(),
            "metrics": metrics or {},
            "prev_content": self._state.accumulated_content,
        }

        if action_report:
            stream_msg["action_report"] = action_report

        try:
            await self._gpts_memory.push_message(
                self._conv_id,
                stream_msg=stream_msg,
                is_first_chunk=is_first_chunk,
            )
            self._state.is_first_chunk = False
            self._state.last_push_time = datetime.now()
            logger.debug(f"[VISPushManager] 推送成功")
            return True
        except Exception as e:
            logger.warning(f"[VISPushManager] 推送失败: {e}")
            return False

    def _build_tool_start_action_report(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        action_id: str,
        thought: Optional[str] = None,
    ) -> Optional[List[Any]]:
        """构建工具开始时的 ActionReport"""
        try:
            from derisk.agent.core.action.base import ActionOutput

            action = ActionOutput(
                content="",
                action_id=action_id,
                action=tool_name,
                action_name=tool_name,
                name=tool_name,
                action_input=tool_args,
                state="running",
                stream=True,
                is_exe_success=True,
                thought=thought or "",
            )
            return [action]
        except ImportError:
            logger.warning("[VISPushManager] ActionOutput 导入失败")
            return None

    def _build_tool_result_action_report(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result_content: str,
        action_id: str,
        success: bool = True,
        thought: Optional[str] = None,
    ) -> Optional[List[Any]]:
        """构建工具结果的 ActionReport"""
        try:
            from derisk.agent.core.action.base import ActionOutput

            view = (
                result_content[: self._config.max_content_preview]
                if result_content
                else ""
            )

            action = ActionOutput(
                content=result_content,
                action_id=action_id,
                action=tool_name,
                action_name=tool_name,
                name=tool_name,
                action_input=tool_args,
                state="complete" if success else "failed",
                is_exe_success=success,
                view=view,
                stream=False,
                thought=thought or "",
            )
            return [action]
        except ImportError:
            logger.warning("[VISPushManager] ActionOutput 导入失败")
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "enabled": self.enabled,
            "message_id": self._state.message_id,
            "accumulated_thinking_length": len(self._state.accumulated_thinking),
            "accumulated_content_length": len(self._state.accumulated_content),
            "last_push_time": self._state.last_push_time.isoformat()
            if self._state.last_push_time
            else None,
        }


def create_vis_push_manager(
    agent_info: Any,
    gpts_memory: Optional[Any] = None,
    conv_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> VISPushManager:
    """
    工厂函数：从 AgentInfo 创建 VISPushManager

    Args:
        agent_info: AgentInfo 实例
        gpts_memory: GptsMemory 实例
        conv_id: 会话 ID
        session_id: 会话 ID

    Returns:
        VISPushManager 实例
    """
    config = VISPushConfig(
        enabled=getattr(agent_info, "enable_vis_push", True),
        push_thinking=getattr(agent_info, "vis_push_thinking", True),
        push_tool_calls=getattr(agent_info, "vis_push_tool_calls", True),
    )

    return VISPushManager(
        gpts_memory=gpts_memory,
        conv_id=conv_id,
        session_id=session_id,
        agent_name=getattr(agent_info, "name", "agent"),
        config=config,
    )
