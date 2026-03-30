"""
VIS Push Hooks - VIS 推送钩子实现

提供基于钩子系统的 VIS 推送能力，符合 Core V2 的架构设计。
通过场景配置启用，而非硬编码在 Agent 中。

设计原则：
1. 钩子驱动 - 通过 SceneHook 扩展
2. 配置控制 - 通过 SceneProfile 或 AgentInfo 启用
3. 职责分离 - Agent 专注于业务，Hook 专注于推送
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from .scene_strategy import (
    SceneHook,
    AgentPhase,
    HookPriority,
    HookContext,
    HookResult,
)
from .vis_push_manager import VISPushManager, VISPushConfig

logger = logging.getLogger(__name__)


class VISPushHook(SceneHook):
    """
    VIS 推送钩子

    在 Agent 执行的各个阶段推送消息到 VIS。
    支持通过配置控制推送行为。

    示例：
        # 创建钩子
        hook = VISPushHook(
            gpts_memory=gpts_memory,
            conv_id="conv-123",
            config=VISPushConfig(enabled=True)
        )

        # 添加到场景配置
        profile = SceneProfileBuilder()
            .hooks([hook])
            .build()
    """

    def __init__(
        self,
        gpts_memory: Optional[Any] = None,
        conv_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_name: str = "agent",
        config: Optional[VISPushConfig] = None,
        priority: HookPriority = HookPriority.LOW,  # 低优先级，不影响其他钩子
    ):
        """
        初始化 VIS 推送钩子

        Args:
            gpts_memory: GptsMemory 实例
            conv_id: 会话 ID
            session_id: 会话 ID
            agent_name: Agent 名称
            config: 推送配置
            priority: 钩子优先级
        """
        self._vis_manager = VISPushManager(
            gpts_memory=gpts_memory,
            conv_id=conv_id,
            session_id=session_id,
            agent_name=agent_name,
            config=config or VISPushConfig(),
        )
        self._priority = priority

    @property
    def priority(self) -> HookPriority:
        """钩子优先级"""
        return self._priority

    def set_gpts_memory(self, gpts_memory: Any, conv_id: str) -> None:
        """设置 GptsMemory"""
        self._vis_manager.set_gpts_memory(gpts_memory, conv_id)

    @property
    def vis_manager(self) -> VISPushManager:
        """获取 VIS 推送管理器"""
        return self._vis_manager

    async def execute(self, context: HookContext) -> HookResult:
        """
        执行钩子

        根据阶段调用相应的推送方法
        """
        if not self._vis_manager.enabled:
            return HookResult(proceed=True)

        try:
            phase = context.phase

            if phase == AgentPhase.BEFORE_THINK:
                return await self._handle_before_think(context)
            elif phase == AgentPhase.AFTER_THINK:
                return await self._handle_after_think(context)
            elif phase == AgentPhase.BEFORE_TOOL:
                return await self._handle_before_tool(context)
            elif phase == AgentPhase.AFTER_TOOL:
                return await self._handle_after_tool(context)
            elif phase == AgentPhase.COMPLETE:
                return await self._handle_complete(context)
            elif phase == AgentPhase.ERROR:
                return await self._handle_error(context)
            else:
                return HookResult(proceed=True)

        except Exception as e:
            logger.warning(f"[VISPushHook] 执行失败: {e}")
            return HookResult(proceed=True, error=str(e))

    async def _handle_before_think(self, context: HookContext) -> HookResult:
        """处理思考前阶段"""
        # 初始化消息
        if context.step == 0:
            self._vis_manager.init_message(goal=context.original_input or "")

        return HookResult(proceed=True)

    async def _handle_after_think(self, context: HookContext) -> HookResult:
        """处理思考后阶段"""
        if context.thinking:
            await self._vis_manager.push_thinking(
                content=context.thinking,
                is_first_chunk=context.step == 0,
            )

        return HookResult(proceed=True)

    async def _handle_before_tool(self, context: HookContext) -> HookResult:
        """处理工具执行前阶段"""
        if context.tool_name:
            await self._vis_manager.push_tool_start(
                tool_name=context.tool_name,
                tool_args=context.tool_args or {},
                thought=context.thinking,
            )

        return HookResult(proceed=True)

    async def _handle_after_tool(self, context: HookContext) -> HookResult:
        """处理工具执行后阶段"""
        if context.tool_name and context.tool_result is not None:
            result_str = (
                str(context.tool_result)
                if not isinstance(context.tool_result, str)
                else context.tool_result
            )
            await self._vis_manager.push_tool_result(
                tool_name=context.tool_name,
                result_content=result_str,
                tool_args=context.tool_args,
                success=True,
                thought=context.thinking,
            )

        return HookResult(proceed=True)

    async def _handle_complete(self, context: HookContext) -> HookResult:
        """处理完成阶段"""
        if context.output:
            await self._vis_manager.push_response(
                content=context.output,
                status="complete",
            )

        return HookResult(proceed=True)

    async def _handle_error(self, context: HookContext) -> HookResult:
        """处理错误阶段"""
        if context.error:
            await self._vis_manager.push_error(
                error_message=str(context.error),
            )

        return HookResult(proceed=True)


class VISPushThinkHook(SceneHook):
    """
    思考阶段 VIS 推送钩子

    专门用于推送 thinking 内容，可独立配置
    """

    def __init__(
        self,
        vis_manager: VISPushManager,
        priority: HookPriority = HookPriority.LOW,
    ):
        self._vis_manager = vis_manager
        self._priority = priority

    @property
    def priority(self) -> HookPriority:
        return self._priority

    async def execute(self, context: HookContext) -> HookResult:
        if not self._vis_manager.enabled:
            return HookResult(proceed=True)

        if context.phase == AgentPhase.AFTER_THINK and context.thinking:
            await self._vis_manager.push_thinking(content=context.thinking)

        return HookResult(proceed=True)


class VISPushToolHook(SceneHook):
    """
    工具阶段 VIS 推送钩子

    专门用于推送工具调用信息，可独立配置
    """

    def __init__(
        self,
        vis_manager: VISPushManager,
        priority: HookPriority = HookPriority.LOW,
    ):
        self._vis_manager = vis_manager
        self._priority = priority

    @property
    def priority(self) -> HookPriority:
        return self._priority

    async def execute(self, context: HookContext) -> HookResult:
        if not self._vis_manager.enabled:
            return HookResult(proceed=True)

        if context.phase == AgentPhase.BEFORE_TOOL and context.tool_name:
            await self._vis_manager.push_tool_start(
                tool_name=context.tool_name,
                tool_args=context.tool_args or {},
            )
        elif context.phase == AgentPhase.AFTER_TOOL and context.tool_name:
            result_str = str(context.tool_result) if context.tool_result else ""
            await self._vis_manager.push_tool_result(
                tool_name=context.tool_name,
                result_content=result_str,
            )

        return HookResult(proceed=True)


def create_vis_push_hooks(
    gpts_memory: Optional[Any] = None,
    conv_id: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_name: str = "agent",
    config: Optional[VISPushConfig] = None,
    combined: bool = True,
) -> list:
    """
    工厂函数：创建 VIS 推送钩子

    Args:
        gpts_memory: GptsMemory 实例
        conv_id: 会话 ID
        session_id: 会话 ID
        agent_name: Agent 名称
        config: 推送配置
        combined: 是否使用组合钩子（单一钩子处理所有阶段）

    Returns:
        钩子列表
    """
    if combined:
        # 使用单一组合钩子
        return [
            VISPushHook(
                gpts_memory=gpts_memory,
                conv_id=conv_id,
                session_id=session_id,
                agent_name=agent_name,
                config=config,
            )
        ]
    else:
        # 使用分离钩子
        vis_manager = VISPushManager(
            gpts_memory=gpts_memory,
            conv_id=conv_id,
            session_id=session_id,
            agent_name=agent_name,
            config=config or VISPushConfig(),
        )

        return [
            VISPushThinkHook(vis_manager=vis_manager),
            VISPushToolHook(vis_manager=vis_manager),
        ]
