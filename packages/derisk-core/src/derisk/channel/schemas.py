"""Channel schemas for specific platforms.

This module defines the Pydantic schemas for DingTalk and Feishu channel configurations.
Additional platforms (WeChat, QQ) can be added following the same pattern.
"""

from typing import Literal, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field


class DingTalkConfig(BaseModel):
    """DingTalk channel configuration."""

    model_config = ConfigDict(title="DingTalkConfig")

    app_id: str = Field(
        ...,
        description="DingTalk App ID (AppKey)",
    )
    app_secret: str = Field(
        ...,
        description="DingTalk App Secret (AppSecret)",
    )
    webhook_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for outgoing messages",
    )
    token: Optional[str] = Field(
        default=None,
        description="Token for signature validation",
    )
    aes_key: Optional[str] = Field(
        default=None,
        description="AES key for message encryption/decryption",
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="DingTalk Agent ID",
    )
    callback_url: Optional[str] = Field(
        default=None,
        description="Callback URL for receiving DingTalk events",
    )


class FeishuConfig(BaseModel):
    """Feishu channel configuration."""

    model_config = ConfigDict(title="FeishuConfig")

    app_id: str = Field(
        ...,
        description="Feishu App ID",
    )
    app_secret: str = Field(
        ...,
        description="Feishu App Secret",
    )
    encrypt_key: Optional[str] = Field(
        default=None,
        description="Encrypt key for message encryption/decryption",
    )
    verification_token: Optional[str] = Field(
        default=None,
        description="Verification token for event callback",
    )
    domain: Literal["feishu", "lark"] = Field(
        default="feishu",
        description="Domain type (feishu for China, lark for international)",
    )
    callback_url: Optional[str] = Field(
        default=None,
        description="Callback URL for receiving Feishu events",
    )


# Future: WeChat and QQ configurations can be added here
# class WeChatConfig(BaseModel):
#     """WeChat channel configuration."""
#     ...
#
#
# class QQConfig(BaseModel):
#     """QQ channel configuration."""
#     ...