from typing import Optional, Dict

from derisk.agent import Resource, AgentMemory, ConversableAgent, AgentContext
from derisk.agent.core import sandbox_tool_dict
from derisk.agent.core.action.base import ToolCall
from derisk.agent.core.sandbox.tools.browser_tool import BROWSER_TOOLS
from derisk.agent.expand.actions.tool_action import ToolInput, ToolAction


class SandboxAction(ToolAction):
    name = "SandboxTool"

    async def tool_init_params(self) -> Optional[Dict]:
        """准备工具默认初始化参数"""
        return {

        }

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
        if tool_call.name in sandbox_tool_dict:
            agent: ConversableAgent = kwargs.get('agent')
            agent_context: AgentContext = kwargs.get('agent_context')
            if not agent.sandbox_manager or not agent.sandbox_manager.client:
                raise ValueError("没有可用的沙箱环境,无法使用沙箱环境工具！")
            sandbox_client = agent.sandbox_manager.client
            return cls(action_uid=tool_call.tool_call_id,
                       action_input=ToolInput(tool_name=tool_call.name,
                                              tool_call_id=tool_call.tool_call_id,
                                              thought=tool_call.thought,
                                              args=tool_call.args),
                       init_params={
                           "client": sandbox_client,
                           "conversation_id": agent_context.conv_id,
                       })
        else:
            return None
