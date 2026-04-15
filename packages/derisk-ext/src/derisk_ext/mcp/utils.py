import logging


def setup_logger(level: str | int = logging.INFO):
    """Setup logger - delegates to derisk's unified logging system.

    This function no longer calls logging.basicConfig to prevent duplicate log output.
    The actual logging setup is handled by derisk.util.logger.setup_logging.
    """
    logger = logging.getLogger("mcp")
    logger.setLevel(level)
    return logger
