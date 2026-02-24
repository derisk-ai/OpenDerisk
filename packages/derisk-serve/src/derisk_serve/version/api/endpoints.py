from typing import Optional

from fastapi import APIRouter

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..config import ServeConfig

router = APIRouter()

global_system_app: Optional[SystemApp] = None


@router.get("")
async def query_version() -> Result[str]:
    """Query current application version."""
    # Import version from packages/__init__.py
    import packages

    return Result.succ(packages.__version__)


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints."""
    global global_system_app
    global_system_app = system_app