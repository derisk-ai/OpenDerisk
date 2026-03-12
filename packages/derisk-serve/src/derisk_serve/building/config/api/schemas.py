# Define your Pydantic schemas here
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List, Union

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    model_to_dict,
    Field,
    model_validator,
)
from derisk.agent import AgentResource
from derisk.agent.core.plan.base import TeamContext, SingleAgentContext
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.core.plan.unified_context import UnifiedTeamContext
from derisk.agent.core.schema import DynamicParam
from derisk.context.operator import GroupedConfigItem
from derisk.vis.schema import ChatLayout
from derisk_serve.agent.app.recommend_question.recommend_question import (
    RecommendQuestion,
)
from derisk_serve.agent.model import NativeTeamContext
from ..config import SERVE_APP_NAME_HUMP


class ChatInParamType(Enum):
    INT = "int"
    STRING = "string"
    FLOAT = "float"
    SELECT = "select"
    FILE_UPLOAD = "file_upload"


class ChatInParamDefine(BaseModel):
    param_type: str = Field(
        ...,
        description="The param type of app chat in.",
    )
    param_description: Optional[str] = Field(
        None,
        description="The param decription of app chat in.",
    )
    sub_types: Optional[List[str]] = Field(
        None,
        description="The sub type of chat in param.",
    )
    param_default_value: Optional[str] = Field(
        None,
        description="The param value of app chat in.",
    )
    param_render_type: Optional[str] = Field(
        None,
        description="The param value render type of app chat in.",
    )


class ChatInParam(BaseModel):
    param_type: str = Field(
        ...,
        description="The param type of app chat in.",
    )
    sub_type: Optional[str] = Field(
        None,
        description="The sub type of chat in param.",
    )
    param_description: Optional[str] = Field(
        None,
        description="The param placeholder.",
    )
    param_render_type: Optional[str] = Field(
        None,
        description="The param value render type of app chat in.",
    )
    param_type_options: Optional[List] = Field(
        None,
        description="The param options value of app chat in.",
    )

    param_default_value: Optional[Any] = Field(
        None,
        description="The param value of app chat in.",
    )


class ChatInParamValue(BaseModel):
    param_type: str = Field(
        ...,
        description="The param type of app chat in.",
    )
    sub_type: Optional[str] = Field(
        None,
        description="The sub type of chat in param.",
    )
    param_value: str = Field(..., description="The chat in param  value")


class LLMResource(BaseModel):
    llm_strategy: Optional[str] = Field(
        None, description="The team leader's llm strategy"
    )
    llm_strategy_value: Union[Optional[str], Optional[List[Any]]] = Field(
        None, description="The team leader's llm config"
    )
    llm_param: Optional[Dict] = Field(None, description="The llm model param config")
    mist_keys: Optional[List[str]] = Field(
        None, description="The mist keys configuration"
    )
    agent_llm_config: Optional[Dict[str, Any]] = Field(
        None, description="The agent llm config"
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class Layout(BaseModel):
    model_config = ConfigDict(title=f"Layout")

    chat_layout: ChatLayout = Field(..., description="对话输出布局模式")
    chat_in_layout: Optional[List[ChatInParam]] = Field(
        None, description="对话输入布局动态参数"
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class ServeRequest(BaseModel):
    """Building/config request model"""

    model_config = ConfigDict(title=f"ServeRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[int] = Field(None, description="id主键")
    app_code: str = Field(..., description="应用代码")
    code: Optional[str] = Field(None, description="当前配置代码")
    team_mode: Optional[str] = Field(None, description="当前版本配置的对话模式")
    team_context: Optional[
        Union[str, AutoTeamContext, SingleAgentContext, UnifiedTeamContext]
    ] = Field(None, description="应用的TeamContext信息")
    resources: Optional[List[AgentResource]] = Field(
        None, description="应用的Resources信息"
    )
    details: Optional[List[str]] = Field(None, description="应用的小弟details信息")
    recommend_questions: Optional[List[RecommendQuestion]] = Field(
        None, description="推荐问题"
    )
    version_info: Optional[str] = Field(None, description="版本信息")
    creator: Optional[str] = Field(None, description="创建者(域账户)")
    description: Optional[str] = Field(None, description="备注描述")
    is_published: Optional[bool] = Field(False, description="是否已发布")
    gmt_last_edit: Optional[datetime] = Field(None, description="最后一次编辑时间")
    editor: Optional[str] = Field(None, description="最后修改者")
    system_prompt_template: Optional[str] = Field(None, description="system prompt模版")
    user_prompt_template: Optional[str] = Field(None, description="user prompt模版")
    ext_config: Optional[Dict] = Field(None, description="扩展配置")
    runtime_config: Optional[Dict] = Field(
        None, description="Agent运行时配置，包含DoomLoop检测、Loop执行、WorkLog压缩等"
    )
    gmt_create: Optional[str] = Field(None, description="Creation time")
    gmt_modified: Optional[str] = Field(None, description="Modification time")

    ## 模型配置
    llm_config: Optional[LLMResource] = Field(None, description="模型配置")
    ## 应用布局信息
    layout: Optional[Layout] = Field(None, description="布局配置")
    ## 知识配置
    resource_knowledge: Optional[List[AgentResource]] = Field(
        None, description="知识配置"
    )
    ## 工具配置
    resource_tool: Optional[List[AgentResource]] = Field(None, description="工具配置")
    ## Agent配置
    resource_agent: Optional[List[AgentResource]] = Field(None, description="agent配置")
    ## 应用自定义参数
    custom_variables: Optional[List[DynamicParam]] = Field(
        None, description="自定义参数配置"
    )
    ## 推理引擎名称
    resource_reasoning_engine: Optional[List[AgentResource]] = Field(
        None, description="推理引擎配置,Agent为ReasoningPlanner时可用"
    )
    ## 上下文工程配置
    context_config: Optional[GroupedConfigItem] = Field(
        None, description="上下文工程配置"
    )
    ## Agent版本
    agent_version: Optional[str] = Field(
        "v1", description="Agent版本: v1(经典) or v2(Core_v2)"
    )

    @staticmethod
    def _parse_team_context(
        team_mode: Optional[str],
        team_context: Optional[
            Union[str, dict, AutoTeamContext, SingleAgentContext, UnifiedTeamContext]
        ],
    ) -> Optional[Union[AutoTeamContext, SingleAgentContext, UnifiedTeamContext]]:
        """Parse team_context from string to appropriate object type"""
        if team_context is None:
            return None

        # Already an instance of the expected type
        if isinstance(
            team_context, (AutoTeamContext, SingleAgentContext, UnifiedTeamContext)
        ):
            return team_context

        # Handle JSON string
        if isinstance(team_context, str):
            try:
                context_dict = json.loads(team_context)
            except json.JSONDecodeError:
                # If it's not valid JSON, return the string as is
                return None  # or could return team_context as raw string

            # Check for agent_version to determine V2 context
            agent_version = context_dict.get("agent_version", "v1")
            if agent_version == "v2":
                return UnifiedTeamContext(**context_dict)

            # Parse based on team_mode
            from derisk_serve.agent.team.base import TeamMode

            if team_mode == TeamMode.SINGLE_AGENT.value:
                return SingleAgentContext(**context_dict)
            elif team_mode == TeamMode.AUTO_PLAN.value:
                return AutoTeamContext(**context_dict)
            return SingleAgentContext(**context_dict)  # Default fallback

        # Handle dict
        if isinstance(team_context, dict):
            # Check for agent_version to determine V2 context
            agent_version = team_context.get("agent_version", "v1")
            if agent_version == "v2":
                return UnifiedTeamContext(**team_context)

            from derisk_serve.agent.team.base import TeamMode

            if team_mode == TeamMode.SINGLE_AGENT.value:
                return SingleAgentContext(**team_context)
            elif team_mode == TeamMode.AUTO_PLAN.value:
                return AutoTeamContext(**team_context)
            return SingleAgentContext(**team_context)  # Default fallback

        return None

    @model_validator(mode="before")
    @classmethod
    def validate_team_context(
        cls, values: Union[Dict[str, Any], Any]
    ) -> Union[Dict[str, Any], Any]:
        """Validate and parse team_context field"""
        if not isinstance(values, dict):
            return values

        team_mode = values.get("team_mode")
        team_context = values.get("team_context")

        parsed_context = cls._parse_team_context(team_mode, team_context)
        if parsed_context is not None:
            values["team_context"] = parsed_context

        return values

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


ServerResponse = ServeRequest


class AppParamType(Enum):
    Resource = "resource"
    Model = "model"
    Temperature = "temperature"
    MaxNewTokens = "max_new_tokens"
    # ImageFile = "image_file"
    # ExcelFile = "excel_file"
    # TextFile = "text_file"


class ChatParamRequest(BaseModel):
    param_type: str = Field(
        ...,
        description="The param type of app chat in.",
    )
    resource_type: Optional[str] = Field(
        None,
        description="The name of resource param type.",
    )
    resource_version: Optional[str] = Field(
        "v1",
        description="The version of resource param type.",
    )
