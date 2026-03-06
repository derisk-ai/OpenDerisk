"""Feishu message sender.

This module provides a sender class for sending various types of messages
through the Feishu platform.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from derisk.channel.base import SendMessageResult

from .client import FeishuClient

logger = logging.getLogger(__name__)


class FeishuSender:
    """Message sender for Feishu platform.

    This class provides methods for sending different types of messages
    including text, interactive cards, and media messages.
    """

    def __init__(self, client: FeishuClient):
        """Initialize the sender.

        Args:
            client: The Feishu client instance.
        """
        self._client = client

    async def send_text(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send a text message.

        Args:
            receive_id: The receiver ID (chat_id, open_id, or user_id).
            text: The text content.
            receive_id_type: Type of the receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        return await self._client.send_text_message(
            receive_id=receive_id,
            text=text,
            receive_id_type=receive_id_type,
        )

    async def send_post(
        self,
        receive_id: str,
        title: str,
        content: List[List[Dict[str, Any]]],
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send a post (rich text) message.

        Args:
            receive_id: The receiver ID.
            title: Post title.
            content: Post content segments.
            receive_id_type: Type of the receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        post_content = {"title": title, "content": content}
        return await self._client.send_message(
            receive_id=receive_id,
            content=json.dumps(post_content),
            msg_type="post",
            receive_id_type=receive_id_type,
        )

    async def send_markdown(
        self,
        receive_id: str,
        title: str,
        markdown_content: str,
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send a markdown-style post message.

        This converts markdown to Feishu post format.

        Args:
            receive_id: The receiver ID.
            title: Post title.
            markdown_content: Markdown content.
            receive_id_type: Type of the receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        content = self._markdown_to_post_content(markdown_content)
        return await self.send_post(
            receive_id=receive_id,
            title=title,
            content=content,
            receive_id_type=receive_id_type,
        )

    def _markdown_to_post_content(self, markdown: str) -> List[List[Dict[str, Any]]]:
        """Convert markdown to Feishu post content format.

        This is a simple conversion that handles basic formatting.

        Args:
            markdown: Markdown text.

        Returns:
            Feishu post content structure.
        """
        paragraphs: List[List[Dict[str, Any]]] = []
        lines = markdown.split("\n")

        for line in lines:
            if not line.strip():
                continue

            segments: List[Dict[str, Any]] = []

            if line.startswith("# "):
                segments.append(
                    {
                        "tag": "text",
                        "text": line[2:],
                        "style": ["bold"],
                    }
                )
            elif line.startswith("## "):
                segments.append(
                    {
                        "tag": "text",
                        "text": line[3:],
                        "style": ["bold"],
                    }
                )
            elif line.startswith("- "):
                segments.append(
                    {
                        "tag": "text",
                        "text": "• " + line[2:],
                    }
                )
            elif line.startswith("* ") and line.endswith("*"):
                segments.append(
                    {
                        "tag": "text",
                        "text": line[2:-1],
                        "style": ["italic"],
                    }
                )
            elif line.startswith("**") and line.endswith("**"):
                segments.append(
                    {
                        "tag": "text",
                        "text": line[2:-2],
                        "style": ["bold"],
                    }
                )
            else:
                segments.append({"tag": "text", "text": line})

            paragraphs.append(segments)

        return paragraphs

    async def send_interactive_card(
        self,
        receive_id: str,
        title: str,
        content: str,
        receive_id_type: str = "chat_id",
        buttons: Optional[List[Dict[str, Any]]] = None,
    ) -> SendMessageResult:
        """Send an interactive card message.

        Args:
            receive_id: The receiver ID.
            title: Card title.
            content: Card content (markdown supported in template).
            receive_id_type: Type of the receive_id.
            buttons: Optional list of buttons.

        Returns:
            SendMessageResult indicating success or failure.
        """
        card: Dict[str, Any] = {
            "type": "template",
            "data": {
                "template_id": "AAqk3gJ",
                "template_variable": {
                    "title": title,
                    "content": content,
                },
            },
        }

        if buttons:
            card = {
                "config": {"wide_screen_mode": True},
                "elements": [
                    {"tag": "div", "text": {"content": content, "tag": "lark_md"}},
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "content": btn.get("text", ""),
                                    "tag": "plain_text",
                                },
                                "type": btn.get("type", "primary"),
                                "value": btn.get("value", {}),
                            }
                            for btn in buttons
                        ],
                    },
                ],
            }

        return await self._client.send_message(
            receive_id=receive_id,
            content=json.dumps(card),
            msg_type="interactive",
            receive_id_type=receive_id_type,
        )

    async def send_image(
        self,
        receive_id: str,
        image_key: str,
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send an image message.

        Args:
            receive_id: The receiver ID.
            image_key: The image key from Feishu.
            receive_id_type: Type of the receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        content = json.dumps({"image_key": image_key})
        return await self._client.send_message(
            receive_id=receive_id,
            content=content,
            msg_type="image",
            receive_id_type=receive_id_type,
        )

    async def send_file(
        self,
        receive_id: str,
        file_key: str,
        file_name: Optional[str] = None,
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send a file message.

        Args:
            receive_id: The receiver ID.
            file_key: The file key from Feishu.
            file_name: Optional file name.
            receive_id_type: Type of the receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        content: Dict[str, Any] = {"file_key": file_key}
        if file_name:
            content["file_name"] = file_name

        return await self._client.send_message(
            receive_id=receive_id,
            content=json.dumps(content),
            msg_type="file",
            receive_id_type=receive_id_type,
        )

    async def reply_text(
        self,
        message_id: str,
        text: str,
    ) -> SendMessageResult:
        """Reply to a message with text.

        Args:
            message_id: The message ID to reply to.
            text: The reply text.

        Returns:
            SendMessageResult indicating success or failure.
        """
        content = json.dumps({"text": text})
        return await self._client.reply_message(
            message_id=message_id,
            content=content,
            msg_type="text",
        )

    async def send_text_with_mentions(
        self,
        receive_id: str,
        text: str,
        mention_ids: List[str],
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send a text message with user mentions.

        Args:
            receive_id: The receiver ID.
            text: The text content with placeholders for mentions.
            mention_ids: List of user IDs to mention.
            receive_id_type: Type of the receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        content_parts: List[Dict[str, Any]] = []

        mentions: List[Dict[str, Any]] = []

        for i, user_id in enumerate(mention_ids):
            placeholder = f'<at user_id="{user_id}"></at>'
            mentions.append(
                {
                    "key": placeholder,
                    "id": {"open_id": user_id},
                    "name": "",
                }
            )
            content_parts.append({"tag": "at", "user_id": user_id})
            content_parts.append({"tag": "text", "text": " "})

        content_parts.append({"tag": "text", "text": text})

        post_content = {
            "title": "",
            "content": [content_parts],
        }

        return await self._client.send_message(
            receive_id=receive_id,
            content=json.dumps(post_content),
            msg_type="post",
            receive_id_type=receive_id_type,
        )
