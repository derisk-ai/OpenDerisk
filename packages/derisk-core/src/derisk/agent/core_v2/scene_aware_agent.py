"""
SceneAwareAgent - 场景感知 ReAct Agent

集成场景管理功能到 ReAct 推理 Agent
支持场景自动检测、切换、工具注入和钩子执行

设计原则:
- 场景驱动：基于场景动态调整 Agent 行为
- 无缝集成：继承 ReActReasoningAgent，保持接口兼容
- 自动检测：根据用户输入自动识别和切换场景
- 状态追踪：维护完整的场景切换历史
"""

from typing import AsyncIterator, Dict, Any, Optional, List
import logging
from pathlib import Path
from datetime import datetime

from .builtin_agents.react_reasoning_agent import ReActReasoningAgent
from .agent_info import AgentInfo
from .llm_adapter import LLMAdapter
from .scene_definition import (
    AgentRoleDefinition,
    SceneDefinition,
    SceneSwitchDecision,
    SceneState,
    SceneSwitchRecord,
)
from .scene_definition_parser import SceneDefinitionParser
from .scene_switch_detector import SceneSwitchDetector, SessionContext
from .scene_runtime_manager import SceneRuntimeManager
from .tools_v2 import ToolRegistry

logger = logging.getLogger(__name__)


class SceneAwareAgent(ReActReasoningAgent):
    """
    场景感知的 ReAct Agent

    扩展 ReActReasoningAgent，增加场景管理能力：
    1. 加载和管理场景定义
    2. 自动检测场景切换
    3. 动态注入场景工具
    4. 构建场景化 System Prompt
    5. 执行场景钩子
    """

    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        # 场景相关配置
        agent_role_md: Optional[str] = None,
        scene_md_dir: Optional[str] = None,
        agent_role: Optional[AgentRoleDefinition] = None,
        scene_definitions: Optional[Dict[str, SceneDefinition]] = None,
        # 场景检测配置
        enable_auto_scene_switch: bool = True,
        scene_switch_check_interval: int = 1,
        scene_confidence_threshold: float = 0.7,
        # 其他配置
        **kwargs,
    ):
        """
        初始化场景感知 Agent

        Args:
            info: Agent 信息
            llm_adapter: LLM 适配器
            agent_role_md: Agent 角色 MD 文件路径
            scene_md_dir: 场景 MD 文件目录
            agent_role: Agent 角色定义（直接传入，优先级高于 MD 文件）
            scene_definitions: 场景定义字典（直接传入，优先级高于 MD 文件）
            enable_auto_scene_switch: 是否启用自动场景切换
            scene_switch_check_interval: 检查场景切换的间隔（每N轮检查一次）
            scene_confidence_threshold: 场景切换置信度阈值
            **kwargs: 其他传给父类的参数
        """
        # 调用父类初始化
        super().__init__(info=info, llm_adapter=llm_adapter, **kwargs)

        # 场景管理配置
        self.enable_auto_scene_switch = enable_auto_scene_switch
        self.scene_switch_check_interval = scene_switch_check_interval
        self.scene_confidence_threshold = scene_confidence_threshold

        # 初始化组件
        self._parser = SceneDefinitionParser()
        self._agent_role: Optional[AgentRoleDefinition] = None
        self._scene_definitions: Dict[str, SceneDefinition] = {}
        self._scene_manager: Optional[SceneRuntimeManager] = None
        self._scene_detector: Optional[SceneSwitchDetector] = None

        # 当前会话的场景状态
        self._current_scene_id: Optional[str] = None
        self._scene_history: List[SceneSwitchRecord] = []

        # 加载角色和场景定义
        if agent_role:
            self._agent_role = agent_role
        elif agent_role_md:
            await self._load_agent_role(agent_role_md)

        if scene_definitions:
            self._scene_definitions = scene_definitions
        elif scene_md_dir:
            await self._load_scene_definitions(scene_md_dir)

        # 初始化场景管理器
        if self._agent_role:
            self._scene_manager = SceneRuntimeManager(
                agent_role=self._agent_role, scene_definitions=self._scene_definitions
            )

        # 初始化场景检测器
        if self._scene_definitions:
            self._scene_detector = SceneSwitchDetector(
                available_scenes=list(self._scene_definitions.values()),
                llm_client=self.llm_client,
                confidence_threshold=scene_confidence_threshold,
            )

        logger.info(
            f"[SceneAwareAgent] Initialized: {self.info.name}, "
            f"scenes={len(self._scene_definitions)}, "
            f"auto_switch={enable_auto_scene_switch}"
        )

    async def _load_agent_role(self, md_path: str) -> None:
        """加载 Agent 角色定义"""
        try:
            self._agent_role = await self._parser.parse_agent_role(md_path)
            logger.info(f"[SceneAwareAgent] Loaded agent role: {self._agent_role.name}")
        except Exception as e:
            logger.error(f"[SceneAwareAgent] Failed to load agent role: {e}")
            raise

    async def _load_scene_definitions(self, md_dir: str) -> None:
        """加载场景定义"""
        try:
            dir_path = Path(md_dir)
            if not dir_path.exists():
                logger.warning(f"[SceneAwareAgent] Scene directory not found: {md_dir}")
                return

            # 查找所有场景 MD 文件
            scene_files = list(dir_path.glob("scene-*.md"))

            for scene_file in scene_files:
                try:
                    scene_def = await self._parser.parse_scene_definition(
                        str(scene_file)
                    )
                    self._scene_definitions[scene_def.scene_id] = scene_def
                    logger.info(f"[SceneAwareAgent] Loaded scene: {scene_def.scene_id}")
                except Exception as e:
                    logger.warning(
                        f"[SceneAwareAgent] Failed to load scene {scene_file}: {e}"
                    )

            logger.info(
                f"[SceneAwareAgent] Loaded {len(self._scene_definitions)} scenes"
            )
        except Exception as e:
            logger.error(f"[SceneAwareAgent] Failed to load scenes: {e}")

    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """
        主执行循环（带场景检测）

        Args:
            message: 用户输入
            stream: 是否流式输出

        Yields:
            str: 输出内容
        """
        # 1. 检测和切换场景
        if self.enable_auto_scene_switch and self._should_check_scene():
            switch_decision = await self._detect_and_switch_scene(message)

            if switch_decision and switch_decision.should_switch:
                yield f"\n[场景切换] {self._current_scene_id} → {switch_decision.target_scene}\n"

        # 2. 如果没有激活场景，选择初始场景
        if not self._current_scene_id and self._scene_definitions:
            initial_scene = await self._select_initial_scene(message)
            if initial_scene:
                await self._activate_scene(initial_scene.scene_id)
                yield f"\n[场景激活] {initial_scene.scene_name}\n"

        # 3. 执行 ReAct 推理循环
        async for chunk in super().run(message, stream):
            yield chunk

    def _should_check_scene(self) -> bool:
        """检查是否应该检测场景"""
        # 每隔一定步数检查一次场景
        if self._current_step % self.scene_switch_check_interval == 0:
            return True

        # 当前没有场景时，必须检查
        if not self._current_scene_id:
            return True

        return False

    async def _detect_and_switch_scene(
        self, user_input: str
    ) -> Optional[SceneSwitchDecision]:
        """检测并切换场景"""
        if not self._scene_detector:
            return None

        # 构建会话上下文
        context = SessionContext(
            session_id=self._session_id or self.info.name,
            conv_id=getattr(self, "_conv_id", None) or self._session_id,
            current_scene_id=self._current_scene_id,
            message_count=len(self._messages),
            last_user_input=user_input,
            last_scene_switch_time=self._get_last_switch_time(),
        )

        # 检测场景
        decision = await self._scene_detector.detect_scene(user_input, context)

        # 执行切换
        if decision.should_switch and decision.target_scene != self._current_scene_id:
            await self._switch_scene(
                from_scene=self._current_scene_id,
                to_scene=decision.target_scene,
                reason=decision.reasoning,
            )

        return decision

    async def _select_initial_scene(self, user_input: str) -> Optional[SceneDefinition]:
        """选择初始场景"""
        if not self._scene_detector:
            # 如果没有检测器，选择优先级最高的场景
            if self._scene_definitions:
                return max(
                    self._scene_definitions.values(), key=lambda s: s.trigger_priority
                )
            return None

        # 使用检测器选择场景
        decision = await self._scene_detector.detect_scene(
            user_input,
            SessionContext(
                session_id=self._session_id or self.info.name,
                conv_id=getattr(self, "_conv_id", None) or self._session_id,
                current_scene_id=None,
                message_count=0,
            ),
        )

        if decision.target_scene:
            return self._scene_definitions.get(decision.target_scene)

        return None

    async def _activate_scene(self, scene_id: str) -> None:
        """激活场景"""
        if not self._scene_manager:
            logger.warning("[SceneAwareAgent] Scene manager not initialized")
            return

        result = await self._scene_manager.activate_scene(
            scene_id=scene_id, session_id=self._session_id or self.info.name, agent=self
        )

        if result.get("success"):
            self._current_scene_id = scene_id

            # 记录激活历史
            record = SceneSwitchRecord(
                from_scene=None,
                to_scene=scene_id,
                timestamp=datetime.now(),
                reason="Initial activation",
            )
            self._scene_history.append(record)

            logger.info(f"[SceneAwareAgent] Activated scene: {scene_id}")

    async def _switch_scene(
        self, from_scene: Optional[str], to_scene: str, reason: str = ""
    ) -> None:
        """切换场景"""
        if not self._scene_manager:
            logger.warning("[SceneAwareAgent] Scene manager not initialized")
            return

        result = await self._scene_manager.switch_scene(
            from_scene=from_scene,
            to_scene=to_scene,
            session_id=self._session_id or self.info.name,
            agent=self,
            reason=reason,
        )

        if result.get("success"):
            self._current_scene_id = to_scene

            # 记录切换历史
            record = SceneSwitchRecord(
                from_scene=from_scene,
                to_scene=to_scene,
                timestamp=datetime.now(),
                reason=reason,
            )
            self._scene_history.append(record)

            logger.info(
                f"[SceneAwareAgent] Switched scene: {from_scene} -> {to_scene}, "
                f"reason={reason}"
            )

    def _get_last_switch_time(self) -> Optional[datetime]:
        """获取最后一次场景切换时间"""
        if self._scene_history:
            return self._scene_history[-1].timestamp
        return None

    def _build_system_prompt(self) -> str:
        """
        构建 System Prompt（场景化）

        整合基础角色设定和当前场景设定
        """
        if not self._scene_manager:
            return super()._build_system_prompt()

        # 构建场景化 System Prompt
        scene_prompt = self._scene_manager.build_system_prompt(self._current_scene_id)

        # 添加 ReAct 推理相关提示词
        react_prompt = super()._build_system_prompt()

        # 合并提示词
        if scene_prompt:
            return f"{scene_prompt}\n\n{react_prompt}"

        return react_prompt

    def get_current_scene(self) -> Optional[str]:
        """获取当前激活的场景 ID"""
        return self._current_scene_id

    def get_scene_history(self) -> List[SceneSwitchRecord]:
        """获取场景切换历史"""
        return self._scene_history.copy()

    def get_available_scenes(self) -> List[str]:
        """获取可用场景列表"""
        return list(self._scene_definitions.keys())

    def get_scene_info(
        self, scene_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取场景信息

        Args:
            scene_id: 场景 ID（默认当前场景）

        Returns:
            场景信息字典
        """
        target_scene = scene_id or self._current_scene_id
        if not target_scene:
            return None

        scene_def = self._scene_definitions.get(target_scene)
        if not scene_def:
            return None

        return {
            "scene_id": scene_def.scene_id,
            "scene_name": scene_def.scene_name,
            "description": scene_def.description,
            "trigger_keywords": scene_def.trigger_keywords,
            "workflow_phases": len(scene_def.workflow_phases),
            "tools_count": len(scene_def.scene_tools),
        }

    @classmethod
    def create_from_md(
        cls,
        agent_role_md: str,
        scene_md_dir: str,
        name: str = "scene-aware-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        max_steps: int = 30,
        enable_auto_scene_switch: bool = True,
        **kwargs,
    ) -> "SceneAwareAgent":
        """
        从 MD 文件创建场景感知 Agent

        Args:
            agent_role_md: Agent 角色 MD 文件路径
            scene_md_dir: 场景 MD 文件目录
            name: Agent 名称
            model: 模型名称
            api_key: API Key
            api_base: API Base URL
            max_steps: 最大步数
            enable_auto_scene_switch: 是否启用自动场景切换
            **kwargs: 其他参数

        Returns:
            SceneAwareAgent 实例
        """
        from .llm_adapter import LLMConfig, LLMFactory

        info = AgentInfo(name=name, max_steps=max_steps, **kwargs)

        llm_config = LLMConfig(model=model, api_key=api_key, api_base=api_base)

        llm_adapter = LLMFactory.create(llm_config)

        return cls(
            info=info,
            llm_adapter=llm_adapter,
            agent_role_md=agent_role_md,
            scene_md_dir=scene_md_dir,
            enable_auto_scene_switch=enable_auto_scene_switch,
            **kwargs,
        )


# ==================== 导出 ====================

__all__ = [
    "SceneAwareAgent",
]
