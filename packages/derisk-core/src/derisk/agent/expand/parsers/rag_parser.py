from enum import Enum
from typing import Optional, Type, List, Union

from derisk._private.pydantic import BaseModel, Field, model_to_dict
from derisk.agent import Action, BlankAction, AgentMessage
from derisk.agent.core.base_parser import AgentParser, SchemaType
from derisk.agent.core.reasoning.reasoning_action import KnowledgeRetrieveAction, KnowledgeRetrieveActionInput
from derisk.agent.expand.actions.tool_action import ToolAction, ToolInput
from derisk.agent.util.llm.llm_client import AgentLLMOut


class AgenticRAGState(Enum):
    """Enum for Deep Search Action states."""
    REFLECTION = "reflection"
    FINAL_SUMMARIZE = "final_summarize"


class AgenticRAGModel(BaseModel):
    """Model for AgenticRAG."""
    knowledge: Optional[List[str]] = Field(
        None,
        description="List of knowledge IDs to be used in the action.",
    )
    tools: Optional[List[dict]] = Field(
        None,
        description="List of tools to be used in the action, each tool is a dict with 'tool' and 'args'.",
    )
    intention: Optional[str] = Field(
        None,
        description="Intention of the action, a concise description of the action's goal.",
    )

    def to_dict(self):
        """Convert to dict."""
        return model_to_dict(self)


class RagAgentParaser(AgentParser[AgenticRAGModel]):
    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.JSON

    @property
    def model_type(self) -> Optional[Type[AgenticRAGModel]]:
        return AgenticRAGModel

    def parse_actions(self, llm_out:  AgentLLMOut, action_cls_list: List[Type[Action]], **kwargs) -> Optional[list[Action]]:
        received_message: Optional[AgentMessage] = kwargs.get("received_message")
        state: Optional[str] = kwargs.get("state")
        actions: List[Action] = []
        if state == AgenticRAGState.FINAL_SUMMARIZE.value:
            actions.append(BlankAction(terminate=True))
        else:
            rag_out: AgenticRAGModel = self.parse(llm_out)
            if rag_out.tools:
                for tool in rag_out.tools:
                    tool_action = ToolAction()
                    tool_action.action_input = ToolInput(tool_name=tool["tool"], args=tool["args"], thought=None)
                    actions.append(tool_action)
            elif rag_out.knowledge:
                kn_action = KnowledgeRetrieveAction()
                kn_action.action_input = KnowledgeRetrieveActionInput(func="search", knowledge_ids=rag_out.knowledge,
                                                                      query=received_message.content if received_message else "")
                actions.append(kn_action)
            else:
                pass
                # raise ValueError(f"没有可用的数据来源！")

        return actions
