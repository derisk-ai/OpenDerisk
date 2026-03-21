"""Catalog merge tests."""

from derisk_app.feature_plugins.catalog import merge_catalog_with_state, is_known_plugin


def test_merge_catalog_includes_user_groups():
    items = merge_catalog_with_state({})
    ids = {x["id"] for x in items}
    assert "user_groups" in ids
    ug = next(x for x in items if x["id"] == "user_groups")
    assert ug["enabled"] is False
    assert ug["settings"] == {}


def test_merge_catalog_respects_persisted_state():
    items = merge_catalog_with_state(
        {"user_groups": {"enabled": True, "settings": {"k": 1}}}
    )
    ug = next(x for x in items if x["id"] == "user_groups")
    assert ug["enabled"] is True
    assert ug["settings"] == {"k": 1}


def test_is_known_plugin():
    assert is_known_plugin("user_groups") is True
    assert is_known_plugin("nope") is False
