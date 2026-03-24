from derisk.vis import Vis


class DrskConfirmResponse(Vis):
    """用户确认响应展示组件"""

    def vis_tag(cls) -> str:
        return "drsk-confirm-response"
