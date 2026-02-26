"""Channel API endpoints.

This module provides REST API endpoints for channel management.
"""

from functools import cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import (
    ChannelRequest,
    ChannelResponse,
    ChannelTestResponse,
)

router = APIRouter()

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance."""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


@cache
def _parse_api_keys(api_keys: str) -> List[str]:
    """Parse the string api keys to a list.

    Args:
        api_keys: The string api keys.

    Returns:
        List of api keys.
    """
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    request: Request = None,
    service: Service = Depends(get_service),
) -> Optional[str]:
    """Check the api key.

    If the api key is not set, allow all.
    """
    if request.url.path.startswith("/api/v1"):
        return None

    if service.config.api_keys:
        api_keys = _parse_api_keys(service.config.api_keys)
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "message": "",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                },
            )
        return token
    else:
        return None


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get(
    "/channels",
    response_model=Result[List[ChannelResponse]],
    dependencies=[Depends(check_api_key)],
)
async def list_channels(
    include_disabled: bool = Query(
        default=False, description="Include disabled channels"
    ),
    service: Service = Depends(get_service),
) -> Result[List[ChannelResponse]]:
    """List all channels.

    Args:
        include_disabled: Whether to include disabled channels.

    Returns:
        List of channels.
    """
    channels = await service.list_channels(include_disabled)
    return Result.succ(channels)


@router.post(
    "/channels",
    response_model=Result[ChannelResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_channel(
    request: ChannelRequest,
    service: Service = Depends(get_service),
) -> Result[ChannelResponse]:
    """Create a new channel.

    Args:
        request: The channel creation request.

    Returns:
        The created channel.
    """
    # Validate channel type
    valid_types = ["dingtalk", "feishu", "wechat", "qq"]
    if request.channel_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel type: {request.channel_type}. Valid types: {valid_types}",
        )

    channel = await service.create_channel(request)
    return Result.succ(channel)


@router.get(
    "/channels/{channel_id}",
    response_model=Result[ChannelResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_channel(
    channel_id: str,
    service: Service = Depends(get_service),
) -> Result[ChannelResponse]:
    """Get a specific channel by ID.

    Args:
        channel_id: The channel ID.

    Returns:
        The channel details.
    """
    channel = await service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return Result.succ(channel)


@router.put(
    "/channels/{channel_id}",
    response_model=Result[ChannelResponse],
    dependencies=[Depends(check_api_key)],
)
async def update_channel(
    channel_id: str,
    request: ChannelRequest,
    service: Service = Depends(get_service),
) -> Result[ChannelResponse]:
    """Update a channel.

    Args:
        channel_id: The channel ID.
        request: The update request.

    Returns:
        The updated channel.
    """
    try:
        request.id = channel_id  # Ensure ID matches
        channel = await service.update_channel(channel_id, request)
        return Result.succ(channel)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/channels/{channel_id}",
    dependencies=[Depends(check_api_key)],
)
async def delete_channel(
    channel_id: str,
    service: Service = Depends(get_service),
):
    """Delete a channel.

    Args:
        channel_id: The channel ID.
    """
    removed = await service.delete_channel(channel_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return Result.succ(None)


@router.post(
    "/channels/{channel_id}/test",
    response_model=Result[ChannelTestResponse],
    dependencies=[Depends(check_api_key)],
)
async def test_channel(
    channel_id: str,
    service: Service = Depends(get_service),
) -> Result[ChannelTestResponse]:
    """Test the connection to a channel.

    Args:
        channel_id: The channel ID.

    Returns:
        The test result.
    """
    result = await service.test_connection(channel_id)
    return Result.succ(result)


@router.post(
    "/channels/{channel_id}/enable",
    dependencies=[Depends(check_api_key)],
)
async def enable_channel(
    channel_id: str,
    service: Service = Depends(get_service),
):
    """Enable a channel.

    Args:
        channel_id: The channel ID.
    """
    try:
        await service.enable_channel(channel_id)
        return Result.succ({"enabled": True, "channel_id": channel_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/channels/{channel_id}/disable",
    dependencies=[Depends(check_api_key)],
)
async def disable_channel(
    channel_id: str,
    service: Service = Depends(get_service),
):
    """Disable a channel.

    Args:
        channel_id: The channel ID.
    """
    try:
        await service.disable_channel(channel_id)
        return Result.succ({"enabled": False, "channel_id": channel_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Webhook endpoints (placeholder - actual implementation in derisk-ext)
@router.post(
    "/webhook/dingtalk/{channel_id}",
    summary="DingTalk Webhook (Placeholder)",
)
async def dingtalk_webhook(
    channel_id: str,
    request: Request,
    service: Service = Depends(get_service),
):
    """DingTalk webhook endpoint.

    This is a placeholder. The actual implementation should be provided
    by the DingTalk channel handler in derisk-ext.

    Args:
        channel_id: The channel ID.
        request: The incoming webhook request.
    """
    # Check if channel exists
    channel = await service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")

    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel is disabled")

    # Placeholder response
    # In actual implementation, this would:
    # 1. Validate signature from DingTalk
    # 2. Parse the message
    # 3. Process through the channel handler
    # 4. Return appropriate response

    return {
        "status": "received",
        "channel_id": channel_id,
        "message": "Webhook received (placeholder - implement in derisk-ext)",
    }


@router.post(
    "/webhook/feishu/{channel_id}",
    summary="Feishu Webhook (Placeholder)",
)
async def feishu_webhook(
    channel_id: str,
    request: Request,
    service: Service = Depends(get_service),
):
    """Feishu webhook endpoint.

    This is a placeholder. The actual implementation should be provided
    by the Feishu channel handler in derisk-ext.

    Args:
        channel_id: The channel ID.
        request: The incoming webhook request.
    """
    # Check if channel exists
    channel = await service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")

    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel is disabled")

    # Placeholder response
    return {
        "status": "received",
        "channel_id": channel_id,
        "message": "Webhook received (placeholder - implement in derisk-ext)",
    }


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints.

    Args:
        system_app: The system application instance.
        config: The service configuration.
    """
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app