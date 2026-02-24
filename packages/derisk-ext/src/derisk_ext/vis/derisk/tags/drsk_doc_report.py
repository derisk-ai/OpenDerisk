import uuid
from typing import Optional, Dict, Any
from derisk.vis import Vis
from .drsk_content import DrskTextContent
from .drsk_doc import GenerateDocTypeEnum


class DrskDocReport(Vis):
    """NexReport."""

    def __init__(self, **kwargs):
        uid = kwargs.get("uid")
        self._uid = uid if uid else uuid.uuid4().hex
        super().__init__(**kwargs)

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the drsk_vis protocol.

        Display corresponding content using drsk_vis protocol

        Args:
            **kwargs:

        Returns:
        drsk_vis protocol text
        """
        content = kwargs.get("content")
        title = kwargs.get("title")
        message_id = kwargs.get("message_id")
        description = kwargs.get("description")
        state = kwargs.get("state", "complete")
        doc_type = kwargs.get("doc_type", GenerateDocTypeEnum.YUQUE.value)
        if not content:
            content = {
                "uid": message_id,
                "type": "all",
                "title": "开始撰写文档",
                "state": state,
            }
            return content
        if isinstance(content, str):
            drsk_think = DrskTextContent(uid=self._uid, type="all", markdown=content)
            return drsk_think.to_dict()
        elif isinstance(content, dict):
            if self._uid:
                content["uid"] = self._uid
            if "type" not in content:
                content["type"] = "all"
            if title:
                content["title"] = title
            if description:
                content["description"] = description
            if state:
                content["state"] = state
            if doc_type:
                content["doc_type"] = doc_type
            return content
        else:
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "drsk-doc-report"
