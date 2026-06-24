"""Register built-in extractors at app startup.

Mirrors `register_builtin_tools()` in derisk-core/agent/tools/decorators.py.
Called once by the knowledge Serve's `Service.init_app`.

Importing this module has the side effect of registering all `@extractor`-
decorated classes in `builtin.py` with the global registry. The function
exists so callers can express intent explicitly and so we can guard against
double-registration in tests.
"""

from __future__ import annotations

import logging

from . import get_extractor_registry
from . import builtin as _builtin  # noqa: F401 — side effect: registers extractors

logger = logging.getLogger(__name__)

_registered = False


def register_builtin_extractors() -> None:
    """Register all built-in extractors (idempotent)."""
    global _registered
    if _registered:
        return
    # Importing `builtin` runs the @extractor decorators, which register
    # instances with the global registry. The import above already did this.
    # The flag just prevents redundant log noise on repeated calls.
    _registered = True
    reg = get_extractor_registry()
    logger.info(
        "Registered %d built-in knowledge extractors: %s",
        len(reg.list_all()),
        [e.name for e in reg.list_all()],
    )
