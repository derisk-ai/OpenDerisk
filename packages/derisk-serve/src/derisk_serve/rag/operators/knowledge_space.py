import asyncio
from abc import ABC
from functools import reduce
from typing import List, Optional, Any

from derisk.core import (
    BaseMessage,
    ChatPromptTemplate,
    HumanPromptTemplate,
    ModelMessage,
)
from derisk.core.awel import JoinOperator
from derisk.core.awel.flow import (
    FunctionDynamicOptions,
    IOField,
    OperatorCategory,
    OperatorType,
    OptionValue,
    Parameter,
    ViewMetadata,
)
from derisk.core.awel.task.base import IN, OUT
from derisk.core.interface.operators.prompt_operator import BasePromptBuilderOperator
from derisk.core.interface.operators.retriever import RetrieverOperator
from derisk.rag.embedding.embedding_factory import RerankEmbeddingFactory
from derisk.rag.retriever.rerank import RerankEmbeddingsRanker
from derisk.util.function_utils import rearrange_args_by_type
from derisk.util.i18n_utils import _
from derisk_serve.rag.retriever.knowledge_space import KnowledgeSpaceRetriever


# def _load_space_name() -> List[OptionValue]:
#     return [
#         OptionValue(label=space.name, name=space.name, value=space.name)
#         for space in knowledge_space_service.get_knowledge_space(
#             KnowledgeSpaceRequest()
#         )
#     ]


class SpaceRetrieverOperator(RetrieverOperator[IN, OUT], ABC):
    """knowledge space retriever operator."""

    # metadata = ViewMetadata(
    #     label=_("Knowledge Base Operator"),
    #     name="space_operator",
    #     category=OperatorCategory.RAG,
    #     description=_("knowledge space retriever operator."),
    #     inputs=[IOField.build_from(_("Query"), "query", str, _("user query"))],
    #     outputs=[
    #         IOField.build_from(
    #             _("related chunk content"),
    #             "related chunk content",
    #             List,
    #             description=_("related chunk content"),
    #         )
    #     ],
    #     parameters=[
    #         Parameter.build_from(
    #             _("Space Name"),
    #             "space_name",
    #             str,
    #             options=FunctionDynamicOptions(func=_load_space_name),
    #             optional=False,
    #             default=None,
    #             description=_("space name."),
    #         )
    #     ],
    #     documentation_url="https://github.com/openai/openai-python",
    # )

    def __init__(
        self,
        knowledge_ids: Optional[List[str]],
        rerank_top_k: Optional[int] = 5,
        similarity_top_k: Optional[int] = 10,
        retrieve_mode: Optional[str] = "semantic",
        metadata_filter: Optional[bool] = True,
        rerank: Optional[bool] = True,
        similarity_score_threshold: Optional[float] = 0.0,
        bm25_score_threshold: Optional[float] = 0.0,
        rerank_score_threshold: Optional[float] = 0.3,
        system_app: Optional[Any] = None,
        **kwargs,
    ):
        """
        Args:
            space_id (str): The space name.
            top_k (Optional[int]): top k.
            score_threshold (
            Optional[float], optional
            ): The recall score. Defaults to 0.3.
        """
        self._knowledge_ids = knowledge_ids
        self._top_k = rerank_top_k
        self._score_threshold = rerank_score_threshold
        self._similarity_top_k = similarity_top_k
        self._similarity_score_threshold = similarity_score_threshold
        self._bm25_score_threshold = bm25_score_threshold
        self._retrieve_mode = retrieve_mode
        self._rerank = rerank
        self._metadata_filter = metadata_filter
        self._system_app = system_app

        super().__init__(**kwargs)

    async def aretrieve(self, query: IN) -> OUT:
        """Map input value to output value.

        Args:
            query (IN): The input value.

        Returns:
            OUT: The output value.
        """

        search_tasks = []
        query = query.get("query")
        # todo multi thread
        for knowledge_id in self._knowledge_ids:
            space_retriever = KnowledgeSpaceRetriever(
                space_id=knowledge_id,
                top_k=self._top_k,
                system_app=self._system_app,
            )

            if isinstance(query, str):
                search_tasks.append(
                    space_retriever.aretrieve_with_scores(
                        query, self._similarity_score_threshold
                    )
                )
            elif isinstance(query, list):
                search_tasks = [
                    space_retriever.aretrieve_with_scores(
                        q, self._similarity_score_threshold
                    )
                    for q in query
                ]
                # candidates = await asyncio.gather(*search_tasks)
        task_results = await asyncio.gather(*search_tasks)
        candidates = reduce(lambda x, y: x + y, task_results)
        if self._rerank:
            rerank_embeddings = RerankEmbeddingFactory.get_instance(
                self.system_app
            ).create()
            reranker = RerankEmbeddingsRanker(
                rerank_embeddings, topk=self._top_k
            )
            rerank_candidates = reranker.rank(candidates, query)

            return rerank_candidates


class KnowledgeSpacePromptBuilderOperator(
    BasePromptBuilderOperator, JoinOperator[List[ModelMessage]]
):
    """The operator to build the prompt with static prompt.

    The prompt will pass to this operator.
    """

    metadata = ViewMetadata(
        label=_("Knowledge Space Prompt Builder Operator"),
        name="knowledge_space_prompt_builder_operator",
        description=_("Build messages from prompt template and chat history."),
        operator_type=OperatorType.JOIN,
        category=OperatorCategory.CONVERSION,
        parameters=[
            Parameter.build_from(
                _("Chat Prompt Template"),
                "prompt",
                ChatPromptTemplate,
                description=_("The chat prompt template."),
            ),
            Parameter.build_from(
                _("History Key"),
                "history_key",
                str,
                optional=True,
                default="chat_history",
                description=_("The key of history in prompt dict."),
            ),
            Parameter.build_from(
                _("String History"),
                "str_history",
                bool,
                optional=True,
                default=False,
                description=_("Whether to convert the history to string."),
            ),
        ],
        inputs=[
            IOField.build_from(
                _("user input"),
                "user_input",
                str,
                is_list=False,
                description=_("user input"),
            ),
            IOField.build_from(
                _("space related context"),
                "related_context",
                List,
                is_list=False,
                description=_("context of knowledge space."),
            ),
            IOField.build_from(
                _("History"),
                "history",
                BaseMessage,
                is_list=True,
                description=_("The history."),
            ),
        ],
        outputs=[
            IOField.build_from(
                _("Formatted Messages"),
                "formatted_messages",
                ModelMessage,
                is_list=True,
                description=_("The formatted messages."),
            )
        ],
    )

    def __init__(
        self,
        prompt: ChatPromptTemplate,
        history_key: str = "chat_history",
        check_storage: bool = True,
        str_history: bool = False,
        **kwargs,
    ):
        """Create a new history dynamic prompt builder operator.
        Args:

            prompt (ChatPromptTemplate): The chat prompt template.
            history_key (str, optional): The key of history in prompt dict. Defaults to
                "chat_history".
            check_storage (bool, optional): Whether to check the storage. Defaults to
                True.
            str_history (bool, optional): Whether to convert the history to string.
                Defaults to False.
        """

        self._prompt = prompt
        self._history_key = history_key
        self._str_history = str_history
        BasePromptBuilderOperator.__init__(self, check_storage=check_storage, **kwargs)
        JoinOperator.__init__(self, combine_function=self.merge_context, **kwargs)

    @rearrange_args_by_type
    async def merge_context(
        self,
        user_input: str,
        related_context: List[str],
        history: Optional[List[BaseMessage]],
    ) -> List[ModelMessage]:
        """Merge the prompt and history."""
        prompt_dict = dict()
        prompt_dict["context"] = related_context
        for prompt in self._prompt.messages:
            if isinstance(prompt, HumanPromptTemplate):
                prompt_dict[prompt.input_variables[0]] = user_input

        if history:
            if self._str_history:
                prompt_dict[self._history_key] = BaseMessage.messages_to_string(history)
            else:
                prompt_dict[self._history_key] = history
        return await self.format_prompt(self._prompt, prompt_dict)
