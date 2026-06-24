"""Models Configuration Parameters.

Heavyweight cluster-worker parameter classes (ModelWorkerParameters,
ModelControllerParameters, ModelAPIServerParameters, ModelServiceConfig,
BaseModelRegistryParameters, DBModelRegistryParameters, WorkerType) were
removed along with `derisk.model.cluster`. Only `ModelsDeployParameters`
remains — it parses `[[models.llms]]` / `[[models.embeddings]]` /
`[[models.rerankers]]` lists from TOML config to surface default model
names; the actual provider wiring is handled by
`derisk.agent.util.llm.provider.ProviderRegistry` + `ModelConfigCache`.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from derisk.core.interface.parameter import (
    EmbeddingDeployModelParameters,
    LLMDeployModelParameters,
    RerankerDeployModelParameters,
)
from derisk.util.i18n_utils import _
from derisk.util.parameter_utils import BaseParameters


@dataclass
class ModelsDeployParameters(BaseParameters):
    default_llm: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "Default LLM model name, used to specify which model to use when you "
                "have multiple LLMs"
            ),
        },
    )
    default_embedding: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "Default embedding model name, used to specify which model to use when "
                "you have multiple embedding models"
            ),
        },
    )
    default_reranker: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "Default reranker model name, used to specify which model to use when "
                "you have multiple reranker models"
            ),
        },
    )
    llms: List[LLMDeployModelParameters] = field(
        default_factory=list,
        metadata={
            "help": _(
                "LLM model deploy configuration. If you deploy in cluster mode, you "
                "just deploy one model."
            )
        },
    )
    embeddings: List[EmbeddingDeployModelParameters] = field(
        default_factory=list,
        metadata={
            "help": _(
                "Embedding model deploy configuration. If you deploy in cluster "
                "mode, you just deploy one model."
            )
        },
    )
    rerankers: List[RerankerDeployModelParameters] = field(
        default_factory=list,
        metadata={
            "help": _(
                "Reranker model deploy configuration. If you deploy in cluster "
                "mode, you just deploy one model."
            )
        },
    )

    def __post_init__(self):
        """Post init method."""
        llms, embeds, rerankers = [], [], []
        for llm in self.llms:
            llms.append(llm.name)
        for embedding in self.embeddings:
            embeds.append(embedding.name)
        for reranker in self.rerankers:
            rerankers.append(reranker.name)
        if not self.default_llm and llms:
            self.default_llm = llms[0]
        if not self.default_embedding and embeds:
            self.default_embedding = embeds[0]
        if not self.default_reranker and rerankers:
            self.default_reranker = rerankers[0]
