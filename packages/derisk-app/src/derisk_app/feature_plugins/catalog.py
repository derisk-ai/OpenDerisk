"""Code-defined catalog for builtin feature plugins (metadata + JSON Schema hints)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


@dataclass(frozen=True)
class FeaturePluginManifest:
    """Static manifest shipped with the product; not stored in derisk.json."""

    id: str
    title: str
    description: str
    category: str
    requires_restart: bool = True
    # Optional JSON Schema object for plugin-specific settings (UI forms).
    settings_schema: Optional[Dict[str, Any]] = None
    # When True, recommend OAuth2 + admin_users for write operations (enforced in API when configured).
    suggest_oauth2_admin: bool = True


_MANIFESTS: Dict[str, FeaturePluginManifest] = {
    "user_groups": FeaturePluginManifest(
        id="user_groups",
        title="用户权限组",
        description=(
            "面向登录用户的分组与成员管理（RBAC 数据面）；"
            "后续可基于权限组对 Agent、工具等做访问控制。"
        ),
        category="access_control",
        requires_restart=True,
        settings_schema=None,
        suggest_oauth2_admin=True,
    ),
}


def list_manifests() -> List[FeaturePluginManifest]:
    return list(_MANIFESTS.values())


def get_manifest(plugin_id: str) -> Optional[FeaturePluginManifest]:
    return _MANIFESTS.get(plugin_id)


def is_known_plugin(plugin_id: str) -> bool:
    return plugin_id in _MANIFESTS


def _entry_enabled_and_settings(
    entry: Optional[Union[Dict[str, Any], Any]],
) -> tuple[bool, Dict[str, Any]]:
    """Normalize FeaturePluginEntry, dict, or None."""
    if entry is None:
        return False, {}
    if isinstance(entry, dict):
        return bool(entry.get("enabled")), dict(entry.get("settings") or {})
    enabled = bool(getattr(entry, "enabled", False))
    raw = getattr(entry, "settings", None) or {}
    return enabled, dict(raw) if isinstance(raw, dict) else {}


def merge_catalog_with_state(
    feature_plugins: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Merge manifests with persisted enabled/settings for API responses."""
    out: List[Dict[str, Any]] = []
    for m in list_manifests():
        en, st = _entry_enabled_and_settings(feature_plugins.get(m.id))
        out.append(
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "category": m.category,
                "requires_restart": m.requires_restart,
                "settings_schema": m.settings_schema,
                "suggest_oauth2_admin": m.suggest_oauth2_admin,
                "enabled": en,
                "settings": st,
            }
        )
    return out
