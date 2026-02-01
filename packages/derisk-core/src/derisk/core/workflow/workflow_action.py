import json
from abc import abstractmethod, ABC
from typing import Optional

import aiohttp

from derisk._private.pydantic import BaseModel, Field
from derisk.agent import Action, ActionOutput, Resource
from derisk.agent.resource.workflow import WorkflowResource, WorkflowPlatform
from derisk.model.cluster import worker_manager
from derisk.model.parameter import WorkerType
from derisk.util.date_utils import current_ms


class WorkflowActionInput(BaseModel):
    name: str = Field(..., description="workflow name")
    query: str = Field(..., description="workflow input query")
    thought: Optional[str] = Field(None, description="thought")


class WorkflowExecutor(ABC):
    @abstractmethod
    async def execute(self, param: WorkflowActionInput, resource: WorkflowResource, **kwargs) -> str:
        """执行工作流"""


class LingWorkflowExecutor(WorkflowExecutor):
    async def execute(self, param: WorkflowActionInput, resource: WorkflowResource, **kwargs) -> str:
        """执行工作流"""
        models = await worker_manager.get_all_model_instances(WorkerType.LLM.value)
        instance = next((instance for instance in models if instance.worker_key.startswith("aistudio")), None)
        key = instance.model_params.api_key
        resp_body = ""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url="https://antchat.alipay.com/api/v1/agent/stream_chat",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    'Accept-Charset': 'utf-8',
                },
                json={
                    "userId": "315588",  # todo
                    "agentId": resource.id,
                    "query": param.query,
                },
                ssl=False
            ) as response:
                response.raise_for_status()
                async for line_bytes in response.content:
                    line = line_bytes.decode("utf-8", errors="replace")
                    if not line or not line.startswith("data:"):
                        continue

                    try:
                        chunk = json.loads(line[5:])
                        contents = chunk.get("data", {}).get("contents", [])
                        for content in contents:
                            text = content.get("content", {}).get("text", "")
                            resp_body += text
                    except Exception as e:
                        pass
        return resp_body


_executors: dict[str, WorkflowExecutor] = {
    WorkflowPlatform.Ling.value: LingWorkflowExecutor(),
}


class WorkflowAction(Action[WorkflowActionInput]):
    name = "Workflow"

    async def run(self, ai_message: str = None, **kwargs) -> ActionOutput:

        action_id = kwargs.get("action_id", None)
        param: WorkflowActionInput = self.action_input or self._input_convert(ai_message, WorkflowActionInput)
        resource: WorkflowResource = workflow_resource(self.resource, param.name)
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
            action_id=action_id or self.action_uid,
            is_exe_success=success,
            action=resource.name,
            name=self.name,
            action_input=param.query,
            content=result,
            view="",  # todo
            observations=result,
            cost_ms=current_ms() - start_ms,
        )


def workflow_resource(resource: Resource, name: str) -> Optional[WorkflowResource]:
    if isinstance(resource, WorkflowResource):
        return resource if resource.name == name else None

    if resource.is_pack:
        for sub_resource in resource.sub_resources:
            _resource = workflow_resource(sub_resource, name)
            if _resource is not None:
                return _resource

    return None
