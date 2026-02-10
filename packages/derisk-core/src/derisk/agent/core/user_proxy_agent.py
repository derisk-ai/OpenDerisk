"""A proxy agent for the user."""

from typing import List, Optional

from .file_system.file_tree import TreeNodeData
from .memory.gpts.gpts_memory import AgentTaskContent, AgentTaskType
from .schema import Status
from .. import  Agent, AgentMessage
from .base_agent import ConversableAgent
from .profile import ProfileConfig

HUMAN_ROLE = "Human"

class UserProxyAgent(ConversableAgent):
    """A proxy agent for the user.

    That can execute code and provide feedback to the other agents.
    """

    profile: ProfileConfig = ProfileConfig(
        name="User",
        role=HUMAN_ROLE,
        description=(
            "A human admin. Interact with the planner to discuss the reasoning_engine. "
            "Plan execution needs to be approved by this admin."
        ),
    )

    is_human: bool = True

    ask_user: bool = False

    show_message: bool = True

    def have_ask_user(self):
        """If have ask user info in message."""
        return self.ask_user

    async def receive(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
        is_recovery: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> None:
        """Receive a message from another agent."""
        if not silent:
            await self._a_process_received_message(message, sender)
        # 收到消息更新节点
        await self.memory.gpts_memory.upsert_task(conv_id=self.agent_context.conv_id,
                                                  task=TreeNodeData(
                                                      node_id=message.message_id,
                                                      parent_id=message.goal_id,
                                                      content=AgentTaskContent(agent_name=sender.name,
                                                                               task_type=AgentTaskType.TASK.value,
                                                                               message_id=message.message_id),
                                                      state=Status.COMPLETE.value,
                                                      name=message.current_goal,
                                                      description="结论"
                                                  ))
        if message.action_report:
            if any([item.ask_user for item in message.action_report]):
                self.ask_user = True
