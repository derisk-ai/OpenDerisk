"""Channel API schemas.

This module defines the Pydantic schemas for the channel API.
"""

from typing import Any, Dict, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_to_dict

from ..config import SERVE_APP_NAME_HUMP


class ChannelRequest(BaseModel):
    """Request schema for creating/updating a channel."""

    model_config = ConfigDict(title=f"ChannelRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the channel (auto-generated if not provided)",
    )
    name: str = Field(
        ...,
        description="Human-readable name for the channel",
    )
    channel_type: str = Field(
        ...,
        description="Channel type (dingtalk, feishu, wechat, qq)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the channel is enabled",
    )
    config: Dict[str, Any] = Field(
        ...,
        description="Platform-specific configuration (e.g., DingTalkConfig, FeishuConfig)",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class ChannelResponse(BaseModel):
    """Response schema for a channel."""

    model_config = ConfigDict(
        title=f"ChannelResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the channel",
    )
    name: str = Field(
        ...,
        description="Human-readable name for the channel",
    )
    channel_type: str = Field(
        ...,
        description="Channel type (dingtalk, feishu, wechat, qq)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the channel is enabled",
    )
    config: Dict[str, Any] = Field(
        ...,
        description="Platform-specific configuration",
    )
    status: str = Field(
        default="disconnected",
        description="Channel connection status (connected, disconnected, error)",
    )
    last_connected: Optional[str] = Field(
        default=None,
        description="Last successful connection time",
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message if any",
    )
    gmt_created: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )
    gmt_modified: Optional[str] = Field(
        default=None,
        description="Record update time",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class ChannelTestResponse(BaseModel):
    """Response schema for testing a channel connection."""

    model_config = ConfigDict(
        title=f"ChannelTestResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    success: bool = Field(
        ...,
        description="Whether the connection test was successful",
    )
    message: str = Field(
        ...,
        description="Result message",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional details about the test",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)