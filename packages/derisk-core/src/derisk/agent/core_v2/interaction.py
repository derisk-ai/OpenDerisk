"""
Interaction - 交互协议系统

实现Agent与用户之间的标准化交互
支持询问、通知、授权、确认、选择等多种交互类型
"""

from typing import List, Optional, Dict, Any, Callable, Awaitable, Literal, Union
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime
import uuid
import asyncio
import logging

logger = logging.getLogger(__name__)


class InteractionType(str, Enum):
    """交互类型"""
    ASK = "ask"  # 询问
    NOTIFY = "notify"  # 通知
    AUTHORIZE = "authorize"  # 授权
    CONFIRM = "confirm"  # 确认
    SELECT = "select"  # 选择
    INPUT = "input"  # 输入
    MULTIPLE_SELECT = "multiple_select"  # 多选
    FILE_UPLOAD = "file_upload"  # 文件上传


class InteractionPriority(str, Enum):
    """交互优先级"""
    CRITICAL = "critical"  # 关键 - 必须立即处理
    HIGH = "high"  # 高优先级
    NORMAL = "normal"  # 正常
    LOW = "low"  # 低优先级


class InteractionStatus(str, Enum):
    """交互状态"""
    PENDING = "pending"  # 等待处理
    RESPONSED = "responsed"  # 已响应
    TIMEOUT = "timeout"  # 超时
    CANCELLED = "cancelled"  # 已取消
    FAILED = "failed"  # 失败


class NotifyLevel(str, Enum):
    """通知级别"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


class InteractionOption(BaseModel):
    """交互选项"""
    label: str  # 显示文本
    value: str  # 选项值
    description: Optional[str] = None  # 选项描述
    icon: Optional[str] = None  # 图标
    disabled: bool = False  # 是否禁用
    default: bool = False  # 是否默认选中


class InteractionRequest(BaseModel):
    """交互请求"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    type: InteractionType
    title: str
    content: str
    options: List[InteractionOption] = Field(default_factory=list)
    priority: InteractionPriority = InteractionPriority.NORMAL
    
    timeout: Optional[int] = None  # 超时时间(秒)
    default_choice: Optional[str] = None  # 默认选择
    allow_cancel: bool = True  # 是否允许取消
    allow_skip: bool = False  # 是否允许跳过
    
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class InteractionResponse(BaseModel):
    """交互响应"""
    request_id: str
    choice: Optional[str] = None  # 用户选择
    choices: List[str] = Field(default_factory=list)  # 多选结果
    input_value: Optional[str] = None  # 输入值
    file_path: Optional[str] = None  # 文件路径
    
    status: InteractionStatus = InteractionStatus.RESPONSED
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    user_message: Optional[str] = None  # 用户的额外消息
    cancel_reason: Optional[str] = None  # 取消原因

    class Config:
        use_enum_values = True


class InteractionHandler(ABC):
    """交互处理器基类"""
    
    @abstractmethod
    async def handle(self, request: InteractionRequest) -> InteractionResponse:
        """处理交互请求"""
        pass
    
    @abstractmethod
    async def can_handle(self, request: InteractionRequest) -> bool:
        """是否可以处理该请求"""
        pass


class CLIInteractionHandler(InteractionHandler):
    """CLI交互处理器"""
    
    async def can_handle(self, request: InteractionRequest) -> bool:
        return True
    
    async def handle(self, request: InteractionRequest) -> InteractionResponse:
        """CLI方式处理交互"""
        print(f"\n{'='*60}")
        print(f"[{request.type.upper()}] {request.title}")
        print(f"{'='*60}")
        print(request.content)
        
        if request.options:
            print("\n选项:")
            for i, opt in enumerate(request.options, 1):
                default_mark = " (默认)" if opt.default else ""
                disabled_mark = " [禁用]" if opt.disabled else ""
                print(f"  {i}. {opt.label}{default_mark}{disabled_mark}")
                if opt.description:
                    print(f"     {opt.description}")
        
        print(f"{'='*60}")
        
        loop = asyncio.get_event_loop()
        
        if request.type == InteractionType.ASK:
            answer = await loop.run_in_executor(None, input, "请输入: ")
            return InteractionResponse(request_id=request.id, input_value=answer)
        
        elif request.type == InteractionType.CONFIRM:
            default = "Y" if any(o.default for o in request.options if o.value in ["yes", "y"]) else "N"
            answer = await loop.run_in_executor(None, input, f"确认? [Y/n] (默认: {default}): ")
            answer = answer.strip() or default
            return InteractionResponse(
                request_id=request.id,
                choice="yes" if answer.lower() in ["y", "yes", "是"] else "no"
            )
        
        elif request.type == InteractionType.SELECT:
            answer = await loop.run_in_executor(None, input, "请选择 (输入编号): ")
            try:
                idx = int(answer) - 1
                if 0 <= idx < len(request.options):
                    return InteractionResponse(
                        request_id=request.id,
                        choice=request.options[idx].value
                    )
            except ValueError:
                pass
            
            default_opt = next((o for o in request.options if o.default), None)
            if default_opt:
                return InteractionResponse(request_id=request.id, choice=default_opt.value)
            
            return InteractionResponse(
                request_id=request.id,
                status=InteractionStatus.FAILED,
                cancel_reason="无效选择"
            )
        
        elif request.type == InteractionType.AUTHORIZE:
            answer = await loop.run_in_executor(None, input, "授权? [y/N]: ")
            return InteractionResponse(
                request_id=request.id,
                choice="allow" if answer.lower() in ["y", "yes", "是"] else "deny"
            )
        
        elif request.type == InteractionType.NOTIFY:
            print("按回车继续...")
            await loop.run_in_executor(None, input)
            return InteractionResponse(request_id=request.id)
        
        else:
            return InteractionResponse(request_id=request.id, status=InteractionStatus.FAILED)


class InteractionManager:
    """
    交互管理器
    
    职责:
    1. 管理交互请求和响应
    2. 路由到合适的处理器
    3. 超时处理
    4. 响应缓存
    
    示例:
        manager = InteractionManager()
        manager.register_handler("cli", CLIInteractionHandler())
        
        choice = await manager.ask_user("请选择功能", ["查询", "编辑", "删除"])
        confirmed = await manager.confirm("确定要删除吗?")
        authorized = await manager.request_authorization("执行shell命令", {"command": "rm -rf"})
    """
    
    def __init__(self, default_handler: Optional[InteractionHandler] = None):
        self._handlers: Dict[str, InteractionHandler] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._response_cache: Dict[str, InteractionResponse] = {}
        self._default_handler = default_handler or CLIInteractionHandler()
        
        self._request_count = 0
        self._timeout_count = 0
        self._cancelled_count = 0

    def register_handler(self, name: str, handler: InteractionHandler):
        """注册处理器"""
        self._handlers[name] = handler
        logger.info(f"[InteractionManager] 注册处理器: {name}")

    def unregister_handler(self, name: str):
        """注销处理器"""
        self._handlers.pop(name, None)

    async def _dispatch(self, request: InteractionRequest) -> InteractionResponse:
        """分发请求到处理器"""
        handler = None
        
        for name, h in self._handlers.items():
            if await h.can_handle(request):
                handler = h
                break
        
        if not handler:
            handler = self._default_handler
        
        return await handler.handle(request)

    async def ask_user(
        self,
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        timeout: int = 60,
        allow_skip: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        询问用户
        
        Args:
            question: 问题内容
            title: 标题
            default: 默认值
            timeout: 超时时间
            allow_skip: 是否允许跳过
            context: 上下文
            
        Returns:
            str: 用户输入
        """
        request = InteractionRequest(
            type=InteractionType.ASK,
            title=title,
            content=question,
            default_choice=default,
            timeout=timeout,
            allow_skip=allow_skip,
            context=context or {}
        )
        
        return await self._execute_with_timeout(request)

    async def confirm(
        self,
        message: str,
        title: str = "确认",
        default: bool = False,
        timeout: int = 30
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
        request = InteractionRequest(
            type=InteractionType.CONFIRM,
            title=title,
            content=message,
            options=[
                InteractionOption(label="是", value="yes", default=default),
                InteractionOption(label="否", value="no", default=not default)
            ],
            timeout=timeout
        )
        
        response = await self._execute_with_timeout_response(request)
        return response.choice == "yes"

    async def select(
        self,
        message: str,
        options: List[Union[str, Dict[str, Any]]],
        title: str = "请选择",
        default: Optional[str] = None,
        timeout: int = 60,
        allow_cancel: bool = True
    ) -> str:
        """
        选择操作
        
        Args:
            message: 选择消息
            options: 选项列表 (字符串或字典)
            title: 标题
            default: 默认选项值
            timeout: 超时时间
            allow_cancel: 是否允许取消
            
        Returns:
            str: 选择结果
        """
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
                    default=(opt.get("value") == default)
                ))
        
        request = InteractionRequest(
            type=InteractionType.SELECT,
            title=title,
            content=message,
            options=formatted_options,
            default_choice=default,
            timeout=timeout,
            allow_cancel=allow_cancel
        )
        
        return await self._execute_with_timeout(request)

    async def multiple_select(
        self,
        message: str,
        options: List[Union[str, Dict[str, Any]]],
        title: str = "多选",
        defaults: Optional[List[str]] = None,
        timeout: int = 90
    ) -> List[str]:
        """
        多选操作
        
        Args:
            message: 选择消息
            options: 选项列表
            title: 标题
            defaults: 默认选项值列表
            timeout: 超时时间
            
        Returns:
            List[str]: 选择结果列表
        """
        defaults = defaults or []
        formatted_options = []
        
        for opt in options:
            if isinstance(opt, str):
                formatted_options.append(InteractionOption(
                    label=opt,
                    value=opt,
                    default=(opt in defaults)
                ))
            elif isinstance(opt, dict):
                value = opt.get("value", "")
                formatted_options.append(InteractionOption(
                    label=opt.get("label", value),
                    value=value,
                    description=opt.get("description"),
                    default=(value in defaults)
                ))
        
        request = InteractionRequest(
            type=InteractionType.MULTIPLE_SELECT,
            title=title,
            content=message,
            options=formatted_options,
            timeout=timeout
        )
        
        response = await self._execute_with_timeout_response(request)
        return response.choices

    async def request_authorization(
        self,
        action: str,
        context: Optional[Dict[str, Any]] = None,
        title: str = "需要授权",
        timeout: int = 60
    ) -> bool:
        """
        请求授权
        
        Args:
            action: 要执行的动作
            context: 上下文信息
            title: 标题
            timeout: 超时时间
            
        Returns:
            bool: 是否授权
        """
        context_str = ""
        if context:
            context_str = "\n\n相关信息:\n"
            for k, v in context.items():
                context_str += f"  - {k}: {v}\n"
        
        request = InteractionRequest(
            type=InteractionType.AUTHORIZE,
            title=title,
            content=f"请求执行: {action}{context_str}",
            options=[
                InteractionOption(label="允许", value="allow"),
                InteractionOption(label="拒绝", value="deny", default=True)
            ],
            timeout=timeout,
            context=context or {}
        )
        
        response = await self._execute_with_timeout_response(request)
        return response.choice == "allow"

    async def notify(
        self,
        message: str,
        level: NotifyLevel = NotifyLevel.INFO,
        title: str = "通知",
        timeout: Optional[int] = None
    ):
        """
        发送通知
        
        Args:
            message: 通知内容
            level: 通知级别
            title: 标题
            timeout: 超时时间
        """
        request = InteractionRequest(
            type=InteractionType.NOTIFY,
            title=title,
            content=message,
            priority=InteractionPriority.NORMAL if level == NotifyLevel.INFO else InteractionPriority.HIGH,
            metadata={"level": level.value},
            timeout=timeout
        )
        
        await self._dispatch(request)

    async def notify_success(self, message: str, title: str = "成功"):
        """成功通知"""
        await self.notify(message, NotifyLevel.SUCCESS, title)

    async def notify_warning(self, message: str, title: str = "警告"):
        """警告通知"""
        await self.notify(message, NotifyLevel.WARNING, title)

    async def notify_error(self, message: str, title: str = "错误"):
        """错误通知"""
        await self.notify(message, NotifyLevel.ERROR, title)

    async def request_file_upload(
        self,
        message: str = "请上传文件",
        accepted_types: Optional[List[str]] = None,
        max_size: Optional[int] = None,
        title: str = "文件上传",
        timeout: int = 300
    ) -> Optional[str]:
        """
        请求文件上传
        
        Args:
            message: 提示消息
            accepted_types: 接受的文件类型
            max_size: 最大文件大小(字节)
            title: 标题
            timeout: 超时时间
            
        Returns:
            Optional[str]: 文件路径
        """
        request = InteractionRequest(
            type=InteractionType.FILE_UPLOAD,
            title=title,
            content=message,
            metadata={
                "accepted_types": accepted_types,
                "max_size": max_size
            },
            timeout=timeout
        )
        
        response = await self._execute_with_timeout_response(request)
        return response.file_path

    async def _execute_with_timeout(self, request: InteractionRequest) -> Any:
        """执行带超时的请求，返回响应的主要值"""
        response = await self._execute_with_timeout_response(request)
        
        if request.type == InteractionType.ASK:
            return response.input_value or request.default_choice or ""
        elif request.type in [InteractionType.SELECT, InteractionType.CONFIRM, InteractionType.AUTHORIZE]:
            return response.choice or request.default_choice or ""
        elif request.type == InteractionType.MULTIPLE_SELECT:
            return response.choices
        elif request.type == InteractionType.FILE_UPLOAD:
            return response.file_path
        
        return response

    async def _execute_with_timeout_response(
        self,
        request: InteractionRequest
    ) -> InteractionResponse:
        """执行带超时的请求，返回完整响应"""
        self._request_count += 1
        
        if request.timeout:
            try:
                response = await asyncio.wait_for(
                    self._dispatch(request),
                    timeout=request.timeout
                )
                self._response_cache[request.id] = response
                return response
            except asyncio.TimeoutError:
                self._timeout_count += 1
                logger.warning(f"[InteractionManager] 请求超时: {request.id[:8]}")
                return InteractionResponse(
                    request_id=request.id,
                    status=InteractionStatus.TIMEOUT,
                    cancel_reason="请求超时"
                )
        else:
            response = await self._dispatch(request)
            self._response_cache[request.id] = response
            return response

    async def submit_response(self, response: InteractionResponse):
        """
        提交响应 (用于外部系统)
        
        Args:
            response: 响应对象
        """
        self._response_cache[response.request_id] = response
        
        if response.request_id in self._pending_requests:
            future = self._pending_requests.pop(response.request_id)
            if not future.done():
                future.set_result(response)

    async def cancel_request(self, request_id: str, reason: str = ""):
        """
        取消请求
        
        Args:
            request_id: 请求ID
            reason: 取消原因
        """
        self._cancelled_count += 1
        
        if request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(InteractionResponse(
                    request_id=request_id,
                    status=InteractionStatus.CANCELLED,
                    cancel_reason=reason
                ))

    def get_cached_response(self, request_id: str) -> Optional[InteractionResponse]:
        """获取缓存的响应"""
        return self._response_cache.get(request_id)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_requests": self._request_count,
            "timeout_count": self._timeout_count,
            "cancelled_count": self._cancelled_count,
            "pending_count": len(self._pending_requests),
            "cached_responses": len(self._response_cache),
            "registered_handlers": list(self._handlers.keys())
        }


class WebSocketInteractionHandler(InteractionHandler):
    """WebSocket交互处理器"""
    
    def __init__(self, websocket_manager: Any = None):
        self._websocket_manager = websocket_manager
        self._pending_futures: Dict[str, asyncio.Future] = {}
    
    async def can_handle(self, request: InteractionRequest) -> bool:
        return self._websocket_manager is not None
    
    async def handle(self, request: InteractionRequest) -> InteractionResponse:
        """通过WebSocket发送请求并等待响应"""
        if not self._websocket_manager:
            raise RuntimeError("WebSocket manager not configured")
        
        future = asyncio.Future()
        self._pending_futures[request.id] = future
        
        try:
            await self._websocket_manager.send_to_session(
                request.session_id,
                {
                    "type": "interaction",
                    "request": request.dict()
                }
            )
            
            if request.timeout:
                response = await asyncio.wait_for(future, timeout=request.timeout)
            else:
                response = await future
            
            return response
        except asyncio.TimeoutError:
            return InteractionResponse(
                request_id=request.id,
                status=InteractionStatus.TIMEOUT
            )
        finally:
            self._pending_futures.pop(request.id, None)
    
    async def receive_response(self, response_data: Dict[str, Any]):
        """接收来自WebSocket的响应"""
        request_id = response_data.get("request_id")
        if request_id in self._pending_futures:
            future = self._pending_futures[request_id]
            if not future.done():
                response = InteractionResponse(**response_data)
                future.set_result(response)


class BatchInteractionManager(InteractionManager):
    """
    批量交互管理器 - 支持批量处理多个交互请求
    
    示例:
        manager = BatchInteractionManager()
        
        questions = [
            {"question": "名称", "default": "test"},
            {"question": "年龄", "default": "18"},
        ]
        answers = await manager.batch_ask(questions)
    """
    
    async def batch_ask(
        self,
        questions: List[Dict[str, Any]],
        title: str = "批量输入",
        timeout: int = 120
    ) -> Dict[str, str]:
        """
        批量询问
        
        Args:
            questions: 问题列表
            title: 标题
            timeout: 总超时时间
            
        Returns:
            Dict[str, str]: 问题名到答案的映射
        """
        results = {}
        
        for q in questions:
            key = q.get("key", q.get("question"))
            answer = await self.ask_user(
                question=q.get("question", ""),
                title=title,
                default=q.get("default"),
                timeout=q.get("timeout", timeout // len(questions))
            )
            results[key] = answer
        
        return results
    
    async def batch_confirm(
        self,
        items: List[Dict[str, Any]],
        title: str = "批量确认"
    ) -> Dict[str, bool]:
        """
        批量确认
        
        Args:
            items: 项目列表
            title: 标题
            
        Returns:
            Dict[str, bool]: 项目ID到确认结果的映射
        """
        results = {}
        
        for item in items:
            item_id = item.get("id", str(items.index(item)))
            confirmed = await self.confirm(
                message=item.get("message", ""),
                title=f"{title} ({items.index(item) + 1}/{len(items)})",
                default=item.get("default", False)
            )
            results[item_id] = confirmed
        
        return results


interaction_manager = InteractionManager()