from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from derisk.vis import Vis

logger = logging.getLogger(__name__)


class DrskDeliverable(Vis):
    """交付物卡片 VIS 组件 - 在左侧面板展示可交付文件和任务文件入口"""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        content = kwargs.get("content", {})
        return content

    @classmethod
    def vis_tag(cls):
        return "drsk-deliverable"
