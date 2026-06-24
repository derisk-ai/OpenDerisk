import functools
import logging

import click

from derisk.util.i18n_utils import _

logger = logging.getLogger("derisk_cli")


def add_start_server_options(func):
    @click.option(
        "-c",
        "--config",
        type=str,
        required=True,
        help=(_("The config file to start server")),
    )
    @click.option(
        "-d",
        "--daemon",
        is_flag=True,
        help=(
            _(
                "Run in daemon mode. It will run in the background. If you want to stop"
                " it, use `derisk stop` command"
            )
        ),
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper
