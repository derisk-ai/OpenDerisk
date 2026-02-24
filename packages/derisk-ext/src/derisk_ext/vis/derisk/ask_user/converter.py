from abc import ABC
from typing import Optional

from derisk.agent import ActionOutput
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.vis.schema import VisConfirm
from derisk_ext.vis.derisk.tags.drsk_confirm import DrskConfirm


class AskUserVisConverter(ABC):
    @classmethod
    def convert(cls, ask_user_action_reports: list[ActionOutput], message: GptsMessage) -> Optional[str]:
        raise NotImplemented


class AskUserBeforeAction(AskUserVisConverter):
    @classmethod
    def convert(cls, ask_user_action_reports: list[ActionOutput], message: GptsMessage) -> Optional[str]:
        def _make_one_markdown(report: ActionOutput) -> str:
            return f"* 动作:{report.action_name}({report.action}),参数:{report.action_input}"

        markdown = "\n\n".join([_make_one_markdown(report)
                                for report in ask_user_action_reports])
        if not markdown:
            return None

        markdown = "将执行如下动作:\n\n" + markdown + "\n\n是否确认执行?"
        return DrskConfirm().sync_display(content=VisConfirm(
            uid=message.message_id + "_confirm",
            message_id=message.message_id + "_confirm",
            type="all",
            markdown=markdown,
            disabled=False,
            extra={"approval_message_id": message.message_id}
        ).to_dict())


# class AskUserIncompleteConclusion(AskUserVisConverter):
#     @classmethod
#     def convert(cls, ask_user_action_reports: list[ActionOutput], message: GptsMessage) -> Optional[str]:
#         def _make_one_markdown(report: ActionOutput) -> str | None:
#             if not report or not report.extra:
#                 return None
#             return report.extra.get("ask_user_content")
#
#         markdown = "\n\n* ".join([m for report in ask_user_action_reports
#                                   if (m := _make_one_markdown(report))])
#         if not markdown:
#             return None
#
#         ask_view = DrskInteract().sync_display(content=VisInteract(
#             uid=message.message_id + "_interact",
#             message_id=message.message_id + "_interact",
#             type="all",
#             title="请补充信息",
#             markdown=markdown,
#             interact_type="notice",
#             position="tail",
#         ).to_dict())
#         # 将问题拼接在final_report后面
#         origin_action_report = ActionOutput.from_dict(json.loads(message.action_report))
#         origin_action_report.view + "" + ask_view
#         message.action_report = json.dumps(origin_action_report, ensure_ascii=False)
#         return None
#         # return origin_view + "\n\n" + DrskInteract().sync_display(content=VisInteract(
#         #     uid=message.message_id + "_interact",
#         #     message_id=message.message_id + "_interact",
#         #     type="all",
#         #     title="请补充信息",
#         #     markdown=markdown,
#         #     interact_type="notice",
#         #     position="tail",
#         # ).to_dict())
