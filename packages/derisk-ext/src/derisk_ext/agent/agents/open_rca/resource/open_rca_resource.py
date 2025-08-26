import dataclasses
import logging
from typing import Type, Optional, Any, List, cast, Union, Tuple, Dict

from derisk._private.config import Config
from derisk.agent import Resource, ResourceType
from derisk.agent.resource import ResourceParameters
from derisk.core import Chunk
from derisk.util import ParameterDescription

CFG = Config()

logger = logging.getLogger(__name__)





@dataclasses.dataclass
class OpenRcaSceneParameters(ResourceParameters):
    """The DB parameters for the datasource."""

    scene: str = dataclasses.field(metadata={"help": "Open Rca scene name"})

    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
        cls,
        parameters: Type["OpenRcaSceneParameters"],
        version: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Convert the parameters to configurations."""
        conf: List[ParameterDescription] = cast(
            List[ParameterDescription],
            super().to_configurations(
                parameters,
                **kwargs,
            ),
        )
        version = version or cls._resource_version()
        if version != "v1":
            return conf
        # Compatible with old version
        for param in conf:
            if param.param_name == "scene":
                return param.valid_values or []
        return []

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "OpenRcaSceneParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        if "scene" not in copied_data and "value" in copied_data:
            copied_data["scene"] = copied_data.pop("value")
        if "name" not in copied_data:
            copied_data["name"] = "OpenRcaScene"
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


def get_open_rca_scenes():
    from derisk_ext.agent.agents.open_rca.resource.open_rca_base import OpenRcaScene
    results = []
    for scene in OpenRcaScene:
        results.append(scene)
    return results

class OpenRcaSceneResource(Resource[OpenRcaSceneParameters]):
    async def get_prompt(self, *, lang: str = "en", prompt_type: str = "default", question: Optional[str] = None,
                         resource_name: Optional[str] = None, **kwargs) -> Tuple[str, Optional[Dict]]:
        return "", None


    def __init__(self, name: str, scene: Optional[str] = None, **kwargs):
        self._scene = scene
        self._name = name


    @classmethod
    def type(cls) -> Union[ResourceType,str]:
        return "open_rca_scene"
    @property
    def scene(self) -> str:
        """Return the resource type."""
        return self._scene

    @property
    def name(self) -> str:
        """Return the resource name."""
        return self._name
    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[OpenRcaSceneParameters]:


        results = [
            {
                "label": item,
                "key": item,
                "name": item,
                "value": item,
            }
            for item in get_open_rca_scenes()
        ]

        @dataclasses.dataclass
        class _DynDBParameters(OpenRcaSceneParameters):
            scene: str = dataclasses.field(
                metadata={"help": "OpenRca scene name", "valid_values": results}
            )

        return _DynDBParameters

