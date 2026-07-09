"""ToolEntry — TOOLS 槽工具入口契约(RFC-005 S18)。

独立成文件以解开 input↔executor 循环依赖:executor/dispatcher 与
bundle 都依赖 ToolEntry,放此处作共享桥。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# executor_id 约定:Agent 自带工具用此常量,由 Agent 自身提供执行句柄,
# 不走资源 Executor(ToolDispatcher 据此特殊路由)。
BUILTIN_EXECUTOR_ID = "agent:builtin"


@dataclass(frozen=True)
class ToolEntry:
    """TOOLS 槽的标准内容:工具声明 + 执行路由信息(RFC-005 S18)。

    统一了"资源工具"(executor_id 指向真实 Executor)与"Agent 自带工具"
    (executor_id=BUILTIN_EXECUTOR_ID,由 Agent 自身执行)。派发器按
    tool_name 查 ToolEntry → 据 executor_id 决定路由。

    Attributes:
        tool_name: LLM 回传的工具名(派发键)。
        tool: 实际工具句柄(BaseTool/FunctionTool/可执行对象),由 Agent/资源提供。
        capability_id: 归属能力(绑定输入投影↔执行投影;builtin 用 "agent:builtin")。
        executor_id: 执行体路由键;BUILTIN_EXECUTOR_ID 表示走 Agent 自身句柄。
        description: 工具描述(给 LLM 的 schema 用,可选)。
    """

    tool_name: str
    tool: Any
    capability_id: str
    executor_id: str = BUILTIN_EXECUTOR_ID
    description: str = ""