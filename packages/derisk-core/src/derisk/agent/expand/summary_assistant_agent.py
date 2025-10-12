"""Summary Assistant Agent."""

import logging
from typing import Dict, List, Optional, Tuple

from derisk.rag.retriever.rerank import RetrieverNameRanker
from derisk_serve.agent.resource.knowledge_pack import KnowledgePackSearchResource
from derisk_serve.agent.resource.tool.local_tool import LocalToolPack

from .. import AgentMessage, Agent, Resource
from ..core.action.blank_action import BlankAction
from ..core.base_agent import ConversableAgent
from ..core.profile import DynConfig, ProfileConfig
from ..resource import ToolPack

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """
您是一个总结专家,您的目标是 根据找到的知识{{resource_prompt}}或历史对话记忆
{{most_recent_memories}}进行归纳总结，专业且有逻辑的回答用户问题。 
1.请用中文回答
2. 总结回答时请务必保留原文中的图片、引用、视频等链接内容
3. 原文中的图片、引用、视频等链接格式, 出现在原文内容中，内容后，段落中都可以认为属于原文内容，请确保在总结答案中依然输出这些内容，不要丢弃，不要修改.(参考图片链接格式：![image.png](xxx) 、普通链接格式:[xxx](xxx))
4.优先从给出的资源中总结用户问题答案，如果没有找到相关信息，则尝试从当前会话的历史对话记忆中找相关信息，忽略无关的信息.
5. 回答时总结内容需要结构良好的，中文字数不超过150字，尽可能涵盖上下文里面所有你认为有用的知识点，如果提供的资源信息带有图片![image.png](xxx) ，链接[xxx](xxx))或者表格,总结的时候也将图片，链接，表格按照markdown格式进行输出。
6. 注意需要并在每段总结的**中文**末尾结束标点符号前面注明内容来源的链接编号,语雀链接,语雀标题[[i]](https://yuque_url.com),i 为引用的序号，eg:1,2,3。

## 用户问题:
{{question}}
"""
USER_PROMPT_TEMPLATE = """"""

class SummaryAssistantAgent(ConversableAgent):
    """Summary Assistant Agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "Aristotle",
            category="agent",
            key="derisk_agent_expand_summary_assistant_agent_profile_name",
        ),
        role=DynConfig(
            "Summarizer",
            category="agent",
            key="derisk_agent_expand_summary_assistant_agent_profile_role",
        ),
        goal=DynConfig(
            "Summarize answer summaries based on user questions from provided "
            "resource information or from historical conversation memories.",
            category="agent",
            key="derisk_agent_expand_summary_assistant_agent_profile_goal",
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
        system_prompt_template=SYSTEM_PROMPT_TEMPLATE,
        user_prompt_template=USER_PROMPT_TEMPLATE,
        desc=DynConfig(
            "You can summarize provided text content according to user's questions"
            " and output the summarization.",
            category="agent",
            key="derisk_agent_expand_summary_assistant_agent_profile_desc",
        ),
    )

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
                resource_reference = {}
                for resource in self.resource.sub_resources:
                    if isinstance(resource, KnowledgePackSearchResource):
                        prompt, resource_reference = await resource.get_prompt(
                            question=question, lang=self.language
                        )
                        prompt_list.append(prompt)
                    if isinstance(resource, LocalToolPack):
                        if resource.sub_resources:
                            tool = resource.sub_resources[0]
                            tool_result = await self.run_tool(
                                name=tool.name,
                                args={
                                    "query": question
                                },
                                resource=resource,
                            )
                            prompt_list.append(tool_result)
                if resource_reference is not None:
                    info_map.update(resource_reference)
                return "\n".join(prompt_list), info_map
            else:
                resource_prompt, resource_reference = await self.resource.get_prompt(
                    lang=self.language, question=question
                )
                return resource_prompt, resource_reference
        return None, None

    async def init_reply_message(
        self,
        received_message: AgentMessage,
        rely_messages: Optional[List[AgentMessage]] = None,
        sender: Optional[Agent] = None,
        rounds: Optional[int] = None,
    ) -> AgentMessage:
        reply_message = await super().init_reply_message(
            received_message=received_message,
            rely_messages=rely_messages,
            sender=sender,
            rounds=rounds,
        )
        reply_message.context = {
            "user_question": received_message.content,
        }
        return reply_message

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

    async def run_tool(
        self,
        name: str,
        args: dict,
        resource: Resource,
        raw_tool_input: Optional[str] = None,
    ) -> str:
        """Run the tool."""
        is_terminal = None
        try:
            tool_packs = ToolPack.from_resource(resource)
            if not tool_packs:
                raise ValueError("The tool resource is not found！")
            tool_pack: ToolPack = tool_packs[0]

            from derisk.agent.resource import BaseTool
            tool_info: BaseTool = await tool_pack.get_resources_info(resource_name=name)
            logger.info(tool_info)

            if raw_tool_input and tool_pack.parse_execute_args(
                resource_name=name, input_str=raw_tool_input
            ):
                parsed_args = tool_pack.parse_execute_args(
                    resource_name=name, input_str=raw_tool_input
                )
                if parsed_args and isinstance(parsed_args, tuple):
                    args = parsed_args[1]

            try:
                tool_result = await tool_pack.async_execute(resource_name=name, **args)
            except Exception as e:
                logger.exception(f"Tool [{name}] execute failed!")
                err_msg = f"Tool [{tool_pack.name}:{name}] execute failed! {str(e)}"
                tool_result = err_msg

            return str(tool_result)
        except Exception as e:
            logger.exception("Tool Action Run Failed！")
            return "Tool Action Run Failed！"
