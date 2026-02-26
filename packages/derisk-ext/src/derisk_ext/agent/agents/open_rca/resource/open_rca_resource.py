import dataclasses
import logging
import os
from typing import Type, Optional, Any, List, cast, Union, Tuple, Dict

from derisk._private.config import Config
from derisk.agent import Resource, ResourceType
from derisk.agent.resource import PackResourceParameters, ResourceParameters
from derisk.configs.model_config import PILOT_PATH
from derisk.util import ParameterDescription
from derisk.util.template_utils import render
from derisk.util.i18n_utils import _

CFG = Config()

logger = logging.getLogger(__name__)

OPEN_RCA_DEFAULT_DATA_DIR = os.path.join(PILOT_PATH, "dataset/openrca")

open_rca_scene_prompt_template = """<open-rca-scene>
<scene>{{scene_name}}</scene>
<data_path>{{data_path}}</data_path>
</open-rca-scene>"""

SCENE_DESCRIPTIONS = {
    "bank": "银行微服务系统场景",
    "telecom": "电信运营商微服务场景",
    "market": "市场营销系统场景",
}


def _load_scene_info(scene_name: str) -> Dict[str, Any]:
    """Load scene information including scene name and data path."""
    from derisk_ext.agent.agents.open_rca.resource.open_rca_base import OpenRcaScene

    try:
        scene = OpenRcaScene(scene_name)
        scene_description = SCENE_DESCRIPTIONS.get(scene_name, f"{scene_name} 场景")
        scene_data_path = os.path.join(
            OPEN_RCA_DEFAULT_DATA_DIR, scene_name.capitalize()
        )

        return {
            "name": scene_name,
            "description": scene_description,
            "data_path": scene_data_path,
        }
    except Exception as e:
        logger.warning(f"Error loading scene info for {scene_name}: {e}")
        return {
            "name": scene_name,
            "description": SCENE_DESCRIPTIONS.get(scene_name, f"{scene_name} 场景"),
            "data_path": os.path.join(
                OPEN_RCA_DEFAULT_DATA_DIR, scene_name.capitalize()
            ),
        }


@dataclasses.dataclass
class OpenRcaSceneParameters(PackResourceParameters):
    """The DB parameters for the datasource."""

    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v2"

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
        for param in conf:
            if param.param_name == "scene":
                return param.valid_values or []
        return []

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "OpenRcaSceneParameters":
        """Create a new instance from a dictionary."""
        copied_data = (data or {}).copy()
        if "scene" not in copied_data and "value" in copied_data:
            copied_data["scene"] = copied_data.pop("value")
        if "name" not in copied_data:
            copied_data["name"] = "OpenRcaScene"
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


def get_open_rca_scenes():
    from derisk_ext.agent.agents.open_rca.resource.open_rca_base import OpenRcaScene

    results = []
    for scene in OpenRcaScene:
        results.append(scene.value)
    return results


class OpenRcaSceneResource(Resource[ResourceParameters]):
    def __init__(
        self, name: str = "OpenRcaScene Resource", scene: Optional[str] = None, **kwargs
    ):
        self._resource_name = name
        self._scene = scene
        self._data_path = kwargs.get("data_path")

    @property
    def name(self) -> str:
        """Return the resource name."""
        return self._resource_name

    @property
    def scene(self) -> Optional[str]:
        """Return the scene name."""
        return self._scene

    @property
    def data_path(self) -> Optional[str]:
        """Return the data path."""
        return self._data_path

    @classmethod
    def type(cls) -> Union[ResourceType, str]:
        return "open_rca_scene"

    @classmethod
    def type_alias(cls) -> str:
        return "open_rca_scene"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[OpenRcaSceneParameters]:
        @dataclasses.dataclass
        class _DynOpenRcaSceneParameters(OpenRcaSceneParameters):
            scenes_list = get_open_rca_scenes()
            valid_values = [
                {
                    "label": f"[{scene_name}]{_load_scene_info(scene_name)['description']}",
                    "key": scene_name,
                    "name": scene_name,
                    "value": scene_name,
                    "scene": scene_name,
                    "data_path": _load_scene_info(scene_name).get("data_path"),
                }
                for scene_name in get_open_rca_scenes()
            ]

            name: str = dataclasses.field(
                default="OpenRcaScene",
                metadata={"help": _("Resource name")},
            )
            scene: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("OpenRca scene name"),
                    "valid_values": valid_values,
                },
            )
            data_path: Optional[str] = dataclasses.field(
                default=None,
                metadata={"help": _("Scene data path")},
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
                for param in conf:
                    if param.param_name == "scene":
                        return param.valid_values or []
                return []

            @classmethod
            def from_dict(
                cls, data: dict, ignore_extra_fields: bool = True
            ) -> "OpenRcaSceneParameters":
                """Create a new instance from a dictionary."""
                copied_data = (data or {}).copy()

                scene_key = copied_data.get("scene") or copied_data.get("value")
                if scene_key:
                    for valid_value in cls.valid_values:
                        if (
                            valid_value.get("scene") == scene_key
                            or valid_value.get("value") == scene_key
                        ):
                            for key in ["data_path"]:
                                if key not in copied_data or not copied_data.get(key):
                                    if valid_value.get(key):
                                        copied_data[key] = valid_value.get(key)
                            break

                return super().from_dict(
                    copied_data, ignore_extra_fields=ignore_extra_fields
                )

        return _DynOpenRcaSceneParameters

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, Optional[Dict]]:
        """Get the prompt with scene information."""
        params = {
            "scene_name": self._scene,
            "data_path": self._data_path or "",
        }

        prompt = render(open_rca_scene_prompt_template, params)

        scene_meta = {
            "name": self._scene,
            "data_path": self._data_path,
        }
        return prompt, scene_meta

    @property
    def is_async(self) -> bool:
        """Return whether the resource is asynchronous."""
        return True

    def execute(self, *args, resource_name: Optional[str] = None, **kwargs) -> Any:
        """Execute the resource synchronously (not supported)."""
        if self.is_async:
            raise RuntimeError("Sync execution is not supported")

    async def async_execute(
        self,
        *args,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Execute the resource asynchronously."""
        return await self.get_prompt(
            lang=kwargs.get("lang", "en"),
            prompt_type=kwargs.get("prompt_type", "default"),
            resource_name=resource_name,
            **kwargs,
        )
