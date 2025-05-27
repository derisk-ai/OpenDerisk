import dataclasses
import logging
from typing import Any, List, Optional, Type, cast

from derisk import SystemApp
from derisk.agent import ResourceType
from derisk.agent.resource.knowledge import (
    RetrieverResource,
    RetrieverResourceParameters,
)
from derisk.core import Chunk
from derisk.util import ParameterDescription
from derisk.util.i18n_utils import _
from derisk_serve.rag.api.schemas import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from derisk_serve.rag.service.service import Service

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class KnowledgePackLoadResourceParameters(RetrieverResourceParameters):
    knowledges: List[dict] = dataclasses.field(
        default=None, metadata={"help": _("Knowledge space ids")}
    )
    top_k: int = dataclasses.field(
        default=10, metadata={"help": _("Knowledge retriver top k")}
    )
    similarity_score_threshold: Optional[float] = dataclasses.field(
        default=0.0, metadata={"help": _("similarity_score_threshold")}
    )
    score_threshold: Optional[float] = dataclasses.field(
        default=0.0, metadata={"help": _("Knowledge score threshold")}
    )
    single_knowledge_top_k: Optional[int] = dataclasses.field(
        default=20, metadata={"help": _("Single Knowledge Base top k")}
    )
    enable_rerank: Optional[bool] = dataclasses.field(
        default=True, metadata={"help": _("Knowledge rerank")}
    )
    rerank_model: Optional[str] = dataclasses.field(
        default="bge-reranker-v2-m3", metadata={"help": _("Knowledge rerank")}
    )
    enable_summary: Optional[bool] = dataclasses.field(
        default=True, metadata={"help": _("Knowledge enable summary")}
    )
    summary_model: Optional[str] = dataclasses.field(
        default="aistudio/DeepSeek-V3", metadata={"help": _("Knowledge summary model")}
    )
    summary_prompt: Optional[str] = dataclasses.field(
        default="你是一个内容总结专家，请根据query对检索到的文档进行总结，要求总结的内容和query是相关的。1.如果已知信息包含的图片、链接、表格、代码块等特殊markdown标签格式的信息，确保在答案中包含原文这些图片、链接、表格和代码标签，不要丢弃不要修改，如:图片格式：![image.png](xxx),链接格式:[xxx](xxx),表格格式:|xxx|xxx|xxx|,代码格式:```xxx```.2.如果无法从提供的内容中获取答案,请说:知识库中提供的内容不足以回答此问题 禁止胡乱编造.3.回答的时候最好按照1.2.3.点进行总结,并以markdwon格式显示."
        "检索到的知识: {text}\n",
        metadata={"help": _("Knowledge summary prompt")},
    )
    enable_split_query: Optional[bool] = dataclasses.field(
        default=True, metadata={"help": _("enable split query")}
    )
    split_query_model: Optional[str] = dataclasses.field(
        default="tomato_r4_bailing_10b_sst_mft",
        metadata={"help": _("split query model")},
    )
    split_query_prompt: Optional[str] = dataclasses.field(
        default='你是一个问题拆解助手，你的任务是：对一个Query里可能涉及的多个子问题进行拆解。\n你应该使用以下方法保障问题拆解质量: 1.首先判断该Query是否需要拆解，如果你认为该Query只包含1个问题，那么无需拆解，否则需要拆解 2.如果需要拆解，你要尽可能使用Query使用过的字词，来减少问题拆解的多样性 3.如果无需拆解，返回Query即可 4.返回string lists形式，例如["a"]或者["a","b"]\n\n接下来，对以下输入进行拆解->\n\n输入:{query}\n输出:\n',
        metadata={"help": _("Knowledge summary model")},
    )
    enable_rewrite_query: Optional[bool] = dataclasses.field(
        default=False, metadata={"help": _("enable rewrite query")}
    )
    rewrite_query_model: Optional[str] = dataclasses.field(
        default="tomato_r4_bailing_10b_sst_mft",
        metadata={"help": _("rewrite query model")},
    )
    rewrite_query_prompt: Optional[str] = dataclasses.field(
        default='你是一个问题重写助手，你的任务是：对一个Query进行重写。\n你应该使用以下方法保障问题重写质量: 1.首先判断该Query是否需要重写，如果你认为该Query只包含1个问题，那么无需重写，否则需要重写 2.如果需要重写，你要尽可能使用Query使用过的字词，来减少问题重写的多样性 3.如果无需重写，返回Query即可 4.返回string lists形式，例如["a"]或者["a","b"]\n\n接下来，对以下输入进行改写->\n\n输入:{query}\n输出:\n',
        metadata={"help": _("rewrite_query_prompt")},
    )
    search_with_historical: Optional[bool] = dataclasses.field(
        default=False, metadata={"help": _("search with historical")}
    )
    tag_filters: Optional[List[dict]] = dataclasses.field(
        default=None,
        metadata={
            "help": _("tag filter"),
            "valid_values": [
                {"label": _("tag"), "key": "tag", "description": _("tag filter")}
            ],
        },
    )
    summary_with_historical: Optional[bool] = dataclasses.field(
        default=False, metadata={"help": _("summary with historical")}
    )
    retrieve_mode: Optional[str] = dataclasses.field(
        default="hybrid",
        metadata={"help": _("retrieve mode, semantic/keyword/hybrid}")},
    )

    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
        cls,
        parameters: Type["KnowledgePackLoadResourceParameters"],
        version: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Convert the parameters to configurations."""
        conf: List[ParameterDescription] = cast(
            List[ParameterDescription], super().to_configurations(parameters)
        )
        version = version or cls._resource_version()
        if version != "v1":
            return conf
        # Compatible with old version
        for param in conf:
            if param.param_name == "knowledges":
                return param.valid_values or []
        return []

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "KnowledgePackLoadResourceParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        if "space_name" not in copied_data and "value" in copied_data:
            copied_data["space_name"] = copied_data.pop("value")
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


class KnowledgePackSearchResource(RetrieverResource):
    """Knowledge Space retriever resource."""

    def __init__(
        self,
        name: str,
        knowledges: List[dict],
        top_k: int = 10,
        similarity_score_threshold: Optional[float] = 0.0,
        score_threshold: Optional[float] = 0.0,
        single_knowledge_top_k: Optional[int] = 20,
        enable_rerank: Optional[bool] = True,
        enable_summary: Optional[bool] = True,
        rerank_model: Optional[str] = "bge-reranker-v2-m3",
        summary_model: Optional[str] = None,
        summary_prompt: Optional[str] = None,
        enable_split_query: Optional[bool] = True,
        split_query_model: Optional[str] = None,
        split_query_prompt: Optional[str] = None,
        enable_rewrite_query: Optional[bool] = False,
        rewrite_query_model: Optional[str] = None,
        rewrite_query_prompt: Optional[str] = None,
        search_with_historical: Optional[bool] = False,
        tag_filters: Optional[List[dict]] = None,
        summary_with_historical: Optional[bool] = False,
        retrieve_mode: Optional[str] = None,
        system_app: SystemApp = None,
    ):
        # TODO: Build the retriever in a thread pool, it will block the event loop
        if knowledges:
            self._top_k = top_k
            self._similarity_score_threshold = similarity_score_threshold
            self._score_threshold = score_threshold
            self._single_knowledge_top_k = single_knowledge_top_k
            self._enable_rerank = enable_rerank
            self._rerank_model = rerank_model
            self._enable_summary = enable_summary
            self._summary_model = summary_model
            self._summary_prompt = summary_prompt
            self._split_query_model = split_query_model
            self._enable_split_query = enable_split_query
            self._split_query_prompt = split_query_prompt
            self._enable_rewrite_query = enable_rewrite_query
            self._rewrite_query_model = rewrite_query_model
            self._rewrite_query_prompt = rewrite_query_prompt
            self._search_with_historical = search_with_historical
            self._tag_filters = tag_filters
            self._summary_with_historical = summary_with_historical
            self._retrieve_mode = retrieve_mode
            self._knowledge_ids = [
                knowledge.get("knowledge_id") for knowledge in knowledges
            ]
            # knowledge = knowledges[0]
            self._rag_service = Service.get_instance(system_app)
            super().__init__(name)
            self.knowledge_spaces = []
            for knowledge_id in self._knowledge_ids:
                knowledge_space = get_knowledge_spaces_info(knowledge_id=knowledge_id)
                if not knowledge_space:
                    raise ValueError(
                        f"Knowledge {knowledge_id} not found, "
                        f"please check the knowledge id."
                    )
                self.knowledge_spaces.append(knowledge_space[0])
            if self.knowledge_spaces is not None and len(self.knowledge_spaces) > 0:
                self._retriever_name = self.knowledge_spaces[0].name
                self._retriever_desc = self.knowledge_spaces[0].desc
            else:
                self._retriever_name = None
                self._retriever_desc = None
        else:
            super().__init__(name)

    @property
    def retriever_name(self) -> str:
        """Return the resource name."""
        return self._retriever_name

    @property
    def retriever_desc(self) -> str:
        """Return the retriever desc."""
        return self._retriever_desc

    @property
    def description(self) -> str:
        """Return the resource name."""
        desc = ""
        for i, knowledge_space in enumerate(self.knowledge_spaces):
            desc += f"{i + 1}. name:{knowledge_space.name}, " \
                    f"knowledge_id:{knowledge_space.knowledge_id}, " \
                    f"知识库描述:{knowledge_space.desc}\n"
        return desc

    @property
    def is_empty(self) -> bool:
        """Return whether the knowledge_ids is empty."""
        return not (hasattr(self, "_knowledge_ids") and self._knowledge_ids)

    @classmethod
    def type(cls) -> ResourceType:
        """Return the resource type."""
        return ResourceType.KnowledgePack

    @classmethod
    def resource_parameters_class(
        cls, **kwargs
    ) -> Type[KnowledgePackLoadResourceParameters]:
        from derisk_app.knowledge.request.request import KnowledgeSpaceRequest
        from derisk_app.knowledge.service import KnowledgeService

        knowledge_space_service = KnowledgeService()
        knowledge_spaces = knowledge_space_service.get_knowledge_space(
            KnowledgeSpaceRequest(**kwargs)
        )
        results = [
            {"label": ks.name, "key": ks.knowledge_id, "description": ks.desc}
            for ks in knowledge_spaces
        ]

        @dataclasses.dataclass
        class _DynamicKnowledgeSpaceLoadResourceParameters(
            KnowledgePackLoadResourceParameters
        ):
            knowledges: List[dict] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Knowledge space name"),
                    "valid_values": results,
                },
            )

        return _DynamicKnowledgeSpaceLoadResourceParameters

    async def retrieve(
        self,
        query: str,
        filters: Optional["MetadataFilters"] = None,
        score: float = 0.0,
    ) -> List["Chunk"]:
        """Retrieve knowledge chunks.

        Args:
            query (str): query text.
            filters: (Optional[MetadataFilters]) metadata filters.
            score: (float) similarity score.

        Returns:
            List[Chunk]: list of chunks
        """
        search_res: KnowledgeSearchResponse = await self._retrieve(query=query)
        candidates = []
        for doc in search_res.document_response_list:
            candidates.append(
                Chunk(
                    content=doc.content,
                    score=doc.score,
                    metadata={
                        "retriever": self._retriever_name,
                    },
                )
            )
        return candidates

    async def get_summary(
        self,
        *,
        query: str,
        selected_knowledge_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> KnowledgeSearchResponse:
        """Get the summary.
        Args:
            query(str): The question.
            selected_knowledge_ids(Optional[List[str]]): selected_knowledge_ids.
        """
        search_res: KnowledgeSearchResponse = await self._retrieve(
            query=query,
            knowledge_ids=selected_knowledge_ids,
        )
        return search_res

    async def _retrieve(
        self,
        query: str,
        knowledge_ids: Optional[List[str]] = None,
    ) -> KnowledgeSearchResponse:
        """Retrieve knowledge chunks.

        Args:
            query (str): query text.
            filters: (Optional[MetadataFilters]) metadata filters.
            score: (float) similarity score.

        Returns:
            List[Chunk]: list of chunks
        """
        selected_knowledge_ids = []
        for knowledge_id in knowledge_ids:
            if knowledge_id in self._knowledge_ids:
                logger.info(
                    f"Knowledge {knowledge_id} is selected, "
                    f"and the knowledge id is {knowledge_id}"
                )
                selected_knowledge_ids.append(knowledge_id)
        if not selected_knowledge_ids:
            logger.info("no knowledge space selected, use all knowledge spaces")
            selected_knowledge_ids = self._knowledge_ids
        request = KnowledgeSearchRequest(
            knowledge_ids=selected_knowledge_ids,
            query=query,
            top_k=self._top_k,
            score_threshold=self._similarity_score_threshold,
            single_knowledge_top_k=self._single_knowledge_top_k,
            enable_rerank=self._enable_rerank,
            rerank_model=self._rerank_model,
            enable_summary=self._enable_summary,
            summary_model=self._summary_model,
            summary_prompt=self._summary_prompt,
            split_query_model=self._summary_prompt,
            split_query_prompt=self._split_query_prompt,
            enable_split_query=self._enable_split_query,
            mode=self._retrieve_mode,
        )
        search_res = await self._rag_service.knowledge_search(request)
        if not request.enable_summary:
            search_res.summary_content = ""
            url_to_index = {}
            for sub_query, candidates in search_res.references.items():
                text = ""
                for i, chunk in enumerate(candidates):

                    title = chunk.get('metadata').get(
                        'title'
                    ) if chunk.get('metadata') else ""

                    text += f"{chunk.get('content')}-([title:{title})\n"
                text = f"\n{sub_query}:\n" + text
                search_res.summary_content += text
        return search_res


def get_knowledge_spaces_info(**kwargs):
    from derisk_app.knowledge.request.request import KnowledgeSpaceRequest
    from derisk_app.knowledge.service import KnowledgeService

    knowledge_space_service = KnowledgeService()
    knowledge_spaces = knowledge_space_service.get_knowledge_space(
        KnowledgeSpaceRequest(**kwargs)
    )

    return knowledge_spaces
