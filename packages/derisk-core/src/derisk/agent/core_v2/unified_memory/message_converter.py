"""
MessageConverter - 消息格式转换器

实现 AgentMessage ↔ GptsMessage 双向转换，
用于 Core V1 和 Core V2 消息格式的互操作。

使用场景:
1. Core V2 Agent 处理来自 Core V1 的消息
2. Core V2 Agent 生成需要写入 GptsMemory 的消息
3. 历史消息加载时格式转换
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from derisk.core.schema.types import ChatCompletionUserMessageParam

if TYPE_CHECKING:
    from derisk.agent.core.memory.gpts.base import GptsMessage
    from derisk.agent.core.types import AgentMessage


class MessageConverter:
    """
    消息格式转换器

    提供 AgentMessage (Core V2) 和 GptsMessage (Core V1) 之间的双向转换。

    字段映射:
    ┌────────────────────┬────────────────────┐
    │ AgentMessage (V2)  │ GptsMessage (V1)   │
    ├────────────────────┼────────────────────┤
    │ message_id         │ message_id         │
    │ content            │ content            │
    │ content_types      │ content_types      │
    │ message_type       │ message_type       │
    │ thinking           │ thinking           │
    │ name               │ sender_name        │
    │ rounds             │ rounds             │
    │ round_id           │ (N/A)              │
    │ context            │ context            │
    │ action_report      │ action_report      │
    │ review_info        │ review_info        │
    │ current_goal       │ current_goal       │
    │ goal_id            │ goal_id            │
    │ model_name         │ model_name         │
    │ role               │ role               │
    │ success            │ is_success         │
    │ resource_info      │ resource_info      │
    │ show_message       │ show_message       │
    │ system_prompt      │ system_prompt      │
    │ user_prompt        │ user_prompt        │
    │ gmt_create         │ created_at         │
    │ observation        │ observation        │
    │ metrics            │ metrics            │
    │ tool_calls         │ tool_calls         │
    │ (N/A)              │ conv_id            │
    │ (N/A)              │ conv_session_id    │
    │ (N/A)              │ sender             │
    │ (N/A)              │ sender_name        │
    │ (N/A)              │ receiver           │
    │ (N/A)              │ receiver_name      │
    │ (N/A)              │ avatar             │
    │ (N/A)              │ app_code           │
    │ (N/A)              │ app_name           │
    └────────────────────┴────────────────────┘

    示例:
        from derisk.agent.core_v2.unified_memory.message_converter import MessageConverter

        # GptsMessage -> AgentMessage
        agent_msg = MessageConverter.gpts_to_agent(gpts_msg)

        # AgentMessage -> GptsMessage (需要额外信息)
        gpts_msg = MessageConverter.agent_to_gpts(
            agent_msg,
            conv_id="conv_123",
            sender="assistant",
            sender_name="助手"
        )
    """

    @staticmethod
    def gpts_to_agent(gpts_msg: "GptsMessage") -> "AgentMessage":
        """
        将 GptsMessage 转换为 AgentMessage

        Args:
            gpts_msg: GptsMessage 实例

        Returns:
            AgentMessage 实例
        """
        from derisk.agent.core.types import AgentMessage

        return AgentMessage(
            message_id=gpts_msg.message_id,
            content=gpts_msg.content,
            content_types=gpts_msg.content_types,
            message_type=gpts_msg.message_type,
            thinking=gpts_msg.thinking,
            name=gpts_msg.sender_name,
            rounds=gpts_msg.rounds,
            round_id=None,  # GptsMessage 没有 round_id
            context=gpts_msg.context,
            action_report=gpts_msg.action_report,
            review_info=gpts_msg.review_info,
            current_goal=gpts_msg.current_goal,
            goal_id=gpts_msg.goal_id,
            model_name=gpts_msg.model_name,
            role=gpts_msg.role,
            success=gpts_msg.is_success,
            resource_info=gpts_msg.resource_info,
            show_message=gpts_msg.show_message,
            system_prompt=gpts_msg.system_prompt,
            user_prompt=gpts_msg.user_prompt,
            gmt_create=gpts_msg.created_at,
            observation=gpts_msg.observation,
            metrics=gpts_msg.metrics,
            tool_calls=gpts_msg.tool_calls,
        )

    @staticmethod
    def agent_to_gpts(
        agent_msg: "AgentMessage",
        conv_id: str,
        conv_session_id: Optional[str] = None,
        sender: str = "assistant",
        sender_name: str = "Agent",
        receiver: Optional[str] = None,
        receiver_name: Optional[str] = None,
        app_code: Optional[str] = None,
        app_name: Optional[str] = None,
        avatar: Optional[str] = None,
    ) -> "GptsMessage":
        """
        将 AgentMessage 转换为 GptsMessage

        注意: AgentMessage 不包含 conv_id、sender、receiver 等字段，
        这些需要通过参数提供。

        Args:
            agent_msg: AgentMessage 实例
            conv_id: 会话 ID
            conv_session_id: 会话 session ID (默认等于 conv_id)
            sender: 发送者角色
            sender_name: 发送者名称
            receiver: 接收者角色
            receiver_name: 接收者名称
            app_code: 应用代码
            app_name: 应用名称
            avatar: 头像

        Returns:
            GptsMessage 实例
        """
        from derisk.agent.core.memory.gpts.base import GptsMessage

        return GptsMessage(
            # 会话信息
            conv_id=conv_id,
            conv_session_id=conv_session_id or conv_id,
            # 发送者信息
            sender=sender,
            sender_name=sender_name or agent_msg.name or "Agent",
            receiver=receiver or "user",
            receiver_name=receiver_name or "User",
            avatar=avatar,
            # 应用信息
            app_code=app_code or "",
            app_name=app_name or sender_name or "Agent",
            # 消息内容
            message_id=agent_msg.message_id or str(uuid.uuid4().hex),
            content=agent_msg.content,
            rounds=agent_msg.rounds,
            content_types=agent_msg.content_types,
            message_type=agent_msg.message_type,
            is_success=agent_msg.success,
            thinking=agent_msg.thinking,
            goal_id=agent_msg.goal_id,
            current_goal=agent_msg.current_goal,
            context=agent_msg.context,
            action_report=agent_msg.action_report,
            review_info=agent_msg.review_info,
            model_name=agent_msg.model_name,
            resource_info=agent_msg.resource_info,
            system_prompt=agent_msg.system_prompt,
            user_prompt=agent_msg.user_prompt,
            show_message=agent_msg.show_message,
            created_at=agent_msg.gmt_create or datetime.now(),
            updated_at=agent_msg.gmt_create or datetime.now(),
            observation=agent_msg.observation,
            metrics=agent_msg.metrics,
            tool_calls=agent_msg.tool_calls,
            role=agent_msg.role or sender,
        )

    @staticmethod
    def agent_to_gpts_with_context(
        agent_msg: "AgentMessage",
        context: Any,
    ) -> "GptsMessage":
        """
        使用 AgentContext 将 AgentMessage 转换为 GptsMessage

        Args:
            agent_msg: AgentMessage 实例
            context: AgentContext 实例 (包含 conv_id 等信息)

        Returns:
            GptsMessage 实例
        """
        from derisk.agent.core.memory.gpts.base import GptsMessage

        # 从 context 提取信息
        conv_id = getattr(context, 'conv_id', None) or getattr(context, 'conversation_id', '') or ''
        conv_session_id = getattr(context, 'conv_session_id', None) or getattr(context, 'session_id', '') or conv_id
        app_code = getattr(context, 'agent_app_code', None) or getattr(context, 'app_code', '') or ''

        return GptsMessage(
            conv_id=conv_id,
            conv_session_id=conv_session_id,
            sender=getattr(context, 'role', 'assistant') or 'assistant',
            sender_name=getattr(context, 'name', 'Agent') or agent_msg.name or 'Agent',
            receiver=getattr(context, 'receiver', 'user') or 'user',
            receiver_name=getattr(context, 'receiver_name', 'User') or 'User',
            avatar=getattr(context, 'avatar', None),
            app_code=app_code,
            app_name=getattr(context, 'name', 'Agent') or agent_msg.name or 'Agent',
            message_id=agent_msg.message_id or str(uuid.uuid4().hex),
            content=agent_msg.content,
            rounds=agent_msg.rounds,
            content_types=agent_msg.content_types,
            message_type=agent_msg.message_type,
            is_success=agent_msg.success,
            thinking=agent_msg.thinking,
            goal_id=agent_msg.goal_id,
            current_goal=agent_msg.current_goal,
            context=agent_msg.context,
            action_report=agent_msg.action_report,
            review_info=agent_msg.review_info,
            model_name=agent_msg.model_name,
            resource_info=agent_msg.resource_info,
            system_prompt=agent_msg.system_prompt,
            user_prompt=agent_msg.user_prompt,
            show_message=agent_msg.show_message,
            created_at=agent_msg.gmt_create or datetime.now(),
            updated_at=agent_msg.gmt_create or datetime.now(),
            observation=agent_msg.observation,
            metrics=agent_msg.metrics,
            tool_calls=agent_msg.tool_calls,
            role=agent_msg.role or getattr(context, 'role', 'assistant') or 'assistant',
        )

    @staticmethod
    def dict_to_agent_message(data: Dict[str, Any]) -> "AgentMessage":
        """
        从字典创建 AgentMessage

        Args:
            data: 消息字典

        Returns:
            AgentMessage 实例
        """
        from derisk.agent.core.types import AgentMessage

        # 处理时间字段
        gmt_create = data.get("gmt_create") or data.get("created_at")
        if isinstance(gmt_create, str):
            try:
                gmt_create = datetime.fromisoformat(gmt_create.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                gmt_create = None
        elif not isinstance(gmt_create, datetime):
            gmt_create = None

        return AgentMessage(
            message_id=data.get("message_id") or str(uuid.uuid4().hex),
            content=data.get("content"),
            content_types=data.get("content_types"),
            message_type=data.get("message_type"),
            thinking=data.get("thinking"),
            name=data.get("name") or data.get("sender_name"),
            rounds=data.get("rounds", 0),
            round_id=data.get("round_id"),
            context=data.get("context"),
            action_report=data.get("action_report"),
            review_info=data.get("review_info"),
            current_goal=data.get("current_goal"),
            goal_id=data.get("goal_id"),
            model_name=data.get("model_name"),
            role=data.get("role"),
            success=data.get("success", data.get("is_success", True)),
            resource_info=data.get("resource_info"),
            show_message=data.get("show_message", True),
            system_prompt=data.get("system_prompt"),
            user_prompt=data.get("user_prompt"),
            gmt_create=gmt_create,
            observation=data.get("observation"),
            metrics=data.get("metrics"),
            tool_calls=data.get("tool_calls"),
        )

    @staticmethod
    def dict_to_gpts_message(data: Dict[str, Any]) -> "GptsMessage":
        """
        从字典创建 GptsMessage

        Args:
            data: 消息字典

        Returns:
            GptsMessage 实例
        """
        from derisk.agent.core.memory.gpts.base import GptsMessage

        # 处理时间字段
        created_at = data.get("created_at") or data.get("gmt_create")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                created_at = datetime.now()
        elif not isinstance(created_at, datetime):
            created_at = datetime.now()

        updated_at = data.get("updated_at") or created_at
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                updated_at = created_at
        elif not isinstance(updated_at, datetime):
            updated_at = created_at

        return GptsMessage(
            conv_id=data.get("conv_id", ""),
            conv_session_id=data.get("conv_session_id", data.get("conv_id", "")),
            sender=data.get("sender", ""),
            sender_name=data.get("sender_name", ""),
            receiver=data.get("receiver"),
            receiver_name=data.get("receiver_name"),
            message_id=data.get("message_id", str(uuid.uuid4().hex)),
            role=data.get("role", ""),
            content=data.get("content"),
            rounds=data.get("rounds", 0),
            content_types=data.get("content_types"),
            message_type=data.get("message_type"),
            is_success=data.get("is_success", data.get("success", True)),
            avatar=data.get("avatar"),
            thinking=data.get("thinking"),
            app_code=data.get("app_code"),
            app_name=data.get("app_name"),
            goal_id=data.get("goal_id"),
            current_goal=data.get("current_goal"),
            context=data.get("context"),
            action_report=data.get("action_report"),
            review_info=data.get("review_info"),
            model_name=data.get("model_name"),
            resource_info=data.get("resource_info"),
            system_prompt=data.get("system_prompt"),
            user_prompt=data.get("user_prompt"),
            show_message=data.get("show_message", True),
            created_at=created_at,
            updated_at=updated_at,
            observation=data.get("observation"),
            metrics=data.get("metrics"),
            tool_calls=data.get("tool_calls"),
        )

    @staticmethod
    def messages_to_llm_format(
        messages: List[Union["AgentMessage", "GptsMessage"]]
    ) -> List[Dict[str, Any]]:
        """
        将消息列表转换为 LLM API 格式

        Args:
            messages: 消息列表 (可以是 AgentMessage 或 GptsMessage)

        Returns:
            LLM API 格式的消息列表
        """
        result = []

        for msg in messages:
            # 获取角色
            role = getattr(msg, 'role', 'user') or 'user'

            # 获取内容
            content = getattr(msg, 'content', '')
            if content is None:
                content = ''

            # 构建消息
            llm_msg = {
                "role": role,
                "content": str(content),
            }

            # 添加可选字段 (but not for tool messages - OpenAI doesn't accept name on tool msgs)
            if role != "tool":
                if hasattr(msg, 'name') and msg.name:
                    llm_msg["name"] = msg.name
                elif hasattr(msg, 'sender_name') and msg.sender_name:
                    llm_msg["name"] = msg.sender_name

            # Preserve tool_calls for assistant messages (OpenAI function-call pairing)
            tool_calls = getattr(msg, 'tool_calls', None)
            if tool_calls:
                llm_msg["tool_calls"] = tool_calls

            # Preserve tool_call_id for tool messages (OpenAI function-call pairing)
            tool_call_id = None
            if hasattr(msg, 'context') and isinstance(msg.context, dict):
                tool_call_id = msg.context.get('tool_call_id')
            if not tool_call_id:
                tool_call_id = getattr(msg, 'tool_call_id', None)
            if tool_call_id:
                llm_msg["tool_call_id"] = tool_call_id

            result.append(llm_msg)

        return result

    @staticmethod
    def convert_history_to_agent_messages(
        history: List[Any]
    ) -> List["AgentMessage"]:
        """
        将历史消息列表转换为 AgentMessage 列表

        自动检测消息类型并调用相应的转换方法

        Args:
            history: 历史消息列表

        Returns:
            AgentMessage 列表
        """
        from derisk.agent.core.types import AgentMessage
        from derisk.agent.core.memory.gpts.base import GptsMessage

        result = []

        for msg in history:
            if isinstance(msg, AgentMessage):
                result.append(msg)
            elif isinstance(msg, GptsMessage):
                result.append(MessageConverter.gpts_to_agent(msg))
            elif isinstance(msg, dict):
                result.append(MessageConverter.dict_to_agent_message(msg))
            else:
                # 尝试从对象创建
                try:
                    agent_msg = AgentMessage(
                        message_id=getattr(msg, 'message_id', None) or str(uuid.uuid4().hex),
                        content=getattr(msg, 'content', str(msg)),
                        role=getattr(msg, 'role', 'user'),
                        name=getattr(msg, 'name', getattr(msg, 'sender_name', None)),
                        rounds=getattr(msg, 'rounds', 0),
                    )
                    result.append(agent_msg)
                except Exception:
                    pass

        return result


# 提供便捷函数
def gpts_to_agent(gpts_msg: "GptsMessage") -> "AgentMessage":
    """便捷函数: GptsMessage -> AgentMessage"""
    return MessageConverter.gpts_to_agent(gpts_msg)


def agent_to_gpts(
    agent_msg: "AgentMessage",
    conv_id: str,
    **kwargs
) -> "GptsMessage":
    """便捷函数: AgentMessage -> GptsMessage"""
    return MessageConverter.agent_to_gpts(agent_msg, conv_id=conv_id, **kwargs)