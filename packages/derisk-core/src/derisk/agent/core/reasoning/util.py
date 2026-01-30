from derisk.agent import Agent
from derisk.agent.core.base_team import ManagerAgent


def is_summary_agent(agent: Agent) -> bool:
    if not agent:
        return False
    if not hasattr(agent, "reasoning_engine"):
        return False

    reasoning_engine = getattr(agent, "reasoning_engine")
    if not reasoning_engine:
        return False

    from derisk_ext.reasoning_engine.summary_reasoning_engine import SummaryReasoningEngine
    return isinstance(reasoning_engine, SummaryReasoningEngine)


def has_summary_sub_agent(agent: Agent) -> bool:
    if not agent or not isinstance(agent, ManagerAgent):
        return False

    return any((sub_agent for sub_agent in agent.agents if is_summary_agent(sub_agent)))


def find_summary_agent(agent: ManagerAgent) -> Agent | None:
    """Find current Summary Agent"""

    if not agent or not isinstance(agent, ManagerAgent):
        return None

    return next((sub_agent for sub_agent in agent.agents if is_summary_agent(sub_agent)), None)