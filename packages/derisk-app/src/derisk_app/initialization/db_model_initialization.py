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
from derisk_serve.flow.models.models import ServeEntity as FlowServeEntity
from derisk_serve.flow.models.models import VariablesEntity as FlowVariableEntity
from derisk_serve.prompt.models.models import ServeEntity as PromptManageEntity
from derisk_serve.rag.models.chunk_db import DocumentChunkEntity
from derisk_serve.rag.models.document_db import KnowledgeDocumentEntity
from derisk_serve.rag.models.models import KnowledgeSpaceEntity
from derisk_serve.mcp.models.models import ServeEntity as McpManageEntity
from derisk_serve.model.models.models import ServeEntity as ModelManageentity
from derisk_serve.agent.db.gpts_tool_messages import GptsToolMessagesEntity
from derisk_serve.agent.db.gpts_tool import GptsToolDetailEntity

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
    FlowServeEntity,
    RecommendQuestionEntity,
    FlowVariableEntity,
    McpManageEntity,
    ModelManageentity,
    GptsToolMessagesEntity,
    GptsToolDetailEntity
]
