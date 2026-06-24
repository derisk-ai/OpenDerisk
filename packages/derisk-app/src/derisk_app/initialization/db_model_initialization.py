"""Import all models to make sure they are registered with SQLAlchemy."""

from derisk.model.streaming.db_models import StreamingToolConfig
from derisk.storage.chat_history.chat_history_db import (
    ChatHistoryEntity,
    ChatHistoryMessageEntity,
)
from derisk_app.openapi.api_v1.feedback.feed_back_db import ChatFeedBackEntity
from derisk_serve.agent.app.recommend_question.recommend_question import (
    RecommendQuestionEntity,
)
from derisk_serve.channel.models import ChannelEntity

from derisk_serve.datasource.manages.connect_config_db import ConnectConfigEntity
from derisk_serve.file.models.models import ServeEntity as FileServeEntity
from derisk_serve.flow.models.models import ServeEntity as FlowServeEntity
from derisk_serve.flow.models.models import VariablesEntity as FlowVariableEntity
from derisk_serve.prompt.models.models import ServeEntity as PromptManageEntity
# TODO: rewire to new knowledge module (Task #9)
# Old rag DB models (DocumentChunkEntity, KnowledgeDocumentEntity, KnowledgeSpaceEntity)
# were removed along with derisk_serve.rag. New knowledge module will register its own.
from derisk_serve.config.models.models import ServeEntity as ConfigServeEntity
from derisk_serve.building.app.models.models import ServeEntity as AppServeEntity
from derisk_serve.building.app.models.models_details import AppDetailServeEntity
from derisk_serve.building.config.models.models import (
    ServeEntity as AppConfigServeEntity,
)
from derisk_serve.mcp.models.models import ServeEntity as MCPServeEntity
from derisk_serve.channel.models.models import ChannelEntity
from derisk_app.auth.user_service import UserEntity
from derisk_app.config_storage.oauth2_db_storage import OAuth2ConfigEntity
from derisk_app.feature_plugins.user_groups.models import (
    UserGroupEntity,
    UserGroupMemberEntity,
)
from derisk_app.feature_plugins.permissions.models import (
    RoleEntity,
    RolePermissionEntity,
    UserRoleEntity,
    GroupRoleEntity,
    PermissionDefinitionEntity,
    RolePermissionDefEntity,
)
from derisk_app.feature_plugins.system_config_model import SystemConfigEntity

_MODELS = [
    FileServeEntity,
    PromptManageEntity,
    # TODO: rewire to new knowledge module (Task #9)
    # KnowledgeSpaceEntity,
    # KnowledgeDocumentEntity,
    # DocumentChunkEntity,
    ChatFeedBackEntity,
    ConnectConfigEntity,
    ChatHistoryEntity,
    ChatHistoryMessageEntity,
    FlowServeEntity,
    RecommendQuestionEntity,
    FlowVariableEntity,
    ConfigServeEntity,
    AppServeEntity,
    AppDetailServeEntity,
    AppConfigServeEntity,
    MCPServeEntity,
    ChannelEntity,
    StreamingToolConfig,
    UserEntity,
    UserGroupEntity,
    UserGroupMemberEntity,
    OAuth2ConfigEntity,
    RoleEntity,
    RolePermissionEntity,
    UserRoleEntity,
    GroupRoleEntity,
    PermissionDefinitionEntity,
    RolePermissionDefEntity,
    SystemConfigEntity,
]
