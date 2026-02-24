from typing import Optional, Union, List, Any, Dict
from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_to_dict,
    validator,
    model_validator,
)
from ...resource.base import AgentResource


class TeamContext(BaseModel):
    can_ask_user: Optional[bool] = Field(
        True,
        description="Can ask user",
        examples=[
            True,
            False,
        ],
    )
    llm_strategy: Optional[str] = Field(
        None, description="The team leader's llm strategy"
    )
    llm_strategy_value: Union[Optional[str], Optional[List[Any]]] = Field(
        None, description="The team leader's llm config"
    )
    mist_keys: Optional[List[str]] = Field(
        None, description="独立分配的AI云mist"
    )
    prompt_template: Optional[str] = Field(
        None, description="The team leader's system prompt template!"
    )
    user_prompt_template: Optional[str] = Field(
        None, description="The team leader's user prompt template!"
    )
    prologue: Optional[str] = Field(
        None, description="The prologue of the agent"
    )
    vis_mode: Optional[str] = Field(
        None, description="The layout mode of the agent"
    )
    resources: Optional[list[AgentResource]] = Field(
        None, description="The team leader's resource!"
    )
    use_sandbox: Optional[bool]= Field(
        False, description="This Agent Use sandbox"
    )


    @model_validator(mode="before")
    def preprocess_resources(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """预处理resources字段：处理JSON字符串或字典列表"""
        if "resources" in values:
            resources = values["resources"]
            if isinstance(resources, str):
                import json
                try:
                    values["resources"] = AgentResource.from_json_list_str(resources)
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid JSON string for resources: {resources}")
            elif isinstance(resources, list):
                # 转换字典元素为AgentResource实例
                new_resources = []
                for item in resources:
                    if isinstance(item, dict):
                        new_resources.append(AgentResource.from_dict(item))
                    elif isinstance(item, AgentResource):
                        new_resources.append(item)
                values["resources"] = new_resources
        return values

    def to_dict(self):
        return model_to_dict(self)


class SingleAgentContext(TeamContext):
    agent_name: Optional[str] = Field(None, description="Current agent name")
    agent_role: Optional[str] = Field(None, description="Current agent role")
