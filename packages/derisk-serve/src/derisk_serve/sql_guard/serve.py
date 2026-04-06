"""SQL Guard module registration."""

import logging
from typing import Optional, Union

from fastapi import FastAPI

from derisk.component import SystemApp
from derisk_serve.sql_guard.config import SQLGuardConfig
from derisk_serve.sql_guard.guard import SQLGuard, get_sql_guard

logger = logging.getLogger(__name__)

# Component name for registration
SQL_GUARD_COMPONENT_NAME = "derisk_serve_sql_guard"


def init_sql_guard(
    system_app: SystemApp,
    app: Optional[Union[FastAPI]] = None,
    config: Optional[SQLGuardConfig] = None,
):
    """Initialize the SQL Guard module.

    Args:
        system_app: The system application.
        app: Optional FastAPI app to register API routes.
        config: Optional configuration override.
    """
    guard = get_sql_guard(config)
    logger.info(
        f"SQL Guard initialized: enabled={guard.config.enabled}, "
        f"mode={guard.config.default_mode}"
    )

    # Register API routes if FastAPI app is provided
    if app is not None:
        from derisk_serve.sql_guard.api.endpoints import router

        app.include_router(router, prefix="/api/v2/serve", tags=["SQL Guard"])
        logger.info("SQL Guard API routes registered")

    return guard
