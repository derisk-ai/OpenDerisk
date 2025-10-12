import dataclasses
from abc import ABC
from enum import Enum
from typing import Union, Optional, Tuple, Dict

from derisk.agent import Resource, ResourceType
from derisk.util.i18n_utils import _
from derisk.util.template_utils import render

prompt_template = "{id}：调用此工具与 {id} API进行交互。{id} API 有什么用？{description}"


class WorkflowPlatform(str, Enum):
    Ling = "ling"  # 灵矽


@dataclasses.dataclass
class WorkflowResourceParameter:
    platform: str = dataclasses.field(metadata={"help": _("platform source")})
    id: str = dataclasses.field(metadata={"help": _("id of the workflow")})
    description: str = dataclasses.field(metadata={"help": _("workflow description")})
    extra: str = dataclasses.field(default=None, metadata={"help": _("workflow description")})


class WorkflowResource(Resource[WorkflowResourceParameter], ABC):
    def __init__(self, platform: str, id: str, description: str, extra: str = None, **kwargs):
        self._platform: str = platform
        self._id: str = id
        self._description = description
        self._extra = extra

    @property
    def name(self) -> str:
        return self._id

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def extra(self) -> str:
        return self._extra

    @classmethod
    def type(cls) -> Union[ResourceType, str]:
        return ResourceType.Workflow

    async def get_prompt(self, **kwargs) -> Tuple[str, Optional[Dict]]:
        return render(prompt_template, {
            "id": self._id,
            "description": self._description,
        }), None
