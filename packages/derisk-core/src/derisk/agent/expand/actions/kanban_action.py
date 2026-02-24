import logging
from typing import Optional, Tuple, Any

from derisk.agent import Resource, AgentMemory, ConversableAgent, AgentContext, AgentMessage
from derisk.agent.core import system_tool_dict
from derisk.agent.core.action.base import ToolCall, Action
from derisk.agent.expand.actions.system_action import SystemAction
from derisk.agent.expand.actions.tool_action import ToolInput
from derisk.agent.expand.pdca_agent.plan_manager import AsyncKanbanManager
from derisk.agent.resource import BaseTool, ToolPack
from derisk.vis import SystemVisTag
from derisk.vis.schema import TodoListContent

logger = logging.getLogger(__name__)


class KanbanAction(SystemAction):
    name = "KanbanTool"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_view_tag: str = SystemVisTag.VisTodo.value

    async def _get_tool_info(self, resource: Resource, tool_name: str) -> Tuple[Optional[Resource], Optional[BaseTool]]:
        tool_info = None
        if tool_name in system_tool_dict:
            tool_info = system_tool_dict[tool_name]
        return None, tool_info

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional[Action] = None,
        resource: Optional[Resource] = None,
        **kwargs,
    ) -> Optional[Action]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """
        if tool_call.name in ["create_kanban", "submit_deliverable"]:

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

    async def gen_view(self, message_id, tool_call_id, tool_info: BaseTool, status,
                       tool_pack: Optional[ToolPack] = None,
                       args: Optional[Any] = None,
                       out_type: Optional[str] = "json",
                       tool_result: Optional[Any] = None, err_msg: Optional[str] = None, tool_cost: float = 0,
                       start_time: Optional[Any] = None, view_type: Optional[str] = 'all',
                       markdown: Optional[Any] = None, eval_view: Optional[dict] = None, **kwargs):
        logger.info(f"Tool Action gen view!{self.action_view_tag}")
        # 设置进度

        pm: Optional[AsyncKanbanManager] = self.init_params.get('pm')
        todo_dict = await pm.get_todolist_data()

        # Build visualization content
        vis_content = TodoListContent(**todo_dict)
        return self.render_protocol.sync_display(content=vis_content.to_dict())
