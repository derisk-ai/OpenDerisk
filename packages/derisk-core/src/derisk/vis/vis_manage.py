import logging
from collections import defaultdict
from typing import Dict, Tuple, Type, Optional, cast

from derisk import BaseComponent
from derisk.component import ComponentType, SystemApp
from derisk.vis import VisProtocolConverter

logger = logging.getLogger(__name__)

class VisConvertManager(BaseComponent):
    """Manages the registration and retrieval of vis mode."""

    name = ComponentType.VIS_CONVERTER_PACKAGE

    def __init__(self, system_app: SystemApp):
        """Create a new VisManager."""
        super().__init__(system_app)
        self.system_app = system_app
        self._vis_converts: Dict[str, Tuple[Type[VisProtocolConverter], VisProtocolConverter]] = (
            defaultdict()
        )


    def init_app(self, system_app: SystemApp):
        """Initialize the AgentManager."""
        self.system_app = system_app

    def after_start(self):
        from derisk.util.module_utils import model_scan

        """Register all VisConvert."""

        from derisk.vis.vis_converter import DefaultVisConverter
        self.register_vis_convert(DefaultVisConverter)


        """Register Extend VisConvert"""
        for _, convert in scan_vis_converts("derisk_ext.vis").items():
            try:
                self.register_vis_convert(convert)
            except Exception as e:
                logger.exception(f"failed to register vis_convert: {_} -- {repr(e)}")


    def register_vis_convert(
        self, cls: Type[VisProtocolConverter]
    ) -> str:
        """Register an vis convert."""
        inst = cls()
        render_name = inst.render_name
        if render_name in self._vis_converts:
            raise ValueError(f"VisConvert:{render_name} already register!")
        self._vis_converts[render_name] = (cls, inst)
        return render_name


    def get(self, render_name: str) -> VisProtocolConverter:
        if render_name not in self._vis_converts:
            logger.error(f"VisConvert:{render_name} not register!")
            raise ValueError(f"VisConvert:{render_name} not register!")
        return self._vis_converts[render_name][1]
    def get_by_name(self, render_name: str) -> Type[VisProtocolConverter]:
        """Return an VisConvert by name.

        Args:
            render_name (str): The name of the VisConvert to retrieve.

        Returns:
            Type[VisProtocolConverter]: The VisConvert with the given name.

        Raises:
            ValueError: If the VisConvert with the given name is not registered.
        """
        if render_name not in self._vis_converts:
            raise ValueError(f"VisConvert:{render_name} not register!")
        return self._vis_converts[render_name][0]


    def list_all(self):
        """Return a list of all registered VisConvert and their descriptions."""

        result = []
        for name, value in self._vis_converts.items():
            result.append(
                {
                    "name": name,
                    "incremental": value[1].incremental,
                    "description": value[1].description,
                }
            )
        return result

    def list_all_web_use(self):
        """Return a list of all registered VisConvert and their descriptions."""

        result = []
        for name, value in self._vis_converts.items():
            if value[1].web_use:
                result.append(
                    {
                        "name": name,
                        "incremental": value[1].incremental,
                        "description": value[1].description,
                    }
                )
        return result

_SYSTEM_APP: Optional[SystemApp] = None


def initialize_vis_convert(system_app: SystemApp):
    """Initialize the vis manager."""
    global _SYSTEM_APP
    _SYSTEM_APP = system_app
    vis_convert_manager = VisConvertManager(system_app)
    system_app.register_instance(vis_convert_manager)


def get_vis_manager(system_app: Optional[SystemApp] = None) -> VisConvertManager:
    """Return the vis manager.

    Args:
        system_app (Optional[SystemApp], optional): The system app. Defaults to None.

    Returns:
        VisConvertManager: The vis manager.
    """
    if not _SYSTEM_APP:
        if not system_app:
            system_app = SystemApp()
        initialize_vis_convert(system_app)
    app = system_app or _SYSTEM_APP
    return VisConvertManager.get_instance(cast(SystemApp, app))




def scan_vis_converts(path:str):
    """Scan and register all agents."""
    from derisk.util.module_utils import ModelScanner, ScannerConfig

    scanner = ModelScanner[VisProtocolConverter]()

    config = ScannerConfig(
        module_path=path,
        base_class=VisProtocolConverter,
        recursive=True,
    )
    scanner.scan_and_register(config)
    return scanner.get_registered_items()
