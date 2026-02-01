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


# Action marks for filtering
AGENT_MARK = [AgentStart.name]
KNOWLEDGE_MARK = [KnowledgeSearch.name]
USER_INTERACTION_MARK = ["send_to_user"]
MEMORY_MARK = ["summary", "review"]

# Constants for LLM output keys
CONST_LLMOUT_THOUGHT = "thought"
CONST_LLMOUT_TITLE = "scratch_pad"
CONST_LLMOUT_TOOLS = "tool_calls"

# XML tag patterns
_TAG_PATTERNS = {
    "scratch_pad": r"<scratch_pad>(.*?)</scratch_pad>",
    "thought": r"<thought>(.*?)</thought>",
    "tool_calls": r"<tool_calls>(.*?)</tool_calls>",
}


def _extract_xml_tag(text: str, tag: str) -> Optional[str]:
    """Extract content within an XML tag.

    Args:
        text: The text to search in.
        tag: The tag name (without angle brackets).

    Returns:
        The extracted content or None if not found.
    """
    pattern = _TAG_PATTERNS.get(tag)
    if not pattern:
        return None
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


class ReActOutputParser(AgentParser):
    """Parser for ReAct format model outputs using XML tags.

    This parser extracts structured information from language model outputs
    that follow the pattern:
        <scratch_pad>...</scratch_pad>
        <thought>...</thought>
        <tool_calls>[...]</tool_calls>
    """

    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.XML

    @property
    def model_type(self) -> Optional[Type[ReActOut]]:
        return ReActOut

    def parse_actions(
        self, llm_out: AgentLLMOut, action_cls_list: List[Type[Action]], **kwargs
    ) -> Optional[list[Action]]:
        """Parse actions from LLM output.

        Args:
            llm_out: The LLM output.
            action_cls_list: List of Action classes to try parsing with.
            **kwargs: Additional arguments.

        Returns:
            List of parsed actions.
        """
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
        """Parse ReAct format output into structured components.

        Args:
            llm_out: The LLM output containing text.

        Returns:
            ReActOut object with parsed thought, scratch_pad, and tool_calls.
        """
        text = llm_out.content.strip()

        # Extract XML tag contents
        scratch_pad = _extract_xml_tag(text, "scratch_pad")
        thought = _extract_xml_tag(text, "thought")

        # Extract and parse tool calls
        tool_calls_str = _extract_xml_tag(text, "tool_calls")
        steps: List[ToolCall] = []

        if tool_calls_str:
            tool_calls_str = tool_calls_str.strip()
            try:
                tool_calls = extract_tool_calls(tool_calls_str)
                for item in tool_calls:
                    for k, v in item.items():
                        steps.append(ToolCall(name=k, args=v))
            except Exception as e:
                logger.warning(f"Failed to parse tool_calls: {e}")

        # Log for debugging (optional, can be removed for production)
        if not scratch_pad:
            logger.debug("未找到 <scratch_pad> 标签内容")
        if not thought:
            logger.debug("未找到 <thought> 标签内容")
        if not tool_calls_str and steps:
            logger.debug("解析到的工具调用为空")

        return ReActOut(
            steps=steps,
            is_terminal=False,
            thought=thought,
            scratch_pad=scratch_pad,
        )