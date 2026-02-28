"""
Permission - 权限检查和管理系统

参考OpenCode的Permission Ruleset设计
实现细粒度的工具权限控制
"""

from typing import Callable, Optional, Dict, Any, Awaitable
from pydantic import BaseModel, Field
from enum import Enum
import asyncio

from .agent_info import PermissionAction, PermissionRuleset


class PermissionRequest(BaseModel):
    """权限请求"""

    tool_name: str  # 工具名称
    tool_args: Dict[str, Any] = Field(default_factory=dict)  # 工具参数
    context: Dict[str, Any] = Field(default_factory=dict)  # 上下文信息
    reason: Optional[str] = None  # 请求原因

    class Config:
        json_schema_extra = {
            "example": {
                "tool_name": "bash",
                "tool_args": {"command": "rm -rf /"},
                "context": {"session_id": "123"},
                "reason": "执行清理操作",
            }
        }


class PermissionResponse(BaseModel):
    """权限响应"""

    granted: bool  # 是否授权
    action: PermissionAction  # 执行动作
    reason: Optional[str] = None  # 原因说明
    user_message: Optional[str] = None  # 给用户的消息

    class Config:
        json_schema_extra = {
            "example": {
                "granted": False,
                "action": "deny",
                "reason": "危险命令禁止执行",
                "user_message": "抱歉,bash命令执行危险操作被拒绝",
            }
        }


class PermissionDeniedError(Exception):
    """权限拒绝异常"""

    def __init__(self, message: str, tool_name: str = None):
        self.message = message
        self.tool_name = tool_name
        super().__init__(self.message)


class PermissionChecker:
    """
    权限检查器 - 管理权限请求和响应

    示例:
        checker = PermissionChecker(ruleset)

        # 同步检查
        response = checker.check("bash", {"command": "ls"})

        # 异步检查(需要用户确认)
        response = await checker.check_async(
            "bash",
            {"command": "rm -rf /"},
            ask_user_callback=prompt_user
        )
    """

    def __init__(self, ruleset: PermissionRuleset):
        self.ruleset = ruleset
        self._ask_callbacks: Dict[str, Callable] = {}

    def check(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> PermissionResponse:
        """
        检查工具权限(同步)

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            context: 上下文信息

        Returns:
            PermissionResponse: 权限响应
        """
        action = self.ruleset.check(tool_name)

        if action == PermissionAction.ALLOW:
            return PermissionResponse(
                granted=True, action=action, reason="权限规则允许"
            )
        elif action == PermissionAction.DENY:
            return PermissionResponse(
                granted=False,
                action=action,
                reason=f"工具 '{tool_name}' 被权限规则拒绝",
                user_message=f"抱歉,工具 '{tool_name}' 的执行被拒绝",
            )
        else:  # ASK
            # 同步模式下,ASK默认拒绝
            return PermissionResponse(
                granted=False,
                action=action,
                reason=f"工具 '{tool_name}' 需要用户确认,但同步模式无法交互",
                user_message=f"工具 '{tool_name}' 需要您的确认才能执行",
            )

    async def check_async(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        ask_user_callback: Optional[
            Callable[[PermissionRequest], Awaitable[bool]]
        ] = None,
        reason: Optional[str] = None,
    ) -> PermissionResponse:
        """
        检查工具权限(异步,支持用户交互)

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            context: 上下文信息
            ask_user_callback: 用户确认回调函数
            reason: 请求原因

        Returns:
            PermissionResponse: 权限响应
        """
        action = self.ruleset.check(tool_name)

        if action == PermissionAction.ALLOW:
            return PermissionResponse(
                granted=True, action=action, reason="权限规则允许"
            )
        elif action == PermissionAction.DENY:
            return PermissionResponse(
                granted=False,
                action=action,
                reason=f"工具 '{tool_name}' 被权限规则拒绝",
                user_message=f"抱歉,工具 '{tool_name}' 的执行被拒绝",
            )
        else:  # ASK
            if ask_user_callback is None:
                # 没有提供回调函数,默认拒绝
                return PermissionResponse(
                    granted=False,
                    action=action,
                    reason=f"工具 '{tool_name}' 需要用户确认,但未提供交互回调",
                    user_message=f"工具 '{tool_name}' 需要您的确认才能执行",
                )

            # 创建权限请求
            request = PermissionRequest(
                tool_name=tool_name,
                tool_args=tool_args or {},
                context=context or {},
                reason=reason,
            )

            # 调用用户确认回调
            try:
                user_approved = await ask_user_callback(request)

                if user_approved:
                    return PermissionResponse(
                        granted=True,
                        action=action,
                        reason="用户已确认授权",
                        user_message="权限已授予",
                    )
                else:
                    return PermissionResponse(
                        granted=False,
                        action=action,
                        reason="用户拒绝授权",
                        user_message="您拒绝了该工具的执行",
                    )
            except Exception as e:
                return PermissionResponse(
                    granted=False,
                    action=action,
                    reason=f"用户确认过程出错: {str(e)}",
                    user_message="权限确认失败",
                )

    def register_ask_callback(
        self, name: str, callback: Callable[[PermissionRequest], Awaitable[bool]]
    ):
        """注册用户确认回调函数"""
        self._ask_callbacks[name] = callback

    def unregister_ask_callback(self, name: str):
        """注销用户确认回调函数"""
        self._ask_callbacks.pop(name, None)


class InteractivePermissionChecker(PermissionChecker):
    """
    交互式权限检查器 - 提供CLI交互

    示例:
        checker = InteractivePermissionChecker(ruleset)

        response = await checker.check_async(
            "bash",
            {"command": "rm -rf /"},
            ask_user_callback=checker.cli_ask
        )
    """

    @staticmethod
    async def cli_ask(request: PermissionRequest) -> bool:
        """
        CLI方式询问用户

        Args:
            request: 权限请求

        Returns:
            bool: 用户是否授权
        """
        print(f"\n{'=' * 60}")
        print(f"⚠️  权限请求")
        print(f"{'=' * 60}")
        print(f"工具名称: {request.tool_name}")
        print(f"工具参数: {request.tool_args}")
        if request.reason:
            print(f"请求原因: {request.reason}")
        print(f"{'=' * 60}")

        # 在事件循环中运行同步输入
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(None, input, "是否授权执行? [y/N]: ")

        return answer.lower() in ["y", "yes", "是"]


class PermissionManager:
    """
    权限管理器 - 管理多个Agent的权限

    示例:
        manager = PermissionManager()

        # 为Agent注册权限规则
        manager.register("primary", primary_ruleset)
        manager.register("plan", plan_ruleset)

        # 检查权限
        checker = manager.get_checker("primary")
        response = checker.check("bash", {"command": "ls"})
    """

    def __init__(self):
        self._checkers: Dict[str, PermissionChecker] = {}
        self._default_ask_callback: Optional[Callable] = None

    def register(
        self,
        agent_name: str,
        ruleset: PermissionRuleset,
        ask_callback: Optional[Callable] = None,
    ):
        """
        为Agent注册权限规则

        Args:
            agent_name: Agent名称
            ruleset: 权限规则集
            ask_callback: 用户确认回调函数
        """
        checker = PermissionChecker(ruleset)

        if ask_callback:
            checker.register_ask_callback("default", ask_callback)
        elif self._default_ask_callback:
            checker.register_ask_callback("default", self._default_ask_callback)

        self._checkers[agent_name] = checker

    def get_checker(self, agent_name: str) -> Optional[PermissionChecker]:
        """获取Agent的权限检查器"""
        return self._checkers.get(agent_name)

    def set_default_ask_callback(
        self, callback: Callable[[PermissionRequest], Awaitable[bool]]
    ):
        """设置默认的用户确认回调函数"""
        self._default_ask_callback = callback

    async def check_async(
        self,
        agent_name: str,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> PermissionResponse:
        """
        检查Agent的工具权限(异步)

        Args:
            agent_name: Agent名称
            tool_name: 工具名称
            tool_args: 工具参数
            context: 上下文信息
            reason: 请求原因

        Returns:
            PermissionResponse: 权限响应
        """
        checker = self.get_checker(agent_name)

        if checker is None:
            # 没有找到对应的检查器,默认拒绝
            return PermissionResponse(
                granted=False,
                action=PermissionAction.DENY,
                reason=f"未找到Agent '{agent_name}' 的权限配置",
            )

        return await checker.check_async(
            tool_name, tool_args, context, checker._ask_callbacks.get("default"), reason
        )


# 全局权限管理器
permission_manager = PermissionManager()


def register_agent_permission(
    agent_name: str, ruleset: PermissionRuleset, ask_callback: Optional[Callable] = None
):
    """注册Agent权限(便捷函数)"""
    permission_manager.register(agent_name, ruleset, ask_callback)


async def check_permission(
    agent_name: str,
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> PermissionResponse:
    """检查权限(便捷函数)"""
    return await permission_manager.check_async(
        agent_name, tool_name, tool_args, context, reason
    )
