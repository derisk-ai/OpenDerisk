"""Import all models to make sure they are registered with SQLAlchemy."""

from derisk.model.cluster.registry_impl.db_storage import ModelInstanceEntity
from derisk.storage.chat_history.chat_history_db import (
    ChatHistoryEntity,
    ChatHistoryMessageEntity,
)
from derisk_app.openapi.api_v1.feedback.feed_back_db import ChatFeedBackEntity
from derisk_serve.agent.app.recommend_question.recommend_question import (
    RecommendQuestionEntity,
)
from derisk_serve.datasource.manages.connect_config_db import ConnectConfigEntity
from derisk_serve.file.models.models import ServeEntity as FileServeEntity
from derisk_serve.prompt.models.models import ServeEntity as PromptManageEntity
from derisk_serve.rag.models.chunk_db import DocumentChunkEntity
from derisk_serve.rag.models.document_db import KnowledgeDocumentEntity
from derisk_serve.rag.models.models import KnowledgeSpaceEntity

_MODELS = [
    FileServeEntity,
    PromptManageEntity,
    KnowledgeSpaceEntity,
    KnowledgeDocumentEntity,
    DocumentChunkEntity,
    ChatFeedBackEntity,
    ConnectConfigEntity,
    ChatHistoryEntity,
    ChatHistoryMessageEntity,
    ModelInstanceEntity,
    RecommendQuestionEntity,
]
