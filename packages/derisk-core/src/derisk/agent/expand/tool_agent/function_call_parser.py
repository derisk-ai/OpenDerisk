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
    Parser for native Function Call outputs.

    This parser extracts structured information from language model outputs
    that use native Function Calling capability. It supports:
    1. Native tool_calls from LLM response
    2. Extracting scratch_pad/thought from content or thinking_content
    3. Fallback to XML parsing for backward compatibility
    """

    def __init__(
        self,
        thought_prefix: str = "Thought:",
        action_prefix: str = "Action:",
        action_input_prefix: str = "Action Input:",
        observation_prefix: str = "Observation:",
        terminate_action: str = "terminate",
        extract_scratch_pad: bool = False,
    ):
        """
        Initialize the Function Call output parser.

        Args:
            thought_prefix: Prefix string that indicates the start of a thought (legacy).
            action_prefix: Prefix string that indicates the start of an action (legacy).
            action_input_prefix: Prefix string that indicates the start of action input (legacy).
            observation_prefix: Prefix string that indicates the start of an observation (legacy).
            terminate_action: String that indicates termination action.
            extract_scratch_pad: Whether to try extracting scratch_pad from content.
        """
        self.thought_prefix = thought_prefix
        self.action_prefix = action_prefix
        self.action_input_prefix = action_input_prefix
        self.observation_prefix = observation_prefix
        self.terminate_action = terminate_action
        self.extract_scratch_pad = extract_scratch_pad

        self.thought_prefix_escaped = re.escape(thought_prefix)
        self.action_prefix_escaped = re.escape(action_prefix)
        self.action_input_prefix_escaped = re.escape(action_input_prefix)
        self.observation_prefix_escaped = re.escape(observation_prefix)
        super().__init__()

    @property
    def model_type(self) -> Optional[Type[ReActOut]]:
        return ReActOut

    def parse_actions(
        self, llm_out: AgentLLMOut, action_cls_list: List[Type[Action]], **kwargs
    ) -> Optional[list[Action]]:
        actions: List[Action] = []
        react_out: ReActOut = self.parse(llm_out)
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
        Parse the native Function Call output into structured steps.

        In native Function Call mode:
        1. tool_calls come from llm_out.tool_calls (native LLM response)
        2. thought/scratch_pad comes from content or thinking_content
        3. No need to parse XML format like <tool_calls>

        Args:
            llm_out: The LLM output containing content, thinking_content, and tool_calls.

        Returns:
            ReActOut containing thought, scratch_pad, and steps (tool calls).
        """
        steps = []
        thought = None
        scratch_pad = None

        # Debug log: log what we received
        logger.info(f"FunctionCallOutputParser.parse: tool_calls={llm_out.tool_calls}")
        logger.info(
            f"FunctionCallOutputParser.parse: content length={len(llm_out.content) if llm_out.content else 0}"
        )

        if llm_out.thinking_content:
            thought = llm_out.thinking_content.strip()

        content = llm_out.content.strip() if llm_out.content else ""

        if self.extract_scratch_pad:
            scratch_pad = self._extract_scratch_pad(content)
            if scratch_pad and not thought:
                thought = content.replace(scratch_pad, "").strip()
        elif content and not thought:
            thought = content

        if llm_out.tool_calls:
            for item in llm_out.tool_calls:
                if not isinstance(item, dict):
                    logger.warning(f"tool_call item is not dict: {type(item)}")
                    continue
                tool_call_id = item.get("id", "")
                function_info = item.get("function", {})
                if not isinstance(function_info, dict):
                    logger.warning(f"function info is not dict: {type(function_info)}")
                    continue
                function_name = function_info.get("name")
                func_args = function_info.get("arguments")
                logger.info(
                    f"Parsing tool_call: id={tool_call_id}, name={function_name}, args={func_args[:100] if func_args else None}..."
                )
                try:
                    parsed_args = json.loads(func_args) if func_args else None
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(
                        f"Failed to parse args as JSON: {e}, raw_args={func_args}"
                    )
                    parsed_args = func_args
                steps.append(
                    ToolCall(
                        tool_call_id=tool_call_id, name=function_name, args=parsed_args
                    )
                )

        logger.info(f"FunctionCallOutputParser.parse: steps count={len(steps)}")

        return ReActOut(
            steps=steps if steps else None,
            is_terminal=False,
            thought=thought,
            scratch_pad=scratch_pad,
        )

    def _extract_scratch_pad(self, content: str) -> Optional[str]:
        """
        Extract scratch_pad from content if present.

        Supports both XML format and plain text format.
        """
        if not content:
            return None

        xml_match = re.search(r"<scratch_pad>(.*?)</scratch_pad>", content, re.DOTALL)
        if xml_match:
            return xml_match.group(1).strip()

        return None
