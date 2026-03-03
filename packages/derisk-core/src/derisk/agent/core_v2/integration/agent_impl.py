"""
V2PDCAAgent - 基于 Core_v2 的 PDCA Agent 实现

整合原有的 PDCA 能力与 Core_v2 架构，完整支持 MCP、Knowledge、Skill 等资源
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
from ..llm_utils import call_llm, LLMCaller

logger = logging.getLogger(__name__)


class ResourceMixin:
    """资源处理混入类，为Agent提供资源处理能力"""
    
    resources: Dict[str, Any] = {}
    
    def get_knowledge_context(self) -> str:
        """获取知识资源上下文"""
        knowledge_list = self.resources.get("knowledge", [])
        if not knowledge_list:
            return ""
        
        parts = ["<knowledge-resources>"]
        for idx, k in enumerate(knowledge_list, 1):
            space_id = k.get("space_id", k.get("id", ""))
            space_name = k.get("space_name", k.get("name", space_id))
            parts.append(f"<knowledge-{idx}>")
            parts.append(f"<space-id>{space_id}</space-id>")
            parts.append(f"<space-name>{space_name}</space-name>")
            if k.get("description"):
                parts.append(f"<description>{k.get('description')}</description>")
            parts.append(f"</knowledge-{idx}>")
        parts.append("</knowledge-resources>")
        
        return "\n".join(parts)
    
    def get_skills_context(self) -> str:
        """获取技能资源上下文"""
        skills_list = self.resources.get("skills", [])
        if not skills_list:
            return ""
        
        parts = ["<agent-skills>"]
        for idx, s in enumerate(skills_list, 1):
            name = s.get("name", s.get("skill_name", ""))
            code = s.get("code", s.get("skill_code", ""))
            description = s.get("description", "")
            path = s.get("path", s.get("sandbox_path", ""))
            owner = s.get("owner", s.get("author", ""))
            branch = s.get("branch", "main")
            
            parts.append(f"<skill-{idx}>")
            parts.append(f"<name>{name}</name>")
            parts.append(f"<code>{code}</code>")
            if description:
                parts.append(f"<description>{description}</description>")
            if path:
                parts.append(f"<path>{path}</path>")
            if owner:
                parts.append(f"<owner>{owner}</owner>")
            parts.append(f"<branch>{branch}</branch>")
            parts.append(f"</skill-{idx}>")
        parts.append("</agent-skills>")
        
        return "\n".join(parts)
    
    def build_resource_prompt(self, base_prompt: str = "") -> str:
        """构建包含资源信息的完整提示"""
        prompt_parts = [base_prompt] if base_prompt else []
        
        knowledge_ctx = self.get_knowledge_context()
        if knowledge_ctx:
            prompt_parts.append(knowledge_ctx)
        
        skills_ctx = self.get_skills_context()
        if skills_ctx:
            prompt_parts.append(skills_ctx)
        
        return "\n\n".join(prompt_parts)


class V2PDCAAgent(AgentBase, ResourceMixin):
    """
    V2 PDCA Agent - 基于 Core_v2 架构实现

    集成原有的 PDCA 循环能力：
    1. Plan - 任务规划
    2. Do - 任务执行
    3. Check - 结果检查
    4. Act - 调整行动
    
    支持 MCP、Knowledge、Skill 等完整资源类型

    示例:
        agent = V2PDCAAgent(
            info=AgentInfo(name="pdca", mode=AgentMode.PRIMARY),
            tools={"bash": bash_tool},
            resources={
                "knowledge": [{"space_id": "kb_001"}],
                "skills": [{"skill_code": "code_assistant"}],
            },
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
        self._initialized_mcp = False

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
        
        if self.model_provider:
            try:
                content = await call_llm(self.model_provider, message)
                if content:
                    return {"type": "response", "content": content}
                return {"type": "response", "content": "抱歉，模型返回了空响应，请稍后重试。"}
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}", exc_info=True)
                return {"type": "response", "content": f"抱歉，模型调用失败: {str(e)}"}
        
        return {
            "type": "response",
            "content": "抱歉，未配置模型服务，无法处理您的请求。",
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
            resource_context = self.build_resource_prompt()
            
            prompt_parts = [f"""请为以下任务制定执行计划。

任务: {message}

可用工具: {", ".join(self.tools.keys())}"""]
            
            if resource_context:
                prompt_parts.append(f"""
可用资源:
{resource_context}""")
            
            prompt_parts.append("""
请以 JSON 数组格式返回计划，每个步骤包含:
- step: 步骤编号
- action: "tool_call" 或 "response"
- tool_name: 工具名称(tool_call 时)
- tool_args: 工具参数(tool_call 时)
- content: 响应内容(response 时)
- description: 步骤描述

只返回 JSON 数组，不要其他内容。""")
            
            prompt = "\n".join(prompt_parts)

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
                content = await call_llm(self.model_provider, message)
                if content:
                    return {"type": "response", "content": content}
                return {"type": "response", "content": "抱歉，模型返回了空响应。"}
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}", exc_info=True)
                return {"type": "response", "content": f"抱歉，模型调用失败: {str(e)}"}
        
        return {"type": "response", "content": "抱歉，未配置模型服务。"}

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
        "planner": AgentMode.PRIMARY,
        "worker": AgentMode.SUBAGENT,
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


def create_default_agent(
    name: str = "primary",
    model: str = "gpt-4",
    api_key: Optional[str] = None,
    max_steps: int = 20,
    **kwargs,
) -> "ProductionAgentWithInteraction":
    """
    创建默认的主 Agent (ProductionAgentWithInteraction)

    这是 Core_v2 推荐的默认 Agent，具备最完整的能力：
    - LLM 调用
    - 工具执行
    - 目标追踪
    - 权限检查
    - 用户交互（主动提问、授权审批、方案选择）
    - Todo 管理
    - 中断恢复

    Args:
        name: Agent 名称
        model: 模型名称
        api_key: API Key
        max_steps: 最大执行步骤
        **kwargs: 其他参数

    Returns:
        ProductionAgentWithInteraction: 默认 Agent 实例

    Example:
        agent = create_default_agent(
            name="my-agent",
            model="gpt-4",
            api_key="sk-xxx",
        )
        agent.init_interaction()
        async for chunk in agent.run("帮我完成代码重构"):
            print(chunk)
    """
    from ..production_interaction import ProductionAgentWithInteraction
    return ProductionAgentWithInteraction.create(
        name=name,
        model=model,
        api_key=api_key,
        max_steps=max_steps,
        **kwargs,
    )
