from derisk import BaseComponent, SystemApp
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk.agent.core.reasoning.reasoning_engine import ReasoningEngine
from derisk.component import ComponentType

_HAS_SCAN = False


class ReasoningManage(BaseComponent):
    name = ComponentType.REASONING_MANAGER

    def init_app(self, system_app: SystemApp):
        pass

    def after_start(self):
        global _HAS_SCAN

        if _HAS_SCAN:
            return

        _register()

        _HAS_SCAN = True


def _register():
    from derisk.util.module_utils import ModelScanner, ScannerConfig

    for baseclass, path in [
        (ReasoningEngine, "derisk_ext.reasoning_engine"),
        (ReasoningArgSupplier, "derisk_ext.reasoning_arg_supplier"),
    ]:
        scanner = ModelScanner[baseclass]()
        config = ScannerConfig(
            module_path=path,
            base_class=baseclass,
            recursive=True,
        )
        scanner.scan_and_register(config)
        for _, subclass in scanner.get_registered_items().items():
            baseclass.register(subclass=subclass)
