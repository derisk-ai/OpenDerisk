import dataclasses
from typing import Optional, Any, Tuple, List, Dict, Type

from derisk.core import Chunk
from .base import Resource, ResourceParameters, ResourceType
from ...util.i18n_utils import _


@dataclasses.dataclass
class ReasoningEngineResourceParameters(ResourceParameters):
    name: str = dataclasses.field(metadata={"help": _("Resource name")})
    prompt_template: Optional[str] = dataclasses.field(
        default=None, metadata={"help": _("Resource name")}
    )
    system_prompt_template: Optional[str] = dataclasses.field(
        default=None, metadata={"help": _("Resource name")}
    )
    reasoning_arg_suppliers: Optional[list[str]] = dataclasses.field(
        default=None, metadata={"help": _("Resource name")}
    )


class ReasoningEngineResource(Resource[ResourceParameters]):
    def __init__(
        self,
        name: str,
        prompt_template: str = None,
        system_prompt_template: str = None,
        reasoning_arg_suppliers: list[str] = None,
        **kwargs,
    ):
        self._name = name
        self._prompt_template = prompt_template
        self._system_prompt_template = system_prompt_template
        self._reasoning_arg_suppliers = reasoning_arg_suppliers

    @classmethod
    def type(cls) -> ResourceType:
        return ResourceType.ReasoningEngine

    @property
    def name(self) -> str:
        """Return the resource name."""
        return self._name

    @property
    def prompt_template(self) -> str:
        return self._prompt_template

    @property
    def system_prompt_template(self) -> str:
        return self._system_prompt_template

    @property
    def reasoning_arg_suppliers(self) -> list[str]:
        return self._reasoning_arg_suppliers

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[ResourceParameters]:
        """Return the resource parameters class."""
        return ReasoningEngineResourceParameters

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, Optional[Dict]]:
        pass

    async def get_resources(
        self,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
    ) -> Tuple[Optional[List[Chunk]], str, Optional[Dict]]:
        pass

    def execute(self, *args, resource_name: Optional[str] = None, **kwargs) -> Any:
        pass

    async def async_execute(
        self, *args, resource_name: Optional[str] = None, **kwargs
    ) -> Any:
        pass
