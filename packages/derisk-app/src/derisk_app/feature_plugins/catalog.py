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
    # Internal: list of sub-plugins to enable/disable together
    _internal_plugins: Optional[List[str]] = None


_MANIFESTS: Dict[str, FeaturePluginManifest] = {
    "access_control": FeaturePluginManifest(
        id="access_control",
        title="权限控制系统",
        description=(
            "完整的 RBAC 权限管理系统，包含用户权限组和角色权限管理。"
            "启用后需配合 OAuth2 登录使用。"
        ),
        category="access_control",
        requires_restart=True,
        settings_schema={
            "type": "object",
            "properties": {
                "default_policy": {
                    "type": "string",
                    "enum": ["allow_authenticated", "deny_all"],
                    "default": "allow_authenticated",
                    "description": "默认策略：allow_authenticated=已认证用户允许访问，deny_all=默认拒绝",
                },
                "superadmin_users": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "绕过所有权限检查的用户登录名列表",
                },
            },
        },
        suggest_oauth2_admin=True,
        _internal_plugins=["user_groups", "permissions"],
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
    """Merge manifests with persisted enabled/settings for API responses.

    For unified plugins (like access_control), the enabled state is computed
    from its sub-plugins (user_groups and permissions).
    """
    out: List[Dict[str, Any]] = []
    for m in list_manifests():
        # For unified plugins, compute enabled state from sub-plugins
        if m._internal_plugins:
            # Check if any sub-plugin is enabled
            any_enabled = any(
                _entry_enabled_and_settings(feature_plugins.get(sub_id))[0]
                for sub_id in m._internal_plugins
            )
            # Merge settings from all sub-plugins
            merged_settings: Dict[str, Any] = {}
            for sub_id in m._internal_plugins:
                _, sub_settings = _entry_enabled_and_settings(feature_plugins.get(sub_id))
                merged_settings.update(sub_settings)
            en, st = any_enabled, merged_settings
        else:
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