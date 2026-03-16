"""OAuth2 flow implementation - authorization, token exchange, userinfo."""

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# GitHub OAuth2 endpoints
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USERINFO_URL = "https://api.github.com/user"


class OAuth2Service:
    """OAuth2 flow service - handles login redirect, callback, userinfo fetch."""

    def __init__(self):
        pass

    def get_authorization_url(
        self,
        provider_id: str,
        provider_config: Dict[str, Any],
        redirect_uri: str,
        state: str,
    ) -> Optional[str]:
        """Build OAuth2 authorization URL."""
        if provider_config.get("type") == "github":
            client_id = provider_config.get("client_id", "")
            scope = provider_config.get("scope", "read:user user:email")
            if not client_id:
                return None
            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
            }
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            return f"{GITHUB_AUTH_URL}?{qs}"
        elif provider_config.get("type") == "custom":
            auth_url = provider_config.get("authorization_url", "")
            client_id = provider_config.get("client_id", "")
            scope = provider_config.get("scope", "")
            if not auth_url or not client_id:
                return None
            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "response_type": "code",
            }
            if scope:
                params["scope"] = scope
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            sep = "&" if "?" in auth_url else "?"
            return f"{auth_url}{sep}{qs}"
        return None

    async def exchange_code_for_token(
        self,
        provider_id: str,
        provider_config: Dict[str, Any],
        redirect_uri: str,
        code: str,
    ) -> Optional[str]:
        """Exchange authorization code for access token."""
        if provider_config.get("type") == "github":
            token_url = GITHUB_TOKEN_URL
            data = {
                "client_id": provider_config.get("client_id", ""),
                "client_secret": provider_config.get("client_secret", ""),
                "code": code,
                "redirect_uri": redirect_uri,
            }
            headers = {"Accept": "application/json"}
        elif provider_config.get("type") == "custom":
            token_url = provider_config.get("token_url", "")
            if not token_url:
                return None
            data = {
                "client_id": provider_config.get("client_id", ""),
                "client_secret": provider_config.get("client_secret", ""),
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
            headers = {"Accept": "application/json"}
        else:
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(token_url, data=data, headers=headers)
                resp.raise_for_status()
                result = resp.json()
                return result.get("access_token")
        except Exception as e:
            logger.exception(f"Token exchange failed: {e}")
            return None

    async def fetch_userinfo(
        self, provider_id: str, provider_config: Dict[str, Any], access_token: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch user info from OAuth provider."""
        if provider_config.get("type") == "github":
            userinfo_url = GITHUB_USERINFO_URL
            headers = {"Authorization": f"Bearer {access_token}"}
        elif provider_config.get("type") == "custom":
            userinfo_url = provider_config.get("userinfo_url", "")
            if not userinfo_url:
                return None
            headers = {"Authorization": f"Bearer {access_token}"}
        else:
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(userinfo_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                # Normalize to common format
                return {
                    "id": str(data.get("id", "")),
                    "login": data.get("login", ""),
                    "username": data.get("username", data.get("login", "")),
                    "name": data.get("name", ""),
                    "email": data.get("email", ""),
                    "avatar_url": data.get("avatar_url", ""),
                    "avatar": data.get("avatar", data.get("avatar_url", "")),
                    "picture": data.get("picture", ""),
                }
        except Exception as e:
            logger.exception(f"Userinfo fetch failed: {e}")
            return None
