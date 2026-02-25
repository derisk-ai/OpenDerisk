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

CONST_LLMOUT_THOUGHT = "thought"
CONST_LLMOUT_TITLE = "scratch_pad"
CONST_LLMOUT_TOOLS = "tool_calls"


class ReActOutputParser(AgentParser):
    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.XML
    """
    Parser for ReAct format model outputs with configurable prefixes.

    This parser extracts structured information from language model outputs
    that follow the ReAct pattern: Thought -> Action -> Action Input -> Observation.
    
    Supports two tool_call formats:
    1. Named format: {"tool_name": "...", "args": {...}, "thought": "..."} 
    2. Compact format: {"工具名": {参数对象}}
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

    def _parse_tool_call_item(self, item: dict) -> Optional[ToolCall]:
        """
        Parse a single tool call item, supporting two formats:

        Format 1 (Named): {"tool_name": "...", "args": {...}, "thought": "..."}
        Format 2 (Compact): {"工具名": {参数对象}} 或 {"工具名": {参数对象}, "thought": "..."}

        Args:
            item: A dictionary representing a tool call

        Returns:
            ToolCall object or None if parsing fails
        """
        if not isinstance(item, dict):
            return None

        # Format 1: Named format with tool_name/name/action key
        name = item.get("tool_name") or item.get("name") or item.get("action")
        if name:
            args = item.get("args", {})
            thought = item.get("thought")
            if args is None:
                args = {}
            return ToolCall(name=name, args=args, thought=thought)

        # Format 2: Compact format {"工具名": {参数}}
        # In this format, the key is the tool name and the value is the args
        # It might also have a "thought" key
        thought = item.get("thought")
        for key, value in item.items():
            if key == "thought":
                continue
            # The key is the tool name, value should be the args dict
            if isinstance(value, dict):
                return ToolCall(name=key, args=value, thought=thought)
            elif value is None:
                # Tool with no args
                return ToolCall(name=key, args={}, thought=thought)

        return None

    @property
    def model_type(self) -> Optional[Type[ReActOut]]:
        return ReActOut

    def parse_actions(
        self, llm_out: AgentLLMOut, action_cls_list: List[Type[Action]], **kwargs
    ) -> Optional[list[Action]]:
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
            llm_out: The llm out.

        Returns:
            List of ReActStep dataclasses, each containing thought, action,
                action_input, and observation.
        """

        # Split the text into steps based on thought prefix
        steps = []

        # Remove any leading/trailing whitespace
        text = llm_out.content.strip()

        # 提取 <scratch_pad> 内容
        scratch_pad = ""
        scratch_pad_match = re.search(
            r"<scratch_pad>(.*?)</scratch_pad>", text, re.DOTALL
        )
        if scratch_pad_match:
            scratch_pad = scratch_pad_match.group(1).strip()
        else:
            logger.warning("未找到 <scratch_pad> 标签内容")

        # 提取 <thought> 内容
        thought = ""
        thought_match = re.search(r"<thought>(.*?)</thought>", text, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()
        else:
            logger.warning("未找到 <thought> 标签内容")

        # 提取 <tool_calls> 内容
        steps = []
        tool_calls_match = re.search(
            r"<tool_calls>(.*?)(?:</tool_calls>|\Z)", text, re.DOTALL
        )

        if tool_calls_match:
            # group(1) 捕获的是 <tool_calls> 和 (</tool_calls> 或字符串末尾) 之间的内容
            tool_calls_str = tool_calls_match.group(1).strip()
            tool_calls = extract_tool_calls(tool_calls_str)
            for item in tool_calls:
                parsed = self._parse_tool_call_item(item)
                if parsed:
                    steps.append(parsed)
        else:
            logger.warning("未找到 <tool_calls> 标签内容")

        return ReActOut(
            steps=steps, is_terminal=False, thought=thought, scratch_pad=scratch_pad
        )
