"""Manages the registration and retrieval of agents."""

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Type, cast

from derisk.component import BaseComponent, ComponentType, SystemApp
from .agent import Agent
from .base_agent import ConversableAgent
from .agent_alias import AgentAliasManager

logger = logging.getLogger(__name__)


def participant_roles(agents: List[Agent]) -> str:
    """Return a string listing the roles of the agents."""
    # Default to all agents registered
    roles = []
    for agent in agents:
        roles.append(f"{agent.name}: {agent.desc}")
    return "\n".join(roles)


def mentioned_agents(message_content: str, agents: List[Agent]) -> Dict:
    """Return a dictionary mapping agent names to mention counts.

    Finds and counts agent mentions in the string message_content, taking word
    boundaries into account.

    Returns: A dictionary mapping agent names to mention counts (to be included,
    at least one mention must occur)
    """
    mentions = dict()
    for agent in agents:
        regex = (
            r"(?<=\W)" + re.escape(agent.name) + r"(?=\W)"
        )  # Finds agent mentions, taking word boundaries into account
        count = len(
            re.findall(regex, " " + message_content + " ")
        )  # Pad the message to help with matching
        if count > 0:
            mentions[agent.name] = count
    return mentions


class AgentManager(BaseComponent):
    """Manages the registration and retrieval of agents."""

    name = ComponentType.AGENT_MANAGER

    def __init__(self, system_app: SystemApp):
        """Create a new AgentManager."""
        super().__init__(system_app)
        self.system_app = system_app
        self._agents: Dict[str, Tuple[Type[ConversableAgent], ConversableAgent]] = (
            defaultdict()
        )
        self._core_agents: Set[str] = set()

    def init_app(self, system_app: SystemApp):
        """Initialize the AgentManager."""
        self.system_app = system_app

    def after_start(self):
        from derisk.util.module_utils import model_scan

        """Register all agents."""
        core_agents = [agent for _, agent in scan_agents("derisk.agent.expand").items()]
        for agent in core_agents:
            self.register_agent(agent)
        self._core_agents = list(core_agents)

        """Register Extend Agent"""
        for _, agent in scan_agents("derisk_ext.agent.agents").items():
            try:
                self.register_agent(agent)
            except Exception as e:
                logger.exception(f"failed to register agent: {_} -- {repr(e)}")

        """Register Manager Agent"""

    def register_agent(
        self, cls: Type[ConversableAgent], ignore_duplicate: bool = False
    ) -> str:
        """Register an agent."""
        logger.info(f"register_agent:{cls}")
        inst = cls()
        profile = inst.role
        if profile in self._agents and (
            profile in self._core_agents or not ignore_duplicate
        ):
            raise ValueError(f"Agent:{profile} already register!")
        self._agents[profile] = (cls, inst)

        # 自动注册Agent别名（从profile.aliases获取）
        aliases = []

        # 方式1：从inst.profile.aliases获取
        if hasattr(inst, "profile"):
            profile_obj = inst.profile
            if hasattr(profile_obj, "aliases") and profile_obj.aliases:
                aliases = profile_obj.aliases
                logger.debug(
                    f"[AgentManager] Found aliases from inst.profile.aliases: {aliases}"
                )

        # 方式2：从profile配置中获取（如果使用DynConfig）
        if not aliases and hasattr(inst, "_profile_config"):
            profile_config = inst._profile_config
            if hasattr(profile_config, "aliases") and profile_config.aliases:
                aliases_value = profile_config.aliases
                if hasattr(aliases_value, "query"):
                    aliases = aliases_value.query()
                elif aliases_value:
                    aliases = aliases_value
                logger.debug(
                    f"[AgentManager] Found aliases from profile config: {aliases}"
                )

        # 注册别名
        if aliases and isinstance(aliases, list):
            AgentAliasManager.register_agent_aliases(profile, aliases)
            logger.info(
                f"[AgentManager] Auto-registered aliases for {profile}: {aliases}"
            )

        return profile

    def get(self, name: str) -> ConversableAgent:
        """Get agent instance by name (supports alias resolution)."""
        resolved_name = AgentAliasManager.resolve_alias(name)

        if resolved_name != name:
            logger.info(f"[AgentManager.get] Resolved alias: {name} -> {resolved_name}")

        if resolved_name in self._agents:
            return self._agents[resolved_name][1]
        else:
            return None

    def get_by_name(self, name: str) -> Type[ConversableAgent]:
        """Return an agent by name (supports alias resolution).

        Args:
            name (str): The name of the agent to retrieve (can be an alias).

        Returns:
            Type[ConversableAgent]: The agent with the given name.

        Raises:
            ValueError: If the agent with the given name is not registered.
        """
        resolved_name = AgentAliasManager.resolve_alias(name)

        if resolved_name != name:
            logger.info(
                f"[AgentManager.get_by_name] Resolved alias: {name} -> {resolved_name}"
            )

        if resolved_name not in self._agents:
            raise ValueError(f"Agent:{name} (resolved: {resolved_name}) not register!")
        return self._agents[resolved_name][0]

    def get_agent(self, name: str) -> ConversableAgent:
        """Return an agent instance by name (supports alias resolution).

        Args:
            name (str): The name of the agent to retrieve (can be an alias).

        Returns:
            Type[ConversableAgent]: The agent instance with the given name.

        Raises:
            ValueError: If the agent with the given name is not registered.
        """
        resolved_name = AgentAliasManager.resolve_alias(name)

        if resolved_name != name:
            logger.info(f"[AgentManager] Resolved alias: {name} -> {resolved_name}")

        if resolved_name not in self._agents:
            raise ValueError(f"Agent:{name} (resolved: {resolved_name}) not register!")
        return self._agents[resolved_name][1]

    def get_describe_by_name(self, name: str) -> str:
        """Return the description of an agent by name (supports alias resolution)."""
        resolved_name = AgentAliasManager.resolve_alias(name)
        return self._agents[resolved_name][1].desc or ""

    def all_agents(self) -> Dict[str, str]:
        """Return a dictionary of all registered agents and their descriptions."""
        result = {}
        for name, value in self._agents.items():
            result[name] = value[1].desc or ""
        return result

    def list_agents(self):
        """Return a list of all registered agents and their descriptions."""
        global _CACHED_AGENTS
        if _CACHED_AGENTS:
            return _CACHED_AGENTS

        result = []
        for name, value in self._agents.items():
            goal = value[1].goal
            desc = value[1].desc if hasattr(value[1], "desc") else ""
            result.append(
                {
                    "name": value[1].role,
                    "desc": desc or goal,
                    "is_team": True
                    if hasattr(value[1], "is_team") and value[1].is_team
                    else False,
                }
            )
        result.sort(key=lambda a: a["name"])
        _CACHED_AGENTS = result
        return result


_CACHED_AGENTS = []

_SYSTEM_APP: Optional[SystemApp] = None


def initialize_agent(system_app: SystemApp):
    """Initialize the agent manager."""
    global _SYSTEM_APP
    _SYSTEM_APP = system_app
    agent_manager = AgentManager(system_app)
    system_app.register_instance(agent_manager)


def get_agent_manager(system_app: Optional[SystemApp] = None) -> AgentManager:
    """Return the agent manager.

    Args:
        system_app (Optional[SystemApp], optional): The system app. Defaults to None.

    Returns:
        AgentManager: The agent manager.
    """
    if not _SYSTEM_APP:
        if not system_app:
            system_app = SystemApp()
        initialize_agent(system_app)
    app = system_app or _SYSTEM_APP
    return AgentManager.get_instance(cast(SystemApp, app))


def scan_agents(path: str):
    """Scan and register all agents."""
    from derisk.util.module_utils import ModelScanner, ScannerConfig

    from .base_agent import ConversableAgent

    scanner = ModelScanner[ConversableAgent]()

    config = ScannerConfig(
        module_path=path,
        base_class=ConversableAgent,
        recursive=True,
    )
    scanner.scan_and_register(config)
    return scanner.get_registered_items()
