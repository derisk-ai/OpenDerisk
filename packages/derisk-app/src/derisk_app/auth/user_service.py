"""User service for OAuth2 login - create/update/list users from OAuth provider."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Column, DateTime, Integer, String, or_

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class UserEntity(Model):
    """User entity matching the user table schema."""

    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=True)
    fullname = Column(String(50), nullable=True)
    oauth_provider = Column(String(64), nullable=True, comment="OAuth2 provider")
    oauth_id = Column(String(255), nullable=True, comment="OAuth provider user ID")
    email = Column(String(255), nullable=True, comment="User email")
    avatar = Column(String(512), nullable=True, comment="Avatar URL")
    role = Column(
        String(20), nullable=True, default="normal", comment="User role: normal/admin"
    )
    is_active = Column(
        Integer, nullable=False, default=1, comment="1=active, 0=disabled"
    )
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False)
    gmt_modify = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


def _entity_to_dict(user: UserEntity) -> Dict[str, Any]:
    """Convert UserEntity to plain dict (safe to use after session close)."""
    return {
        "id": user.id,
        "name": user.name or "",
        "fullname": user.fullname or "",
        "email": user.email or "",
        "avatar": user.avatar or "",
        "oauth_provider": user.oauth_provider or "",
        "oauth_id": user.oauth_id or "",
        "role": user.role or "normal",
        "is_active": user.is_active if user.is_active is not None else 1,
        "gmt_create": user.gmt_create.isoformat() if user.gmt_create else None,
        "gmt_modify": user.gmt_modify.isoformat() if user.gmt_modify else None,
    }


class UserDao(BaseDao):
    """DAO for user table operations."""

    def get_by_oauth(self, provider: str, oauth_id: str) -> Optional[Dict[str, Any]]:
        """Get user by OAuth provider and id."""
        with self.session() as session:
            user = (
                session.query(UserEntity)
                .filter(
                    UserEntity.oauth_provider == provider,
                    UserEntity.oauth_id == oauth_id,
                )
                .first()
            )
            return _entity_to_dict(user) if user else None

    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by id."""
        with self.session() as session:
            user = session.query(UserEntity).filter(UserEntity.id == user_id).first()
            return _entity_to_dict(user) if user else None

    def create_or_update_from_oauth(
        self,
        provider: str,
        oauth_id: str,
        user_info: Dict[str, Any],
        role: str = "normal",
    ) -> Dict[str, Any]:
        """Create or update user from OAuth user info, return plain dict.

        Returns a dict instead of the ORM entity to avoid DetachedInstanceError
        after the session closes.
        """
        with self.session() as session:
            user = (
                session.query(UserEntity)
                .filter(
                    UserEntity.oauth_provider == provider,
                    UserEntity.oauth_id == oauth_id,
                )
                .first()
            )
            name = (
                user_info.get("login")
                or user_info.get("username")
                or user_info.get("name", "")
            )
            fullname = user_info.get("name") or user_info.get("fullname", "")
            email = user_info.get("email", "")
            avatar = (
                user_info.get("avatar_url")
                or user_info.get("avatar")
                or user_info.get("picture", "")
            )

            if user:
                user.name = name or user.name
                user.fullname = fullname or user.fullname
                user.email = email or user.email
                user.avatar = avatar or user.avatar
                # Do NOT override role for existing users
                merged = session.merge(user)
                session.commit()
                session.refresh(merged)
                return _entity_to_dict(merged)
            else:
                user = UserEntity(
                    name=name,
                    fullname=fullname,
                    oauth_provider=provider,
                    oauth_id=oauth_id,
                    email=email,
                    avatar=avatar,
                    role=role,
                    is_active=1,
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                return _entity_to_dict(user)

    def list_users(
        self, page: int = 1, page_size: int = 20, keyword: str = ""
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List users with pagination and optional keyword filter."""
        with self.session() as session:
            query = session.query(UserEntity)
            if keyword:
                like = f"%{keyword}%"
                query = query.filter(
                    or_(
                        UserEntity.name.ilike(like),
                        UserEntity.fullname.ilike(like),
                        UserEntity.email.ilike(like),
                    )
                )
            total = query.count()
            users = (
                query.order_by(UserEntity.gmt_create.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [_entity_to_dict(u) for u in users], total

    def update_user(
        self,
        user_id: int,
        role: Optional[str] = None,
        is_active: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update user role or is_active status."""
        with self.session() as session:
            user = session.query(UserEntity).filter(UserEntity.id == user_id).first()
            if not user:
                return None
            if role is not None:
                user.role = role
            if is_active is not None:
                user.is_active = is_active
            session.commit()
            session.refresh(user)
            return _entity_to_dict(user)


class UserService:
    """Service for user operations."""

    def __init__(self):
        self._dao = UserDao()

    def get_or_create_from_oauth(
        self,
        provider: str,
        oauth_id: str,
        user_info: Dict[str, Any],
        role: str = "normal",
    ) -> Optional[Dict[str, Any]]:
        """Get or create user from OAuth info, return user dict for session."""
        try:
            return self._dao.create_or_update_from_oauth(
                provider, oauth_id, user_info, role=role
            )
        except Exception as e:
            logger.exception(f"Failed to get/create user from OAuth: {e}")
            return None

    def list_users(
        self, page: int = 1, page_size: int = 20, keyword: str = ""
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List users with pagination."""
        try:
            return self._dao.list_users(page, page_size, keyword)
        except Exception as e:
            logger.exception(f"Failed to list users: {e}")
            return [], 0

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a single user by id."""
        try:
            return self._dao.get_by_id(user_id)
        except Exception as e:
            logger.exception(f"Failed to get user {user_id}: {e}")
            return None

    def update_user(
        self,
        user_id: int,
        role: Optional[str] = None,
        is_active: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update user role or active status."""
        try:
            return self._dao.update_user(user_id, role=role, is_active=is_active)
        except Exception as e:
            logger.exception(f"Failed to update user {user_id}: {e}")
            return None
