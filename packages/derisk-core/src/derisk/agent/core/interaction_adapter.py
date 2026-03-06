"""
Interaction Adapter for Core V1

为 Core V1 的 ConversableAgent 提供统一的交互能力
支持主动提问、工具授权、方案选择等功能
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
import asyncio
import logging

from ..interaction.interaction_protocol import (
    InteractionType,
    InteractionPriority,
    InteractionStatus,
    InteractionRequest,
    InteractionResponse,
    InteractionOption,
    NotifyLevel,
    InteractionTimeoutError,
    InteractionPendingError,
)
from ..interaction.interaction_gateway import (
    InteractionGateway,
    get_interaction_gateway,
)
from ..interaction.recovery_coordinator import (
    RecoveryCoordinator,
    get_recovery_coordinator,
)

if TYPE_CHECKING:
    from derisk.agent.core import ConversableAgent

logger = logging.getLogger(__name__)


class InteractionAdapter:
    """
    交互适配器 - 将用户交互集成到 Core V1 Agent
    
    使用方式：
    ```python
    agent = ConversableAgent(...)
    adapter = InteractionAdapter(agent)
    
    # 主动提问
    answer = await adapter.ask("请提供数据库连接信息")
    
    # 工具授权
    authorized = await adapter.request_tool_permission("bash", {"command": "rm -rf"})
    
    # 方案选择
    plan = await adapter.choose_plan([
        {"id": "plan_a", "name": "方案A：快速实现"},
        {"id": "plan_b", "name": "方案B：完整实现"},
    ])
    ```
    """
    
    def __init__(
        self,
        agent: "ConversableAgent",
        gateway: Optional[InteractionGateway] = None,
        recovery_coordinator: Optional[RecoveryCoordinator] = None,
    ):
        self.agent = agent
        self.gateway = gateway or get_interaction_gateway()
        self.recovery = recovery_coordinator or get_recovery_coordinator()
        
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._session_auth_cache: Dict[str, bool] = {}
    
    @property
    def session_id(self) -> str:
        """获取会话ID"""
        if hasattr(self.agent, "agent_context") and self.agent.agent_context:
            return self.agent.agent_context.conv_session_id
        return "default_session"
    
    @property
    def agent_name(self) -> str:
        """获取 Agent 名称"""
        return getattr(self.agent, "name", "agent")
    
    async def ask(
        self,
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        options: Optional[List[str]] = None,
        timeout: int = 300,
        context: Optional[Dict] = None,
    ) -> str:
        """
        主动向用户提问
        
        适用场景：
        - 缺少必要信息时请求用户提供
        - 需要澄清模糊指令
        - 需要用户指定参数
        """
        snapshot = await self._create_snapshot()
        
        interaction_type = InteractionType.SELECT if options else InteractionType.ASK
        
        formatted_options = []
        if options:
            for opt in options:
                if isinstance(opt, str):
                    formatted_options.append(InteractionOption(
                        label=opt,
                        value=opt,
                        default=(opt == default)
                    ))
        
        request = InteractionRequest(
            interaction_type=interaction_type,
            priority=InteractionPriority.HIGH,
            title=title,
            message=question,
            options=formatted_options,
            session_id=self.session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent_name,
            timeout=timeout,
            default_choice=default,
            state_snapshot=snapshot,
            context=context or {},
        )
        
        response = await self.gateway.send_and_wait(request)
        
        if response.status == InteractionStatus.TIMEOUT:
            if default:
                return default
            raise InteractionTimeoutError(f"用户未在 {timeout} 秒内响应")
        
        if response.status == InteractionStatus.CANCELLED:
            return default or ""
        
        return response.input_value or response.choice or ""
    
    async def confirm(
        self,
        message: str,
        title: str = "确认",
        default: bool = False,
        timeout: int = 60,
    ) -> bool:
        """
        确认操作
        
        Args:
            message: 确认消息
            title: 标题
            default: 默认值
            timeout: 超时时间
            
        Returns:
            bool: 是否确认
        """
        snapshot = await self._create_snapshot()
        
        request = InteractionRequest(
            interaction_type=InteractionType.CONFIRM,
            priority=InteractionPriority.HIGH,
            title=title,
            message=message,
            options=[
                InteractionOption(label="是", value="yes", default=default),
                InteractionOption(label="否", value="no", default=not default),
            ],
            session_id=self.session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent_name,
            timeout=timeout,
            default_choice="yes" if default else "no",
            state_snapshot=snapshot,
        )
        
        response = await self.gateway.send_and_wait(request)
        return response.choice == "yes"
    
    async def select(
        self,
        message: str,
        options: List[Dict[str, Any]],
        title: str = "请选择",
        default: Optional[str] = None,
        timeout: int = 120,
    ) -> str:
        """
        让用户从选项中选择
        
        Args:
            message: 选择消息
            options: 选项列表
            title: 标题
            default: 默认选项值
            timeout: 超时时间
            
        Returns:
            str: 选择结果
        """
        snapshot = await self._create_snapshot()
        
        formatted_options = []
        for opt in options:
            if isinstance(opt, str):
                formatted_options.append(InteractionOption(
                    label=opt,
                    value=opt,
                    default=(opt == default)
                ))
            elif isinstance(opt, dict):
                formatted_options.append(InteractionOption(
                    label=opt.get("label", opt.get("value", "")),
                    value=opt.get("value", ""),
                    description=opt.get("description"),
                    default=(opt.get("value") == default),
                ))
        
        request = InteractionRequest(
            interaction_type=InteractionType.SELECT,
            priority=InteractionPriority.HIGH,
            title=title,
            message=message,
            options=formatted_options,
            session_id=self.session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent_name,
            timeout=timeout,
            default_choice=default,
            state_snapshot=snapshot,
        )
        
        response = await self.gateway.send_and_wait(request)
        return response.choice or default or ""
    
    async def request_tool_permission(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        reason: Optional[str] = None,
        timeout: int = 120,
    ) -> bool:
        """
        请求工具执行授权
        
        适用场景：
        - 危险命令执行（rm -rf, drop table 等）
        - 敏感数据访问
        - 外部网络请求
        """
        cache_key = f"{tool_name}:{hash(frozenset(tool_args.items()))}"
        if cache_key in self._session_auth_cache:
            return self._session_auth_cache[cache_key]
        
        if hasattr(self.agent, "permission_ruleset") and self.agent.permission_ruleset:
            from derisk.agent.core.agent_info import PermissionAction
            action = self.agent.permission_ruleset.check(tool_name)
            if action == PermissionAction.ALLOW:
                return True
            if action == PermissionAction.DENY:
                return False
        
        snapshot = await self._create_snapshot()
        
        risk_level = self._assess_risk_level(tool_name, tool_args)
        
        request = InteractionRequest(
            interaction_type=InteractionType.AUTHORIZE,
            priority=InteractionPriority.CRITICAL if risk_level == "high" else InteractionPriority.HIGH,
            title=f"需要授权: {tool_name}",
            message=self._format_auth_message(tool_name, tool_args, reason, risk_level),
            options=[
                InteractionOption(label="允许（本次）", value="allow_once", default=True),
                InteractionOption(label="允许（本次会话）", value="allow_session"),
                InteractionOption(label="拒绝", value="deny"),
            ],
            session_id=self.session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent_name,
            tool_name=tool_name,
            timeout=timeout,
            state_snapshot=snapshot,
            context={"tool_args": tool_args, "reason": reason, "risk_level": risk_level},
        )
        
        await self.recovery.create_interaction_checkpoint(
            session_id=self.session_id,
            execution_id=self._get_execution_id(),
            interaction_request=request,
            agent=self.agent,
        )
        
        response = await self.gateway.send_and_wait(request)
        
        granted = response.choice in ["allow_once", "allow_session"]
        
        if response.choice == "allow_session":
            self._session_auth_cache[cache_key] = True
        
        return granted
    
    async def choose_plan(
        self,
        plans: List[Dict[str, Any]],
        title: str = "请选择执行方案",
        timeout: int = 300,
    ) -> str:
        """
        让用户选择执行方案
        
        适用场景：
        - 多种技术路线可选
        - 成本/时间权衡
        - 风险级别选择
        """
        snapshot = await self._create_snapshot()
        
        options = []
        for plan in plans:
            pros = plan.get("pros", [])
            cons = plan.get("cons", [])
            estimated_time = plan.get("estimated_time", "未知")
            
            description = f"预计耗时: {estimated_time}"
            if pros:
                description += f"\n优点: {', '.join(pros)}"
            if cons:
                description += f"\n缺点: {', '.join(cons)}"
            
            options.append(InteractionOption(
                label=plan.get("name", plan.get("id", "")),
                value=plan.get("id", ""),
                description=description,
            ))
        
        message = "我分析了多种可行方案，请选择您偏好的执行方案："
        
        request = InteractionRequest(
            interaction_type=InteractionType.CHOOSE_PLAN,
            priority=InteractionPriority.HIGH,
            title=title,
            message=message,
            options=options,
            session_id=self.session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent_name,
            timeout=timeout,
            state_snapshot=snapshot,
            context={"plans": plans},
        )
        
        response = await self.gateway.send_and_wait(request)
        return response.choice
    
    async def notify(
        self,
        message: str,
        level: NotifyLevel = NotifyLevel.INFO,
        title: Optional[str] = None,
        progress: Optional[float] = None,
    ):
        """发送通知（无需等待响应）"""
        interaction_type = InteractionType.NOTIFY_PROGRESS if progress else InteractionType.NOTIFY
        
        request = InteractionRequest(
            interaction_type=interaction_type,
            priority=InteractionPriority.NORMAL,
            title=title or "通知",
            message=message,
            session_id=self.session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent_name,
            metadata={"level": level.value, "progress": progress},
        )
        
        await self.gateway.send(request)
    
    async def notify_success(self, message: str, title: str = "成功"):
        """发送成功通知"""
        await self.notify(message, NotifyLevel.SUCCESS, title)
    
    async def notify_error(self, message: str, title: str = "错误"):
        """发送错误通知"""
        await self.notify(message, NotifyLevel.ERROR, title)
    
    async def notify_warning(self, message: str, title: str = "警告"):
        """发送警告通知"""
        await self.notify(message, NotifyLevel.WARNING, title)
    
    async def create_todo(
        self,
        content: str,
        priority: int = 0,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """创建 Todo"""
        return await self.recovery.create_todo(
            session_id=self.session_id,
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
        await self.recovery.update_todo(
            session_id=self.session_id,
            todo_id=todo_id,
            status=status,
            result=result,
            error=error,
        )
    
    def get_todos(self) -> List:
        """获取 Todo 列表"""
        return self.recovery.get_todos(self.session_id)
    
    def get_progress(self) -> tuple:
        """获取进度"""
        return self.recovery.get_progress(self.session_id)
    
    async def _create_snapshot(self) -> Dict[str, Any]:
        """创建当前状态快照"""
        return {
            "timestamp": datetime.now().isoformat() if hasattr(datetime, 'now') else "",
            "agent_name": self.agent_name,
            "step_index": self._get_current_step(),
            "session_id": self.session_id,
        }
    
    def _get_execution_id(self) -> str:
        """获取执行ID"""
        return getattr(self.agent, "_execution_id", f"exec_{self.session_id}")
    
    def _get_current_step(self) -> int:
        """获取当前步骤"""
        return getattr(self.agent, "_current_step", 0)
    
    def _format_auth_message(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        reason: Optional[str],
        risk_level: str,
    ) -> str:
        """格式化授权消息"""
        lines = [f"**工具**: {tool_name}"]
        
        if tool_args:
            lines.append("\n**参数**:")
            for k, v in tool_args.items():
                lines.append(f"  - {k}: {v}")
        
        if reason:
            lines.append(f"\n**原因**: {reason}")
        
        lines.append(f"\n**风险级别**: {risk_level.upper()}")
        
        return "\n".join(lines)
    
    def _assess_risk_level(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """评估风险级别"""
        high_risk_tools = ["bash", "shell", "execute", "delete", "drop"]
        high_risk_patterns = ["rm -rf", "DROP", "DELETE", "truncate", "format"]
        
        if tool_name.lower() in high_risk_tools:
            args_str = str(tool_args).lower()
            for pattern in high_risk_patterns:
                if pattern.lower() in args_str:
                    return "high"
            return "medium"
        
        return "low"


def create_interaction_adapter(agent: "ConversableAgent") -> InteractionAdapter:
    """创建交互适配器"""
    return InteractionAdapter(agent)


__all__ = [
    "InteractionAdapter",
    "create_interaction_adapter",
]