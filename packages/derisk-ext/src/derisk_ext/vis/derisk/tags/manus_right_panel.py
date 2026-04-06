from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from derisk.vis import Vis

logger = logging.getLogger(__name__)


class ManusRightPanel(Vis):
    """Manus 右面板 VIS 组件 - 展示步骤详情、输出内容和产物"""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        content = kwargs.get("content", {})
        return content

    @classmethod
    def vis_tag(cls):
        return "manus-right-panel"
