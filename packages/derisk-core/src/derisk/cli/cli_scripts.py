import copy
import logging

import click

logging.basicConfig(
    level=logging.WARNING,
    encoding="utf-8",
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("derisk_cli")


@click.group()
@click.option(
    "--log-level",
    required=False,
    type=str,
    default="warn",
    help="Log level",
)
@click.version_option()
def cli(log_level: str):
    logger.setLevel(logging.getLevelName(log_level.upper()))


def add_command_alias(command, name: str, hidden: bool = False, parent_group=None):
    if not parent_group:
        parent_group = cli
    new_command = copy.deepcopy(command)
    new_command.hidden = hidden
    parent_group.add_command(new_command, name=name)


@click.group()
def start():
    """Start specific server."""
    pass


@click.group()
def stop():
    """Start specific server."""
    pass


@click.group()
def install():
    """Install dependencies, plugins, etc."""
    pass


@click.group()
def db():
    """Manage your metadata database and your datasources."""
    pass


@click.group()
def new():
    """New a template."""
    pass


@click.group()
def app():
    """Manage your apps(derisks)."""
    pass


@click.group()
def repo():
    """The repository to install the derisks from."""
    pass


@click.group()
def run():
    """Run your derisks."""
    pass


@click.group()
def net():
    """Net tools."""
    pass


@click.group()
def tool():
    """DERISK Tools."""


stop_all_func_list = []


@click.command(name="all")
def stop_all():
    """Stop all servers"""
    for stop_func in stop_all_func_list:
        stop_func()


cli.add_command(start)
cli.add_command(stop)
# cli.add_command(install)
cli.add_command(db)
cli.add_command(new)
cli.add_command(app)
cli.add_command(repo)
cli.add_command(run)
cli.add_command(net)
cli.add_command(tool)
add_command_alias(stop_all, name="all", parent_group=stop)

try:
    from derisk.model.cli import (
        _stop_all_model_server,
        model_cli_group,
        start_apiserver,
        start_model_controller,
        start_model_worker,
        stop_apiserver,
        stop_model_controller,
        stop_model_worker,
    )

    add_command_alias(model_cli_group, name="model", parent_group=cli)
    add_command_alias(start_model_controller, name="controller", parent_group=start)
    add_command_alias(start_model_worker, name="worker", parent_group=start)
    add_command_alias(start_apiserver, name="apiserver", parent_group=start)

    add_command_alias(stop_model_controller, name="controller", parent_group=stop)
    add_command_alias(stop_model_worker, name="worker", parent_group=stop)
    add_command_alias(stop_apiserver, name="apiserver", parent_group=stop)
    stop_all_func_list.append(_stop_all_model_server)

except ImportError as e:
    logging.warning(f"Integrating derisk model command line tool failed: {e}")

try:
    from derisk_app._cli import (
        _stop_all_derisk_server,
        migration,
        start_webserver,
        stop_webserver,
    )

    add_command_alias(start_webserver, name="webserver", parent_group=start)
    add_command_alias(stop_webserver, name="webserver", parent_group=stop)
    # Add migration command
    add_command_alias(migration, name="migration", parent_group=db)
    stop_all_func_list.append(_stop_all_derisk_server)

except ImportError as e:
    logging.warning(f"Integrating derisk webserver command line tool failed: {e}")

try:
    from derisk_app.knowledge._cli.knowledge_cli import knowledge_cli_group

    add_command_alias(knowledge_cli_group, name="knowledge", parent_group=cli)
except ImportError as e:
    logging.warning(f"Integrating derisk knowledge command line tool failed: {e}")


try:
    from derisk.util.tracer.tracer_cli import trace_cli_group

    add_command_alias(trace_cli_group, name="trace", parent_group=cli)
except ImportError as e:
    logging.warning(f"Integrating derisk trace command line tool failed: {e}")

try:
    from derisk_serve.utils.cli import serve

    add_command_alias(serve, name="serve", parent_group=new)
except ImportError as e:
    logging.warning(f"Integrating derisk serve command line tool failed: {e}")


try:
    from derisk.util.cli.flow_compat import tool_flow_cli_group
    from derisk.util.derisks.cli import (
        add_repo,
        list_installed_apps,
        list_repos,
        new_derisks,
        reinstall,
        remove_repo,
        update_repo,
    )
    from derisk.util.derisks.cli import install as app_install
    from derisk.util.derisks.cli import list_all_apps as app_list_remote
    from derisk.util.derisks.cli import uninstall as app_uninstall

    add_command_alias(list_repos, name="list", parent_group=repo)
    add_command_alias(add_repo, name="add", parent_group=repo)
    add_command_alias(remove_repo, name="remove", parent_group=repo)
    add_command_alias(update_repo, name="update", parent_group=repo)
    add_command_alias(app_install, name="install", parent_group=app)
    add_command_alias(app_uninstall, name="uninstall", parent_group=app)
    add_command_alias(reinstall, name="reinstall", parent_group=app)
    add_command_alias(app_list_remote, name="list-remote", parent_group=app)
    add_command_alias(list_installed_apps, name="list", parent_group=app)
    add_command_alias(new_derisks, name="app", parent_group=new)
    add_command_alias(tool_flow_cli_group, name="flow", parent_group=tool)

except ImportError as e:
    logging.warning(f"Integrating derisk derisks command line tool failed: {e}")

try:
    from derisk_client._cli import flow as run_flow

    add_command_alias(run_flow, name="flow", parent_group=run)
except ImportError as e:
    logging.warning(f"Integrating derisk client command line tool failed: {e}")

try:
    from derisk.util.network._cli import start_forward

    add_command_alias(start_forward, name="forward", parent_group=net)
except ImportError as e:
    logging.warning(f"Integrating derisk net command line tool failed: {e}")


def main():
    return cli()


if __name__ == "__main__":
    main()
