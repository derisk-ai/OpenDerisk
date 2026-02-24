import dataclasses
from abc import ABC
from enum import Enum
from typing import Union, Optional, Tuple, Dict, Type, Any

from derisk.agent import Resource, ResourceType
from derisk.agent.resource import ResourceParameters
from derisk.util.i18n_utils import _
from derisk.util.template_utils import render

prompt_template = "{{id}}：调用此工具与 {{id}} API进行交互。{{id}} API 有什么用？{{description}}"


class WorkflowPlatform(str, Enum):
    Ling = "ling"  # 灵矽


@dataclasses.dataclass
class WorkflowResourceParameter(ResourceParameters):
    platform: str = dataclasses.field(metadata={"help": _("platform source")})
    id: str = dataclasses.field(metadata={"help": _("id of the workflow")})
    description: str = dataclasses.field(metadata={"help": _("workflow description")})
    extra: str = dataclasses.field(default=None, metadata={"help": _("workflow description")})


class WorkflowResource(Resource[WorkflowResourceParameter], ABC):
    def __init__(self, name: str, platform: str, id: str, description: str, extra: str = None, **kwargs):
        self._name = name
        self._platform: str = platform
        self._id: str = id
        self._description = description
        self._extra = extra

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def id(self) -> str:
        return self._id

    @property
    def description(self) -> str:
        return self._description

    @property
    def extra(self) -> str:
        return self._extra

    @classmethod
    def type(cls) -> Union[ResourceType, str]:
        return ResourceType.Workflow

    @classmethod
    def resource_parameters_class(cls, **kwargs):
        return WorkflowResourceParameter

    async def get_prompt(self, **kwargs) -> Tuple[str, Optional[Dict]]:
        return render(prompt_template, {
            "id": self._name,
            "description": self._description,
        }), None
