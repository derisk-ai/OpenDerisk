"""Authorization Audit Log 数据库模型和 DAO.

用于持久化存储工具授权审计日志，支持授权决策追踪、安全审计和合规分析。
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Float,
    select,
    and_,
    or_,
    desc,
)
from sqlalchemy import func as sa_func

from derisk.storage.metadata import BaseDao, Model
from derisk._private.pydantic import BaseModel, ConfigDict


class AuthorizationDecision(str, Enum):
    """授权决策类型."""

    GRANTED = "granted"
    DENIED = "denied"
    NEED_CONFIRMATION = "need_confirmation"
    CACHED = "cached"


class PermissionAction(str, Enum):
    """权限动作类型."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# ========== Pydantic Models ==========


class AuthorizationAuditLog(BaseModel):
    """授权审计日志 Pydantic 模型."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    session_id: str
    user_id: Optional[str] = None
    agent_name: Optional[str] = None
    tool_name: str
    arguments: Optional[Dict[str, Any]] = None
    decision: str  # AuthorizationDecision
    action: str  # PermissionAction
    reason: Optional[str] = None
    risk_level: Optional[str] = None
    risk_score: Optional[int] = None
    risk_factors: Optional[List[str]] = None
    cached: bool = False
    duration_ms: float = 0.0
    created_at: datetime = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "decision": self.decision,
            "action": self.action,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "cached": self.cached,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuthorizationAuditStats(BaseModel):
    """授权审计统计."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    total_count: int = 0
    granted_count: int = 0
    denied_count: int = 0
    cached_count: int = 0
    confirmation_count: int = 0
    avg_risk_score: float = 0.0
    avg_duration_ms: float = 0.0
    high_risk_count: int = 0
    critical_risk_count: int = 0


# ========== SQLAlchemy Entity ==========


class AuthorizationAuditLogEntity(Model):
    """授权审计日志数据库实体."""

    __tablename__ = "authorization_audit_log"
    __table_args__ = (
        Index("idx_audit_session", "session_id"),
        Index("idx_audit_tool", "tool_name"),
        Index("idx_audit_decision", "decision"),
        Index("idx_audit_risk_level", "risk_level"),
        Index("idx_audit_created_at", "created_at"),
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_agent", "agent_name"),
    )

    id = Column(Integer, primary_key=True, comment="autoincrement id")

    # 上下文信息
    session_id = Column(String(255), nullable=False, comment="Session identifier")
    user_id = Column(String(255), nullable=True, comment="User identifier")
    agent_name = Column(String(255), nullable=True, comment="Agent name")

    # 工具信息
    tool_name = Column(String(255), nullable=False, comment="Tool name")
    arguments = Column(Text, nullable=True, comment="Tool arguments (JSON)")

    # 决策信息
    decision = Column(String(32), nullable=False, comment="Authorization decision")
    action = Column(String(16), nullable=False, comment="Permission action")
    reason = Column(Text, nullable=True, comment="Reason for the decision")

    # 风险评估
    risk_level = Column(String(16), nullable=True, comment="Risk level")
    risk_score = Column(Integer, nullable=True, comment="Risk score (0-100)")
    risk_factors = Column(Text, nullable=True, comment="Risk factors (JSON array)")

    # 缓存信息
    cached = Column(Integer, nullable=False, default=0, comment="Whether from cache")

    # 性能指标
    duration_ms = Column(
        Float, nullable=False, default=0.0, comment="Duration in milliseconds"
    )

    # 时间戳
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When the audit log was created",
    )


# ========== DAO ==========


class AuthorizationAuditLogDao(BaseDao):
    """授权审计日志 DAO."""

    def _entity_to_model(
        self, entity: AuthorizationAuditLogEntity
    ) -> AuthorizationAuditLog:
        """将数据库实体转换为 Pydantic 模型."""
        return AuthorizationAuditLog(
            id=entity.id,
            session_id=entity.session_id,
            user_id=entity.user_id,
            agent_name=entity.agent_name,
            tool_name=entity.tool_name,
            arguments=json.loads(entity.arguments) if entity.arguments else None,
            decision=entity.decision,
            action=entity.action,
            reason=entity.reason,
            risk_level=entity.risk_level,
            risk_score=entity.risk_score,
            risk_factors=json.loads(entity.risk_factors)
            if entity.risk_factors
            else None,
            cached=bool(entity.cached),
            duration_ms=entity.duration_ms,
            created_at=entity.created_at,
        )

    def _model_to_entity(
        self, log: AuthorizationAuditLog
    ) -> AuthorizationAuditLogEntity:
        """将 Pydantic 模型转换为数据库实体."""
        return AuthorizationAuditLogEntity(
            session_id=log.session_id,
            user_id=log.user_id,
            agent_name=log.agent_name,
            tool_name=log.tool_name,
            arguments=json.dumps(log.arguments, ensure_ascii=False)
            if log.arguments
            else None,
            decision=log.decision,
            action=log.action,
            reason=log.reason,
            risk_level=log.risk_level,
            risk_score=log.risk_score,
            risk_factors=json.dumps(log.risk_factors, ensure_ascii=False)
            if log.risk_factors
            else None,
            cached=1 if log.cached else 0,
            duration_ms=log.duration_ms,
            created_at=log.created_at or datetime.utcnow(),
        )

    def create(self, log: AuthorizationAuditLog) -> int:
        """创建审计日志记录.

        Args:
            log: 授权审计日志模型

        Returns:
            创建的记录 ID
        """
        entity = self._model_to_entity(log)
        session = self.get_raw_session()
        session.add(entity)
        session.commit()
        record_id = entity.id
        session.close()
        return record_id

    async def create_async(self, log: AuthorizationAuditLog) -> int:
        """异步创建审计日志记录."""
        entity = self._model_to_entity(log)
        async with self.a_session(commit=True) as session:
            session.add(entity)
            await session.flush()
            return entity.id

    def get_by_id(self, log_id: int) -> Optional[AuthorizationAuditLog]:
        """根据 ID 获取审计日志."""
        session = self.get_raw_session()
        entity = (
            session.query(AuthorizationAuditLogEntity)
            .filter(AuthorizationAuditLogEntity.id == log_id)
            .first()
        )
        session.close()
        return self._entity_to_model(entity) if entity else None

    async def get_by_id_async(self, log_id: int) -> Optional[AuthorizationAuditLog]:
        """异步根据 ID 获取审计日志."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(AuthorizationAuditLogEntity).where(
                    AuthorizationAuditLogEntity.id == log_id
                )
            )
            entity = result.scalar_one_or_none()
            return self._entity_to_model(entity) if entity else None

    def list(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        decision: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List[AuthorizationAuditLog]:
        """查询审计日志列表.

        Args:
            session_id: 会话 ID 过滤
            user_id: 用户 ID 过滤
            agent_name: Agent 名称过滤
            tool_name: 工具名称过滤
            decision: 决策类型过滤
            risk_level: 风险等级过滤
            start_time: 开始时间
            end_time: 结束时间
            page: 页码
            page_size: 每页数量

        Returns:
            审计日志列表
        """
        session = self.get_raw_session()
        query = session.query(AuthorizationAuditLogEntity)

        if session_id:
            query = query.filter(AuthorizationAuditLogEntity.session_id == session_id)
        if user_id:
            query = query.filter(AuthorizationAuditLogEntity.user_id == user_id)
        if agent_name:
            query = query.filter(AuthorizationAuditLogEntity.agent_name == agent_name)
        if tool_name:
            query = query.filter(AuthorizationAuditLogEntity.tool_name == tool_name)
        if decision:
            query = query.filter(AuthorizationAuditLogEntity.decision == decision)
        if risk_level:
            query = query.filter(AuthorizationAuditLogEntity.risk_level == risk_level)
        if start_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at >= start_time)
        if end_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at <= end_time)

        entities = (
            query.order_by(desc(AuthorizationAuditLogEntity.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        session.close()
        return [self._entity_to_model(e) for e in entities]

    async def list_async(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        decision: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List[AuthorizationAuditLog]:
        """异步查询审计日志列表."""
        async with self.a_session(commit=False) as session:
            query = select(AuthorizationAuditLogEntity)

            conditions = []
            if session_id:
                conditions.append(AuthorizationAuditLogEntity.session_id == session_id)
            if user_id:
                conditions.append(AuthorizationAuditLogEntity.user_id == user_id)
            if agent_name:
                conditions.append(AuthorizationAuditLogEntity.agent_name == agent_name)
            if tool_name:
                conditions.append(AuthorizationAuditLogEntity.tool_name == tool_name)
            if decision:
                conditions.append(AuthorizationAuditLogEntity.decision == decision)
            if risk_level:
                conditions.append(AuthorizationAuditLogEntity.risk_level == risk_level)
            if start_time:
                conditions.append(AuthorizationAuditLogEntity.created_at >= start_time)
            if end_time:
                conditions.append(AuthorizationAuditLogEntity.created_at <= end_time)

            if conditions:
                query = query.where(and_(*conditions))

            result = await session.execute(
                query.order_by(desc(AuthorizationAuditLogEntity.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            entities = result.scalars().all()
            return [self._entity_to_model(e) for e in entities]

    def count(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        decision: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """统计审计日志数量."""
        session = self.get_raw_session()
        query = session.query(sa_func.count(AuthorizationAuditLogEntity.id))

        if session_id:
            query = query.filter(AuthorizationAuditLogEntity.session_id == session_id)
        if user_id:
            query = query.filter(AuthorizationAuditLogEntity.user_id == user_id)
        if agent_name:
            query = query.filter(AuthorizationAuditLogEntity.agent_name == agent_name)
        if tool_name:
            query = query.filter(AuthorizationAuditLogEntity.tool_name == tool_name)
        if decision:
            query = query.filter(AuthorizationAuditLogEntity.decision == decision)
        if risk_level:
            query = query.filter(AuthorizationAuditLogEntity.risk_level == risk_level)
        if start_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at >= start_time)
        if end_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at <= end_time)

        count = query.scalar()
        session.close()
        return count or 0

    async def count_async(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        decision: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """异步统计审计日志数量."""
        async with self.a_session(commit=False) as session:
            query = select(sa_func.count(AuthorizationAuditLogEntity.id))

            conditions = []
            if session_id:
                conditions.append(AuthorizationAuditLogEntity.session_id == session_id)
            if user_id:
                conditions.append(AuthorizationAuditLogEntity.user_id == user_id)
            if agent_name:
                conditions.append(AuthorizationAuditLogEntity.agent_name == agent_name)
            if tool_name:
                conditions.append(AuthorizationAuditLogEntity.tool_name == tool_name)
            if decision:
                conditions.append(AuthorizationAuditLogEntity.decision == decision)
            if risk_level:
                conditions.append(AuthorizationAuditLogEntity.risk_level == risk_level)
            if start_time:
                conditions.append(AuthorizationAuditLogEntity.created_at >= start_time)
            if end_time:
                conditions.append(AuthorizationAuditLogEntity.created_at <= end_time)

            if conditions:
                query = query.where(and_(*conditions))

            result = await session.execute(query)
            return result.scalar() or 0

    def get_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AuthorizationAuditStats:
        """获取审计日志统计信息.

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息
        """
        session = self.get_raw_session()
        query = session.query(AuthorizationAuditLogEntity)

        if start_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at >= start_time)
        if end_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at <= end_time)

        entities = query.all()
        session.close()

        total_count = len(entities)
        granted_count = sum(
            1 for e in entities if e.decision == AuthorizationDecision.GRANTED.value
        )
        denied_count = sum(
            1 for e in entities if e.decision == AuthorizationDecision.DENIED.value
        )
        cached_count = sum(1 for e in entities if e.cached)
        confirmation_count = sum(
            1
            for e in entities
            if e.decision == AuthorizationDecision.NEED_CONFIRMATION.value
        )

        risk_scores = [e.risk_score for e in entities if e.risk_score is not None]
        avg_risk_score = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0

        durations = [e.duration_ms for e in entities if e.duration_ms]
        avg_duration_ms = sum(durations) / len(durations) if durations else 0.0

        high_risk_count = sum(1 for e in entities if e.risk_level == "high")
        critical_risk_count = sum(1 for e in entities if e.risk_level == "critical")

        return AuthorizationAuditStats(
            total_count=total_count,
            granted_count=granted_count,
            denied_count=denied_count,
            cached_count=cached_count,
            confirmation_count=confirmation_count,
            avg_risk_score=avg_risk_score,
            avg_duration_ms=avg_duration_ms,
            high_risk_count=high_risk_count,
            critical_risk_count=critical_risk_count,
        )

    async def get_stats_async(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AuthorizationAuditStats:
        """异步获取审计日志统计信息."""
        async with self.a_session(commit=False) as session:
            query = select(AuthorizationAuditLogEntity)

            if start_time:
                query = query.where(
                    AuthorizationAuditLogEntity.created_at >= start_time
                )
            if end_time:
                query = query.where(AuthorizationAuditLogEntity.created_at <= end_time)

            result = await session.execute(query)
            entities = result.scalars().all()

            total_count = len(entities)
            granted_count = sum(
                1 for e in entities if e.decision == AuthorizationDecision.GRANTED.value
            )
            denied_count = sum(
                1 for e in entities if e.decision == AuthorizationDecision.DENIED.value
            )
            cached_count = sum(1 for e in entities if e.cached)
            confirmation_count = sum(
                1
                for e in entities
                if e.decision == AuthorizationDecision.NEED_CONFIRMATION.value
            )

            risk_scores = [e.risk_score for e in entities if e.risk_score is not None]
            avg_risk_score = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0

            durations = [e.duration_ms for e in entities if e.duration_ms]
            avg_duration_ms = sum(durations) / len(durations) if durations else 0.0

            high_risk_count = sum(1 for e in entities if e.risk_level == "high")
            critical_risk_count = sum(1 for e in entities if e.risk_level == "critical")

            return AuthorizationAuditStats(
                total_count=total_count,
                granted_count=granted_count,
                denied_count=denied_count,
                cached_count=cached_count,
                confirmation_count=confirmation_count,
                avg_risk_score=avg_risk_score,
                avg_duration_ms=avg_duration_ms,
                high_risk_count=high_risk_count,
                critical_risk_count=critical_risk_count,
            )

    def get_tool_usage_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """获取工具使用统计.

        Returns:
            每个工具的使用统计列表
        """
        session = self.get_raw_session()
        query = session.query(
            AuthorizationAuditLogEntity.tool_name,
            sa_func.count(AuthorizationAuditLogEntity.id).label("total"),
            sa_func.sum(
                sa_func.case(
                    [(AuthorizationAuditLogEntity.decision == "granted", 1)], else_=0
                )
            ).label("granted"),
            sa_func.sum(
                sa_func.case(
                    [(AuthorizationAuditLogEntity.decision == "denied", 1)], else_=0
                )
            ).label("denied"),
            sa_func.avg(AuthorizationAuditLogEntity.risk_score).label("avg_risk_score"),
        ).group_by(AuthorizationAuditLogEntity.tool_name)

        if start_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at >= start_time)
        if end_time:
            query = query.filter(AuthorizationAuditLogEntity.created_at <= end_time)

        results = query.all()
        session.close()

        return [
            {
                "tool_name": r.tool_name,
                "total": r.total,
                "granted": r.granted or 0,
                "denied": r.denied or 0,
                "avg_risk_score": round(r.avg_risk_score, 2) if r.avg_risk_score else 0,
            }
            for r in results
        ]

    def delete_old_logs(self, days: int = 30) -> int:
        """删除指定天数之前的审计日志.

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        session = self.get_raw_session()
        deleted = (
            session.query(AuthorizationAuditLogEntity)
            .filter(AuthorizationAuditLogEntity.created_at < cutoff)
            .delete()
        )
        session.commit()
        session.close()
        return deleted
