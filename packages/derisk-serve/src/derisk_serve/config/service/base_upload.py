import logging
from collections import defaultdict
from typing import List, Type, Dict, Optional, cast, Generic, TypeVar, Union
from dataclasses import dataclass
from derisk import BaseComponent, SystemApp
from derisk._private.config import Config
from derisk.util import BaseParameters, RegisterParameters

CMP_NAME = "derisk_config_manager"

logger = logging.getLogger(__name__)
CFG = Config()


@dataclass
class UpdaterConfig(BaseParameters, RegisterParameters):
    __type__ = "___updater_config___"
    __cfg_type__ = "utils"


T = TypeVar("T", bound=Union[UpdaterConfig, None])


class BaseConfigUpdater(Generic[T]):

    def __init__(self, system_app: SystemApp, config: UpdaterConfig):
        self._system_app = system_app
        self._config = config

    @classmethod
    def updater_cls(cls) -> str:
        return cls.__name__

    @classmethod
    def config_type(cls) -> str:
        return UpdaterConfig.__type__

    @property
    def description(self):
        return "配置自动更新服务"

    async def get_value(self, **kwargs) -> Optional[str]:
        raise NotImplementedError


class ConfigUpdaterManager(BaseComponent):
    name = CMP_NAME

    def __init__(self, system_app: SystemApp):
        """Create a new BaseConfigUpload."""

        super().__init__(system_app)
        self.system_app = system_app
        self._updaters: Dict[str, Type[BaseConfigUpdater]] = (defaultdict())

        updaters_scanner = scan_config_updater(["derisk_serve.config.service.ext"])
        for _, updater in updaters_scanner.items():
            try:
                self.register(updater)
            except Exception as e:
                logger.warning(f"updater register faild!{_},{updater}", e)

    def init_app(self, system_app: SystemApp):
        self.system_app = system_app

    def register(
        self, cls: Type[BaseConfigUpdater]
    ) -> str:
        """Register an updater."""
        logger.info(f"register:{cls}")
        cls_name = cls.updater_cls()
        # inst = cls(system_app=self.system_app)
        if cls_name in self._updaters:
            raise ValueError(f"Config Updater:{cls_name} already register!")
        self._updaters[cls_name] = cls
        return cls_name

    def get_updater(self, cls_name: str) -> Optional[Type[BaseConfigUpdater]]:
        if cls_name in self._updaters:
            return self._updaters[cls_name]
        else:
            return None

    def list_info(self):
        return [{"name": k, "descriptiion": v.description} for k, v in self._updaters.items()]


def scan_config_updater(config_upload_paths: List[str]):
    """
    Scan the component path address specified in the current component package.
    Args:
        config_upload_paths: The component path address of the current component package
    Returns:

    """
    from derisk.util.module_utils import ModelScanner, ScannerConfig

    scanner = ModelScanner[BaseConfigUpdater]()
    for path in config_upload_paths:
        config = ScannerConfig(
            module_path=path,
            base_class=BaseConfigUpdater,
            recursive=True,
        )
        scanner.scan_and_register(config)
    return scanner.get_registered_items()


_SYSTEM_APP: Optional[SystemApp] = None


def initialize_config_update(system_app: SystemApp):
    """Initialize the config update manager."""
    global _SYSTEM_APP
    _SYSTEM_APP = system_app
    config_manager = ConfigUpdaterManager(system_app)
    system_app.register_instance(config_manager)


def get_config_update_manager(system_app: Optional[SystemApp] = None) -> ConfigUpdaterManager:
    """Return the config update manager.

    Args:
        system_app (Optional[SystemApp], optional): The system app. Defaults to None.

    Returns:
        ConfigUpdaterManager: The config update manager.
    """
    if not _SYSTEM_APP:
        if not system_app:
            system_app = SystemApp()
        initialize_config_update(system_app)
    app = system_app or _SYSTEM_APP
    return ConfigUpdaterManager.get_instance(cast(SystemApp, app))
