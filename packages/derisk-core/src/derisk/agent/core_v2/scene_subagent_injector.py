"""
SceneSubagentInjector - 场景子Agent自动注入器

实现场景驱动的LLM自主多Agent决策：
1. Agent初始化时，根据场景配置自动注入TaskTool
2. 自动创建并配置SubagentManager
3. LLM运行时100%自主决策调用

使用方式：
```python
# 方式1：在Agent初始化后自动注入
from derisk.agent.core_v2.scene_subagent_injector import inject_subagents_from_scene

agent = ReActReasoningAgent.create(name="assistant", model="gpt-4")
await inject_subagents_from_scene(agent, TaskScene.CODING)

# 方式2：在SceneProfile中配置（推荐）
profile = SceneProfile(
    scene=TaskScene.CODING,
    subagent_policy=SubagentPolicy(enabled=True, subagents=[...]),
)
# Agent创建时自动注入
```
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .task_scene import TaskScene, SceneProfile, SubagentPolicy, SubagentConfig

logger = logging.getLogger(__name__)


# =============================================================================
# 预定义的子Agent配置
# =============================================================================

BUILTIN_SUBAGENT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "general": {
        "name": "general",
        "description": "通用助手Agent，处理一般性任务",
        "capabilities": ["general", "reasoning"],
        "max_steps": 15,
        "priority": 0,
    },
    "explore": {
        "name": "explore",
        "description": "代码库探索Agent，快速搜索和理解代码结构",
        "capabilities": ["code-search", "file-search", "structure-analysis"],
        "allowed_tools": ["read", "grep", "glob", "list_files", "search"],
        "max_steps": 10,
        "priority": 10,
    },
    "librarian": {
        "name": "librarian",
        "description": "文档检索Agent，查找外部文档和最佳实践",
        "capabilities": ["doc-search", "api-reference", "best-practices"],
        "allowed_tools": ["webfetch", "websearch", "read"],
        "max_steps": 8,
        "priority": 8,
    },
    "code-reviewer": {
        "name": "code-reviewer",
        "description": "代码审查Agent，检查代码质量和安全问题",
        "capabilities": ["code-review", "security-audit", "quality-check"],
        "allowed_tools": ["read", "grep", "glob"],
        "max_steps": 12,
        "priority": 9,
    },
    "oracle": {
        "name": "oracle",
        "description": "高级顾问Agent，提供架构建议和复杂问题分析",
        "capabilities": ["architecture", "design-review", "problem-analysis"],
        "max_steps": 5,
        "priority": 15,
        "temperature": 0.3,
    },
    "tester": {
        "name": "tester",
        "description": "测试Agent，编写和执行测试用例",
        "capabilities": ["test-generation", "test-execution", "coverage-analysis"],
        "allowed_tools": ["read", "write", "edit", "bash"],
        "max_steps": 15,
        "priority": 7,
    },
    "coder": {
        "name": "coder",
        "description": "代码实现Agent，专注于编写代码",
        "capabilities": ["coding", "implementation", "debugging"],
        "allowed_tools": ["read", "write", "edit", "grep", "glob", "bash"],
        "max_steps": 20,
        "priority": 10,
    },
    "analyst": {
        "name": "analyst",
        "description": "数据分析Agent，处理日志和数据文件",
        "capabilities": ["data-analysis", "log-analysis", "report-generation"],
        "allowed_tools": ["read", "grep", "glob", "bash"],
        "max_steps": 12,
        "priority": 6,
    },
}


# =============================================================================
# 场景子Agent策略预设
# =============================================================================

SCENE_SUBAGENT_PRESETS: Dict[str, Dict[str, Any]] = {
    "general": {
        "enabled": True,
        "subagents": ["general"],
        "default_timeout": 300,
    },
    "coding": {
        "enabled": True,
        "subagents": ["explore", "code-reviewer", "tester", "oracle"],
        "max_concurrent": 3,
    },
    "analysis": {
        "enabled": True,
        "subagents": ["explore", "analyst", "librarian"],
        "default_timeout": 600,
    },
    "research": {
        "enabled": True,
        "subagents": ["explore", "librarian", "oracle"],
        "default_timeout": 900,
        "max_concurrent": 2,
    },
    "debug": {
        "enabled": True,
        "subagents": ["explore", "analyst", "code-reviewer"],
        "default_timeout": 600,
    },
    "refactoring": {
        "enabled": True,
        "subagents": ["explore", "code-reviewer", "oracle", "tester"],
        "default_timeout": 900,
    },
    "documentation": {
        "enabled": True,
        "subagents": ["explore"],
        "max_concurrent": 2,
    },
    "testing": {
        "enabled": True,
        "subagents": ["explore", "tester", "code-reviewer"],
    },
    "creative": {
        "enabled": False,
        "subagents": [],
    },
}


def get_builtin_subagent_config(name: str) -> Optional[Dict[str, Any]]:
    """获取内置子Agent配置"""
    return BUILTIN_SUBAGENT_CONFIGS.get(name)


def get_scene_subagent_preset(scene: str) -> Dict[str, Any]:
    """获取场景的子Agent预设"""
    return SCENE_SUBAGENT_PRESETS.get(scene, {"enabled": False, "subagents": []})


# =============================================================================
# 核心注入器
# =============================================================================


class SceneSubagentInjector:
    """
    场景子Agent注入器

    职责：
    1. 根据场景配置创建SubagentManager
    2. 注册场景定义的子Agent
    3. 自动注入TaskTool到Agent工具列表
    4. 注入子Agent描述到系统提示

    使用示例：
    ```python
    # 创建注入器
    injector = SceneSubagentInjector()

    # 注入到Agent
    await injector.inject(agent, scene=TaskScene.CODING)

    # 或使用场景配置
    await injector.inject_from_profile(agent, profile)
    ```
    """

    def __init__(self):
        self._manager = None
        self._injected_agents: Dict[str, bool] = {}

    async def inject(
        self,
        agent: Any,
        scene: "TaskScene",
        custom_subagents: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        根据场景注入子Agent能力

        Args:
            agent: 主Agent实例
            scene: 任务场景
            custom_subagents: 自定义子Agent列表（覆盖场景预设）
            session_id: 会话ID

        Returns:
            是否成功注入
        """
        from .task_scene import TaskScene, SubagentPolicy, SubagentConfig

        # 获取场景预设
        scene_value = scene.value if hasattr(scene, "value") else str(scene)
        preset = get_scene_subagent_preset(scene_value)

        if not preset.get("enabled", False) and not custom_subagents:
            logger.debug(
                f"[SceneSubagentInjector] Scene {scene_value} has subagent disabled"
            )
            return False

        # 构建子Agent配置列表
        subagent_names = custom_subagents or preset.get("subagents", [])
        subagent_configs = []

        for name in subagent_names:
            config = get_builtin_subagent_config(name)
            if config:
                subagent_configs.append(SubagentConfig(**config))
            else:
                logger.warning(f"[SceneSubagentInjector] Unknown subagent: {name}")

        if not subagent_configs:
            logger.warning(
                f"[SceneSubagentInjector] No valid subagents for scene {scene_value}"
            )
            return False

        # 创建策略
        policy = SubagentPolicy(
            enabled=True,
            subagents=subagent_configs,
            default_timeout=preset.get("default_timeout", 300),
            max_concurrent=preset.get("max_concurrent", 5),
        )

        return await self._do_inject(agent, policy, session_id)

    async def inject_from_profile(
        self,
        agent: Any,
        profile: "SceneProfile",
        session_id: Optional[str] = None,
    ) -> bool:
        """
        从场景配置注入

        Args:
            agent: 主Agent实例
            profile: 场景配置
            session_id: 会话ID

        Returns:
            是否成功注入
        """
        policy = profile.subagent_policy

        if not policy.enabled:
            logger.debug(
                f"[SceneSubagentInjector] Subagent disabled in profile: {profile.name}"
            )
            return False

        return await self._do_inject(agent, policy, session_id)

    async def _do_inject(
        self, agent: Any, policy: "SubagentPolicy", session_id: Optional[str] = None
    ) -> bool:
        try:
            from .subagent_manager import SubagentManager, SubagentInfo

            self._manager = SubagentManager()

            for sub_config in policy.subagents:
                info = SubagentInfo(
                    name=sub_config.name,
                    description=sub_config.description,
                    capabilities=sub_config.capabilities,
                    max_steps=sub_config.max_steps,
                    timeout=sub_config.timeout,
                )

                info._factory = self._create_subagent_factory(sub_config, agent)
                self._manager.register(info)
                logger.info(
                    f"[SceneSubagentInjector] Registered subagent: {sub_config.name}"
                )

            orchestrator = None
            if policy.enabled:
                try:
                    from .multi_agent import MultiAgentOrchestrator

                    orchestrator = MultiAgentOrchestrator(
                        max_parallel_agents=policy.max_concurrent,
                    )
                    self._orchestrator = orchestrator
                    logger.info(
                        "[SceneSubagentInjector] Created MultiAgentOrchestrator"
                    )
                except Exception as e:
                    logger.warning(
                        f"[SceneSubagentInjector] Failed to create orchestrator: {e}"
                    )

            distributed_executor = None
            if policy.enabled:
                try:
                    from .distributed_execution import DistributedTaskExecutor

                    distributed_executor = DistributedTaskExecutor()
                    self._distributed_executor = distributed_executor
                    logger.info(
                        "[SceneSubagentInjector] Created DistributedTaskExecutor"
                    )
                except Exception as e:
                    logger.warning(
                        f"[SceneSubagentInjector] Failed to create distributed executor: {e}"
                    )

            if policy.auto_inject_task_tool:
                await self._inject_task_tool(agent, policy)

            await self._inject_system_prompt(agent, policy)

            if hasattr(agent, "_subagent_manager"):
                agent._subagent_manager = self._manager
            if hasattr(agent, "_subagent_policy"):
                agent._subagent_policy = policy
            if hasattr(agent, "_orchestrator"):
                agent._orchestrator = orchestrator
            if hasattr(agent, "_distributed_executor"):
                agent._distributed_executor = distributed_executor

            agent_id = (
                getattr(agent, "info", {}).get("name", "unknown")
                if hasattr(agent, "info")
                else "unknown"
            )
            self._injected_agents[agent_id] = True

            logger.info(
                f"[SceneSubagentInjector] Injection complete: "
                f"{len(policy.subagents)} subagents, "
                f"orchestrator={'yes' if orchestrator else 'no'}, "
                f"distributed_executor={'yes' if distributed_executor else 'no'}"
            )
            return True

        except Exception as e:
            logger.error(f"[SceneSubagentInjector] Injection failed: {e}")
            return False

    def _create_subagent_factory(self, config: "SubagentConfig", parent_agent: Any):
        async def factory():
            from .builtin_agents import ReActReasoningAgent
            from .agent_info import AgentInfo

            info = AgentInfo(
                name=config.name,
                max_steps=config.max_steps,
            )

            llm_adapter = getattr(parent_agent, "llm_adapter", None)
            if not llm_adapter:
                llm_adapter = getattr(parent_agent, "_llm_adapter", None)

            sub_agent = ReActReasoningAgent(
                info=info,
                llm_adapter=llm_adapter,
            )

            if config.allowed_tools:
                all_tools = sub_agent.tools.list_names()
                for tool_name in all_tools:
                    if tool_name not in config.allowed_tools:
                        sub_agent.tools.unregister(tool_name)

            return sub_agent

        return factory

    async def _inject_task_tool(self, agent: Any, policy: "SubagentPolicy"):
        try:
            from derisk.agent.tools.builtin.task import (
                TaskTool,
                OrchestrateTool,
                BatchTaskTool,
                register_multi_agent_tools,
            )

            if hasattr(agent, "tools") and agent.tools.get("task"):
                logger.debug("[SceneSubagentInjector] TaskTool already exists")
                return

            if hasattr(agent, "tools"):
                register_multi_agent_tools(
                    agent.tools,
                    subagent_manager=self._manager,
                    orchestrator=getattr(self, "_orchestrator", None),
                    distributed_executor=getattr(self, "_distributed_executor", None),
                )
                logger.info(
                    "[SceneSubagentInjector] 注入3种多Agent工具: task, orchestrate, batch_task"
                )

        except ImportError as e:
            logger.warning(f"[SceneSubagentInjector] 多Agent工具导入失败: {e}")
        except Exception as e:
            logger.error(f"[SceneSubagentInjector] 注入多Agent工具失败: {e}")

    async def _inject_system_prompt(self, agent: Any, policy: "SubagentPolicy"):
        description = policy.get_tool_description()
        if not description:
            return

        if hasattr(agent, "_subagent_description"):
            agent._subagent_description = description

        if hasattr(agent, "_extra_system_sections"):
            agent._extra_system_sections = agent._extra_system_sections or {}
            agent._extra_system_sections["subagents"] = description

        logger.debug(
            f"[SceneSubagentInjector] Injected subagent description: {len(description)} chars"
        )

    def get_manager(self) -> Optional[Any]:
        return self._manager

    def is_injected(self, agent_name: str) -> bool:
        return self._injected_agents.get(agent_name, False)


# =============================================================================
# 便捷函数
# =============================================================================

_injector: Optional[SceneSubagentInjector] = None


def get_injector() -> SceneSubagentInjector:
    """获取全局注入器"""
    global _injector
    if _injector is None:
        _injector = SceneSubagentInjector()
    return _injector


async def inject_subagents_from_scene(
    agent: Any,
    scene: "TaskScene",
    custom_subagents: Optional[List[str]] = None,
) -> bool:
    """
    便捷函数：根据场景注入子Agent能力

    Args:
        agent: 主Agent实例
        scene: 任务场景
        custom_subagents: 自定义子Agent列表

    Returns:
        是否成功注入
    """
    injector = get_injector()
    return await injector.inject(agent, scene, custom_subagents)


async def inject_subagents_from_profile(
    agent: Any,
    profile: "SceneProfile",
) -> bool:
    """
    便捷函数：从场景配置注入

    Args:
        agent: 主Agent实例
        profile: 场景配置

    Returns:
        是否成功注入
    """
    injector = get_injector()
    return await injector.inject_from_profile(agent, profile)


# =============================================================================
# 扩展 SceneProfileBuilder
# =============================================================================


def extend_scene_builder():
    """
    扩展 SceneProfileBuilder 支持 subagent_policy

    使用方式：
    ```python
    profile = (
        SceneProfileBuilder()
        .scene(TaskScene.CODING)
        .name("My Coding Mode")
        .subagents(["explore", "code-reviewer"])  # 启用子Agent
        .build()
    )
    ```
    """
    from .task_scene import SceneProfileBuilder, SubagentPolicy, SubagentConfig

    def subagents(
        self, subagent_names: List[str], enabled: bool = True, **kwargs
    ) -> "SceneProfileBuilder":
        """配置子Agent"""
        configs = []
        for name in subagent_names:
            config = get_builtin_subagent_config(name)
            if config:
                configs.append(SubagentConfig(**config))

        self._subagent_policy = SubagentPolicy(
            enabled=enabled, subagents=configs, **kwargs
        )
        return self

    # 动态添加方法
    SceneProfileBuilder.subagents = subagents


# 自动扩展
extend_scene_builder()
