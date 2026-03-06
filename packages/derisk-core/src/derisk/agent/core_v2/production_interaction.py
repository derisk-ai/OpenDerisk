"""
Production Agent 交互集成

为 ProductionAgent 添加完整的用户交互能力：
- Agent 主动提问
- 工具授权审批  
- 方案选择
- 随处中断/随时恢复
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
import asyncio
import logging

from ..interaction.interaction_protocol import (
    InteractionType,
    InteractionPriority,
    InteractionRequest,
    InteractionResponse,
    InteractionOption,
    NotifyLevel,
    InteractionStatus,
    TodoItem,
)
from ..interaction.interaction_gateway import (
    InteractionGateway,
    get_interaction_gateway,
)
from ..interaction.recovery_coordinator import (
    RecoveryCoordinator,
    get_recovery_coordinator,
)
from .enhanced_interaction import EnhancedInteractionManager

if TYPE_CHECKING:
    from .production_agent import ProductionAgent

logger = logging.getLogger(__name__)


class ProductionAgentInteractionMixin:
    """
    ProductionAgent 交互能力混入类
    
    提供完整的交互能力，可直接混入到 ProductionAgent
    """
    
    _interaction_manager: Optional[EnhancedInteractionManager] = None
    _recovery_coordinator: Optional[RecoveryCoordinator] = None
    _interaction_gateway: Optional[InteractionGateway] = None
    _current_step: int = 0
    
    def init_interaction(
        self: "ProductionAgent",
        gateway: Optional[InteractionGateway] = None,
        recovery: Optional[RecoveryCoordinator] = None,
    ):
        """
        初始化交互能力
        
        Args:
            gateway: 交互网关
            recovery: 恢复协调器
        """
        self._interaction_gateway = gateway or get_interaction_gateway()
        self._recovery_coordinator = recovery or get_recovery_coordinator()
        
        session_id = self._get_session_id()
        
        self._interaction_manager = EnhancedInteractionManager(
            session_id=session_id,
            agent_name=getattr(self, "_info", None) and getattr(self._info, "name", "agent") or "agent",
            gateway=self._interaction_gateway,
            recovery_coordinator=self._recovery_coordinator,
        )
        
        logger.info(f"[ProductionAgent] Interaction initialized for session: {session_id}")
    
    def _get_session_id(self: "ProductionAgent") -> str:
        """获取会话ID"""
        if hasattr(self, "_context") and self._context:
            return getattr(self._context, "session_id", "default_session")
        return "default_session"
    
    @property
    def interaction(self: "ProductionAgent") -> EnhancedInteractionManager:
        """获取交互管理器"""
        if self._interaction_manager is None:
            self.init_interaction()
        return self._interaction_manager
    
    @property
    def recovery(self: "ProductionAgent") -> RecoveryCoordinator:
        """获取恢复协调器"""
        if self._recovery_coordinator is None:
            self._recovery_coordinator = get_recovery_coordinator()
        return self._recovery_coordinator
    
    async def ask_user(
        self: "ProductionAgent",
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        options: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> str:
        """主动向用户提问"""
        await self._create_checkpoint_if_needed()
        return await self.interaction.ask(
            question=question,
            title=title,
            default=default,
            options=options,
            timeout=timeout,
        )
    
    async def request_authorization(
        self: "ProductionAgent",
        tool_name: str,
        tool_args: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> bool:
        """请求工具授权"""
        await self._create_checkpoint_if_needed()
        return await self.interaction.request_authorization_smart(
            tool_name=tool_name,
            tool_args=tool_args,
            reason=reason,
        )
    
    async def choose_plan(
        self: "ProductionAgent",
        plans: List[Dict[str, Any]],
        title: str = "请选择方案",
    ) -> str:
        """让用户选择方案"""
        await self._create_checkpoint_if_needed()
        return await self.interaction.choose_plan(plans=plans, title=title)
    
    async def confirm(
        self: "ProductionAgent",
        message: str,
        title: str = "确认",
        default: bool = False,
    ) -> bool:
        """确认操作"""
        return await self.interaction.confirm(message=message, title=title, default=default)
    
    async def select(
        self: "ProductionAgent",
        message: str,
        options: List[Dict[str, Any]],
        title: str = "请选择",
        default: Optional[str] = None,
    ) -> str:
        """让用户选择"""
        return await self.interaction.select(
            message=message,
            options=options,
            title=title,
            default=default,
        )
    
    async def notify(
        self: "ProductionAgent",
        message: str,
        level: NotifyLevel = NotifyLevel.INFO,
        title: Optional[str] = None,
        progress: Optional[float] = None,
    ):
        """发送通知"""
        await self.interaction.notify(
            message=message,
            level=level,
            title=title,
            progress=progress,
        )
    
    async def notify_progress(self: "ProductionAgent", message: str, progress: float):
        """发送进度通知"""
        await self.interaction.notify(message=message, level=NotifyLevel.INFO, progress=progress)
    
    async def notify_success(self: "ProductionAgent", message: str):
        """发送成功通知"""
        await self.interaction.notify_success(message)
    
    async def notify_error(self: "ProductionAgent", message: str):
        """发送错误通知"""
        await self.interaction.notify_error(message)
    
    async def create_todo(
        self: "ProductionAgent",
        content: str,
        priority: int = 0,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """创建 Todo"""
        return await self.interaction.create_todo(
            content=content,
            priority=priority,
            dependencies=dependencies,
        )
    
    async def start_todo(self: "ProductionAgent", todo_id: str):
        """开始执行 Todo"""
        await self.interaction.start_todo(todo_id)
    
    async def complete_todo(self: "ProductionAgent", todo_id: str, result: Optional[str] = None):
        """完成 Todo"""
        await self.interaction.complete_todo(todo_id, result)
    
    async def fail_todo(self: "ProductionAgent", todo_id: str, error: str):
        """Todo 失败"""
        await self.interaction.fail_todo(todo_id, error)
    
    def get_todos(self: "ProductionAgent") -> List[TodoItem]:
        """获取 Todo 列表"""
        return self.interaction.get_todos()
    
    def get_next_todo(self: "ProductionAgent") -> Optional[TodoItem]:
        """获取下一个 Todo"""
        return self.interaction.get_next_todo()
    
    def get_progress(self: "ProductionAgent") -> tuple:
        """获取进度"""
        return self.interaction.get_progress()
    
    async def create_checkpoint(self: "ProductionAgent", phase: str = "executing"):
        """创建检查点"""
        await self.recovery.create_checkpoint(
            session_id=self._get_session_id(),
            execution_id=getattr(self, "_execution_id", f"exec_{self._get_session_id()}"),
            step_index=self._current_step,
            phase=phase,
            context={},
            agent=self,
        )
        logger.info(f"[ProductionAgent] Checkpoint created at step {self._current_step}")
    
    async def has_recovery_state(self: "ProductionAgent") -> bool:
        """检查是否有恢复状态"""
        return await self.recovery.has_recovery_state(self._get_session_id())
    
    async def recover(
        self: "ProductionAgent",
        resume_mode: str = "continue",
    ):
        """
        恢复执行
        
        Args:
            resume_mode: continue / skip / restart
        """
        result = await self.recovery.recover(
            session_id=self._get_session_id(),
            resume_mode=resume_mode,
        )
        
        if result.success:
            logger.info(f"[ProductionAgent] Recovery successful: {result.summary}")
            return result
        
        logger.warning(f"[ProductionAgent] Recovery failed: {result.error}")
        return result
    
    def set_step(self: "ProductionAgent", step: int):
        """设置当前步骤"""
        self._current_step = step
        if self._interaction_manager:
            self._interaction_manager.set_step(step)
    
    async def _create_checkpoint_if_needed(self: "ProductionAgent"):
        """在需要时创建检查点"""
        if self._current_step % 5 == 0:
            await self.create_checkpoint()


class ProductionAgentWithInteraction(ProductionAgentInteractionMixin):
    """
    带完整交互能力的 ProductionAgent
    
    使用方式：
    ```python
    agent = ProductionAgentWithInteraction.create(
        name="my-agent",
        api_key="sk-xxx",
    )
    
    # 初始化交互
    agent.init_interaction()
    
    # 使用交互功能
    answer = await agent.ask_user("请提供数据库连接信息")
    authorized = await agent.request_authorization("bash", {"command": "rm -rf"})
    plan = await agent.choose_plan([...])
    
    # Todo 管理
    todo_id = await agent.create_todo("实现登录功能")
    await agent.start_todo(todo_id)
    await agent.complete_todo(todo_id)
    
    # 中断恢复
    if await agent.has_recovery_state():
        result = await agent.recover("continue")
    ```
    """
    pass


__all__ = [
    "ProductionAgentInteractionMixin",
    "ProductionAgentWithInteraction",
]