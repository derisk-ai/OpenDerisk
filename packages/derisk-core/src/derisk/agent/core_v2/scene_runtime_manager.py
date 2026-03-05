"""
SceneRuntimeManager - 场景运行时管理器

管理场景生命周期、工具注入、上下文传递

设计原则:
- 统一管理：集中管理所有场景状态
- 会话隔离：每个会话有独立的场景状态
- 工具动态注入：按需注入和清理场景工具
"""

from typing import Optional, Dict, Any, List
import logging
from datetime import datetime

from .scene_definition import (
    AgentRoleDefinition,
    SceneDefinition,
    SceneState,
    SceneSwitchRecord,
)
from .scene_definition_parser import SceneDefinitionParser
from .tools_v2 import ToolRegistry

logger = logging.getLogger(__name__)


class SceneRuntimeManager:
    """
    场景运行时管理器

    职责：
    1. 加载和缓存场景定义
    2. 管理场景状态（激活、切换、退出）
    3. 动态注入和清理工具
    4. 执行场景钩子
    5. 维护场景切换历史
    """

    def __init__(
        self,
        agent_role: AgentRoleDefinition,
        scene_definitions: Optional[Dict[str, SceneDefinition]] = None,
    ):
        """
        初始化场景运行时管理器

        Args:
            agent_role: Agent 基础角色定义
            scene_definitions: 场景定义字典 {scene_id: SceneDefinition}
        """
        self.agent_role = agent_role
        self.scene_definitions = scene_definitions or {}
        self.parser = SceneDefinitionParser()

        # 会话状态管理
        self._session_states: Dict[str, SceneState] = {}

        # 场景切换历史
        self._switch_history: Dict[str, List[SceneSwitchRecord]] = {}

        logger.info(
            f"[SceneRuntimeManager] Initialized with agent={agent_role.name}, "
            f"scenes={len(self.scene_definitions)}"
        )

    async def load_scene_from_md(self, md_path: str) -> SceneDefinition:
        """
        从 MD 文件加载场景定义

        Args:
            md_path: MD 文件路径

        Returns:
            SceneDefinition 实例
        """
        scene_def = await self.parser.parse_scene_definition(md_path)
        self.scene_definitions[scene_def.scene_id] = scene_def

        logger.info(
            f"[SceneRuntimeManager] Loaded scene: {scene_def.scene_id} from {md_path}"
        )

        return scene_def

    async def activate_scene(
        self,
        scene_id: str,
        session_id: str,
        agent: Any,
    ) -> Dict[str, Any]:
        """
        激活场景

        Args:
            scene_id: 场景 ID
            session_id: 会话 ID
            agent: Agent 实例

        Returns:
            激活结果
        """
        # 检查场景是否存在
        if scene_id not in self.scene_definitions:
            raise ValueError(f"Scene not found: {scene_id}")

        scene_def = self.scene_definitions[scene_id]

        # 创建场景状态
        state = SceneState(
            current_scene_id=scene_id,
            activated_at=datetime.now(),
            tools_injected=scene_def.scene_tools.copy(),
            workflow_phase=0,
            step_count=0,
        )

        # 保存状态
        self._session_states[session_id] = state

        # 注入场景工具
        await self._inject_scene_tools(agent, scene_def.scene_tools)

        # 执行 on_enter 钩子（如果定义）
        if scene_def.hooks and scene_def.hooks.on_enter:
            await self._execute_hook(scene_def.hooks.on_enter, agent, state)

        logger.info(
            f"[SceneRuntimeManager] Activated scene: {scene_id} for session {session_id}, "
            f"tools_injected={len(state.tools_injected)}"
        )

        return {
            "success": True,
            "scene_id": scene_id,
            "scene_name": scene_def.scene_name,
            "activated_at": state.activated_at,
            "tools_injected": state.tools_injected,
        }

    async def switch_scene(
        self,
        from_scene: str,
        to_scene: str,
        session_id: str,
        agent: Any,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        切换场景

        Args:
            from_scene: 当前场景 ID
            to_scene: 目标场景 ID
            session_id: 会话 ID
            agent: Agent 实例
            reason: 切换原因

        Returns:
            切换结果
        """
        # 获取当前状态
        current_state = self._session_states.get(session_id)

        # 执行旧场景的 on_exit 钩子
        if from_scene and from_scene in self.scene_definitions:
            old_scene_def = self.scene_definitions[from_scene]
            if old_scene_def.hooks and old_scene_def.hooks.on_exit:
                await self._execute_hook(
                    old_scene_def.hooks.on_exit, agent, current_state
                )

            # 清理旧工具
            await self._cleanup_scene_tools(agent, old_scene_def.scene_tools)

        # 激活新场景
        activation_result = await self.activate_scene(to_scene, session_id, agent)

        # 记录切换历史
        record = SceneSwitchRecord(
            from_scene=from_scene,
            to_scene=to_scene,
            timestamp=datetime.now(),
            reason=reason,
        )

        if session_id not in self._switch_history:
            self._switch_history[session_id] = []
        self._switch_history[session_id].append(record)

        logger.info(
            f"[SceneRuntimeManager] Switched scene: {from_scene} -> {to_scene}, "
            f"session={session_id}, reason={reason}"
        )

        return {
            "success": True,
            "from_scene": from_scene,
            "to_scene": to_scene,
            "switched_at": record.timestamp,
            "reason": reason,
        }

    async def _inject_scene_tools(self, agent: Any, tools: List[str]) -> None:
        """
        注入场景工具到 Agent

        Args:
            agent: Agent 实例
            tools: 工具名称列表
        """
        if not hasattr(agent, "tools"):
            logger.warning("[SceneRuntimeManager] Agent has no tools registry")
            return

        # 注入工具
        # 注意：这里假设工具已经在全局注册，场景只需要指定使用哪些工具
        # 实际注入逻辑需要根据 ToolRegistry 的实现来调整

        logger.info(f"[SceneRuntimeManager] Injected tools: {tools}")

    async def _cleanup_scene_tools(self, agent: Any, tools: List[str]) -> None:
        """
        清理场景工具

        Args:
            agent: Agent 实例
            tools: 工具名称列表
        """
        # TODO: 实现工具清理逻辑
        # 当前暂时不清理，保留所有工具

        logger.info(f"[SceneRuntimeManager] Cleanup tools: {tools} (not implemented)")

    async def _execute_hook(
        self, hook_name: str, agent: Any, state: SceneState
    ) -> None:
        """
        执行场景钩子

        Args:
            hook_name: 钩子函数名
            agent: Agent 实例
            state: 场景状态
        """
        # TODO: 实现钩子执行逻辑
        # 需要根据 hook_name 查找对应的钩子函数并执行

        logger.info(f"[SceneRuntimeManager] Execute hook: {hook_name}")

    def get_current_scene(self, session_id: str) -> Optional[str]:
        """获取当前激活的场景 ID"""
        state = self._session_states.get(session_id)
        return state.current_scene_id if state else None

    def get_scene_state(self, session_id: str) -> Optional[SceneState]:
        """获取场景状态"""
        return self._session_states.get(session_id)

    def get_switch_history(self, session_id: str) -> List[SceneSwitchRecord]:
        """获取场景切换历史"""
        return self._switch_history.get(session_id, [])

    def build_system_prompt(
        self,
        scene_id: Optional[str] = None,
    ) -> str:
        """
        构建 System Prompt

        Args:
            scene_id: 场景 ID（如果为 None，只使用基础角色）

        Returns:
            完整的 System Prompt
        """
        # 基础角色设定
        parts = []

        # 添加 Agent 角色设定
        if self.agent_role.role_definition:
            parts.append(f"# 角色定位\n\n{self.agent_role.role_definition}")

        if self.agent_role.core_capabilities:
            parts.append(
                "# 核心能力\n\n"
                + "\n".join(f"- {cap}" for cap in self.agent_role.core_capabilities)
            )

        if self.agent_role.working_principles:
            parts.append(
                "# 工作原则\n\n"
                + "\n".join(
                    f"{i + 1}. {p}"
                    for i, p in enumerate(self.agent_role.working_principles)
                )
            )

        # 添加场景特定设定
        if scene_id and scene_id in self.scene_definitions:
            scene_def = self.scene_definitions[scene_id]

            if scene_def.scene_role_prompt:
                parts.append(f"\n\n# 场景角色设定\n\n{scene_def.scene_role_prompt}")

            if scene_def.workflow_phases:
                workflow_text = "\n\n# 工作流程\n\n"
                for i, phase in enumerate(scene_def.workflow_phases, 1):
                    workflow_text += f"## 阶段{i}: {phase.name}\n\n"
                    workflow_text += f"{phase.description}\n\n"
                    if phase.steps:
                        for j, step in enumerate(phase.steps, 1):
                            workflow_text += f"{j}. {step}\n"
                        workflow_text += "\n"
                parts.append(workflow_text)

        return "\n\n".join(parts)


# ==================== 导出 ====================

__all__ = [
    "SceneRuntimeManager",
]
