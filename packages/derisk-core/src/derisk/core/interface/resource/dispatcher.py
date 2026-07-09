"""ToolDispatcher —— 工具执行派发(RFC-005 S18)。

按 tool_name 查 ToolEntry → 据 executor_id 路由执行的统一派发器。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from derisk.util.annotations import PublicAPI

from .executor import Executor, ExecutorCall, ExecutorRegistry
from .tool_entry import BUILTIN_EXECUTOR_ID

logger = logging.getLogger(__name__)


@PublicAPI(stability="beta")
@dataclass(frozen=True)
class ToolDispatchResult:
    """工具派发执行结果。

    success=False 时 error 填错误信息,result 无定义。
    consumed 标记是否触发了输入消费(consume,S8)——供 Agent 回调链判断。
    """

    result: Any = None
    success: bool = True
    error: Optional[str] = None
    consumed: bool = False
    executor_id: Optional[str] = None


@PublicAPI(stability="beta")
class ToolDispatcher:
    """按 tool_name 查 ToolEntry → 据 executor_id 路由执行的统一派发器(S18)。

    统一两类工具的执行:
    - **资源工具**(executor_id 指向真实 Executor):registry 取 executor →
      executor.execute(ExecutorCall)。
    - **Agent 自带工具**(executor_id == BUILTIN_EXECUTOR_ID):回调
      ``builtin_executor``(由 Agent 提供,签名 (tool_name, tool, args) → result)。

    路由键:``tool_name``。capability_id 不参与路由(一个 capability 可贡献多工具,
    每个 tool_name 唯一)。executor_id 决定"句柄在哪"。
    """

    def __init__(
        self,
        registry: ExecutorRegistry,
        builtin_executor: Optional[Callable[[str, Any, Dict[str, Any]], Awaitable[Any]]] = None,
    ):
        self.registry = registry
        self.builtin_executor = builtin_executor

    async def dispatch(
        self,
        *,
        tool_name: str,
        args: Dict[str, Any],
        conv_id: str,
        entries: Iterable[Any],
        call_id: Optional[str] = None,
        capability_id_hint: Optional[str] = None,
    ) -> ToolDispatchResult:
        """按 tool_name 派发执行。

        Args:
            tool_name: LLM 回传工具名(派发键)。
            args: 工具参数。
            conv_id: 会话 id(取资源 executor 的引用)。
            entries: TOOLS 槽内容(ToolEntry 列表,或旧式 Contribution 列表,
                后者取其 content 作兼容)。
            call_id: 工具调用 id(透传给 ExecutorCall)。
            capability_id_hint: 可选能力提示(日志用,不参与路由)。

        Returns:
            ToolDispatchResult。
        """
        entry = self._find_entry(entries, tool_name)
        if entry is None:
            return ToolDispatchResult(
                success=False,
                error=f"tool '{tool_name}' not found in TOOLS slot",
            )

        executor_id = getattr(entry, "executor_id", None)
        # ToolEntry 用 .tool;旧式 Contribution(content 是 BaseTool)用 .content
        tool = getattr(entry, "tool", None)
        if tool is None:
            tool = getattr(entry, "content", None)

        # 路由 A:Agent 自带工具 —— 走 builtin_executor 回调
        if executor_id == BUILTIN_EXECUTOR_ID or executor_id is None:
            if self.builtin_executor is None:
                return ToolDispatchResult(
                    success=False,
                    error=(
                        f"tool '{tool_name}' is builtin but no builtin_executor "
                        f"registered"
                    ),
                )
            try:
                result = await self.builtin_executor(tool_name, tool, args)
                return ToolDispatchResult(
                    result=result, executor_id=BUILTIN_EXECUTOR_ID
                )
            except Exception as e:  # noqa: BLE001
                return ToolDispatchResult(success=False, error=str(e))

        # 路由 B:资源工具 —— registry 取 executor 执行
        executor = self.registry.get(conv_id, executor_id)
        if executor is None:
            return ToolDispatchResult(
                success=False,
                error=(
                    f"executor '{executor_id}' not acquired for conv "
                    f"{conv_id}; tool '{tool_name}'"
                ),
            )
        capability_id = capability_id_hint or getattr(entry, "capability_id", "")
        call = ExecutorCall(
            executor_id=executor_id,
            capability_id=capability_id,
            tool_name=tool_name,
            args=args,
            call_id=call_id,
        )
        try:
            result = await executor.execute(call)
            return ToolDispatchResult(result=result, executor_id=executor_id)
        except Exception as e:  # noqa: BLE001
            return ToolDispatchResult(success=False, error=str(e))

    @staticmethod
    def _find_entry(entries: Iterable[Any], tool_name: str) -> Optional[Any]:
        """在 TOOLS 槽内按 tool_name 查条目。

        兼容 ToolEntry(取 .tool_name)与旧式 Contribution(content 为 BaseTool,
        取 .name)。
        """
        for e in entries:
            # ToolEntry 形态
            tn = getattr(e, "tool_name", None)
            if tn is None:
                # 旧式 Contribution:content 是 BaseTool,取其 name
                tool = getattr(e, "content", None)
                tn = getattr(tool, "name", None)
            if tn == tool_name:
                return e
        return None

    @staticmethod
    def build_index(entries: Iterable[Any]) -> Dict[str, Any]:
        """构建 tool_name → entry 索引(O(N) 查找替代每次线性扫)。"""
        index: Dict[str, Any] = {}
        for e in entries:
            tn = getattr(e, "tool_name", None) or getattr(
                getattr(e, "content", None), "name", None
            )
            if tn:
                index[tn] = e
        return index