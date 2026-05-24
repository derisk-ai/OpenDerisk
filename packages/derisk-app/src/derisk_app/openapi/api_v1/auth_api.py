"""OAuth2 and local authentication API - login, callback, register, me, logout."""

import base64
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from derisk_app.auth.oauth import OAuth2Service
from derisk_app.auth.session import (
    SessionManager,
    create_session_token,
    verify_session_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

oauth_service = OAuth2Service()
session_manager = SessionManager()


class LocalLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)


class LocalRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    email: Optional[str] = ""
    fullname: Optional[str] = ""


def _get_config():
    """Get app config with OAuth2 settings."""
    try:
        from derisk_core.config import ConfigManager

        config = ConfigManager.get()
        return config
    except Exception:
        return None


def _get_oauth_config() -> Optional[Dict[str, Any]]:
    """Get OAuth2 config if enabled."""
    config = _get_config()
    if not config or not hasattr(config, "oauth2") or not config.oauth2:
        return None
    oauth2 = config.oauth2
    if not oauth2.enabled:
        return None
    return oauth2.model_dump(mode="json")


def _get_provider_config(provider_id: str) -> Optional[Dict[str, Any]]:
    """Get provider config by id."""
    oauth_config = _get_oauth_config()
    if not oauth_config:
        return None
    providers = oauth_config.get("providers", [])
    for p in providers:
        if p.get("id") == provider_id:
            return p
    return None


def _resolve_role(user_info: Dict[str, Any]) -> tuple[str, str]:
    """Determine legacy role and default RBAC role for a new user.

    Returns:
        tuple: (legacy_role, rbac_default_role) where legacy_role is "admin" or "normal",
               and rbac_default_role is the configured default role for RBAC assignment
    """
    oauth_config = _get_oauth_config()
    if not oauth_config:
        return "normal", "normal_user"
    admin_users = oauth_config.get("admin_users", [])
    login = user_info.get("login") or user_info.get("username") or ""
    is_admin = login and login in admin_users
    legacy_role = "admin" if is_admin else "normal"
    # Use configured default_role, fallback to "normal_user"
    rbac_default_role = (
        oauth_config.get("default_role", "normal_user") if not is_admin else "admin"
    )
    return legacy_role, rbac_default_role


def _is_auth_required() -> bool:
    """Check if authentication is required (OAuth2 enabled or access_control plugin on)."""
    # Check if OAuth2 is explicitly enabled
    oauth_config = _get_oauth_config()
    if oauth_config:
        return True
    # Check if access_control / permissions plugin is enabled
    try:
        from derisk_core.config import ConfigManager
        cfg = ConfigManager.get()
        fp = getattr(cfg, "feature_plugins", None) or {}
        for key in ("access_control", "permissions"):
            entry = fp.get(key)
            if entry is None:
                continue
            enabled = entry.enabled if hasattr(entry, "enabled") else (
                entry.get("enabled") if isinstance(entry, dict) else False
            )
            if enabled:
                return True
    except Exception:
        pass
    return False


def _require_approval_for_registration() -> bool:
    """Check if new user registration requires admin approval."""
    oauth_config = _get_oauth_config()
    if oauth_config:
        return oauth_config.get("require_approval", False)
    return False


@router.get("/oauth/status")
async def oauth_status():
    """Return whether OAuth2 is enabled and available providers (for frontend).

    When OAuth2 is configured (enabled=true) or the access_control plugin is on,
    authentication is required. The 'local' provider (username/password) is always
    included as a built-in login option in that case.

    When neither is configured, returns enabled=false so the frontend uses mock user
    (backward compatible — no login required for unconfigured systems).
    """
    if not _is_auth_required():
        return JSONResponse(
            content={
                "enabled": False,
                "providers": [],
            }
        )

    # Auth is required — collect available providers
    oauth_config = _get_oauth_config()
    available = []
    if oauth_config:
        providers = oauth_config.get("providers", [])
        available = [
            {"id": p["id"], "type": p.get("type", "custom")}
            for p in providers
            if p.get("client_id")
        ]

    # Always include 'local' provider when auth is required
    has_local = any(p["id"] == "local" for p in available)
    if not has_local:
        available.insert(0, {"id": "local", "type": "local"})

    return JSONResponse(
        content={
            "enabled": True,
            "providers": available,
        }
    )


@router.get("/oauth/login")
async def oauth_login(
    request: Request,
    provider: str = Query(..., description="Provider id (e.g. github)"),
):
    """Redirect to OAuth provider authorization page."""
    provider_config = _get_provider_config(provider)
    if not provider_config:
        raise HTTPException(
            status_code=400, detail="OAuth2 not configured or provider not found"
        )

    # Build redirect_uri (callback URL)
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/v1/auth/oauth/callback"
    logger.info(f"[OAuth2 login] redirect_uri={redirect_uri}")

    state = session_manager.create_state(provider=provider)

    auth_url = oauth_service.get_authorization_url(
        provider_id=provider,
        provider_config=provider_config,
        redirect_uri=redirect_uri,
        state=state,
    )
    if not auth_url:
        raise HTTPException(status_code=400, detail="Failed to build authorization URL")

    return RedirectResponse(url=auth_url)


@router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
):
    """Handle OAuth callback - exchange code for token, create session, redirect."""
    if not code or not state:
        return RedirectResponse(url="/login?error=missing_params", status_code=302)

    valid, provider_id = session_manager.verify_state(state)
    if not valid:
        return RedirectResponse(url="/login?error=invalid_state", status_code=302)

    if not provider_id:
        oauth_config = _get_oauth_config()
        if not oauth_config or not oauth_config.get("providers"):
            return RedirectResponse(url="/login?error=no_provider", status_code=302)
        provider_id = oauth_config["providers"][0]["id"]

    provider_config = _get_provider_config(provider_id)
    if not provider_config:
        return RedirectResponse(url="/login?error=invalid_provider", status_code=302)

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/v1/auth/oauth/callback"

    access_token = await oauth_service.exchange_code_for_token(
        provider_id=provider_id,
        provider_config=provider_config,
        redirect_uri=redirect_uri,
        code=code,
    )
    if not access_token:
        return RedirectResponse(
            url="/login?error=token_exchange_failed", status_code=302
        )

    user_info = await oauth_service.fetch_userinfo(
        provider_id=provider_id,
        provider_config=provider_config,
        access_token=access_token,
    )
    if not user_info:
        return RedirectResponse(url="/login?error=userinfo_failed", status_code=302)

    oauth_id = str(user_info.get("id", ""))
    legacy_role, rbac_default_role = _resolve_role(user_info)

    from derisk_app.auth.user_service import UserService

    user_service = UserService()
    user = user_service.get_or_create_from_oauth(
        provider_id,
        oauth_id,
        user_info,
        role=legacy_role,
        rbac_default_role=rbac_default_role,
    )
    if not user:
        return RedirectResponse(url="/login?error=user_create_failed", status_code=302)

    # Check if user is disabled
    if not user.get("is_active", 1):
        return RedirectResponse(url="/login?error=user_disabled", status_code=302)

    token = create_session_token(user)

    # Redirect to frontend - token in fragment so it's not sent to server
    base = str(request.base_url).rstrip("/")
    redirect_to = f"{base}/auth/callback/#token={token}"
    response = RedirectResponse(url=redirect_to, status_code=302)
    # Also set cookie for same-origin requests
    response.set_cookie(
        key="derisk_session",
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    # Log cookie details for debugging
    host = request.headers.get("host", "")
    logger.info(f"[local_login] Cookie set: derisk_session, host={host}, scheme={request.url.scheme}, secure={request.url.scheme == 'https'}")
    return response


@router.get("/me")
async def get_current_user(request: Request):
    """Get current logged-in user. Returns 401 if not authenticated."""
    token = request.cookies.get("derisk_session") or request.headers.get(
        "Authorization", ""
    ).replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = verify_session_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return JSONResponse(
        content={
            "user": user,
            "user_channel": "oauth",
            "user_no": str(user.get("id", "")),
            "nick_name": user.get("name", user.get("fullname", "")),
            "avatar_url": user.get("avatar", ""),
            "email": user.get("email", ""),
            "role": user.get("role", "normal"),
        }
    )


@router.post("/logout")
async def logout(request: Request):
    """Logout - clear session."""
    response = JSONResponse(content={"success": True})
    response.delete_cookie("derisk_session")
    return response


def _decode_password(raw: str) -> str:
    """Decode base64-encoded password from frontend. Falls back to raw if not valid base64."""
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        # Sanity check: base64 of an ASCII string re-encodes to the same thing
        if base64.b64encode(decoded.encode("utf-8")).decode("utf-8") == raw:
            return decoded
    except Exception:
        pass
    return raw


@router.post("/local/login")
async def local_login(request: Request, body: LocalLoginRequest):
    """Login with local username/password (password is base64-encoded by frontend)."""
    from derisk_app.auth.user_service import UserService

    password = _decode_password(body.password)
    user_service = UserService()
    user = user_service.verify_local_user(body.username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.get("is_active", 1):
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_session_token(user)
    logger.info(f"[local_login] Login successful for user: {body.username}, token created")

    response = JSONResponse(
        content={
            "success": True,
            "user": user,
            "user_channel": "local",
            "user_no": str(user.get("id", "")),
            "nick_name": user.get("name", user.get("fullname", "")),
            "avatar_url": user.get("avatar", ""),
            "email": user.get("email", ""),
            "role": user.get("role", "normal"),
        }
    )
    response.set_cookie(
        key="derisk_session",
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    # Log cookie details for debugging
    host = request.headers.get("host", "")
    logger.info(f"[local_login] Cookie set: derisk_session, host={host}, scheme={request.url.scheme}, secure={request.url.scheme == 'https'}")
    return response


@router.post("/local/register")
async def local_register(request: Request, body: LocalRegisterRequest):
    """Register a new local user (password is base64-encoded by frontend).

    If require_approval is enabled in OAuth config:
    - User is created with is_active=0 (disabled)
    - A permission request for account_activation is created
    - User must wait for admin approval before logging in
    """
    from derisk_app.auth.user_service import UserService

    password = _decode_password(body.password)
    user_service = UserService()

    # Determine default RBAC role for new local users
    oauth_config = _get_oauth_config()
    rbac_default_role = "normal_user"
    require_approval = False
    if oauth_config:
        rbac_default_role = oauth_config.get("default_role", "normal_user")
        require_approval = oauth_config.get("require_approval", False)

    # Create user (with is_active=0 if approval required)
    user = user_service.create_local_user(
        username=body.username,
        password=password,
        email=body.email or "",
        fullname=body.fullname or body.username,
        rbac_default_role=rbac_default_role,
    )
    if not user:
        raise HTTPException(
            status_code=400, detail="Username already exists or registration failed"
        )

    # If approval required, disable account and create activation request
    if require_approval:
        # Disable account
        user_service.update_user(user["id"], is_active=0)
        user["is_active"] = 0

        # Create account activation request
        try:
            from derisk_app.feature_plugins.permissions.dao import PermissionDao
            permission_dao = PermissionDao()
            permission_dao.create_permission_request(
                user_id=user["id"],
                request_type="account_activation",
                reason=f"New user registration: {body.username}",
            )
            logger.info(f"Created activation request for new user {user['id']} ({body.username})")
        except Exception as e:
            logger.warning(f"Failed to create activation request: {e}")

        # Return success but indicate approval pending
        return JSONResponse(
            content={
                "success": True,
                "user": user,
                "requires_approval": True,
                "message": "Registration successful. Your account is pending admin approval.",
            }
        )

    # Auto-login after registration (when approval not required)
    token = create_session_token(user)

    response = JSONResponse(
        content={
            "success": True,
            "user": user,
            "user_channel": "local",
            "user_no": str(user.get("id", "")),
            "nick_name": user.get("name", user.get("fullname", "")),
            "avatar_url": user.get("avatar", ""),
            "email": user.get("email", ""),
            "role": user.get("role", "normal"),
            "requires_approval": False,
        }
    )
    response.set_cookie(
        key="derisk_session",
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    # Log cookie details for debugging
    host = request.headers.get("host", "")
    logger.info(f"[local_login] Cookie set: derisk_session, host={host}, scheme={request.url.scheme}, secure={request.url.scheme == 'https'}")
    return response
