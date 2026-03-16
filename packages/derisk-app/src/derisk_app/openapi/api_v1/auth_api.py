"""OAuth2 authentication API - login, callback, me, logout."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from derisk_app.auth.oauth import OAuth2Service
from derisk_app.auth.session import SessionManager, create_session_token, verify_session_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

oauth_service = OAuth2Service()
session_manager = SessionManager()


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


def _resolve_role(user_info: Dict[str, Any]) -> str:
    """Determine role for a new user based on admin_users config."""
    oauth_config = _get_oauth_config()
    if not oauth_config:
        return "normal"
    admin_users = oauth_config.get("admin_users", [])
    login = user_info.get("login") or user_info.get("username") or ""
    return "admin" if login and login in admin_users else "normal"


@router.get("/oauth/status")
async def oauth_status():
    """Return whether OAuth2 is enabled and available providers (for frontend)."""
    oauth_config = _get_oauth_config()
    if not oauth_config:
        return JSONResponse(content={
            "enabled": False,
            "providers": [],
        })
    providers = oauth_config.get("providers", [])
    # Only include providers with client_id configured
    available = [
        {"id": p["id"], "type": p.get("type", "custom")}
        for p in providers
        if p.get("client_id")
    ]
    return JSONResponse(content={
        "enabled": True,
        "providers": available,
    })


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
        return RedirectResponse(url="/login?error=token_exchange_failed", status_code=302)

    user_info = await oauth_service.fetch_userinfo(
        provider_id=provider_id,
        provider_config=provider_config,
        access_token=access_token,
    )
    if not user_info:
        return RedirectResponse(url="/login?error=userinfo_failed", status_code=302)

    oauth_id = str(user_info.get("id", ""))
    role = _resolve_role(user_info)

    from derisk_app.auth.user_service import UserService
    user_service = UserService()
    user = user_service.get_or_create_from_oauth(
        provider_id, oauth_id, user_info, role=role
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
    return response


@router.get("/me")
async def get_current_user(request: Request):
    """Get current logged-in user. Returns 401 if not authenticated."""
    token = (
        request.cookies.get("derisk_session")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
    )
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = verify_session_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return JSONResponse(content={
        "user": user,
        "user_channel": "oauth",
        "user_no": str(user.get("id", "")),
        "nick_name": user.get("name", user.get("fullname", "")),
        "avatar_url": user.get("avatar", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "normal"),
    })


@router.post("/logout")
async def logout(request: Request):
    """Logout - clear session."""
    response = JSONResponse(content={"success": True})
    response.delete_cookie("derisk_session")
    return response
