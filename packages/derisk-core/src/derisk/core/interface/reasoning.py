"""The planner interface for breaking down complex tasks into modular components."""

from abc import ABC, abstractmethod
from typing import (
    Optional,
)

from derisk._private.pydantic import BaseModel, Field
from derisk.agent import LLMConfig


class DeriskAbility(BaseModel):
    """
    derisk 能力提供方 (MCP/Tool/子Agent/...)
    """

    id = Field(..., description="id")

    description = Field(..., description="能力描述")


class DeriskPlannerRequest(BaseModel):
    """
    derisk planner模块请求参数
    """

    conv_uid = Field(..., description="会话ID")

    operator = Field(..., description="用户域账号")

    prompt_template: Optional[str] = Field(
        None,
        description="业务方配置的推理Prompt模板, 相关占位参数位于prompt_args中. Prompt模板这两个参数供参考 业务方可以直接使用、扩展，也可自行实现Planner逻辑",
    )

    prompt_args: Optional[dict] = Field(
        None, description="推理模版参数对应的参数值，可按需扩展、替换"
    )

    abilities: Optional[list] = Field(
        None, description="可用能力(MCP/Tool/子Agent/...)"
    )
    llm_config: Optional[LLMConfig] = Field(None, description="模型选用策略配置()")
    stream_out: bool = Field(False, description="是否流式输出")
    temperature: int = Field(0.6, description="模型调用temperature参数")


class DeriskPlannerAction(BaseModel):
    """
    derisk planner模块任务拆解出的action
    """

    intention = Field(..., description="子任务/步骤的意图")

    ability_id = Field(..., description="指定哪个能力方，参见请求参数中的abilities")

    parameters: Optional[str] = Field(
        None,
        description="执行参数。可选，为空则通过大模型根据能力(Tool)参数配置进行填参",
    )

    reason: Optional[str] = Field(None, description="执行该步骤的原因")


class DeriskPlannerResult(BaseModel):
    """
    derisk planner模块请求响应
    """

    conclusion: Optional[str] = Field(
        None,
        description="Task conclusion. Present only when the task can be concluded.",
    )

    actions: Optional[DeriskPlannerAction] = Field(
        None,
        description="Decomposed execution reasoning_engine. Non-empty only when the next action is required.",
    )

    reasoning_content: Optional[str] = Field(
        None,
        description="The reason why task can be concluded or the next action is required.",
    )


class BasePlanner(BaseModel, ABC):
    """
    definition for reasoning_engine interface
    """

    _registry = {}

    @abstractmethod
    async def plan(self, request: DeriskPlannerRequest) -> DeriskPlannerResult:
        """
        Get next actions by chat history
        """

    @classmethod
    def register(cls, name):
        """
        Planner register

          name:
            planner name

        Example:
            @BasePlanner.register(name='my_planner')
            def MyPlanner(BasePlanner):
                ...

        """

        def decorator(subclass):
            if name in cls._registry:
                raise ValueError(f"Planner {name} already registered!")
            cls._registry[name] = subclass
            return subclass

        return decorator

    @classmethod
    def get_planner(cls, name, *args, **kwargs):
        """
        Get planner by name

          name:
            planner name
        """
        planner_class = cls._registry.get(name)
        if not planner_class:
            raise ValueError(f"Planner {name} not found!")
        return planner_class(*args, **kwargs)
