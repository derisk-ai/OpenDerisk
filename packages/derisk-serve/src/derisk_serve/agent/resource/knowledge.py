import dataclasses
import logging
from typing import Any, List, Optional, Type, cast

from derisk import SystemApp
from derisk.agent.resource.knowledge import (
    RetrieverResource,
    RetrieverResourceParameters,
)
from derisk.util import ParameterDescription
from derisk.util.i18n_utils import _
from derisk_serve.rag.retriever.knowledge_space import KnowledgeSpaceRetriever

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class KnowledgeSpaceLoadResourceParameters(RetrieverResourceParameters):
    knowledge: str = dataclasses.field(
        default=None, metadata={"help": _("Knowledge space id")}
    )
    top_k: int = dataclasses.field(
        default=10, metadata={"help": _("Knowledge retriver top k")}
    )
    similarity_score_threshold: Optional[float] = dataclasses.field(
        default=0.0, metadata={"help": _("Knowledge retriver top k")}
    )
    score_threshold: Optional[float] = dataclasses.field(
        default=0.0, metadata={"help": _("Knowledge retriver top k")}
    )
    single_knowledge_top_k: Optional[int] = dataclasses.field(
        default=20, metadata={"help": _("Knowledge retriver top k")}
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
        default="aisudio/DeepSeek-V3", metadata={"help": _("Knowledge summary model")}
    )
    summary_prompt: Optional[str] = dataclasses.field(
        default="你是一个内容总结专家，请根据query对检索到的文档进行总结，要求总结的内容和query是相关的。1.如果已知信息包含的图片、链接、表格、代码块等特殊markdown标签格式的信息，确保在答案中包含原文这些图片、链接、表格和代码标签，不要丢弃不要修改，如:图片格式：![image.png](xxx),链接格式:[xxx](xxx),表格格式:|xxx|xxx|xxx|,代码格式:```xxx```.2.如果无法从提供的内容中获取答案,请说:知识库中提供的内容不足以回答此问题 禁止胡乱编造.3.回答的时候最好按照1.2.3.点进行总结,并以markdwon格式显示.",
        metadata={"help": _("Knowledge summary prompt")},
    )

    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
        cls,
        parameters: Type["KnowledgeSpaceLoadResourceParameters"],
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
            if param.param_name == "knowledge_id":
                return param.valid_values or []
        return []

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "KnowledgeSpaceLoadResourceParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        if "space_name" not in copied_data and "value" in copied_data:
            copied_data["space_name"] = copied_data.pop("value")
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


class KnowledgeSpaceRetrieverResource(RetrieverResource):
    """Knowledge Space retriever resource."""

    def __init__(
        self,
        name: str,
        knowledge: str,
        top_k: int = 10,
        system_app: SystemApp = None,
    ):
        # TODO: Build the retriever in a thread pool, it will block the event loop
        retriever = KnowledgeSpaceRetriever(
            space_id=knowledge,
            top_k=top_k,
            system_app=system_app,
        )
        super().__init__(name, retriever=retriever)

        knowledge_spaces = get_knowledge_spaces_info(knowledge_id=knowledge)
        if knowledge_spaces is not None and len(knowledge_spaces) > 0:
            self._retriever_name = knowledge_spaces[0].name
            self._retriever_desc = knowledge_spaces[0].desc
        else:
            self._retriever_name = None
            self._retriever_desc = None

    @property
    def retriever_name(self) -> str:
        """Return the resource name."""
        return self._retriever_name

    @property
    def retriever_desc(self) -> str:
        """Return the retriever desc."""
        return self._retriever_desc

    @classmethod
    def resource_parameters_class(
        cls, **kwargs
    ) -> Type[KnowledgeSpaceLoadResourceParameters]:
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
            KnowledgeSpaceLoadResourceParameters
        ):
            knowledge: str = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Knowledge space name"),
                    "valid_values": results,
                },
            )

        return _DynamicKnowledgeSpaceLoadResourceParameters


def get_knowledge_spaces_info(**kwargs):
    from derisk_app.knowledge.request.request import KnowledgeSpaceRequest
    from derisk_app.knowledge.service import KnowledgeService

    knowledge_space_service = KnowledgeService()
    knowledge_spaces = knowledge_space_service.get_knowledge_space(
        KnowledgeSpaceRequest(**kwargs)
    )

    return knowledge_spaces
