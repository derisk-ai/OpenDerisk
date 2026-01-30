import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Type

from derisk.agent import Action, BlankAction
from derisk.agent.core.action.base import ToolCall
from derisk.agent.core.base_parser import AgentParser, SchemaType

from derisk.agent.expand.actions.agent_action import AgentStart
from derisk.agent.expand.actions.knowledge_action import KnowledgeSearch
from derisk.agent.util.llm.llm_client import AgentLLMOut

from derisk.util.json_utils import extract_tool_calls

logger = logging.getLogger(__name__)


@dataclass
class ReActOut:
    thought: Optional[str] = None
    scratch_pad: Optional[str] = None
    steps: Optional[List[ToolCall]] = None
    is_terminal: bool = False


AGENT_MARK = [AgentStart.name]
KNOWLEDGE_MARK = [KnowledgeSearch.name]
USER_INTERACTION_MARK = ["send_to_user"]
MEMORY_MARK = ["summary", "review"]


class FunctionCallOutputParser(AgentParser):
    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.TEXT
    """
    Parser for ReAct format model outputs with configurable prefixes.

    This parser extracts structured information from language model outputs
    that follow the ReAct pattern: Thought -> Action -> Action Input -> Observation.
    """

    def __init__(
        self,
        thought_prefix: str = "Thought:",
        action_prefix: str = "Action:",
        action_input_prefix: str = "Action Input:",
        observation_prefix: str = "Observation:",
        terminate_action: str = "terminate",
    ):
        """
        Initialize the ReAct output parser with configurable prefixes.

        Args:
            thought_prefix: Prefix string that indicates the start of a thought.
            action_prefix: Prefix string that indicates the start of an action.
            action_input_prefix: Prefix string that indicates the start of action input.
            observation_prefix: Prefix string that indicates the start of an
                observation.
            terminate_action: String that indicates termination action.
        """
        self.thought_prefix = thought_prefix
        self.action_prefix = action_prefix
        self.action_input_prefix = action_input_prefix
        self.observation_prefix = observation_prefix
        self.terminate_action = terminate_action

        # Escape special regex characters in prefixes
        self.thought_prefix_escaped = re.escape(thought_prefix)
        self.action_prefix_escaped = re.escape(action_prefix)
        self.action_input_prefix_escaped = re.escape(action_input_prefix)
        self.observation_prefix_escaped = re.escape(observation_prefix)
        super().__init__()

    @property
    def model_type(self) -> Optional[Type[ReActOut]]:
        return ReActOut

    def parse_actions(self, llm_out: AgentLLMOut, action_cls_list: List[Type[Action]], **kwargs) -> Optional[
        list[Action]]:

        actions: List[Action] = []
        react_out: ReActOut = self.parse(llm_out)
        ## 根据工具名称解析Action
        if not react_out.steps:
            actions.append(BlankAction(terminate=True))
        else:
            for item in react_out.steps:

                for action_cls in action_cls_list:
                    action = action_cls.parse_action(item, **kwargs)
                    if action:
                        actions.append(action)
                        break
        return actions

    def parse(self, llm_out: AgentLLMOut) -> ReActOut:
        """
        Parse the ReAct format output text into structured steps.

        Args:
            llm_out: The LLM Out.

        Returns:
            List of ReActStep dataclasses, each containing thought, action,
                action_input, and observation.
        """

        # Split the text into steps based on thought prefix
        steps = []

        # Remove any leading/trailing whitespace

        thought = llm_out.content
        if llm_out.tool_calls:
            for item in llm_out.tool_calls:
                tool_call_id = item['id']
                function_name = item['function'].get("name")
                func_args = item['function'].get("arguments")
                steps.append(ToolCall(tool_call_id=tool_call_id, name=function_name, args=json.loads(func_args) if func_args else None))

        return ReActOut(steps=steps, is_terminal=False, thought=thought)
