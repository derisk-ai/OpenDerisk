"""User groups plugin (RBAC-style grouping for logged-in users).

Import ``derisk_app.feature_plugins.user_groups.api`` for the FastAPI router;
this package ``__init__`` stays lightweight so ORM models can load without
registering routes (e.g. during DB migrations).
"""
