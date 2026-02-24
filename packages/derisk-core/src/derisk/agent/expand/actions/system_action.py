from typing import Optional, Tuple

from derisk.agent import Resource, AgentMemory, ConversableAgent, AgentContext, AgentMessage
from derisk.agent.core import system_tool_dict
from derisk.agent.core.action.base import ToolCall
from derisk.agent.expand.actions.tool_action import ToolAction, ToolInput
from derisk.agent.expand.pdca_agent.plan_manager import AsyncKanbanManager
from derisk.agent.resource import BaseTool
from derisk.vis import SystemVisTag


class SystemAction(ToolAction):
    name = "SystemTool"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_view_tag: str = SystemVisTag.VisTool.value

    async def _get_tool_info(self, resource: Resource, tool_name: str) -> Tuple[Optional[Resource], Optional[BaseTool]]:
        tool_info = None
        if tool_name in system_tool_dict:
            tool_info = system_tool_dict[tool_name]
        return None, tool_info

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional["Action"] = None,
        resource: Optional[Resource] = None,
        **kwargs,
    ) -> Optional["Action"]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """
        if tool_call.name in system_tool_dict:

            agent: ConversableAgent = kwargs.get('agent')
            memory: AgentMemory = agent.memory if agent else None
            agent_context: AgentContext = kwargs.get('agent_context')
            pm: AsyncKanbanManager = kwargs.get('pm')
            received_message: AgentMessage = kwargs.get('received_message')

            return cls(action_uid=tool_call.tool_call_id,
                       action_input=ToolInput(tool_name=tool_call.name,
                                              tool_call_id=tool_call.tool_call_id,
                                              thought=tool_call.thought,
                                              args=tool_call.args),
                       init_params={
                           "agent": agent,
                           "pm": pm,
                           "memory": memory,
                           "conversation_id": agent_context.conv_id,
                           "goal_id": received_message.message_id,
                       })
        else:
            return None
