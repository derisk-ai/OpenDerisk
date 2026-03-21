"""Register routers for enabled builtin feature plugins at process startup."""

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_enabled_feature_plugin_routers(app: FastAPI) -> None:
    """Conditionally mount plugin HTTP routes (requires restart after toggling plugins)."""
    try:
        from derisk_core.config import ConfigManager, FeaturePluginEntry

        cfg = ConfigManager.get()
    except Exception as e:
        logger.warning("Feature plugins: skip router registration (config unavailable): %s", e)
        return

    raw = getattr(cfg, "feature_plugins", None) or {}

    def _enabled(plugin_id: str) -> bool:
        entry = raw.get(plugin_id)
        if entry is None:
            return False
        if isinstance(entry, FeaturePluginEntry):
            return bool(entry.enabled)
        if isinstance(entry, dict):
            return bool(entry.get("enabled"))
        return False

    if _enabled("user_groups"):
        from derisk_app.feature_plugins.user_groups.api import router as user_groups_router

        app.include_router(user_groups_router, prefix="/api/v1")
        logger.info("Feature plugin mounted: user_groups at /api/v1/user-groups")
