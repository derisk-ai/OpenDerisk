"""DingTalk message sender.

This module provides a sender class for sending various types of messages
through the DingTalk platform.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from derisk.channel.base import SendMessageResult

from .client import DingTalkClient

logger = logging.getLogger(__name__)


class DingTalkSender:
    """Message sender for DingTalk platform.

    This class provides methods for sending different types of messages
    including text, markdown, and actionCard messages.
    """

    def __init__(self, client: DingTalkClient):
        """Initialize the sender.

        Args:
            client: The DingTalk client instance.
        """
        self._client = client

    async def send_text(
        self,
        user_id: str,
        text: str,
        is_group: bool = False,
        conversation_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send a text message.

        Args:
            user_id: The receiver's user ID (or conversation ID for groups).
            text: The text content.
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.

        Returns:
            SendMessageResult indicating success or failure.
        """
        msg = {
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}),
        }

        if is_group and conversation_id:
            return await self._client.send_group_message(
                conversation_id=conversation_id,
                msg=msg,
            )
        else:
            return await self._client.send_private_message(
                user_id=user_id,
                msg=msg,
            )

    async def send_markdown(
        self,
        user_id: str,
        title: str,
        markdown_content: str,
        is_group: bool = False,
        conversation_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send a markdown message.

        Args:
            user_id: The receiver's user ID.
            title: The message title.
            markdown_content: The markdown content.
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.

        Returns:
            SendMessageResult indicating success or failure.
        """
        msg = {
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps(
                {
                    "title": title,
                    "text": markdown_content,
                }
            ),
        }

        if is_group and conversation_id:
            return await self._client.send_group_message(
                conversation_id=conversation_id,
                msg=msg,
            )
        else:
            return await self._client.send_private_message(
                user_id=user_id,
                msg=msg,
            )

    async def send_action_card(
        self,
        user_id: str,
        title: str,
        text: str,
        btns: List[Dict[str, str]],
        is_group: bool = False,
        conversation_id: Optional[str] = None,
        btn_orientation: str = "0",
    ) -> SendMessageResult:
        """Send an actionCard message.

        Args:
            user_id: The receiver's user ID.
            title: The card title.
            text: The card text (markdown supported).
            btns: List of button dictionaries with 'title' and 'actionURL' keys.
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.
            btn_orientation: Button orientation ("0" vertical, "1" horizontal).

        Returns:
            SendMessageResult indicating success or failure.
        """
        msg = {
            "msgKey": "sampleActionCard",
            "msgParam": json.dumps(
                {
                    "title": title,
                    "text": text,
                    "btnOrientation": btn_orientation,
                    "btnJsonList": btns,
                }
            ),
        }

        if is_group and conversation_id:
            return await self._client.send_group_message(
                conversation_id=conversation_id,
                msg=msg,
            )
        else:
            return await self._client.send_private_message(
                user_id=user_id,
                msg=msg,
            )

    async def send_image(
        self,
        user_id: str,
        photo_url: str,
        is_group: bool = False,
        conversation_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send an image message.

        Args:
            user_id: The receiver's user ID.
            photo_url: The image URL.
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.

        Returns:
            SendMessageResult indicating success or failure.
        """
        msg = {
            "msgKey": "sampleImageMsg",
            "msgParam": json.dumps({"photoURL": photo_url}),
        }

        if is_group and conversation_id:
            return await self._client.send_group_message(
                conversation_id=conversation_id,
                msg=msg,
            )
        else:
            return await self._client.send_private_message(
                user_id=user_id,
                msg=msg,
            )

    async def send_link(
        self,
        user_id: str,
        title: str,
        text: str,
        message_url: str,
        pic_url: Optional[str] = None,
        is_group: bool = False,
        conversation_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send a link message.

        Args:
            user_id: The receiver's user ID.
            title: The link title.
            text: The link text.
            message_url: The link URL.
            pic_url: Optional picture URL.
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.

        Returns:
            SendMessageResult indicating success or failure.
        """
        content: Dict[str, Any] = {
            "title": title,
            "text": text,
            "messageUrl": message_url,
        }
        if pic_url:
            content["picUrl"] = pic_url

        msg = {
            "msgKey": "sampleLink",
            "msgParam": json.dumps(content),
        }

        if is_group and conversation_id:
            return await self._client.send_group_message(
                conversation_id=conversation_id,
                msg=msg,
            )
        else:
            return await self._client.send_private_message(
                user_id=user_id,
                msg=msg,
            )

    async def reply_text(
        self,
        message_id: str,
        text: str,
        conversation_id: str,
        is_group: bool = True,
    ) -> SendMessageResult:
        """Reply to a message with text.

        This uses the group/private message API to send a reply.

        Args:
            message_id: The original message ID.
            text: The reply text.
            conversation_id: The conversation ID.
            is_group: Whether this is a group message.

        Returns:
            SendMessageResult indicating success or failure.
        """
        return await self.send_text(
            user_id="",
            text=text,
            is_group=is_group,
            conversation_id=conversation_id,
        )

    async def send_text_with_mentions(
        self,
        user_id: str,
        text: str,
        mentions: List[str],
        is_group: bool = False,
        conversation_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send a text message with user mentions.

        Args:
            user_id: The receiver's user ID.
            text: The text content.
            mentions: List of user IDs to mention.
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.

        Returns:
            SendMessageResult indicating success or failure.
        """
        mention_text = text
        for user_id_mention in mentions:
            mention_text = f"@{user_id_mention} {mention_text}"

        return await self.send_text(
            user_id=user_id,
            text=mention_text,
            is_group=is_group,
            conversation_id=conversation_id,
        )

    async def send_oa_message(
        self,
        user_id: str,
        title: str,
        content: List[Dict[str, Any]],
        is_group: bool = False,
        conversation_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send an OA (Office Automation) style message.

        Args:
            user_id: The receiver's user ID.
            title: The message title.
            content: List of content rows.
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.

        Returns:
            SendMessageResult indicating success or failure.
        """
        msg = {
            "msgKey": "sampleOA",
            "msgParam": json.dumps(
                {
                    "head": {
                        "bgcolor": "FFBBBBBB",
                        "text": "header",
                    },
                    "body": {
                        "title": title,
                        "form": content,
                        "rich": {
                            "label": {"content": "", "text": ""},
                        },
                    },
                }
            ),
        }

        if is_group and conversation_id:
            return await self._client.send_group_message(
                conversation_id=conversation_id,
                msg=msg,
            )
        else:
            return await self._client.send_private_message(
                user_id=user_id,
                msg=msg,
            )

    async def send_file(
        self,
        user_id: str,
        media_id: str,
        file_name: str,
        file_type: str = "file",
        is_group: bool = False,
        conversation_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send a file message.

        Args:
            user_id: The receiver's user ID.
            media_id: The media ID from DingTalk upload.
            file_name: The file name.
            file_type: The file type (file, voice, video, etc.).
            is_group: Whether to send to a group.
            conversation_id: The conversation ID for group messages.

        Returns:
            SendMessageResult indicating success or failure.
        """
        msg = {
            "msgKey": f"sample{file_type.capitalize()}",
            "msgParam": json.dumps(
                {
                    "media_id": media_id,
                    "file_name": file_name,
                }
            ),
        }

        if is_group and conversation_id:
            return await self._client.send_group_message(
                conversation_id=conversation_id,
                msg=msg,
            )
        else:
            return await self._client.send_private_message(
                user_id=user_id,
                msg=msg,
            )
