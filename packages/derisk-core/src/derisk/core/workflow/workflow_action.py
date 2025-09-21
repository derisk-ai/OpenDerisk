import json
from abc import abstractmethod, ABC
from typing import Optional

import requests

from derisk._private.pydantic import BaseModel, Field
from derisk.agent import Action, ActionOutput, Resource
from derisk.agent.resource.workflow import WorkflowResource, WorkflowPlatform
from derisk.util.date_utils import current_ms


class WorkflowActionInput(BaseModel):
    id: str = Field(..., description="workflow id")
    query: str = Field(..., description="workflow input query")
    thought: str = Field(None, description="thought")


class WorkflowExecutor(ABC):
    @abstractmethod
    async def execute(self, param: WorkflowActionInput, resource: WorkflowResource, **kwargs) -> str:
        """执行工作流"""




_executors: dict[str, WorkflowExecutor] = {

}


class WorkflowAction(Action[WorkflowActionInput]):
    async def run(self, ai_message: str = None, **kwargs) -> ActionOutput:
        param: WorkflowActionInput = self.action_input or self._input_convert(ai_message, WorkflowActionInput)
        resource: WorkflowResource = workflow_resource(self.resource, param.id)
        assert resource is not None, "Agent无workflow"

        executor: WorkflowExecutor = _executors.get(resource.platform)
        assert executor is not None, "workflow非法: platform不存在"

        success = True
        start_ms = current_ms()
        try:
            result: str = await executor.execute(param=param, resource=resource)
        except Exception as e:
            success = False
            result = f"workflow执行失败: {repr(e)}"

        return ActionOutput(
            is_exe_success=success,
            action=resource.name,
            action_name=self.name,
            action_input=param.query,
            content=result,
            view="",  # todo
            observations=result,
            cost_ms=current_ms() - start_ms,
        )


def workflow_resource(resource: Resource, id: str) -> Optional[WorkflowResource]:
    if isinstance(resource, WorkflowResource):
        return resource if resource.name == id else None

    if resource.is_pack:
        for sub_resource in resource.sub_resources:
            _resource = workflow_resource(sub_resource, id)
            if _resource is not None:
                return _resource

    return None
