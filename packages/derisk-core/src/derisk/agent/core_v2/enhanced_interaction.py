"""
Enhanced Interaction Manager for Core V2

增强现有 InteractionManager 的交互能力
支持 WebSocket 实时通信、中断恢复、Todo 管理
"""

from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
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
)
from ..interaction.interaction_gateway import (
    InteractionGateway,
    get_interaction_gateway,
)
from ..interaction.recovery_coordinator import (
    RecoveryCoordinator,
    get_recovery_coordinator,
)

logger = logging.getLogger(__name__)


class AuthorizationCache:
    """授权缓存"""
    
    def __init__(self, scope: str = "session", duration: int = 3600):
        self.scope = scope
        self.duration = duration
        self.created_at = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
    
    def is_valid(self) -> bool:
        if self.scope == "once":
            return False
        if self.scope == "always":
            return True
        current_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else self.created_at
        return (current_time - self.created_at) < self.duration


class EnhancedInteractionManager:
    """
    增强的交互管理器
    
    新增功能：
    1. WebSocket 实时通信
    2. 断线重连与恢复
    3. 离线请求缓存
    4. 授权缓存管理
    5. Todo 管理
    """
    
    def __init__(
        self,
        session_id: str,
        agent_name: str = "agent",
        gateway: Optional[InteractionGateway] = None,
        recovery_coordinator: Optional[RecoveryCoordinator] = None,
        default_timeout: int = 300,
    ):
        self.session_id = session_id
        self.agent_name = agent_name
        self.gateway = gateway or get_interaction_gateway()
        self.recovery = recovery_coordinator or get_recovery_coordinator()
        self.default_timeout = default_timeout
        
        self._authorization_cache: Dict[str, AuthorizationCache] = {}
        self._step_index = 0
        self._execution_id = f"exec_{session_id}"
    
    def set_step(self, step: int):
        """设置当前步骤"""
        self._step_index = step
    
    def set_execution_id(self, execution_id: str):
        """设置执行ID"""
        self._execution_id = execution_id
    
    async def ask(
        self,
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        options: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        context: Optional[Dict] = None,
    ) -> str:
        """询问用户"""
        snapshot = await self._create_snapshot()
        
        interaction_type = InteractionType.SELECT if options else InteractionType.ASK
        
        formatted_options = []
        if options:
            for opt in options:
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
            execution_id=self._execution_id,
            step_index=self._step_index,
            agent_name=self.agent_name,
            timeout=timeout or self.default_timeout,
            default_choice=default,
            state_snapshot=snapshot,
            context=context or {},
        )
        
        response = await self._execute_with_retry(request)
        
        if response.status == InteractionStatus.TIMEOUT:
            if default:
                return default
            raise InteractionTimeoutError(f"等待用户响应超时")
        
        return response.input_value or response.choice or ""
    
    async def confirm(
        self,
        message: str,
        title: str = "确认",
        default: bool = False,
        timeout: Optional[int] = None,
    ) -> bool:
        """确认操作"""
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
            execution_id=self._execution_id,
            step_index=self._step_index,
            agent_name=self.agent_name,
            timeout=timeout or 60,
            default_choice="yes" if default else "no",
            state_snapshot=snapshot,
        )
        
        response = await self._execute_with_retry(request)
        return response.choice == "yes"
    
    async def select(
        self,
        message: str,
        options: List[Union[str, Dict[str, Any]]],
        title: str = "请选择",
        default: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """选择操作"""
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
            execution_id=self._execution_id,
            step_index=self._step_index,
            agent_name=self.agent_name,
            timeout=timeout or 120,
            default_choice=default,
            state_snapshot=snapshot,
        )
        
        response = await self._execute_with_retry(request)
        return response.choice or default or ""
    
    async def request_authorization(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict] = None,
        reason: Optional[str] = None,
        timeout: Optional[int] = None,
        snapshot: Optional[Dict] = None,
    ) -> bool:
        """请求授权（兼容现有接口）"""
        return await self.request_authorization_smart(
            tool_name=tool_name,
            tool_args=tool_args,
            context=context,
            reason=reason,
            timeout=timeout,
            snapshot=snapshot,
        )
    
    async def request_authorization_smart(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict] = None,
        reason: Optional[str] = None,
        timeout: Optional[int] = None,
        snapshot: Optional[Dict] = None,
    ) -> bool:
        """
        智能授权请求
        
        根据规则和缓存决定是否需要用户确认
        """
        cache_key = self._get_auth_cache_key(tool_name, tool_args)
        if cache_key in self._authorization_cache:
            cache = self._authorization_cache[cache_key]
            if cache.is_valid():
                return True
        
        risk_level = self._assess_risk_level(tool_name, tool_args)
        
        request = InteractionRequest(
            interaction_type=InteractionType.AUTHORIZE,
            priority=InteractionPriority.CRITICAL if risk_level == "high" else InteractionPriority.HIGH,
            title=f"需要授权: {tool_name}",
            message=self._format_auth_request_message(tool_name, tool_args, risk_level, reason),
            options=[
                InteractionOption(label="允许本次", value="allow_once", default=True),
                InteractionOption(label="允许本次会话所有同类操作", value="allow_session"),
                InteractionOption(label="总是允许", value="allow_always"),
                InteractionOption(label="拒绝", value="deny"),
            ],
            session_id=self.session_id,
            execution_id=self._execution_id,
            step_index=self._step_index,
            agent_name=self.agent_name,
            tool_name=tool_name,
            timeout=timeout or 120,
            state_snapshot=snapshot or await self._create_snapshot(),
            context=context or {},
            metadata={"risk_level": risk_level, "tool_args": tool_args},
        )
        
        response = await self._execute_with_retry(request)
        
        granted = response.choice in ["allow_once", "allow_session", "allow_always"]
        
        if response.choice == "allow_session":
            self._cache_session_authorization(tool_name, tool_args)
        elif response.choice == "allow_always":
            self._cache_permanent_authorization(tool_name, tool_args)
        
        return granted
    
    async def choose_plan(
        self,
        plans: List[Dict[str, Any]],
        title: str = "请选择方案",
        analysis: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """方案选择"""
        snapshot = await self._create_snapshot()
        
        options = []
        for plan in plans:
            pros = plan.get("pros", [])
            cons = plan.get("cons", [])
            estimated_time = plan.get("estimated_time", "未知")
            risk = plan.get("risk_level", "中")
            
            description = f"预计耗时: {estimated_time}\n风险级别: {risk}\n"
            if pros:
                description += f"优点: {', '.join(pros)}\n"
            if cons:
                description += f"缺点: {', '.join(cons)}"
            
            options.append(InteractionOption(
                label=plan.get("name", plan.get("id", "")),
                value=plan.get("id", ""),
                description=description,
            ))
        
        message = "我分析了多种可行方案：\n\n"
        if analysis:
            message += f"{analysis}\n\n"
        message += "请选择您偏好的执行方案："
        
        request = InteractionRequest(
            interaction_type=InteractionType.CHOOSE_PLAN,
            priority=InteractionPriority.HIGH,
            title=title,
            message=message,
            options=options,
            session_id=self.session_id,
            execution_id=self._execution_id,
            step_index=self._step_index,
            agent_name=self.agent_name,
            timeout=timeout or 300,
            state_snapshot=snapshot,
            context={"plans": plans, "analysis": analysis},
        )
        
        response = await self._execute_with_retry(request)
        return response.choice
    
    async def notify(
        self,
        message: str,
        level: NotifyLevel = NotifyLevel.INFO,
        title: Optional[str] = None,
        progress: Optional[float] = None,
    ):
        """发送通知"""
        interaction_type = InteractionType.NOTIFY_PROGRESS if progress is not None else InteractionType.NOTIFY
        
        request = InteractionRequest(
            interaction_type=interaction_type,
            priority=InteractionPriority.NORMAL,
            title=title or "通知",
            message=message,
            session_id=self.session_id,
            execution_id=self._execution_id,
            step_index=self._step_index,
            agent_name=self.agent_name,
            metadata={"level": level.value, "progress": progress},
        )
        
        await self.gateway.send(request)
    
    async def notify_success(self, message: str, title: str = "成功"):
        await self.notify(message, NotifyLevel.SUCCESS, title)
    
    async def notify_warning(self, message: str, title: str = "警告"):
        await self.notify(message, NotifyLevel.WARNING, title)
    
    async def notify_error(self, message: str, title: str = "错误"):
        await self.notify(message, NotifyLevel.ERROR, title)
    
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
    
    async def start_todo(self, todo_id: str):
        """开始执行 Todo"""
        await self.recovery.update_todo(
            session_id=self.session_id,
            todo_id=todo_id,
            status="in_progress",
        )
    
    async def complete_todo(self, todo_id: str, result: Optional[str] = None):
        """完成 Todo"""
        await self.recovery.update_todo(
            session_id=self.session_id,
            todo_id=todo_id,
            status="completed",
            result=result,
        )
    
    async def fail_todo(self, todo_id: str, error: str):
        """Todo 失败"""
        await self.recovery.update_todo(
            session_id=self.session_id,
            todo_id=todo_id,
            status="failed",
            error=error,
        )
    
    def get_todos(self) -> List:
        """获取 Todo 列表"""
        return self.recovery.get_todos(self.session_id)
    
    def get_next_todo(self):
        """获取下一个可执行的 Todo"""
        return self.recovery.get_next_todo(self.session_id)
    
    def get_progress(self) -> tuple:
        """获取进度"""
        return self.recovery.get_progress(self.session_id)
    
    async def _execute_with_retry(self, request: InteractionRequest) -> InteractionResponse:
        """执行请求"""
        return await self.gateway.send_and_wait(request)
    
    async def _create_snapshot(self) -> Dict[str, Any]:
        """创建快照"""
        return {
            "session_id": self.session_id,
            "execution_id": self._execution_id,
            "step_index": self._step_index,
            "agent_name": self.agent_name,
        }
    
    def _get_auth_cache_key(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """获取授权缓存键"""
        return f"{tool_name}:{hash(frozenset(tool_args.items()))}"
    
    def _cache_session_authorization(self, tool_name: str, tool_args: Dict[str, Any]):
        """缓存会话级授权"""
        cache_key = self._get_auth_cache_key(tool_name, tool_args)
        self._authorization_cache[cache_key] = AuthorizationCache(scope="session")
    
    def _cache_permanent_authorization(self, tool_name: str, tool_args: Dict[str, Any]):
        """缓存永久授权"""
        cache_key = self._get_auth_cache_key(tool_name, tool_args)
        self._authorization_cache[cache_key] = AuthorizationCache(scope="always")
    
    def _assess_risk_level(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """评估风险级别"""
        high_risk_tools = ["bash", "shell", "execute", "delete"]
        high_risk_patterns = ["rm -rf", "DROP", "DELETE", "truncate"]
        
        if tool_name.lower() in high_risk_tools:
            args_str = str(tool_args).lower()
            for pattern in high_risk_patterns:
                if pattern.lower() in args_str:
                    return "high"
            return "medium"
        
        return "low"
    
    def _format_auth_request_message(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        risk_level: str,
        reason: Optional[str],
    ) -> str:
        """格式化授权请求消息"""
        lines = [f"**工具**: {tool_name}"]
        
        if tool_args:
            lines.append("\n**参数**:")
            for k, v in tool_args.items():
                lines.append(f"  - {k}: {v}")
        
        if reason:
            lines.append(f"\n**原因**: {reason}")
        
        lines.append(f"\n**风险级别**: {risk_level.upper()}")
        
        return "\n".join(lines)


def create_enhanced_interaction_manager(
    session_id: str,
    agent_name: str = "agent",
) -> EnhancedInteractionManager:
    """创建增强交互管理器"""
    return EnhancedInteractionManager(
        session_id=session_id,
        agent_name=agent_name,
    )


__all__ = [
    "EnhancedInteractionManager",
    "AuthorizationCache",
    "create_enhanced_interaction_manager",
]