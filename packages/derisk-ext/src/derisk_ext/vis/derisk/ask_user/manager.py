from typing import Optional, Type

from derisk.agent import ActionOutput
from derisk.agent.core.action.base import AskUserType
from derisk.agent.core.memory.gpts import GptsMessage
from derisk_ext.vis.derisk.ask_user.converter import AskUserBeforeAction, AskUserVisConverter

_register = {
    AskUserType.BEFORE_ACTION.value: AskUserBeforeAction,
    # AskUserType.CONCLUSION_INCOMPLETE.value: AskUserIncompleteConclusion,
}


async def convert(ask_type: str, action_outputs: list[ActionOutput], message: GptsMessage) -> Optional[str]:
    if not action_outputs or ask_type not in _register:
        return None
    converter: Type[AskUserVisConverter] = _register.get(ask_type)
    return converter.convert(action_outputs, message)
