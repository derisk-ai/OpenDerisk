from datetime import datetime, timedelta
import logging

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    desc, select,
)
from sqlalchemy.orm import Query

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class GptsConversationsEntity(Model):
    __tablename__ = "gpts_conversations"
    id = Column(Integer, primary_key=True, comment="autoincrement id")

    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation record"
    )
    conv_session_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation record"
    )
    user_goal = Column(Text, nullable=False, comment="User's goals content")

    gpts_name = Column(String(255), nullable=False, comment="The gpts name")
    team_mode = Column(
        String(255), nullable=False, comment="The conversation team mode"
    )
    state = Column(String(255), nullable=True, comment="The gpts state")

    max_auto_reply_round = Column(
        Integer, nullable=False, comment="max auto reply round"
    )
    auto_reply_count = Column(Integer, nullable=False, comment="auto reply count")

    user_code = Column(String(255), nullable=True, comment="user code")
    sys_code = Column(String(255), nullable=True, comment="system app ")
    workspace_id = Column(
        Integer, nullable=True, index=True, comment="workspace id, NULL for legacy/HomeChat"
    )
    task_id = Column(
        Integer, nullable=True, index=True, comment="task id this conversation belongs to"
    )
    vis_render = Column(String(255), nullable=True, comment="vis mode of chat conversation ")
    extra=Column(Text(65535), nullable=True, comment="the extra info of the conversation")
    # PR 4: 心跳字段，由 agent loop 自然进度点 inline 更新（fire-and-forget）
    # RecoveryDaemon 启动时按 is_stale() 判断 RUNNING 会话是否真死
    last_heartbeat = Column(
        DateTime, nullable=True, comment="last heartbeat time of the agent loop"
    )
    # Tier 3.2: lease 字段，多进程部署时显式声明会话所有权
    # acquire_lease 是原子的：worker_id IS NULL OR lease_expires_at < now 时才能拿到
    # 取代单纯心跳的隐式所有权判断，避免双进程同时 retry 同一会话
    worker_id = Column(
        String(128), nullable=True, comment="worker process id holding the lease"
    )
    lease_expires_at = Column(
        DateTime, nullable=True, comment="when the lease expires, NULL if no lease"
    )
    created_at = Column(
        DateTime, name="gmt_create", default=datetime.utcnow, comment="create time"
    )
    updated_at = Column(
        DateTime,
        name="gmt_modified",
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time",
    )

    __table_args__ = (
        UniqueConstraint("conv_id", name="uk_gpts_conversations"),
        Index("idx_gpts_name", "gpts_name"),
    )


class GptsConversationsDao(BaseDao):
    def add(self, entity: GptsConversationsEntity):
        session = self.get_raw_session()
        session.add(entity)
        session.commit()
        id = entity.id
        session.close()
        return id

    async def a_add(self, entity: GptsConversationsEntity):
        async with self.a_session() as session:
            session.add(entity)
            return entity.id

    def get_by_conv_id(self, conv_id: str):
        session = self.get_raw_session()
        gpts_conv = session.query(GptsConversationsEntity)
        if conv_id:
            gpts_conv = gpts_conv.filter(GptsConversationsEntity.conv_id == conv_id)
        result = gpts_conv.first()
        session.close()
        return result

    async def a_get_by_conv_id(self, conv_id: str):
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsConversationsEntity).where(GptsConversationsEntity.conv_id == conv_id).limit(1)
            )
            return result.scalar_one_or_none()

    def get_like_conv_id_asc(self, conv_id: str):
        session = self.get_raw_session()
        try:
            gpts_conv_qry: Query = session.query(GptsConversationsEntity)
            gpts_conv_qry: Query = gpts_conv_qry.filter(
                GptsConversationsEntity.conv_id.like(f"{conv_id}%")
            ).order_by(GptsConversationsEntity.id.asc())
            result = gpts_conv_qry.all()
        finally:
            session.close()
        return result

    async def get_by_session_id_asc(self, conv_session_id: str):
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsConversationsEntity).where(GptsConversationsEntity.conv_session_id == conv_session_id)
                .order_by(GptsConversationsEntity.id.asc())
            )
            return list(result.scalars().all())
        # session = self.get_raw_session()
        # try:
        #     gpts_conv_qry: Query = session.query(GptsConversationsEntity)
        #     gpts_conv_qry: Query = gpts_conv_qry.filter(
        #         GptsConversationsEntity.conv_session_id == conv_session_id
        #     ).order_by(GptsConversationsEntity.id.asc())
        #     result = gpts_conv_qry.all()
        # finally:
        #     session.close()
        # return result

    def get_convs(self, user_code: str = None, system_app: str = None):
        session = self.get_raw_session()
        gpts_conversations = session.query(GptsConversationsEntity)
        if user_code:
            gpts_conversations = gpts_conversations.filter(
                GptsConversationsEntity.user_code == user_code
            )
        if system_app:
            gpts_conversations = gpts_conversations.filter(
                GptsConversationsEntity.system_app == system_app
            )

        result = (
            gpts_conversations.limit(20)
            .order_by(desc(GptsConversationsEntity.id))
            .all()
        )
        session.close()
        return result

    def update(self, conv_id: str, state: str):
        session = self.get_raw_session()
        gpts_convs = session.query(GptsConversationsEntity)
        gpts_convs = gpts_convs.filter(GptsConversationsEntity.conv_id == conv_id)
        gpts_convs.update(
            {GptsConversationsEntity.state: state}, synchronize_session="fetch"
        )
        session.commit()
        session.close()

    def update_heartbeat(self, conv_id: str) -> None:
        """PR 4: 轻量心跳更新（只改 last_heartbeat 列）。

        由 heartbeat.touch_heartbeat 通过 asyncio.create_task 调用，
        fire-and-forget，失败只 log warning，不阻塞 agent loop。
        """
        session = self.get_raw_session()
        try:
            session.query(GptsConversationsEntity).filter(
                GptsConversationsEntity.conv_id == conv_id
            ).update(
                {GptsConversationsEntity.last_heartbeat: datetime.utcnow()},
                synchronize_session="fetch",
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- Tier 3.2: lease 机制 ----

    def acquire_lease(
        self, conv_id: str, worker_id: str, ttl_seconds: int = 90
    ) -> bool:
        """原子地获取会话租约。

        仅当 worker_id IS NULL 或 lease_expires_at < now 时才能拿到。
        多进程部署下，确保同一会话同一时刻只有一个 worker 在跑。

        防御性：如果 lease 列不存在（未跑 migration），返回 False 而非抛异常，
        让 RecoveryDaemon 退化为纯心跳判断。

        Returns:
            True 如果获取成功；False 如果已被其他 worker 持有且未过期，或列不存在。
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)
        session = self.get_raw_session()
        try:
            updated = session.query(GptsConversationsEntity).filter(
                GptsConversationsEntity.conv_id == conv_id,
                (
                    (GptsConversationsEntity.worker_id.is_(None))
                    | (GptsConversationsEntity.lease_expires_at < now)
                ),
            ).update(
                {
                    GptsConversationsEntity.worker_id: worker_id,
                    GptsConversationsEntity.lease_expires_at: expires_at,
                    GptsConversationsEntity.last_heartbeat: now,
                },
                synchronize_session="fetch",
            )
            session.commit()
            return updated > 0
        except Exception as e:
            session.rollback()
            # 列不存在（未跑 migration）→ 退化标志，调用方应回退到心跳 only
            logger.warning(
                f"[lease] acquire failed (column may not exist): {e}"
            )
            return False
        finally:
            session.close()

    def renew_lease(
        self, conv_id: str, worker_id: str, ttl_seconds: int = 90
    ) -> bool:
        """续租：仅当 worker_id 匹配当前 worker 时才能续。

        在 agent loop 自然进度点调用（同 touch_heartbeat）。
        如果租约已被抢占（不应发生但可能），返回 False，调用方应停止 loop。

        防御性：列不存在时返回 False，调用方退化为只更新 last_heartbeat。
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)
        session = self.get_raw_session()
        try:
            updated = session.query(GptsConversationsEntity).filter(
                GptsConversationsEntity.conv_id == conv_id,
                GptsConversationsEntity.worker_id == worker_id,
            ).update(
                {
                    GptsConversationsEntity.lease_expires_at: expires_at,
                    GptsConversationsEntity.last_heartbeat: now,
                },
                synchronize_session="fetch",
            )
            session.commit()
            return updated > 0
        except Exception as e:
            session.rollback()
            logger.debug(f"[lease] renew failed (column may not exist): {e}")
            return False
        finally:
            session.close()

    def release_lease(self, conv_id: str, worker_id: str) -> bool:
        """释放租约：仅当 worker_id 匹配时才清空。

        会话正常结束时调用。如果租约已被抢占（不应发生），返回 False。
        防御性：列不存在时返回 False。
        """
        session = self.get_raw_session()
        try:
            updated = session.query(GptsConversationsEntity).filter(
                GptsConversationsEntity.conv_id == conv_id,
                GptsConversationsEntity.worker_id == worker_id,
            ).update(
                {
                    GptsConversationsEntity.worker_id: None,
                    GptsConversationsEntity.lease_expires_at: None,
                },
                synchronize_session="fetch",
            )
            session.commit()
            return updated > 0
        except Exception as e:
            session.rollback()
            logger.debug(f"[lease] release failed (column may not exist): {e}")
            return False
        finally:
            session.close()

    def get_lease_holder(self, conv_id: str):
        """读取当前租约持有者 (worker_id, lease_expires_at)。

        防御性：列不存在时返回 (None, None)，调用方视为可抢占但 acquire 也会失败，
        最终退化为心跳判断。
        """
        session = self.get_raw_session()
        try:
            conv = (
                session.query(GptsConversationsEntity)
                .filter(GptsConversationsEntity.conv_id == conv_id)
                .first()
            )
            if conv is None:
                return (None, None)
            # 列可能不存在（migration 未跑），用 getattr 防御
            return (
                getattr(conv, "worker_id", None),
                getattr(conv, "lease_expires_at", None),
            )
        except Exception as e:
            logger.debug(f"[lease] get_lease_holder failed: {e}")
            return (None, None)
        finally:
            session.close()

    def get_running_convs(self) -> list:
        """PR 4: 查所有 state=RUNNING 的会话（RecoveryDaemon 启动扫描用）。"""
        session = self.get_raw_session()
        try:
            return (
                session.query(GptsConversationsEntity)
                .filter(GptsConversationsEntity.state == "RUNNING")
                .all()
            )
        finally:
            session.close()

    def delete_chat_message(self, conv_id: str) -> bool:
        session = self.get_raw_session()
        gpts_convs = session.query(GptsConversationsEntity)
        gpts_convs.filter(GptsConversationsEntity.conv_id.like(f"%{conv_id}%")).delete()
        session.commit()
        session.close()
        return True
