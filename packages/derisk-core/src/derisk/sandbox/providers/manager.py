import logging
from collections import defaultdict
from typing import Dict, Type, Optional, cast

from derisk import BaseComponent
from derisk.component import ComponentType, SystemApp
from derisk.sandbox.base import SandboxBase


logger = logging.getLogger(__name__)


class SandboxProviderManager(BaseComponent):
    name = ComponentType.SANDBOX_MANAGER

    def __init__(self, system_app: SystemApp):
        """Create a new VisManager."""
        super().__init__(system_app)
        self.system_app = system_app
        self._sandbox_adapter: Dict[str, Type[SandboxBase]] = defaultdict()

    def init_app(self, system_app: SystemApp):
        """Initialize the SandboxManager."""
        self.system_app = system_app

    def after_start(self):
        """Register default sandbox."""

        """Register Extend sandbox"""
        for _, sandbox in scan_sandbox_provider("derisk_ext.sandbox").items():
            try:
                self.register_sandbox(sandbox)
            except Exception as e:
                logger.exception(f"failed to register sandbox: {_} -- {repr(e)}")

    def register_sandbox(self, cls: Type[SandboxBase]) -> str:
        """Register an sandbox adapter."""

        provider = cls.provider()
        if provider in self._sandbox_adapter:
            logger.warning(
                f"Sandbox Adapter:{provider} already registered, skipping registration."
            )
            return provider
        self._sandbox_adapter[provider] = cls
        return provider

    def get(self, provider: str) -> Type[SandboxBase]:
        if provider not in self._sandbox_adapter:
            raise ValueError(f"Sandbox Adapter:{provider} not register!")
        return self._sandbox_adapter[provider]

    def list_all(self):
        """Return a list of all registered VisConvert and their descriptions."""

        result = []
        for name, value in self._sandbox_adapter.items():
            result.append({"name": name, "cls": value.__name__})
        return result


_SYSTEM_APP: Optional[SystemApp] = None


def initialize_sandbox_adapter(system_app: SystemApp):
    """Initialize the sandbox manager."""
    global _SYSTEM_APP
    _SYSTEM_APP = system_app
    sandbox_manager = SandboxProviderManager(system_app)
    system_app.register_instance(sandbox_manager)
    # Trigger after_start to scan and register sandbox providers
    sandbox_manager.after_start()


def get_sandbox_manager(
    system_app: Optional[SystemApp] = None,
) -> SandboxProviderManager:
    """Return the sandbox manager.

    Args:
        system_app (Optional[SystemApp], optional): The system app. Defaults to None.

    Returns:
        SandboxProviderManager: The sandbox manager.
    """
    if not _SYSTEM_APP:
        if not system_app:
            system_app = SystemApp()
        initialize_sandbox_adapter(system_app)
    app = system_app or _SYSTEM_APP
    return SandboxProviderManager.get_instance(cast(SystemApp, app))


def scan_sandbox_provider(path: str):
    """Scan and register sandbox."""
    from derisk.util.module_utils import ModelScanner, ScannerConfig

    scanner = ModelScanner[SandboxBase]()

    config = ScannerConfig(
        module_path=path,
        base_class=SandboxBase,
        recursive=True,
    )
    scanner.scan_and_register(config)
    return scanner.get_registered_items()
