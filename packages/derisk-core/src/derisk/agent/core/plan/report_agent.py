"""Summary Assistant Agent."""

import logging
from typing import Dict, List, Optional, Tuple

from derisk.rag.retriever.rerank import RetrieverNameRanker

from ... import AgentMessage, Agent
from ...core.action.blank_action import BlankAction
from ...core.base_agent import ConversableAgent
from ...core.profile import DynConfig, ProfileConfig

logger = logging.getLogger(__name__)


class ReportAssistantAgent(ConversableAgent):
    """Reporter Assistant Agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "reporter",
            category="agent",
            key="derisk_agent_reporter_agent_profile_name",
        ),
        role=DynConfig(
            "Report Expert",
            category="agent",
            key="derisk_agent_reporter_agent_profile_role",
        ),
        goal=DynConfig(
            "Summarize answer summaries based on user questions from provided "
            "resource information or from historical conversation memories.",
            category="agent",
            key="derisk_agent_reporter_agent_profile_goal",
        ),
        constraints=DynConfig(
            [
                "Prioritize the summary of answers to user questions from the improved "
                "resource text. If no relevant information is found, summarize it from "
                "the historical dialogue memory given. It is forbidden to make up your "
                "own.",
                "You need to first detect user's question that you need to answer with "
                "your summarization.",
                "Extract the provided text content used for summarization.",
                "Then you need to summarize the extracted text content.",
                "Output the content of summarization ONLY related to user's question. "
                "The output language must be the same to user's question language.",
                "If you think the provided text content is not related to user "
                "questions at all, ONLY output 'Did not find the information you "
                "want.'!!.",
            ],
            category="agent",
            key="derisk_agent_expand_summary_assistant_agent_profile_constraints",
        ),
        desc=DynConfig(
            "You can summarize provided text content according to user's questions"
            " and output the summarization.",
            category="agent",
            key="derisk_agent_expand_summary_assistant_agent_profile_desc",
        ),
    )
    current_goal: str = "答案报告回复"
    def __init__(self, **kwargs):
        """Create a new SummaryAssistantAgent instance."""
        super().__init__(**kwargs)
        self._post_reranks = [RetrieverNameRanker(5)]
        self._init_actions([BlankAction])

    async def load_resource(self, question: str, is_retry_chat: bool = False):
        """Load agent bind resource."""
        if self.resource:
            if self.resource.is_pack:
                prompt_list = []
                info_map = {}
                for resource in self.resource.sub_resources:
                    prompt, resource_reference = await resource.get_prompt(
                        question=question, lang=self.language
                    )
                    prompt_list.append(prompt)
                    if resource_reference is not None:
                        info_map.update(resource_reference)
                return "\n".join(prompt_list), info_map
            else:
                resource_prompt, resource_reference = await self.resource.get_prompt(
                    lang=self.language, question=question
                )
                return resource_prompt, resource_reference
        return None, None

    def post_filters(self, resource_candidates_map: Optional[Dict[str, Tuple]] = None):
        """Post filters for resource candidates."""
        if resource_candidates_map:
            new_candidates_map = resource_candidates_map.copy()
            filter_hit = False
            for resource, (
                candidates,
                references,
                prompt_template,
            ) in resource_candidates_map.items():
                for rerank in self._post_reranks:
                    filter_candidates = rerank.rank(candidates)
                    new_candidates_map[resource] = [], [], prompt_template
                    if filter_candidates and len(filter_candidates) > 0:
                        new_candidates_map[resource] = (
                            filter_candidates,
                            references,
                            prompt_template,
                        )
                        filter_hit = True
                        break
            if filter_hit:
                logger.info("Post filters hit, use new candidates.")
                return new_candidates_map
        return resource_candidates_map
