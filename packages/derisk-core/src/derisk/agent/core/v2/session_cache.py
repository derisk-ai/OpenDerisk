"""SessionPermissionCache — per-agent, in-memory allow_session cache.

Keyed by (tool_name, input_hash). allow_once is not cached (caller just
proceeds). deny revokes any prior allow_session for the same key.

This is the spec §9.3 step-2 session cache. Survives across steps within
a single agent run; cleared on agent restart.
"""
from __future__ import annotations
import hashlib
import json
from typing import Dict


def hash_tool_input(input_: dict) -> str:
    """Stable SHA256 hex of the JSON-serialized input (sorted keys)."""
    payload = json.dumps(input_, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SessionPermissionCache:
    def __init__(self):
        self._allowed: Dict[str, set] = {}  # tool_name -> set of input_hashes

    def is_allowed(self, tool_name: str, input_hash: str) -> bool:
        return input_hash in self._allowed.get(tool_name, set())

    def allow_session(self, tool_name: str, input_hash: str) -> None:
        self._allowed.setdefault(tool_name, set()).add(input_hash)

    def allow_once(self, tool_name: str, input_hash: str) -> None:
        # allow_once is not cached — the caller proceeds, next call re-checks
        pass

    def deny(self, tool_name: str, input_hash: str) -> None:
        bucket = self._allowed.get(tool_name)
        if bucket:
            bucket.discard(input_hash)

    def clear(self) -> None:
        self._allowed.clear()
