"""Derisk configuration storage modules."""

from .oauth2_db_storage import OAuth2ConfigDao, OAuth2ConfigEntity, get_oauth2_db_storage

__all__ = [
    "OAuth2ConfigDao",
    "OAuth2ConfigEntity",
    "get_oauth2_db_storage",
]
