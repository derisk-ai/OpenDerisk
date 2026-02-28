from typing import Any, Awaitable, Callable, Dict, Optional

from pydantic import BaseModel

from .ruleset import PermissionAction, PermissionRuleset


class PermissionCheckResult(BaseModel):
    allowed: bool
    action: PermissionAction
    message: Optional[str] = None
    tool_name: str
    context: Dict[str, Any] = {}


class PermissionChecker:
    def __init__(self, ruleset: PermissionRuleset):
        self.ruleset = ruleset
        self._ask_handler: Optional[Callable] = None

    def set_ask_handler(self, handler: Callable[[str, Dict[str, Any]], Awaitable[bool]]):
        self._ask_handler = handler

    async def check(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> PermissionCheckResult:
        ctx = context or {}
        action = self.ruleset.check(tool_name, ctx)

        if action == PermissionAction.ALLOW:
            return PermissionCheckResult(
                allowed=True,
                action=action,
                tool_name=tool_name,
                context=ctx
            )

        if action == PermissionAction.DENY:
            message = self._get_deny_message(tool_name)
            return PermissionCheckResult(
                allowed=False,
                action=action,
                message=message,
                tool_name=tool_name,
                context=ctx
            )

        if self._ask_handler:
            approved = await self._ask_handler(tool_name, args or {})
            return PermissionCheckResult(
                allowed=approved,
                action=action,
                message=None if approved else "用户拒绝了此操作",
                tool_name=tool_name,
                context=ctx
            )

        return PermissionCheckResult(
            allowed=False,
            action=action,
            message="需要用户确认但未提供确认处理器",
            tool_name=tool_name,
            context=ctx
        )

    def _get_deny_message(self, tool_name: str) -> str:
        rule = self.ruleset.rules.get(tool_name)
        if rule and rule.message:
            return rule.message
        return f"工具 '{tool_name}' 被拒绝执行"