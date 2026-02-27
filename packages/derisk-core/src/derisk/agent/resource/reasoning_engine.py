import dataclasses
from typing import Optional, Any, Tuple, List, Dict, Type, cast

from derisk.core import Chunk
from .base import Resource, ResourceParameters, ResourceType
from ...util import ParameterDescription
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


class ReasoningEngineResource(Resource[ResourceParameters]):
    def __init__(
        self,
        name: str,
        prompt_template: str = None,
        system_prompt_template: str = None,
        **kwargs,
    ):
        self._name = name
        self._prompt_template = prompt_template
        self._system_prompt_template = system_prompt_template

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


    @system_prompt_template.setter
    def system_prompt_template(self, value: str):
        """设置系统提示模板"""
        # 可以在这里添加验证逻辑
        if not isinstance(value, str):
            raise ValueError("系统提示模板必须是字符串类型")
        self._system_prompt_template = value
    @prompt_template.setter
    def prompt_template(self, template:str):
        self._prompt_template = template

    @system_prompt_template.setter
    def system_prompt_template(self,template:str):
        self._system_prompt_template = template

    @classmethod
    def get_reasoning_engines(cls) -> List[Dict]:
        """Get the reasoning_engine list"""
        from derisk.agent.core.reasoning.reasoning_engine import ReasoningEngine
        result = []
        for k,v in ReasoningEngine.get_all_reasoning_engines().items():
            result.append({
                'name': k,
                'description': v.description,
            })
        return result
    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[ResourceParameters]:
        """Return the resource parameters class."""

        @dataclasses.dataclass
        class _DynReasoningEngineParameters(ResourceParameters):
            """Application resource class."""

            reasoning_engines = cls.get_reasoning_engines()
            valid_values = [
                {
                    "label": f"{item.get('description')}({item.get('name')})",
                    "key": item.get("name"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "system_prompt": item.get("")
                }
                for item in reasoning_engines
            ]

            name: str = dataclasses.field(
                metadata={
                    "help": _("Reasoning Engine name"),
                    "valid_values": valid_values,
                },
            )

            @classmethod
            def to_configurations(
                    cls,
                    parameters: Type["ResourceParameters"],
                    version: Optional[str] = None,
                    **kwargs,
            ) -> Any:
                """Convert the parameters to configurations."""
                conf: List[ParameterDescription] = cast(
                    List[ParameterDescription], super().to_configurations(parameters)
                )
                version = version or cls._resource_version()
                if version != "v1":
                    return conf
                # Compatible with old version
                for param in conf:
                    if param.param_name == "name":
                        return param.valid_values or []
                return []

            @classmethod
            def from_dict(
                    cls, data: dict, ignore_extra_fields: bool = True
            ) -> ResourceParameters:
                """Create a new instance from a dictionary."""
                copied_data = data.copy()
                if "name" not in copied_data and "value" in copied_data:
                    copied_data["name"] = copied_data.pop("value")
                return super().from_dict(
                    copied_data, ignore_extra_fields=ignore_extra_fields
                )

        return _DynReasoningEngineParameters

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, Optional[Dict]]:
        return None, None

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
