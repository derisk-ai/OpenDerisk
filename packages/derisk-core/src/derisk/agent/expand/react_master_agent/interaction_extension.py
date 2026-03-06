"""
ReActMaster Agent 交互集成

为 ReActMasterAgent 添加完整的用户交互能力：
- Agent 主动提问
- 工具授权审批
- 方案选择
- 随处中断/随时恢复
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
import asyncio
import logging

from ...interaction.interaction_protocol import (
    InteractionType,
    InteractionPriority,
    InteractionRequest,
    InteractionResponse,
    InteractionOption,
    NotifyLevel,
    InteractionStatus,
    TodoItem,
)
from ...interaction.interaction_gateway import (
    InteractionGateway,
    get_interaction_gateway,
)
from ...interaction.recovery_coordinator import (
    RecoveryCoordinator,
    get_recovery_coordinator,
)
from ...core.interaction_adapter import InteractionAdapter

if TYPE_CHECKING:
    from .react_master_agent import ReActMasterAgent

logger = logging.getLogger(__name__)


class ReActMasterInteractionExtension:
    """
    ReActMaster Agent 交互扩展
    
    为现有的 ReActMasterAgent 添加完整的交互能力
    """
    
    def __init__(
        self,
        agent: "ReActMasterAgent",
        gateway: Optional[InteractionGateway] = None,
        recovery: Optional[RecoveryCoordinator] = None,
    ):
        self.agent = agent
        self.gateway = gateway or get_interaction_gateway()
        self.recovery = recovery or get_recovery_coordinator()
        
        self._interaction_adapter: Optional[InteractionAdapter] = None
        self._current_step = 0
        self._session_auth_cache: Dict[str, bool] = {}
    
    @property
    def adapter(self) -> InteractionAdapter:
        """获取交互适配器"""
        if self._interaction_adapter is None:
            self._interaction_adapter = InteractionAdapter(
                agent=self.agent,
                gateway=self.gateway,
                recovery_coordinator=self.recovery,
            )
        return self._interaction_adapter
    
    @property
    def session_id(self) -> str:
        """获取会话ID"""
        if hasattr(self.agent, "agent_context") and self.agent.agent_context:
            return self.agent.agent_context.conv_session_id
        return "default_session"
    
    async def ask_user(
        self,
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        options: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> str:
        """
        主动向用户提问
        
        使用场景：
        - 缺少必要信息
        - 需要澄清模糊指令
        - 需要用户指定参数
        """
        await self._create_checkpoint_if_needed()
        
        return await self.adapter.ask(
            question=question,
            title=title,
            default=default,
            options=options,
            timeout=timeout,
        )
    
    async def request_tool_authorization(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> bool:
        """
        请求工具执行授权
        
        使用场景：
        - 危险命令执行
        - 敏感数据访问
        - 外部网络请求
        """
        cache_key = f"{tool_name}:{hash(frozenset(str(v) for v in tool_args.values()))}"
        if cache_key in self._session_auth_cache:
            return self._session_auth_cache[cache_key]
        
        await self._create_checkpoint_if_needed()
        
        authorized = await self.adapter.request_tool_permission(
            tool_name=tool_name,
            tool_args=tool_args,
            reason=reason,
        )
        
        if authorized:
            self._session_auth_cache[cache_key] = True
        
        return authorized
    
    async def choose_plan(
        self,
        plans: List[Dict[str, Any]],
        title: str = "请选择执行方案",
    ) -> str:
        """
        让用户选择执行方案
        
        使用场景：
        - 多种技术路线可选
        - 成本/时间权衡
        - 风险级别选择
        """
        await self._create_checkpoint_if_needed()
        
        return await self.adapter.choose_plan(plans=plans, title=title)
    
    async def confirm_action(
        self,
        message: str,
        title: str = "确认操作",
        default: bool = False,
    ) -> bool:
        """确认操作"""
        return await self.adapter.confirm(message=message, title=title, default=default)
    
    async def notify_progress(
        self,
        message: str,
        progress: Optional[float] = None,
    ):
        """发送进度通知"""
        await self.adapter.notify(
            message=message,
            level=NotifyLevel.INFO,
            title="进度更新",
            progress=progress,
        )
    
    async def notify_success(self, message: str):
        """发送成功通知"""
        await self.adapter.notify_success(message)
    
    async def notify_warning(self, message: str):
        """发送警告通知"""
        await self.adapter.notify_warning(message)
    
    async def notify_error(self, message: str):
        """发送错误通知"""
        await self.adapter.notify_error(message)
    
    async def create_todo(
        self,
        content: str,
        priority: int = 0,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """创建 Todo"""
        return await self.adapter.create_todo(
            content=content,
            priority=priority,
            dependencies=dependencies,
        )
    
    async def update_todo(
        self,
        todo_id: str,
        status: Optional[str] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """更新 Todo 状态"""
        await self.adapter.update_todo(
            todo_id=todo_id,
            status=status,
            result=result,
            error=error,
        )
    
    def get_todos(self) -> List[TodoItem]:
        """获取 Todo 列表"""
        return self.adapter.get_todos()
    
    def get_progress(self) -> tuple:
        """获取进度"""
        return self.adapter.get_progress()
    
    async def create_checkpoint(self, phase: str = "executing"):
        """创建检查点"""
        await self.recovery.create_checkpoint(
            session_id=self.session_id,
            execution_id=getattr(self.agent, "_execution_id", f"exec_{self.session_id}"),
            step_index=self._current_step,
            phase=phase,
            context={},
            agent=self.agent,
        )
    
    async def recover(
        self,
        resume_mode: str = "continue",
    ) -> bool:
        """
        恢复执行
        
        Args:
            resume_mode: continue / skip / restart
        """
        result = await self.recovery.recover(
            session_id=self.session_id,
            resume_mode=resume_mode,
        )
        
        if result.success:
            logger.info(f"Recovery successful: {result.summary}")
            return True
        
        logger.warning(f"Recovery failed: {result.error}")
        return False
    
    def set_step(self, step: int):
        """设置当前步骤"""
        self._current_step = step
    
    async def _create_checkpoint_if_needed(self):
        """在需要时创建检查点"""
        pass
    
    def clear_session_cache(self):
        """清除会话缓存"""
        self._session_auth_cache.clear()


def create_interaction_extension(
    agent: "ReActMasterAgent",
    gateway: Optional[InteractionGateway] = None,
    recovery: Optional[RecoveryCoordinator] = None,
) -> ReActMasterInteractionExtension:
    """创建交互扩展"""
    return ReActMasterInteractionExtension(
        agent=agent,
        gateway=gateway,
        recovery=recovery,
    )


__all__ = [
    "ReActMasterInteractionExtension",
    "create_interaction_extension",
]