from derisk.vis import Vis


class DeriskAttachList(Vis):
    """多文件附件列表组件

 vis_tag: d-attach-list

    用于展示多个文件的交付场景，如：
    1. terminate时的文件交付
    2. 批量文件下载
    3. 任务完成的文件汇总

    对应前端组件: d-attach-list
    """

    @classmethod
    def vis_tag(cls):
        return "d-attach-list"
