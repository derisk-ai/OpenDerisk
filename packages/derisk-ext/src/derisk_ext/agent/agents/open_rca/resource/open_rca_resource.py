import dataclasses
import logging
from typing import Type, Optional, Any, List, cast, Union, Tuple, Dict

from derisk._private.config import Config
from derisk.agent import Resource, ResourceType
from derisk.agent.resource import PackResourceParameters, ResourceParameters
from derisk.util import ParameterDescription
from derisk.util.template_utils import render
from derisk.util.i18n_utils import _

CFG = Config()

logger = logging.getLogger(__name__)

open_rca_scene_prompt_template = """<open-rca-scene>
这里是Open RCA场景的基础信息，包含场景名称、场景介绍和文件存放路径。

<scene-info>
<name>{{scene_name}}</name>
<description>{{scene_description}}</description>
<data_path>{{data_path}}</data_path>
</scene-info>

<scene-background>
{{scene_schema}}
</scene-background>
</open-rca-scene>"""

SCENE_DESCRIPTIONS = {
    "bank": "银行微服务系统场景，包含Tomcat、MySQL、Redis等组件的监控数据",
    "telecom": "电信运营商微服务场景，包含网络和服务监控数据",
    "market": "市场营销系统场景，包含业务和性能监控数据",
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
        results.append(scene.value)
    return results


def _load_scene_info(scene_name: str) -> Dict[str, Any]:
    """Load scene information including schema and data path."""
    from derisk_ext.agent.agents.open_rca.resource.open_rca_base import (
        OpenRcaScene,
        get_open_rca_background,
    )

    try:
        scene = OpenRcaScene(scene_name)
        scene_description = SCENE_DESCRIPTIONS.get(scene_name, f"{scene_name} 场景")
        scene_schema = get_open_rca_background(scene_name)

        scene_data_path = None
        match scene:
            case OpenRcaScene.BANK:
                from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Bank import data_path
                scene_data_path = data_path
            case OpenRcaScene.TELECOM:
                from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Telecom import data_path
                scene_data_path = data_path
            case OpenRcaScene.MARKET:
                from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Market import data_path
                scene_data_path = data_path

        return {
            "name": scene_name,
            "description": scene_description,
            "schema": scene_schema,
            "data_path": scene_data_path,
        }
    except Exception as e:
        logger.warning(f"Error loading scene info for {scene_name}: {e}")
        return {
            "name": scene_name,
            "description": SCENE_DESCRIPTIONS.get(scene_name, f"{scene_name} 场景"),
            "schema": None,
            "data_path": None,
        }


class OpenRcaSceneResource(Resource[ResourceParameters]):
    def __init__(self, name: str = "OpenRcaScene Resource", scene: Optional[str] = None, **kwargs):
        self._resource_name = name
        self._scene = scene
        self._scene_description = kwargs.get("scene_description")
        self._scene_schema = kwargs.get("scene_schema")
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
    def scene_description(self) -> Optional[str]:
        """Return the scene description."""
        return self._scene_description

    @property
    def scene_schema(self) -> Optional[str]:
        """Return the scene schema/background."""
        return self._scene_schema

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
                    "scene_description": _load_scene_info(scene_name)["description"],
                    "scene_schema": _load_scene_info(scene_name).get("schema"),
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
                metadata={"help": _("OpenRca scene name"), "valid_values": valid_values},
            )
            scene_description: Optional[str] = dataclasses.field(
                default=None,
                metadata={"help": _("Scene description"), "valid_values": valid_values},
            )
            scene_schema: Optional[str] = dataclasses.field(
                default=None,
                metadata={"help": _("Scene schema/background"), "valid_values": valid_values},
            )
            data_path: Optional[str] = dataclasses.field(
                default=None,
                metadata={"help": _("Scene data path"), "valid_values": valid_values},
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
                copied_data = data.copy()
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
            "scene_description": self._scene_description or "",
            "scene_schema": self._scene_schema or "",
            "data_path": self._data_path or "",
        }

        prompt = render(open_rca_scene_prompt_template, params)

        scene_meta = {
            "name": self._scene,
            "description": self._scene_description,
            "schema": self._scene_schema,
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

