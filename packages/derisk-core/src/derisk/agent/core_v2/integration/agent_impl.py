"""
V2PDCAAgent - 基于 Core_v2 的 PDCA Agent 实现

整合原有的 PDCA 能力与 Core_v2 架构
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from ..agent_base import (
    AgentBase,
    AgentContext,
    AgentExecutionResult,
    AgentMessage,
    AgentState,
)
from ..agent_info import AgentInfo, AgentMode

logger = logging.getLogger(__name__)


class V2PDCAAgent(AgentBase):
    """
    V2 PDCA Agent - 基于 Core_v2 架构实现

    集成原有的 PDCA 循环能力：
    1. Plan - 任务规划
    2. Do - 任务执行
    3. Check - 结果检查
    4. Act - 调整行动

    示例:
        agent = V2PDCAAgent(
            info=AgentInfo(name="pdca", mode=AgentMode.PRIMARY),
            tools={"bash": bash_tool},
            resources={},
        )

        async for chunk in agent.run("帮我完成数据分析任务"):
            print(chunk)
    """

    def __init__(
        self,
        info: AgentInfo,
        tools: Optional[Dict[str, Any]] = None,
        resources: Optional[Dict[str, Any]] = None,
        model_provider: Optional[Any] = None,
        model_config: Optional[Dict] = None,
    ):
        super().__init__(info)
        self.tools = tools or {}
        self.resources = resources or {}
        self.model_provider = model_provider
        self.model_config = model_config or {}
        self._plans: List[Dict[str, Any]] = []
        self._current_plan_idx = 0

    @property
    def available_tools(self) -> List[str]:
        return list(self.tools.keys())

    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        yield f"正在分析任务: {message[:50]}..."

        if self._should_plan(message):
            yield "任务需要规划，开始制定计划..."
            plans = await self._create_plan(message, **kwargs)
            self._plans = plans
            self._current_plan_idx = 0
            yield f"已制定 {len(plans)} 个执行步骤"
        else:
            yield "任务简单，直接执行..."

    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        if self._plans and self._current_plan_idx < len(self._plans):
            plan = self._plans[self._current_plan_idx]
            action = plan.get("action")

            if action == "tool_call":
                return {
                    "type": "tool_call",
                    "tool_name": plan.get("tool_name"),
                    "tool_args": plan.get("tool_args", {}),
                }
            elif action == "response":
                self._current_plan_idx += 1
                return {
                    "type": "response",
                    "content": plan.get("content", ""),
                }
            else:
                self._current_plan_idx += 1
                return {
                    "type": "response",
                    "content": f"执行步骤 {self._current_plan_idx}: {plan.get('description', '完成')}",
                }

        return {
            "type": "response",
            "content": f"任务已完成。共执行 {self._current_plan_idx} 个步骤。",
        }

    async def act(self, tool_name: str, tool_args: Dict[str, Any], **kwargs) -> Any:
        if tool_name not in self.tools:
            raise ValueError(f"工具 '{tool_name}' 不存在")

        tool = self.tools[tool_name]

        if hasattr(tool, "execute"):
            result = tool.execute(**tool_args)
            if asyncio.iscoroutine(result):
                result = await result
        elif callable(tool):
            result = tool(**tool_args)
            if asyncio.iscoroutine(result):
                result = await result
        else:
            raise ValueError(f"工具 '{tool_name}' 无法执行")

        self._current_plan_idx += 1

        if isinstance(result, dict):
            return result
        return {"result": str(result)}

    def _should_plan(self, message: str) -> bool:
        planning_keywords = ["帮我", "完成", "分析", "整理", "创建", "实现", "开发"]
        return any(kw in message for kw in planning_keywords)

    async def _create_plan(self, message: str, **kwargs) -> List[Dict[str, Any]]:
        plans = [
            {
                "step": 1,
                "action": "response",
                "description": "理解任务需求",
                "content": f"我已理解您的需求: {message}",
            },
            {
                "step": 2,
                "action": "tool_call",
                "tool_name": "bash",
                "tool_args": {"command": "pwd"},
                "description": "检查当前工作目录",
            },
            {
                "step": 3,
                "action": "response",
                "description": "总结执行结果",
                "content": "任务已开始执行，请查看执行日志。",
            },
        ]

        if self.model_provider:
            try:
                plans = await self._create_plan_with_llm(message, **kwargs)
            except Exception as e:
                logger.warning(f"LLM 规划失败，使用默认计划: {e}")

        return plans

    async def _create_plan_with_llm(
        self, message: str, **kwargs
    ) -> List[Dict[str, Any]]:
        if not self.model_provider:
            return []

        try:
            prompt = f"""请为以下任务制定执行计划。

任务: {message}

可用工具: {", ".join(self.tools.keys())}

请以 JSON 数组格式返回计划，每个步骤包含:
- step: 步骤编号
- action: "tool_call" 或 "response"
- tool_name: 工具名称(tool_call 时)
- tool_args: 工具参数(tool_call 时)
- content: 响应内容(response 时)
- description: 步骤描述

只返回 JSON 数组，不要其他内容。"""

            response = None
            if hasattr(self.model_provider, "generate"):
                response = await self.model_provider.generate(prompt)
            elif hasattr(self.model_provider, "chat"):
                response = await self.model_provider.chat(
                    [{"role": "user", "content": prompt}]
                )

            if response:
                content = response
                if hasattr(response, "content"):
                    content = response.content
                elif hasattr(response, "choices"):
                    content = response.choices[0].message.content

                plans = json.loads(content)
                if isinstance(plans, list):
                    return plans

        except Exception as e:
            logger.exception(f"LLM 规划异常: {e}")

        return []


class V2SimpleAgent(AgentBase):
    """
    V2 Simple Agent - 简化版 Agent

    适用于简单对话场景
    """

    def __init__(
        self,
        info: AgentInfo,
        model_provider: Optional[Any] = None,
    ):
        super().__init__(info)
        self.model_provider = model_provider

    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        yield f"思考中..."

    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        if self.model_provider:
            try:
                response = None
                if hasattr(self.model_provider, "generate"):
                    response = await self.model_provider.generate(message)
                elif hasattr(self.model_provider, "chat"):
                    response = await self.model_provider.chat(
                        [{"role": "user", "content": message}]
                    )

                if response:
                    content = response
                    if hasattr(response, "content"):
                        content = response.content
                    elif hasattr(response, "choices"):
                        content = response.choices[0].message.content

                    return {"type": "response", "content": content}
            except Exception as e:
                logger.error(f"模型调用失败: {e}")

        return {"type": "response", "content": f"收到: {message}"}

    async def act(self, tool_name: str, tool_args: Dict[str, Any], **kwargs) -> Any:
        return {"result": "Simple agent does not support tools"}


def create_v2_agent(
    name: str = "primary",
    mode: str = "primary",
    tools: Optional[Dict[str, Any]] = None,
    resources: Optional[Dict[str, Any]] = None,
    model_provider: Optional[Any] = None,
    model_config: Optional[Dict] = None,
    permission: Optional[Dict] = None,
) -> AgentBase:
    """
    创建 V2 Agent 的工厂函数

    Args:
        name: Agent 名称
        mode: Agent 模式 (primary, planner, worker)
        tools: 工具字典
        resources: 资源字典
        model_provider: 模型提供者
        model_config: 模型配置
        permission: 权限配置

    Returns:
        AgentBase: 创建的 Agent 实例
    """
    from ..agent_info import AgentMode, PermissionRuleset

    mode_map = {
        "primary": AgentMode.PRIMARY,
        "planner": AgentMode.PLANNER,
        "worker": AgentMode.WORKER,
    }

    permission_ruleset = None
    if permission:
        permission_ruleset = PermissionRuleset.from_dict(permission)
    else:
        permission_ruleset = PermissionRuleset.default()

    info = AgentInfo(
        name=name,
        mode=mode_map.get(mode, AgentMode.PRIMARY),
        permission=permission_ruleset,
    )

    if mode == "planner" or tools:
        return V2PDCAAgent(
            info=info,
            tools=tools,
            resources=resources,
            model_provider=model_provider,
            model_config=model_config,
        )
    else:
        return V2SimpleAgent(
            info=info,
            model_provider=model_provider,
        )
