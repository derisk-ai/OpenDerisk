"""OAuth2 configuration database storage with encryption.

This module provides database persistence for OAuth2 configuration,
with automatic encryption/decryption of sensitive fields like client_secret.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class OAuth2ConfigEntity(Model):
    """OAuth2 configuration entity for database storage (plain text)."""

    __tablename__ = "oauth2_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(
        String(64),
        nullable=False,
        default="global",
        comment="Configuration key (default: global)",
    )
    enabled = Column(
        Integer,
        nullable=False,
        default=0,
        comment="OAuth2 enabled flag (1=true, 0=false)",
    )
    providers_json = Column(
        Text,
        nullable=True,
        comment="OAuth2 providers configuration (JSON array)",
    )
    admin_users_json = Column(
        Text,
        nullable=True,
        comment="Admin users list (JSON array)",
    )
    default_role = Column(
        String(32),
        nullable=True,
        default="viewer",
        comment="Default RBAC role for new OAuth2 users",
    )
    gmt_create = Column(DateTime, nullable=True)
    gmt_modify = Column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "config_key": self.config_key,
            "enabled": bool(self.enabled),
            "providers_json": self.providers_json,
            "admin_users_json": self.admin_users_json,
            "default_role": self.default_role or "viewer",
        }


class OAuth2ConfigDao(BaseDao[OAuth2ConfigEntity, Any, Any]):
    """DAO for OAuth2 configuration."""

    def get_by_key(self, config_key: str = "global") -> Optional[OAuth2ConfigEntity]:
        """Get OAuth2 config by key."""
        with self.session() as session:
            return (
                session.query(OAuth2ConfigEntity)
                .filter(OAuth2ConfigEntity.config_key == config_key)
                .first()
            )

    @staticmethod
    def _is_masked_secret(secret: str) -> bool:
        """Check if a secret is masked (e.g., 'abcd****')."""
        return bool(secret and "****" in secret)

    def _merge_secrets(
        self,
        new_providers: List[Dict[str, Any]],
        old_providers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge new providers with old, preserving secrets when new values are masked.

        If new provider's client_secret is masked (e.g., 'abcd****'),
        use the corresponding old provider's secret (if provider id matches).
        """
        if not old_providers:
            return new_providers

        # Build lookup for old providers by id
        old_by_id = {p.get("id", ""): p for p in old_providers if p.get("id")}

        merged = []
        for new_p in new_providers:
            pid = new_p.get("id", "")
            new_secret = new_p.get("client_secret", "")

            # If secret is masked and we have old provider with same id
            if self._is_masked_secret(new_secret) and pid in old_by_id:
                old_p = old_by_id[pid]
                old_secret = old_p.get("client_secret", "")

                # Make a copy and replace masked secret with original
                merged_p = dict(new_p)
                merged_p["client_secret"] = old_secret
                merged.append(merged_p)
            else:
                # Secret is not masked (new value) or no old provider
                merged.append(new_p)

        return merged

    def save_or_update(
        self,
        enabled: bool,
        providers: List[Dict[str, Any]],
        admin_users: List[str],
        default_role: str = "viewer",
        config_key: str = "global",
    ) -> OAuth2ConfigEntity:
        """Save or update OAuth2 config (stored in plain text, mask on display)."""
        from datetime import datetime

        with self.session() as session:
            entity = (
                session.query(OAuth2ConfigEntity)
                .filter(OAuth2ConfigEntity.config_key == config_key)
                .first()
            )

            # If entity exists, merge secrets to avoid overwriting with masked values
            if entity and entity.providers_json:
                try:
                    old_providers = json.loads(entity.providers_json)
                    providers = self._merge_secrets(providers, old_providers)
                except json.JSONDecodeError:
                    pass

            # Store providers as plain JSON (client_secret included, unmasked)
            providers_json = json.dumps(providers, ensure_ascii=False)
            admin_users_json = json.dumps(admin_users, ensure_ascii=False)

            if entity:
                entity.enabled = 1 if enabled else 0
                entity.providers_json = providers_json
                entity.admin_users_json = admin_users_json
                entity.default_role = default_role
                entity.gmt_modify = datetime.utcnow()
            else:
                entity = OAuth2ConfigEntity(
                    config_key=config_key,
                    enabled=1 if enabled else 0,
                    providers_json=providers_json,
                    admin_users_json=admin_users_json,
                    default_role=default_role,
                    gmt_create=datetime.utcnow(),
                    gmt_modify=datetime.utcnow(),
                )
                session.add(entity)

            session.commit()
            session.refresh(entity)
            return entity

    def _mask_providers_for_display(
        self, providers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Mask sensitive fields (client_secret) for display purposes.

        This returns a copy with client_secret hidden (showing only first 4 chars).
        The actual secret remains in the database.
        """
        if not providers:
            return []

        masked = json.loads(json.dumps(providers))
        for provider in masked:
            secret = provider.get("client_secret", "")
            if secret and len(secret) > 4:
                # Show first 4 chars, mask the rest
                provider["client_secret"] = secret[:4] + "****"
            elif secret:
                provider["client_secret"] = "****"
        return masked

    def get_config(
        self, config_key: str = "global", mask_secrets: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get OAuth2 config from database.

        Args:
            config_key: Configuration key (default: global)
            mask_secrets: If True, mask client_secret in providers for display
        """
        with self.session() as session:
            entity = (
                session.query(OAuth2ConfigEntity)
                .filter(OAuth2ConfigEntity.config_key == config_key)
                .first()
            )
            if not entity:
                return None

            # Read ORM attributes before the session closes to avoid
            # detached-instance access during JSON conversion.
            enabled = bool(entity.enabled)
            admin_users_json = entity.admin_users_json or "[]"
            providers_json = entity.providers_json or "[]"
            default_role = entity.default_role or "viewer"

        try:
            admin_users = json.loads(admin_users_json) if admin_users_json else []
        except json.JSONDecodeError:
            admin_users = []

        try:
            providers = json.loads(providers_json)
        except json.JSONDecodeError:
            providers = []

        # Mask secrets if requested (for display purposes)
        if mask_secrets:
            providers = self._mask_providers_for_display(providers)

        return {
            "enabled": enabled,
            "providers": providers,
            "admin_users": admin_users,
            "default_role": default_role,
        }

    def get_config_with_secrets(
        self, config_key: str = "global"
    ) -> Optional[Dict[str, Any]]:
        """Get OAuth2 config with actual secrets (for internal use only)."""
        return self.get_config(config_key, mask_secrets=False)


class OAuth2DbStorage:
    """High-level storage interface for OAuth2 config."""

    def __init__(self):
        self._dao: Optional[OAuth2ConfigDao] = None

    @property
    def dao(self) -> OAuth2ConfigDao:
        if self._dao is None:
            self._dao = OAuth2ConfigDao()
        return self._dao

    def load(self, mask_secrets: bool = True) -> Optional[Dict[str, Any]]:
        """Load OAuth2 config from database."""
        return self.dao.get_config("global", mask_secrets=mask_secrets)

    def load_with_secrets(self) -> Optional[Dict[str, Any]]:
        """Load OAuth2 config with actual secrets (for internal use only)."""
        return self.dao.get_config_with_secrets("global")

    def save(
        self,
        enabled: bool,
        providers: List[Dict],
        admin_users: List[str],
        default_role: str = "viewer",
    ) -> bool:
        """Save OAuth2 config to database."""
        try:
            self.dao.save_or_update(
                enabled, providers, admin_users, default_role, "global"
            )
            return True
        except Exception as e:
            logger.exception(f"Failed to save OAuth2 config: {e}")
            raise  # Re-raise to let caller handle the error


# Singleton instance
_oauth2_storage: Optional[OAuth2DbStorage] = None


def get_oauth2_db_storage() -> OAuth2DbStorage:
    """Get OAuth2 database storage singleton."""
    global _oauth2_storage
    if _oauth2_storage is None:
        _oauth2_storage = OAuth2DbStorage()
    return _oauth2_storage
