import dataclasses
import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    and_,
    desc,
    or_, select,
)

from derisk.agent import ActionOutput

from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.core.schema import MessageMetrics
from derisk.agent.core.types import AgentReviewInfo
from derisk.storage.metadata import BaseDao, Model
from derisk.util.json_utils import serialize


class GptsMessagesEntity(Model):
    __tablename__ = "gpts_messages"
    id = Column(Integer, primary_key=True, comment="autoincrement id")

    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation record"
    )
    conv_session_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation record"
    )
    message_id = Column(
        String(255), nullable=False, comment="The unique id of the messages"
    )
    sender = Column(
        String(255),
        nullable=False,
        comment="Who(role) speaking in the current conversation turn",
    )
    sender_name = Column(
        String(255),
        nullable=False,
        comment="Who(name) speaking in the current conversation turn",
    )
    receiver = Column(
        String(255),
        nullable=False,
        comment="Who(role) receive message in the current conversation turn",
    )
    receiver_name = Column(
        String(255),
        nullable=False,
        comment="Who(name) receive message in the current conversation turn",
    )
    model_name = Column(String(255), nullable=True, comment="message generate model")
    rounds = Column(Integer, nullable=False, comment="dialogue turns")
    is_success = Column(Boolean, default=True, nullable=True, comment="is success")
    app_code = Column(
        String(255),
        nullable=False,
        comment="The message in which app",
    )
    app_name = Column(
        String(255),
        nullable=False,
        comment="The message in which app name",
    )
    thinking = Column(
        Text(length=2 ** 31 - 1), nullable=True, comment="Thinking of the speech"
    )
    content = Column(
        Text(length=2 ** 31 - 1), nullable=True, comment="Content of the speech"
    )
    content_types = Column(
        String(1000), nullable=True, comment="Content types of the speech"
    )
    message_type = Column(
        String(255),
        nullable=True,
        comment="type of the message"
    )
    system_prompt = Column(
        Text(length=2 ** 31 - 1), nullable=True, comment="this message system prompt"
    )
    user_prompt = Column(
        Text(length=2 ** 31 - 1), nullable=True, comment="this message system prompt"
    )
    show_message = Column(
        Boolean,
        nullable=True,
        comment="Whether the current message needs to be displayed to the user",
    )
    goal_id = Column(
        String(255), nullable=True, comment="The target id to the current message"
    )
    current_goal = Column(
        Text, nullable=True, comment="The target corresponding to the current message"
    )
    context = Column(Text, nullable=True, comment="Current conversation context")
    review_info = Column(
        Text, nullable=True, comment="Current conversation review info"
    )
    action_report = Column(
        Text(length=2 ** 31 - 1),
        nullable=True,
        comment="Current conversation action report",
    )
    resource_info = Column(
        Text,
        nullable=True,
        comment="Current conversation resource info",
    )
    role = Column(
        String(255), nullable=True, comment="The role of the current message content"
    )
    avatar = Column(
        String(255),
        nullable=True,
        comment="The avatar of the agent who send current message content",
    )
    metrics = Column(
        String(1000),
        nullable=True,
        comment="The performance metrics of agent messages",
    )
    tool_calls = Column(
        Text(length=2 ** 31 - 1),
        nullable=True,
        comment="The tool_calls of agent messages",
    )
    observation = Column(
        Text(length=2 ** 31 - 1),
        nullable=True,
        comment="The  message observation",
    )

    created_at = Column(
        DateTime, name="gmt_create", default=datetime.now, comment="create time"
    )
    updated_at = Column(
        DateTime,
        name="gmt_modified",
        default=datetime.now,
        onupdate=datetime.now,
        comment="last update time",
    )
    __table_args__ = (Index("idx_q_messages", "conv_id", "rounds", "sender"),)


class GptsMessagesDao(BaseDao):

    def _from_gpts_message(self, msg: GptsMessage) -> GptsMessagesEntity:
        """将GptsMessage对象转换为GptsMessagesEntity对象（用于数据库存储）"""
        # 处理非空字段的默认值（Entity中nullable=False的字段）
        receiver = msg.receiver or ""
        receiver_name = msg.receiver_name or ""
        app_code = msg.app_code or ""
        app_name = msg.app_name or ""

        # 复杂字段的序列化
        context_str = json.dumps(msg.context, ensure_ascii=False,
                                 default=serialize) if msg.context is not None else None
        review_info_str = json.dumps(dataclasses.asdict(msg.review_info), ensure_ascii=False,
                                     default=serialize) if msg.review_info is not None else None
        action_report_str = json.dumps([item.to_dict() for item in msg.action_report], ensure_ascii=False,
                                       default=serialize) if msg.action_report else None

        resource_info_str = json.dumps(msg.resource_info, ensure_ascii=False,
                                       default=serialize) if msg.resource_info is not None else None
        metrics_str = json.dumps(msg.metrics.to_dict(), ensure_ascii=False,
                                 default=serialize) if msg.metrics is not None else None
        tool_calls_str = json.dumps(msg.tool_calls, ensure_ascii=False,
                                    default=serialize) if msg.tool_calls is not None else None
        content_types_str = json.dumps(msg.content_types, ensure_ascii=False,
                                       default=serialize) if msg.content_types is not None else None

        # 处理content字段（支持str和ChatCompletionUserMessageParam）
        content_val = msg.content
        if isinstance(content_val, dict):  # 假设ChatCompletionUserMessageParam是dict类型
            content_str = json.dumps(content_val)
        else:
            content_str = content_val  # 直接使用字符串或None

        return GptsMessagesEntity(
            conv_id=msg.conv_id or "",
            conv_session_id=msg.conv_session_id or "",
            message_id=msg.message_id or "",
            sender=msg.sender or "",
            sender_name=msg.sender_name or "",
            receiver=receiver,
            receiver_name=receiver_name,
            model_name=msg.model_name,
            rounds=msg.rounds,
            is_success=msg.is_success,
            app_code=app_code,
            app_name=app_name,
            thinking=msg.thinking,
            content=content_str,
            content_types=content_types_str,
            message_type=msg.message_type,
            system_prompt=msg.system_prompt,
            user_prompt=msg.user_prompt,
            show_message=msg.show_message,
            goal_id=msg.goal_id,
            current_goal=msg.current_goal,
            context=context_str,
            review_info=review_info_str,
            action_report=action_report_str,
            resource_info=resource_info_str,
            role=msg.role,
            avatar=msg.avatar,
            metrics=metrics_str,
            tool_calls=tool_calls_str,
            observation=msg.observation,
            created_at=msg.created_at,
            updated_at=msg.updated_at
        )

    def _to_gpts_message(self, entity: GptsMessagesEntity) -> GptsMessage:  # type: ignore
        # 复杂字段的反序列化
        context = json.loads(entity.context) if entity.context else None  # type: ignore
        review_info = AgentReviewInfo(**json.loads(entity.review_info)) if entity.review_info else None  # type: ignore

        # 处理action_report（可能是ActionOutput或dict）
        action_reports = None
        if entity.action_report:
            action_reports = ActionOutput.parse_action_reports(entity.action_report)  # type: ignore

        ## 做新旧历史数据兼容单metrics.action_metrics
        metrics = None
        if entity.metrics:
            metrics_obj = json.loads(entity.metrics)  # type: ignore
            action_metrics_obj = metrics_obj.get('action_metrics')
            if action_metrics_obj and isinstance(action_metrics_obj, dict):
                metrics_obj['action_metrics'] = [action_metrics_obj]
            metrics = MessageMetrics(**metrics_obj)

        content_types = json.loads(entity.content_types) if entity.content_types else None  # type: ignore
        resource_info = json.loads(entity.resource_info) if entity.resource_info else None  # type: ignore

        tool_calls = json.loads(entity.tool_calls) if entity.tool_calls else None  # type: ignore

        # # 处理content字段（可能包含JSON字符串）
        # content_val = entity.content
        # if content_val and content_val.startswith(('{', '[')):  # 简单启发式判断
        #     try:
        #         content_val = json.loads(content_val)
        #     except json.JSONDecodeError:
        #         pass  # 保持原字符串

        return GptsMessage(
            conv_id=entity.conv_id,
            conv_session_id=entity.conv_session_id,
            sender=entity.sender,
            sender_name=entity.sender_name,
            message_id=entity.message_id,
            role=entity.role,
            content=entity.content,
            rounds=entity.rounds,
            content_types=content_types,
            message_type=entity.message_type,
            receiver=entity.receiver or None,  # 空字符串转None
            receiver_name=entity.receiver_name or None,
            is_success=entity.is_success,
            avatar=entity.avatar,
            thinking=entity.thinking,
            app_code=entity.app_code or None,
            app_name=entity.app_name or None,
            goal_id=entity.goal_id,
            current_goal=entity.current_goal,
            context=context,
            action_report=action_reports,
            review_info=review_info,
            model_name=entity.model_name,
            resource_info=resource_info,
            system_prompt=entity.system_prompt,
            user_prompt=entity.user_prompt,
            show_message=entity.show_message,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            observation=entity.observation,
            metrics=metrics,
            tool_calls=tool_calls
        )

    def update_message(self, msg: GptsMessage):
        entity = self._from_gpts_message(msg)
        session = self.get_raw_session()
        message_qry = session.query(GptsMessagesEntity)
        message_qry = message_qry.filter(
            GptsMessagesEntity.message_id == entity.message_id
        )

        # try:
        #     compiled = message_qry.statement.compile(
        #         dialect=session.bind.dialect,
        #         compile_kwargs={"literal_binds": True}
        #     )
        #     print(f"[DEBUG SQL] {compiled}")
        # except Exception as e:
        #     print(f"[WARN] Failed to compile SQL for debug: {e}")
        old_message: Optional[GptsMessagesEntity] = message_qry.one_or_none()

        if old_message:
            message_qry.update(
                {
                    GptsMessagesEntity.conv_id: entity.conv_id,
                    GptsMessagesEntity.sender: entity.sender,
                    GptsMessagesEntity.receiver: entity.receiver,
                    GptsMessagesEntity.model_name: entity.model_name,
                    GptsMessagesEntity.rounds: entity.rounds,
                    GptsMessagesEntity.is_success: entity.is_success,
                    GptsMessagesEntity.app_code: entity.app_code,
                    GptsMessagesEntity.app_name: entity.app_name,
                    GptsMessagesEntity.content: entity.content,
                    GptsMessagesEntity.content_types: entity.content_types,
                    GptsMessagesEntity.current_goal: entity.current_goal,
                    GptsMessagesEntity.context: entity.context,
                    GptsMessagesEntity.review_info: entity.review_info,
                    GptsMessagesEntity.action_report: entity.action_report,
                    GptsMessagesEntity.resource_info: entity.resource_info,
                    GptsMessagesEntity.role: entity.role,
                    GptsMessagesEntity.message_id: entity.message_id,
                    GptsMessagesEntity.goal_id: entity.goal_id,
                    GptsMessagesEntity.thinking: entity.thinking,
                    GptsMessagesEntity.show_message: entity.show_message,
                    GptsMessagesEntity.system_prompt: entity.system_prompt,
                    GptsMessagesEntity.user_prompt: entity.user_prompt,
                    GptsMessagesEntity.sender_name: entity.sender_name,
                    GptsMessagesEntity.receiver_name: entity.receiver_name,
                    GptsMessagesEntity.avatar: entity.avatar,
                    GptsMessagesEntity.conv_session_id: entity.conv_session_id,
                    GptsMessagesEntity.observation: entity.observation,
                    GptsMessagesEntity.metrics: entity.metrics,
                    GptsMessagesEntity.tool_calls: entity.tool_calls,
                },
                synchronize_session="fetch",
            )
        else:
            session.add(entity)

        session.commit()
        session.close()
        return id

    def append(self, entity: dict):
        session = self.get_raw_session()
        message = self._dict_to_entity(entity)
        session.add(message)
        session.commit()
        id = message.id
        session.close()
        return id

    async def get_by_conv_id(self, conv_id: str) -> List[GptsMessage]:
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsMessagesEntity)
                .where(GptsMessagesEntity.conv_id == conv_id)
                .order_by(GptsMessagesEntity.rounds)
            )
            entities = result.scalars().all()
            return [self._to_gpts_message(e) for e in entities]

    def get_by_conv_session_id(
        self, conv_session_id: str
    ) -> List[GptsMessage]:
        session = self.get_raw_session()
        gpts_messages = session.query(GptsMessagesEntity)
        if conv_session_id:
            gpts_messages = gpts_messages.filter(
                GptsMessagesEntity.conv_session_id == conv_session_id
            )
        entities = gpts_messages.order_by(GptsMessagesEntity.rounds).all()
        session.close()
        return [self._to_gpts_message(e) for e in entities]

    def get_by_message_id(self, message_id: str) -> Optional[GptsMessage]:
        session = self.get_raw_session()
        entity = session.query(GptsMessagesEntity).filter(
            GptsMessagesEntity.message_id == message_id
        ).order_by(GptsMessagesEntity.id.desc()).first()
        session.close()
        return self._to_gpts_message(entity) if entity else None

    def get_last_message(self, conv_id: str) -> Optional[GptsMessage]:
        session = self.get_raw_session()
        entity = session.query(GptsMessagesEntity).filter(
            GptsMessagesEntity.conv_id == conv_id
        ).order_by(desc(GptsMessagesEntity.rounds)).first()
        session.close()
        return self._to_gpts_message(entity) if entity else None

    def delete_chat_message(self, conv_id: str) -> bool:
        session = self.get_raw_session()
        gpts_messages = session.query(GptsMessagesEntity)
        gpts_messages.filter(GptsMessagesEntity.conv_id.like(f"%{conv_id}%")).delete()
        session.commit()
        session.close()
        return True

    def delete_by_msg_id(self, message_id: str):
        session = self.get_raw_session()
        old_message_qry = session.query(GptsMessagesEntity)

        old_message_qry = old_message_qry.filter(
            GptsMessagesEntity.message_id == message_id
        )
        old_message = old_message_qry.order_by(GptsMessagesEntity.rounds).one_or_none()
        if old_message:
            session.delete(old_message)
            session.commit()
        session.close()
