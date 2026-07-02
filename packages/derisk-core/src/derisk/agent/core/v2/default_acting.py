"""default_acting_fn 工厂。

流程：resolve → doom → failure_tracker → pre_tool_use hook → execute → post_tool_use hook → truncate

等价 BAIZE tool_action.py:278-680 的 ToolAction.run，但用原生 V2ToolCall/V2ToolResult/ToolContext。
"""
from typing import Any, Optional

from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker
from derisk.agent.core.v2.tool_resolver import ToolResolver
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.hook_integration import (
    build_pre_tool_use_context,
    build_post_tool_use_context,
)
from derisk.agent.tools.context import ToolContext


def make_default_acting_fn(
    *,
    tool_resolver: ToolResolver,
    doom_loop_detector: Any,
    failure_tracker: ToolFailureTracker,
    truncator: Any,
    tool_context_factory: ToolContextFactory,
    hook_manager: Optional[Any] = None,
):
    async def acting_fn(tool_call: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
        tool_name = tool_call.name
        tool_input = tool_call.args

        # 1. DoomLoop 检测
        allowed = await doom_loop_detector.check(tool_name, tool_input)
        if not allowed:
            return V2ToolResult.fail(error="doom loop detected, blocked", tool_name=tool_name)

        # 2. 失败跟踪
        if failure_tracker.is_blocked(tool_name):
            return V2ToolResult.fail(
                error=f"工具 {tool_name} 连续失败超过阈值，已阻止", tool_name=tool_name
            )

        # 3. 解析工具
        tool = tool_resolver.resolve(tool_name)
        if tool is None:
            return V2ToolResult.fail(error=f"工具 {tool_name} 未注册", tool_name=tool_name)

        # 4. pre_tool_use hook（blocking）
        if hook_manager is not None:
            decision = await hook_manager.trigger_blocking(
                "pre_tool_use",
                build_pre_tool_use_context(tool_call, ctx),
            )
            action = getattr(decision, "action", "CONTINUE")
            if action == "DENY":
                reason = getattr(decision, "reason", "no reason")
                return V2ToolResult.fail(error=f"hook denied: {reason}", tool_name=tool_name)
            if action == "ABORT":
                return V2ToolResult.fail(error="hook aborted", tool_name=tool_name)
            if action == "MODIFY":
                modified = getattr(decision, "modified_args", None)
                if modified is not None:
                    tool_input = modified

        # 5. 执行
        try:
            result: V2ToolResult = await tool.execute(tool_input, context=ctx)
        except Exception as e:
            failure_tracker.record_failure(tool_name)
            if hook_manager is not None:
                await hook_manager.trigger(
                    "post_tool_use",
                    build_post_tool_use_context(tool_call, ctx, None, error=str(e)),
                )
            return V2ToolResult.fail(error=f"执行异常: {e}", tool_name=tool_name)

        if not result.success:
            failure_tracker.record_failure(tool_name)
        else:
            failure_tracker.reset(tool_name)

        # 6. post_tool_use hook（fire-and-forget）
        if hook_manager is not None:
            await hook_manager.trigger(
                "post_tool_use",
                build_post_tool_use_context(tool_call, ctx, result),
            )

        # 7. 截断（L1）
        output_content = str(result.output) if result.output is not None else ""
        trunc_result = await truncator.truncate(output_content, tool_name, tool_input)
        if getattr(trunc_result, "truncated", False):
            # 覆写 output 为截断后内容（含 dattach tag）
            result.output = trunc_result.truncated_content

        return result

    return acting_fn
