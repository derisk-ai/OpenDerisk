"""PermissionMode — agent-level permission behavior switch.

See spec §9.2. Stored on the agent, passed to PermissionGate.check().
"""
from __future__ import annotations
from enum import Enum


class PermissionMode(str, Enum):
    DEFAULT = "default"   # per-tool rule check, ask if rule says ask
    PLAN = "plan"         # deny all side-effecting tools, allow read-only
    AUTO = "auto"         # allow all (YOLO)
    BYPASS = "bypass"     # skip PermissionGate entirely (system ops only)
