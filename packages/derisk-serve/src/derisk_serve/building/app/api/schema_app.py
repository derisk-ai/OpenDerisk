import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from derisk.agent.core.plan.base import SingleAgentContext
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.core.schema import DynamicParam
from derisk.agent.resource.base import AgentResource
from derisk.context.operator import GroupedConfigItem
from derisk_serve.agent.app.recommend_question.recommend_question import (
    RecommendQuestion,
)
from derisk_serve.agent.model import NativeTeamContext
from derisk_serve.building.config.api.schemas import Layout, LLMResource


class SceneStrategyRef(BaseModel):
    """场景策略引用"""

    scene_code: str = Field(description="场景编码")
    scene_name: Optional[str] = Field(default=None, description="场景名称")
    is_primary: bool = Field(default=True, description="是否主要场景")
    custom_overrides: Dict[str, Any] = Field(
        default_factory=dict, description="自定义覆盖"
    )


logger = logging.getLogger(__name__)


class BindAppRequest(BaseModel):
    team_app_code: str
    bin_app_codes: List[str]
    bind_type: str = "agent"


class GptsAppDetail(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    app_code: Optional[str] = None
    app_name: Optional[str] = None
    type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    agent_icon: Optional[str] = None
    agent_describe: Optional[str] = None
    node_id: Optional[str] = None
    resources: Optional[list[AgentResource]] = None
    prompt_template: Optional[str] = None
    llm_strategy: Optional[str] = None
    llm_strategy_value: Union[Optional[str], Optional[List[Any]]] = None
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    def to_dict(self):
        return {k: self._serialize(v) for k, v in self.__dict__.items()}

    def _serialize(self, value):
        if isinstance(value, BaseModel):
            return value.to_dict()
        elif isinstance(value, list):
            return [self._serialize(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        else:
            return value

    @classmethod
    def from_dict(cls, d: Dict[str, Any], parse_llm_strategy: bool = False):
        lsv = d.get("llm_strategy_value")
        if parse_llm_strategy and lsv:
            strategies = json.loads(lsv)
            llm_strategy_value = ",".join(strategies)
        else:
            llm_strategy_value = d.get("llm_strategy_value", None)

        return cls(
            app_code=d["app_code"],
            app_name=d["app_name"],
            type=d["type"],
            agent_name=d["agent_name"],
            agent_role=d["agent_role"],
            agent_describe=d.get("agent_describe", None),
            node_id=d["node_id"],
            resources=d.get("resources", None),
            prompt_template=d.get("prompt_template", None),
            llm_strategy=d.get("llm_strategy", None),
            llm_strategy_value=llm_strategy_value,
            created_at=d.get("created_at", None),
            updated_at=d.get("updated_at", None),
        )

    @classmethod
    def from_entity(cls, entity):
        resources = AgentResource.from_json_list_str(entity.resources)
        return cls(
            app_code=entity.app_code,
            app_name=entity.app_name,
            type=entity.type,
            agent_name=entity.agent_name,
            agent_role=entity.agent_role,
            agent_describe=entity.agent_describe,
            node_id=entity.node_id,
            resources=resources,
            prompt_template=entity.prompt_template,
            llm_strategy=entity.llm_strategy,
            llm_strategy_value=entity.llm_strategy_value,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


class GptsApp(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    app_code: Optional[str] = None
    app_name: Optional[str] = None
    app_describe: Optional[str] = None
    app_hub_code: Optional[str] = None
    team_mode: Optional[str] = None
    config_code: Optional[str] = None
    config_version: Optional[str] = None
    language: Optional[str] = "zh"
    agent_version: Optional[str] = "v1"  # v1 (经典) v2 (Core_v2)
    team_context: Optional[Union[str, AutoTeamContext, SingleAgentContext]] = None
    user_code: Optional[str] = None
    sys_code: Optional[str] = None
    is_collected: Optional[str] = None
    icon: Optional[str] = None
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    details: List[GptsAppDetail] = []
    published: Optional[bool] = False
    user_name: Optional[str] = None
    user_icon: Optional[str] = None
    hot_value: Optional[int] = None
    param_need: Optional[List[dict]] = []
    owner_name: Optional[str] = None
    owner_avatar_url: Optional[str] = None
    recommend_questions: Optional[List[RecommendQuestion]] = []
    admins: List[str] = Field(default_factory=list)
    ext_config: Optional[Dict] = None
    runtime_config: Optional[Dict] = None

    ## 其他资源
    all_resources: Optional[List[AgentResource]] = None
    resources: Optional[List[AgentResource]] = None
    ## 模型配置
    llm_config: Optional[LLMResource] = None
    ## 应用布局信息
    layout: Optional[Layout] = None
    ## 知识配置
    resource_knowledge: Optional[List[AgentResource]] = None
    ## 工具配置
    resource_tool: Optional[List[AgentResource]] = None
    ## Agent配置
    resource_agent: Optional[List[AgentResource]] = None
    ## 应用自定义参数
    custom_variables: Optional[List[DynamicParam]] = None
    ## 系统prompt模版
    system_prompt_template: Optional[str] = None
    ## 用户prompt模版
    user_prompt_template: Optional[str] = None
    ## agent信息
    agent: Optional[str] = None
    ## 标记当前是否为推理引擎Agent
    is_reasoning_engine_agent: bool = False
    ## 上下文工程配置
    context_config: Optional[GroupedConfigItem] = None

    ## 场景策略配置
    scene_strategy: Optional[SceneStrategyRef] = Field(
        default=None, description="关联的场景策略"
    )
    scene_strategies: List[SceneStrategyRef] = Field(
        default_factory=list, description="关联的多个场景策略"
    )

    ## 场景文件列表（绑定到应用的.md场景文件）
    scenes: List[str] = Field(
        default_factory=list,
        description="绑定的场景文件ID列表，如 ['coding', 'schedule', 'deploy']",
    )

    creator: Optional[str] = None
    editor: Optional[str] = None

    # By default, keep the last two rounds of conversation records as the context
    keep_start_rounds: int = 1
    keep_end_rounds: int = 2

    def to_dict(self):
        return {k: self._serialize(v) for k, v in self.__dict__.items()}

    def _serialize(self, value):
        if isinstance(value, BaseModel):
            return value.to_dict()
        elif isinstance(value, list):
            return [self._serialize(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        else:
            return value

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(
            app_code=d.get("app_code", None),
            app_name=d["app_name"],
            language=d["language"],
            app_hub_code=d.get("app_hub_code", None),
            app_describe=d["app_describe"],
            team_mode=d["team_mode"],
            team_context=d.get("team_context", None),
            user_code=d.get("user_code", None),
            sys_code=d.get("sys_code", None),
            icon=d.get("icon", None),
            is_collected=d.get("is_collected", None),
            created_at=d.get("created_at", datetime.now()),
            updated_at=d.get("updated_at", datetime.now()),
            details=d.get("details", []),
            published=d.get("published", False),
            param_need=d.get("param_need", None),
            hot_value=d.get("hot_value", None),
            owner_name=d.get("owner_name", None),
            owner_avatar_url=d.get("owner_avatar_url", None),
            recommend_questions=d.get("recommend_questions", []),
            admins=d.get("admins", []),
            keep_start_rounds=d.get("keep_start_rounds", 1),
            keep_end_rounds=d.get("keep_end_rounds", 2),
            llm_config=d.get("llm_config"),
            layout=d.get("layout"),
            resource_knowledge=d.get("resource_knowledge"),
            resource_tool=d.get("resource_tool"),
            resources=d.get("resources"),
            resource_agent=d.get("resource_agent"),
            custom_variables=d.get("custom_variables"),
            system_prompt_template=d.get("system_prompt_template"),
            user_prompt_template=d.get("user_prompt_template"),
            config_code=d.get("config_code"),
            agent=d.get("agent"),
            config_version=d.get("config_version"),
            agent_version=d.get("agent_version", "v1"),
        )

    @model_validator(mode="before")
    @classmethod
    def pre_fill(cls, values):
        if not isinstance(values, dict):
            return values
        is_collected = values.get("is_collected")
        if is_collected is not None and isinstance(is_collected, bool):
            values["is_collected"] = "true" if is_collected else "false"
        return values


class GptsAppQuery(GptsApp):
    page_size: int = 100
    page: int = 1
    is_collected: Optional[str] = None
    is_recent_used: Optional[str] = None
    published: Optional[bool] = None
    ignore_user: Optional[str] = None
    app_codes: Optional[List[str]] = []
    hot_map: Optional[Dict[str, int]] = {}
    need_owner_info: Optional[str] = "true"
    name_filter: Optional[str] = None


class GptsAppResponse(BaseModel):
    total_count: Optional[int] = 0
    total_page: Optional[int] = 0
    current_page: Optional[int] = 0
    app_list: Optional[List[GptsApp]] = Field(
        default_factory=list, description="app list"
    )
    page_size: int = 20
