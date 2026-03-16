"""Session management for OAuth2 - JWT-based session tokens."""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Default secret for JWT signing (override via env OAUTH2_SESSION_SECRET)
DEFAULT_SECRET = "derisk-oauth2-session-secret-change-in-production"
SESSION_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 days


def _get_secret() -> str:
    return os.environ.get("OAUTH2_SESSION_SECRET", DEFAULT_SECRET)


def _sign(payload: str) -> str:
    """Create HMAC signature for payload."""
    return hmac.new(
        _get_secret().encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def create_session_token(user: Dict[str, Any]) -> str:
    """Create a signed session token for the user."""
    payload = {
        "user": user,
        "exp": int(time.time()) + SESSION_EXPIRE_SECONDS,
        "iat": int(time.time()),
    }
    payload_b64 = _base64_encode(json.dumps(payload, sort_keys=True))
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify session token and return user dict if valid."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        if not hmac.compare_digest(sig, _sign(payload_b64)):
            return None
        payload = json.loads(_base64_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("user")
    except Exception as e:
        logger.debug(f"Session token verification failed: {e}")
        return None


def _base64_encode(s: str) -> str:
    import base64
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def _base64_decode(s: str) -> str:
    import base64
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode()).decode()


class SessionManager:
    """Manages OAuth2 session state (for CSRF protection)."""

    def __init__(self):
        self._states: Dict[str, float] = {}
        self._state_ttl = 600  # 10 minutes

    def create_state(self, provider: str = "") -> str:
        """Create a random state for OAuth CSRF protection. Optionally encode provider."""
        token = secrets.token_urlsafe(32)
        state = f"{provider}:{token}" if provider else token
        self._states[state] = time.time()
        return state

    def verify_state(self, state: str) -> Tuple[bool, str]:
        """Verify and consume state. Returns (valid, provider_id)."""
        if state not in self._states:
            return False, ""
        created = self._states.pop(state)
        if time.time() - created > self._state_ttl:
            return False, ""
        provider = state.split(":", 1)[0] if ":" in state else ""
        return True, provider
