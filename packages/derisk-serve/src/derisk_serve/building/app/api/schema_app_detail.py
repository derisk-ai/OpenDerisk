import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


from derisk._private.pydantic import (
    BaseModel,
    ConfigDict, model_to_dict,
)
from derisk.agent.resource.base import AgentResource

logger = logging.getLogger(__name__)


class GptsAppDetail(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    app_code: Optional[str] = None
    app_name: Optional[str] = None
    type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
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
            resources=d["resources"],
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


class AppDetailServeRequest(GptsAppDetail):
    model_config = ConfigDict(title=f"ServeRequest for AppDetail")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


AppDetailServerResponse = AppDetailServeRequest