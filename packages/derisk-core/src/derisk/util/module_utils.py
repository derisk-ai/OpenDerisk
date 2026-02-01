import fnmatch
import importlib
import inspect
import logging
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, Generic, List, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def import_from_string(module_path: str, ignore_import_error: bool = False):
    try:
        module_path, class_name = module_path.rsplit(".", 1)
    except ValueError:
        raise ImportError(f"{module_path} doesn't look like a module path")
    module = importlib.import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError:
        if ignore_import_error:
            return None
        raise ImportError(
            f'Module "{module_path}" does not define a "{class_name}" attribute/class'
        )


def import_from_checked_string(module_path: str, supper_cls: Type):
    cls = import_from_string(module_path)
    if not issubclass(cls, supper_cls):
        raise ImportError(
            f'Module "{module_path}" does not the subclass of {str(supper_cls)}'
        )
    return cls


@dataclass
class ScannerConfig:
    """Configuration for model scanner.

    Args:
        module_path: Dot-separated path, e.g., "derisk.model.proxy.llms"
        base_class: Base class to filter scanned classes
        class_filter: Additional filter function
        recursive: Whether to scan subdirectories recursively
        specific_files: List of specific files to scan (without .py extension)
        skip_files: File patterns to skip (e.g., ["test_*.py", "*_test.py"])
    """

    module_path: str
    base_class: Optional[Type] = None
    class_filter: Optional[Callable[[Type], bool]] = None
    recursive: bool = False
    specific_files: Optional[List[str]] = None
    # eg: ["test_*.py", "*_test.py"]
    skip_files: Optional[List[str]] = None


class ModelScanner(Generic[T]):
    """Flexible model scanner that can scan and register different types of classes.

    The scanner supports:
    1. Scanning specific files
    2. Recursive directory scanning
    3. Class filtering based on base class and custom filters
    4. Error handling and logging
    """

    def __init__(self):
        """Initialize the model scanner."""
        self._registered_items: Dict[str, Type[T]] = {}

    @staticmethod
    def _is_concrete_class(cls: Type) -> bool:
        """Check if a class is concrete (not abstract).

        Args:
            cls: Class to check

        Returns:
            bool: True if the class is concrete
        """
        return inspect.isclass(cls) and not inspect.isabstract(cls)

    def _should_register_class(self, cls: Type, config: ScannerConfig) -> bool:
        """Check if a class should be registered based on configuration.

        Args:
            cls: Class to check
            config: Scanner configuration

        Returns:
            bool: True if the class should be registered
        """
        if not self._is_concrete_class(cls):
            return False

        if config.base_class and not issubclass(cls, config.base_class):
            return False

        if config.class_filter and not config.class_filter(cls):
            return False

        return True

    def _should_skip_file(
        self, file_name: str, skip_files: Optional[List[str]]
    ) -> bool:
        """Check if a file should be skipped based on skip_files patterns.

        Args:
            file_name: Name of the file to check
            skip_files: List of file patterns to skip

        Returns:
            bool: True if the file should be skipped
        """
        if not skip_files:
            return False

        for pattern in skip_files:
            if fnmatch.fnmatch(file_name, pattern):
                return True

        return False

    def _scan_module(
        self, module: ModuleType, config: ScannerConfig
    ) -> Dict[str, Type[T]]:
        """Scan a single module for classes matching criteria.

        Args:
            module: Module to scan
            config: Scanner configuration

        Returns:
            Dict[str, Type[T]]: Dictionary of found classes
        """
        results: Dict[str, Type[T]] = {}

        for name, cls in inspect.getmembers(module):
            if self._should_register_class(cls, config):
                # Check if the class is defined in the current module
                if cls.__module__ == module.__name__:
                    results[name.lower()] = cls

        return results

    def _scan_directory(
        self, base_path: str, config: ScannerConfig
    ) -> Dict[str, Type[T]]:
        results: Dict[str, Type[T]] = {}
        base_dir = Path(base_path).resolve()

        if not base_dir.exists():
            logger.warning(f"Directory not found: {base_path}")
            return results

        # Handle specific files without recursion
        if config.specific_files and not config.recursive:
            for file_stem in config.specific_files:
                file_path = base_dir / f"{file_stem}.py"
                if not file_path.exists():
                    logger.warning(f"Specific file not found: {file_path}")
                    continue

                try:
                    rel_path = file_path.relative_to(base_dir)
                    module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")
                    full_module_path = f"{config.module_path}.{module_name}"

                    # Avoid re-importing already loaded modules
                    if full_module_path in sys.modules:
                        module = sys.modules[full_module_path]
                    else:
                        module = importlib.import_module(full_module_path)

                    module_results = self._scan_module(module, config)
                    for key, value in module_results.items():
                        real_key = f"{full_module_path}.{key}"
                        results[real_key] = value

                except SyntaxError as e:
                    logger.error(
                        f"SyntaxError in module '{full_module_path}' "
                        f"(file: {e.filename or file_path}, line {e.lineno}): {e.msg}"
                    )
                except ImportError as e:
                    logger.warning(f"ImportError in module '{full_module_path}': {e}")
                except Exception as e:
                    logger.error(
                        f"Unexpected error scanning module '{full_module_path}': "
                        f"{type(e).__name__}: {e}\nTraceback:\n{traceback.format_exc()}"
                    )
            return results

        # Regular directory scanning
        pattern = "**/*.py" if config.recursive else "*.py"
        specific_files = set(config.specific_files or [])
        for py_file in base_dir.glob(pattern):
            if py_file.name.startswith("__"):
                continue
            if self._should_skip_file(py_file.name, config.skip_files):
                logger.debug(f"Skipping file {py_file.name} due to skip_files pattern")
                continue
            if specific_files and py_file.stem not in specific_files:
                continue

            try:
                rel_path = py_file.relative_to(base_dir)
                module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")
                full_module_path = f"{config.module_path}.{module_name}"

                if full_module_path in sys.modules:
                    module = sys.modules[full_module_path]
                else:
                    module = importlib.import_module(full_module_path)

                module_results = self._scan_module(module, config)
                for key, value in module_results.items():
                    real_key = f"{full_module_path}.{key}"
                    results[real_key] = value

            except SyntaxError as e:
                logger.error(
                    f"SyntaxError in module '{full_module_path}' "
                    f"(file: {e.filename or py_file}, line {e.lineno}): {e.msg}"
                )
            except ImportError as e:
                logger.exception(f"ImportError in module '{full_module_path}': {e}")
            except Exception as e:
                logger.error(
                    f"Unexpected error scanning module '{full_module_path}': "
                    f"{type(e).__name__}: {e}\nTraceback:\n{traceback.format_exc()}"
                )

        return results

    def scan_and_register(self, config: ScannerConfig) -> Dict[str, Type[T]]:
        """Scan modules according to config and register matching classes.

        Args:
            config: Scanner configuration specifying what and how to scan

        Returns:
            Dict[str, Type[T]]: Dictionary of registered classes
        """
        try:
            # First try to import as a module
            module = importlib.import_module(config.module_path)

            if hasattr(module, "__file__"):
                # If it's a regular module/package, scan its directory
                base_path = os.path.dirname(module.__file__)
                scanned_items = self._scan_directory(base_path, config)
                for key, value in scanned_items.items():
                    self._registered_items[key] = value
            else:
                # If it's a namespace package or single module
                scanned_items = self._scan_module(module, config)
                for key, value in scanned_items.items():
                    self._registered_items[key] = value

            child_items = {}
            for key, value in self._registered_items.items():
                if hasattr(value, "__scan_config__"):
                    _child_scanner = ModelScanner()
                    _child_config = value.__scan_config__
                    if not isinstance(_child_config, ScannerConfig):
                        continue
                    if (
                        hasattr(value, "__is_already_scanned__")
                        and value.__is_already_scanned__
                    ):
                        continue
                    try:
                        _child_scanner.scan_and_register(_child_config)
                        child_items.update(_child_scanner.get_registered_items())
                        value.__is_already_scanned__ = True
                    except Exception as e:
                        logger.warning(f"Error scanning child module {key}: {str(e)}")
            self._registered_items.update(child_items)

        except ImportError as e:
            logger.warning(f"Error importing module {config.module_path}: {str(e)}")

        return self._registered_items

    def get_registered_items(self) -> Dict[str, Type[T]]:
        """Get all registered items.

        Returns:
            Dict[str, Type[T]]: Dictionary of all registered classes
        """
        return self._registered_items

    def get_item(self, name: str) -> Optional[Type[T]]:
        """Get a specific registered item by name.

        Args:
            name: Name of the item to get

        Returns:
            Optional[Type[T]]: The requested class if found, None otherwise
        """
        return self._registered_items.get(name.lower())


def model_scan(module_path: str, base_class: Type, recursive: bool = True, **kwargs) -> Dict[str, Type[T]]:
    """Scan a specific dir and get all items

    Args:
        module_path: Dot-separated path, e.g., "derisk.model.proxy.llms"
        base_class: Base class to filter scanned classes
        class_filter: Additional filter function
        recursive: Whether to scan subdirectories recursively
        specific_files: List of specific files to scan (without .py extension)

    Returns:
        Dict[str, Type[T]]: Dictionary of all registered classes
    """
    scanner = ModelScanner[T]()
    scanner.scan_and_register(ScannerConfig(module_path=module_path, base_class=base_class, recursive=recursive, **kwargs))
    return scanner.get_registered_items()
