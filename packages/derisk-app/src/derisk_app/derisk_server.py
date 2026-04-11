import logging
import os
import sys
from pathlib import Path

from derisk.util.logger import (
    logging_str_to_uvicorn_level,
)
from derisk.util.parameter_utils import _get_dict_from_obj
from derisk.util.system_utils import get_system_info
from derisk.util.tracer import SpanType, SpanTypeRunName, root_tracer
from derisk_app.app import CustomAppCreator, AppCreator

logger = logging.getLogger(__name__)
ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_PATH)

from derisk_core.config.home import get_derisk_home

DEFAULT_JSON_CONFIG_PATH = get_derisk_home() / "derisk.json"


def init_json_config_manager():
    """Initialize the JSON config manager for UI configuration"""
    try:
        config_path = str(DEFAULT_JSON_CONFIG_PATH)
        logger.info(f"Initializing JSON config manager at: {config_path}")

        from derisk_core.config import ConfigManager

        ConfigManager.init(config_path)
        logger.info(
            f"JSON config manager initialized: {ConfigManager.get_config_path()}"
        )
    except Exception as e:
        logger.error(
            f"Failed to initialize JSON config manager: {e}", exc_info=True
        )


def run_uvicorn(creator: AppCreator):
    import uvicorn

    web_config = creator.config.service.web
    # setup_http_service_logging()
    log_level = "info"
    if web_config.log:
        log_level = logging_str_to_uvicorn_level(web_config.log.level)

    loop = "auto"
    try:
        import uvloop

        loop = "uvloop"
    except ImportError:
        pass

    http = "auto"
    try:
        import httptools

        http = "httptools"
    except ImportError:
        pass

    uvicorn.run(
        app=creator.app(),
        factory=True,
        host=web_config.host,
        port=web_config.port,
        log_level=log_level,
        workers=creator.workers(),
        loop=loop,
        http=http,
    )


def run_webserver(config_file: str = None):
    init_json_config_manager()

    if config_file is None:
        creator = CustomAppCreator(config_file)
    else:
        creator = next(
            (
                creator
                for creator in AppCreator.__subclasses__()
                if creator.config_file and creator.config_file.endswith(config_file)
            ),
            CustomAppCreator,
        )(config_file)

    with root_tracer.start_span(
        "run_webserver",
        span_type=SpanType.RUN,
        metadata={
            "run_service": SpanTypeRunName.WEBSERVER,
            "sys_infos": _get_dict_from_obj(get_system_info()),
        },
    ):
        run_uvicorn(creator)


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="DERISK Webserver")
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help=f"Path to the TOML configuration file for service infrastructure. "
        f"Default: configs/derisk-proxy-aliyun.toml. "
        f"Application settings (JSON) are stored in: {DEFAULT_JSON_CONFIG_PATH}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    _args = parse_args()
    _config_file = _args.config
    run_webserver(_config_file)
