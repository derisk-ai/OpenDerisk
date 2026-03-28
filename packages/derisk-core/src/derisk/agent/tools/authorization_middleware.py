"""
ToolAuthorizationMiddleware - 工具授权中间件

为 bash 等工具提供基于执行目录的授权检查：
- 当 cwd 在 sandbox work_dir 内：无需额外授权
- 当 cwd 在 sandbox work_dir 外：需要用户授权

支持 Core 和 CoreV2 两种架构，统一授权流程。
"""

import os
import uuid
import logging
from typing import Dict, Any, Optional, Callable, Awaitable, Tuple
from dataclasses import dataclass
from enum import Enum

from .base import ToolBase
from .context import ToolContext
from .result import ToolResult

logger = logging.getLogger(__name__)


class AuthorizationDecision(Enum):
    """授权决策"""

    ALLOW = "allow"  # 允许执行
    DENY = "deny"  # 拒绝执行
    ASK_USER = "ask_user"  # 需要用户确认


@dataclass
class AuthorizationContext:
    """授权检查上下文"""

    tool_name: str
    tool_args: Dict[str, Any]
    tool_metadata: Any
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    sandbox_work_dir: Optional[str] = None
    agent_name: Optional[str] = None

    @property
    def cache_key(self) -> str:
        """生成缓存key"""
        return f"{self.session_id}:{self.tool_name}:{hash(str(sorted(self.tool_args.items())))}"


@dataclass
class AuthorizationCheckResult:
    """授权检查结果"""

    decision: AuthorizationDecision
    reason: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ToolSpecificAuthorizer:
    """工具特定授权检查器基类"""

    def can_handle(self, tool_name: str) -> bool:
        """是否能处理该工具"""
        raise NotImplementedError

    async def check(
        self,
        context: AuthorizationContext,
    ) -> AuthorizationCheckResult:
        """执行授权检查"""
        raise NotImplementedError


class BashCwdAuthorizer(ToolSpecificAuthorizer):
    """
    Bash 工具 cwd 授权检查器

    检查规则：
    1. 无 sandbox → 需要授权（本地执行）
    2. cwd 未指定 → 在 sandbox 内执行，无需授权
    3. cwd 在 sandbox work_dir 内 → 无需授权
    4. cwd 在 sandbox work_dir 外 → 需要授权

    配置关闭：
    在 ToolMetadata.authorization_config 中设置 {'disable_cwd_check': True} 可关闭此检查
    """

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in ["bash", "shell", "execute_bash"]

    async def check(
        self,
        context: AuthorizationContext,
    ) -> AuthorizationCheckResult:
        """检查 bash 工具的 cwd 授权"""
        tool_args = context.tool_args
        sandbox_work_dir = context.sandbox_work_dir

        # 检查是否通过配置关闭了 cwd 检查
        auth_config = (
            getattr(context.tool_metadata, "authorization_config", {})
            if context.tool_metadata
            else {}
        )
        if auth_config.get("disable_cwd_check", False):
            logger.debug(
                f"[BashCwdAuthorizer] CWD check disabled via config for {context.tool_name}"
            )
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ALLOW,
                reason="CWD authorization check disabled via tool configuration",
            )

        # 1. 无 sandbox，本地执行需要授权
        if not sandbox_work_dir:
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ASK_USER,
                reason="Running bash command in local mode without sandbox protection",
                metadata={
                    "risk_level": "high",
                    "command": tool_args.get("command", ""),
                    "cwd": tool_args.get("cwd"),
                },
            )

        # 2. 获取请求的 cwd
        requested_cwd = tool_args.get("cwd")
        if not requested_cwd:
            # 未指定 cwd，使用默认（在 sandbox 内）
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ALLOW,
                reason="Using default sandbox working directory",
            )

        # 3. 规范化路径并检查
        try:
            is_inside, normalized_cwd, normalized_sandbox = (
                self._check_path_inside_sandbox(requested_cwd, sandbox_work_dir)
            )

            if is_inside:
                return AuthorizationCheckResult(
                    decision=AuthorizationDecision.ALLOW,
                    reason=f"Working directory '{requested_cwd}' is inside sandbox",
                    metadata={
                        "cwd": normalized_cwd,
                        "sandbox_work_dir": normalized_sandbox,
                    },
                )
            else:
                return AuthorizationCheckResult(
                    decision=AuthorizationDecision.ASK_USER,
                    reason=(
                        f"Command execution directory '{requested_cwd}' is outside "
                        f"sandbox working directory '{sandbox_work_dir}'"
                    ),
                    metadata={
                        "risk_level": "high",
                        "command": tool_args.get("command", ""),
                        "cwd": normalized_cwd,
                        "sandbox_work_dir": normalized_sandbox,
                        "requested_cwd": requested_cwd,
                    },
                )

        except Exception as e:
            logger.warning(f"[BashCwdAuthorizer] Path check failed: {e}")
            # 路径检查失败，保守起见需要授权
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ASK_USER,
                reason=f"Cannot verify working directory safety: {str(e)}",
                metadata={
                    "risk_level": "high",
                    "error": str(e),
                },
            )

        # 2. 获取请求的 cwd
        requested_cwd = tool_args.get("cwd")
        if not requested_cwd:
            # 未指定 cwd，使用默认（在 sandbox 内）
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ALLOW,
                reason="Using default sandbox working directory",
            )

        # 3. 规范化路径并检查
        try:
            is_inside, normalized_cwd, normalized_sandbox = (
                self._check_path_inside_sandbox(requested_cwd, sandbox_work_dir)
            )

            if is_inside:
                return AuthorizationCheckResult(
                    decision=AuthorizationDecision.ALLOW,
                    reason=f"Working directory '{requested_cwd}' is inside sandbox",
                    metadata={
                        "cwd": normalized_cwd,
                        "sandbox_work_dir": normalized_sandbox,
                    },
                )
            else:
                return AuthorizationCheckResult(
                    decision=AuthorizationDecision.ASK_USER,
                    reason=(
                        f"Command execution directory '{requested_cwd}' is outside "
                        f"sandbox working directory '{sandbox_work_dir}'"
                    ),
                    metadata={
                        "risk_level": "high",
                        "command": tool_args.get("command", ""),
                        "cwd": normalized_cwd,
                        "sandbox_work_dir": normalized_sandbox,
                        "requested_cwd": requested_cwd,
                    },
                )

        except Exception as e:
            logger.warning(f"[BashCwdAuthorizer] Path check failed: {e}")
            # 路径检查失败，保守起见需要授权
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ASK_USER,
                reason=f"Cannot verify working directory safety: {str(e)}",
                metadata={
                    "risk_level": "high",
                    "error": str(e),
                },
            )

    def _check_path_inside_sandbox(
        self, requested_cwd: str, sandbox_work_dir: str
    ) -> Tuple[bool, str, str]:
        """
        检查请求的路径是否在 sandbox 内

        Returns:
            (is_inside, normalized_cwd, normalized_sandbox)
        """
        # 规范化路径
        requested_abs = os.path.abspath(requested_cwd)
        sandbox_abs = os.path.abspath(sandbox_work_dir)

        # 使用 commonpath 检查是否是子目录
        try:
            common = os.path.commonpath([requested_abs, sandbox_abs])
            is_inside = common == sandbox_abs
        except ValueError:
            # 路径在不同驱动器（Windows）或其他错误
            is_inside = False

        return is_inside, requested_abs, sandbox_abs


class ToolAuthorizationMiddleware:
    """
    工具授权中间件

    统一处理工具执行的授权检查，支持：
    1. 基于工具类型的特定授权策略（如 bash cwd 检查）
    2. 基于 metadata.requires_permission 的基础授权
    3. 用户交互式授权（通过 callback）

    使用方式：
        # Core 架构
        middleware = ToolAuthorizationMiddleware(
            user_callback=ask_user_callback,
        )
        result = await middleware.execute_with_auth(
            tool=bash_tool,
            args={"command": "ls", "cwd": "/etc"},
            context=tool_context,
        )

        # CoreV2 架构
        middleware = ToolAuthorizationMiddleware(
            interaction_gateway=gateway,
        )
        result = await middleware.execute_with_auth(...)
    """

    def __init__(
        self,
        user_callback: Optional[
            Callable[[AuthorizationContext, AuthorizationCheckResult], Awaitable[bool]]
        ] = None,
        interaction_gateway: Optional[Any] = None,
        session_auth_cache: Optional[Dict[str, bool]] = None,
    ):
        """
        初始化中间件

        Args:
            user_callback: 用户授权回调函数，接收 context 和 check_result，返回是否授权
            interaction_gateway: InteractionGateway 实例（用于 CoreV2）
            session_auth_cache: 会话级授权缓存
        """
        self._user_callback = user_callback
        self._interaction_gateway = interaction_gateway
        self._session_auth_cache = session_auth_cache or {}

        # 注册工具特定授权检查器
        self._tool_authorizers: Dict[str, ToolSpecificAuthorizer] = {}
        self._register_default_authorizers()

    def _register_default_authorizers(self):
        """注册默认的工具授权检查器"""
        self.register_authorizer("bash", BashCwdAuthorizer())
        self.register_authorizer("shell", BashCwdAuthorizer())

    def register_authorizer(
        self,
        tool_name: str,
        authorizer: ToolSpecificAuthorizer,
    ):
        """注册工具授权检查器"""
        self._tool_authorizers[tool_name] = authorizer
        logger.info(f"[AuthMiddleware] Registered authorizer for tool: {tool_name}")

    async def execute_with_auth(
        self,
        tool: ToolBase,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None,
        execute_fn: Optional[Callable[..., Awaitable[ToolResult]]] = None,
    ) -> ToolResult:
        """
        带授权检查的工具执行

        Args:
            tool: 工具实例
            args: 工具参数
            context: 工具上下文
            execute_fn: 自定义执行函数（如果为 None，则调用 tool.execute）

        Returns:
            ToolResult: 执行结果或授权失败结果
        """
        # 1. 构建授权上下文
        auth_context = self._build_auth_context(tool, args, context)

        # 2. 执行授权检查
        check_result = await self._check_authorization(auth_context)

        # 3. 根据检查结果处理
        if check_result.decision == AuthorizationDecision.ALLOW:
            # 允许执行
            return await self._execute_tool(tool, args, context, execute_fn)

        elif check_result.decision == AuthorizationDecision.DENY:
            # 明确拒绝
            return ToolResult.fail(
                error=f"Authorization denied: {check_result.reason}",
                tool_name=tool.name,
                error_code="AUTHORIZATION_DENIED",
            )

        else:  # ASK_USER
            # 需要用户授权
            return await self._handle_user_authorization(
                auth_context, check_result, tool, args, context, execute_fn
            )

    def _build_auth_context(
        self,
        tool: ToolBase,
        args: Dict[str, Any],
        context: Optional[ToolContext],
    ) -> AuthorizationContext:
        """构建授权上下文"""
        # 提取 sandbox work_dir
        sandbox_work_dir = None
        if context:
            # 尝试从 context 获取 sandbox_client
            sandbox_client = None
            if hasattr(context, "config"):
                sandbox_client = context.config.get("sandbox_client")
            if not sandbox_client and isinstance(context, dict):
                sandbox_client = context.get("sandbox_client")

            if sandbox_client:
                sandbox_work_dir = getattr(sandbox_client, "work_dir", None)

        return AuthorizationContext(
            tool_name=tool.name,
            tool_args=args,
            tool_metadata=tool.metadata,
            session_id=getattr(context, "conversation_id", None) if context else None,
            user_id=getattr(context, "user_id", None) if context else None,
            sandbox_work_dir=sandbox_work_dir,
            agent_name=getattr(context, "agent_name", None) if context else None,
        )

    async def _check_authorization(
        self,
        context: AuthorizationContext,
    ) -> AuthorizationCheckResult:
        """执行授权检查"""
        # 1. 检查是否有工具特定的授权检查器
        authorizer = self._tool_authorizers.get(context.tool_name)
        if authorizer and authorizer.can_handle(context.tool_name):
            return await authorizer.check(context)

        # 2. 基础授权检查（metadata.requires_permission）
        metadata = context.tool_metadata
        if metadata and getattr(metadata, "requires_permission", False):
            # 需要基础授权，但没有特定检查器
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ASK_USER,
                reason=f"Tool '{context.tool_name}' requires permission",
                metadata={
                    "risk_level": getattr(metadata, "risk_level", "medium"),
                    "approval_message": getattr(metadata, "approval_message", None),
                },
            )

        # 3. 默认允许
        return AuthorizationCheckResult(
            decision=AuthorizationDecision.ALLOW,
            reason="No authorization required",
        )

    async def _handle_user_authorization(
        self,
        auth_context: AuthorizationContext,
        check_result: AuthorizationCheckResult,
        tool: ToolBase,
        args: Dict[str, Any],
        context: Optional[ToolContext],
        execute_fn: Optional[Callable[..., Awaitable[ToolResult]]],
    ) -> ToolResult:
        """处理用户授权流程"""
        # 1. 检查会话缓存
        cache_key = auth_context.cache_key
        if cache_key in self._session_auth_cache:
            logger.info(
                f"[AuthMiddleware] Using cached authorization for {auth_context.tool_name}"
            )
            return await self._execute_tool(tool, args, context, execute_fn)

        # 2. 请求用户授权
        user_approved = await self._request_user_approval(auth_context, check_result)

        if user_approved:
            # 用户授权，缓存并执行
            self._session_auth_cache[cache_key] = True
            return await self._execute_tool(tool, args, context, execute_fn)
        else:
            # 用户拒绝
            return ToolResult.fail(
                error=f"User denied authorization: {check_result.reason}",
                tool_name=auth_context.tool_name,
                error_code="USER_DENIED",
            )

    async def _request_user_approval(
        self,
        auth_context: AuthorizationContext,
        check_result: AuthorizationCheckResult,
    ) -> bool:
        """请求用户授权"""
        # 1. 优先使用 callback
        if self._user_callback:
            try:
                return await self._user_callback(auth_context, check_result)
            except Exception as e:
                logger.error(f"[AuthMiddleware] User callback failed: {e}")
                return False

        # 2. 使用 InteractionGateway（CoreV2 架构）
        if self._interaction_gateway:
            return await self._request_via_gateway(auth_context, check_result)

        # 3. 无交互机制，默认拒绝
        logger.warning(
            f"[AuthMiddleware] No user interaction mechanism available, "
            f"denying authorization for {auth_context.tool_name}"
        )
        return False

    async def _request_via_gateway(
        self,
        auth_context: AuthorizationContext,
        check_result: AuthorizationCheckResult,
    ) -> bool:
        """通过 InteractionGateway 请求用户授权"""
        try:
            from ..interaction.interaction_protocol import (
                InteractionRequest,
                InteractionType,
                InteractionOption,
            )

            # 构建授权请求
            metadata = check_result.metadata or {}
            command = metadata.get("command", "")
            cwd = metadata.get("cwd") or auth_context.tool_args.get("cwd", "")

            message = f"""**Tool Authorization Required**

**Tool:** `{auth_context.tool_name}`
**Command:** `{command}`
**Working Directory:** `{cwd}`

**Reason:** {check_result.reason}

Do you want to allow this command to execute?"""

            request = InteractionRequest(
                request_id=str(uuid.uuid4()),
                interaction_type=InteractionType.AUTHORIZATION,
                title=f"Authorization: {auth_context.tool_name}",
                message=message,
                session_id=auth_context.session_id,
                agent_name=auth_context.agent_name,
                tool_name=auth_context.tool_name,
                options=[
                    InteractionOption(
                        label="Allow Once",
                        value="allow_once",
                        description="Allow this execution only",
                    ),
                    InteractionOption(
                        label="Allow for Session",
                        value="allow_session",
                        description=f"Allow {auth_context.tool_name} for this session",
                    ),
                    InteractionOption(
                        label="Deny",
                        value="deny",
                        description="Cancel this execution",
                    ),
                ],
                metadata={
                    "tool_name": auth_context.tool_name,
                    "tool_args": auth_context.tool_args,
                    "reason": check_result.reason,
                    "risk_level": metadata.get("risk_level", "medium"),
                },
            )

            # 发送请求并等待响应
            response = await self._interaction_gateway.send_and_wait(
                request, timeout=300
            )

            # 处理响应
            if response.status.value == "responded":
                choice = response.choice or ""
                if choice in ["allow_once", "allow_session"]:
                    if choice == "allow_session":
                        # 缓存会话级授权
                        self._session_auth_cache[auth_context.cache_key] = True
                    return True

            return False

        except Exception as e:
            logger.error(f"[AuthMiddleware] Gateway request failed: {e}")
            return False

    async def _execute_tool(
        self,
        tool: ToolBase,
        args: Dict[str, Any],
        context: Optional[ToolContext],
        execute_fn: Optional[Callable[..., Awaitable[ToolResult]]],
    ) -> ToolResult:
        """执行工具"""
        if execute_fn:
            return await execute_fn(tool, args, context)
        else:
            return await tool.execute(args, context)

    def clear_session_cache(self, session_id: Optional[str] = None):
        """清除会话授权缓存"""
        if session_id:
            keys_to_remove = [
                k
                for k in self._session_auth_cache.keys()
                if k.startswith(f"{session_id}:")
            ]
            for key in keys_to_remove:
                del self._session_auth_cache[key]
        else:
            self._session_auth_cache.clear()


# ============ 便捷函数 ============


async def execute_with_authorization(
    tool: ToolBase,
    args: Dict[str, Any],
    context: Optional[ToolContext] = None,
    user_callback: Optional[
        Callable[[AuthorizationContext, AuthorizationCheckResult], Awaitable[bool]]
    ] = None,
    interaction_gateway: Optional[Any] = None,
) -> ToolResult:
    """
    便捷函数：带授权检查的工具执行

    Args:
        tool: 工具实例
        args: 工具参数
        context: 工具上下文
        user_callback: 用户授权回调
        interaction_gateway: InteractionGateway 实例

    Returns:
        ToolResult: 执行结果
    """
    middleware = ToolAuthorizationMiddleware(
        user_callback=user_callback,
        interaction_gateway=interaction_gateway,
    )
    return await middleware.execute_with_auth(tool, args, context)


__all__ = [
    "ToolAuthorizationMiddleware",
    "AuthorizationContext",
    "AuthorizationCheckResult",
    "AuthorizationDecision",
    "ToolSpecificAuthorizer",
    "BashCwdAuthorizer",
    "execute_with_authorization",
]
