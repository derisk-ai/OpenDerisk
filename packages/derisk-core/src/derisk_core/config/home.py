"""Derisk home directory utilities for cross-platform compatibility."""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_derisk_home() -> Path:
    """Get the derisk home directory path.

    Priority:
    1. DERISK_HOME environment variable
    2. ~/.derisk (Path.home() / ".derisk")
    3. ./.derisk (current working directory fallback)
    """
    env_home = os.environ.get("DERISK_HOME")
    if env_home:
        return Path(env_home)

    try:
        return Path.home() / ".derisk"
    except (RuntimeError, KeyError):
        logger.warning(
            "Cannot determine user home directory. "
            "Set DERISK_HOME environment variable or HOME. "
            "Falling back to ./.derisk in current directory."
        )
        return Path.cwd() / ".derisk"
