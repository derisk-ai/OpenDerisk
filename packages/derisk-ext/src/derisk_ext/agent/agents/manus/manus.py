from derisk.agent.core.profile import DynConfig, ProfileConfig
from derisk_ext.agents.expand.react import ReActAgent


class Manus(ReActAgent):
    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "Manus",
            category="agent",
            key="derisk_agent_expand_manus_name",
        ),
        role=DynConfig(
            "General Assistant",
            category="agent",
            key="derisk_agent_expand_manus_role",
        ),
        goal=DynConfig(
            """
            A versatile general-purpose assistant that can uses planning to solve various tasks.
            This agent extends PlanningAgent with a comprehensive set of tools and capabilities,
            including Python execution, web browsing, file operations, and information retrieval
            to handle a wide range of user requests.
            """,
            category="agent",
            key="derisk_agent_expand_manus_goal",
        ),
        constraints=DynConfig(
            [
                "Please read the user's request carefully and extract the specific parameters "
            ],
            category="agent",
            key="derisk_agent_expand_manus_constraints",
        ),
        desc=DynConfig(
            "You can use the following following tools to complete the task objectives: {tool_infos}",
            category="agent",
            key="derisk_agent_expand_manus_desc",
        ),
    )
