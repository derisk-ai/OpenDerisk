from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from derisk.vis import Vis

logger = logging.getLogger(__name__)


class ManusLeftPanel(Vis):
    """Manus 左面板 VIS 组件 - 展示执行步骤、思考过程和产物卡片"""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        content = kwargs.get("content", {})
        return content

    @classmethod
    def vis_tag(cls):
        return "manus-left-panel"
