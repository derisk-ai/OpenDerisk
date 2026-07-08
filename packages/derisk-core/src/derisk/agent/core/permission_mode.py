"""PR 5 Level 1: PermissionMode — 全局权限模式（auto/plan/manual）。

V1 只有 Ruleset（按工具名匹配 ALLOW/ASK/DENY）+ pre-tool hook，没有全局模式开关。
本模块补 Mode 层：作为 5 级链的最外层短路。

5 级链顺序：
1. Mode (本文件) - 全局短路
2. SessionCache - V1 已有（interaction_adapter._session_auth_cache），PR 5 加 conv_id 命名空间
3. Ruleset - V1 已有（base_agent.check_tool_permission / agent_info.PermissionRuleset）
4. Tool hook - V1 已有（tool_action._invoke_pre_tool_hook）
5. ASK 持久化 - PR 5 新增（permission_checkpoint_store）

Mode 语义：
- AUTO: 全放行（Ruleset DENY 仍生效，但 ASK 不再问用户）
- PLAN: 只读工具放行，写工具 ASK
- MANUAL: 全部 ASK（除 Ruleset ALLOW）

设计为 opt-in：agent_context.extra["permission_mode"] 不设置时，Mode 层不短路，
落到 V1 现有 Ruleset + hook + ASK 路径，向后兼容。
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from derisk.agent.tools.base import ToolCategory


class PermissionMode(str, Enum):
    """权限模式。"""
    AUTO = "auto"       # 全放行（除 Ruleset DENY）
    PLAN = "plan"       # 只读工具放行，写工具 ASK
    MANUAL = "manual"   # 全部 ASK（除 Ruleset ALLOW）


# PLAN 模式下视为"写"工具、需要 ASK 的分类
# 只读分类（SEARCH / ANALYSIS / REASONING / UTILITY / VISUALIZATION / USER_INTERACTION）
# 不在内，PLAN 模式下放行
WRITE_CATEGORIES = frozenset({
    ToolCategory.FILE_SYSTEM,
    ToolCategory.SHELL,
    ToolCategory.DATABASE,
    ToolCategory.CODE,
    ToolCategory.SANDBOX,
    ToolCategory.NETWORK,
    ToolCategory.API,
    ToolCategory.MCP,  # MCP 工具副作用未知，保守视为写
    ToolCategory.MEDIA_GEN,
    ToolCategory.PLUGIN,
})


def is_write_category(category: Optional[ToolCategory]) -> bool:
    """工具分类是否为'写'类（PLAN 模式下需 ASK）。"""
    if category is None:
        return False  # 未知分类保守放行
    return category in WRITE_CATEGORIES


def mode_short_circuits_to_allow(
    mode: Optional[PermissionMode],
    tool_category: Optional[ToolCategory] = None,
) -> bool:
    """Mode 是否短路放行该工具（不触发 ASK）。

    返回 True 表示 Mode 层决定放行，跳过后续 ASK。
    返回 False 表示需要继续走 Ruleset / hook / ASK 链路。

    None mode → 不短路，返回 False（向后兼容 V1 行为）。
    """
    if mode is None:
        return False
    if mode == PermissionMode.AUTO:
        return True
    if mode == PermissionMode.MANUAL:
        return False
    # PLAN: 只读放行，写 ASK
    if mode == PermissionMode.PLAN:
        return not is_write_category(tool_category)
    return False


def mode_short_circuits_to_ask(
    mode: Optional[PermissionMode],
    tool_category: Optional[ToolCategory] = None,
) -> bool:
    """Mode 是否短路到 ASK（跳过 Ruleset 直接问用户）。

    MANUAL 模式下所有工具都 ASK（无论 Ruleset 怎么配）。
    PLAN 模式下写工具 ASK（无论 Ruleset 怎么配）。

    返回 False 表示不走 ASK 短路，继续 Ruleset → hook 链路。
    """
    if mode is None:
        return False
    if mode == PermissionMode.MANUAL:
        return True
    if mode == PermissionMode.PLAN:
        return is_write_category(tool_category)
    return False


def parse_permission_mode(value) -> Optional[PermissionMode]:
    """从配置值解析 PermissionMode。None / 空 / 未知值返回 None。"""
    if value is None:
        return None
    if isinstance(value, PermissionMode):
        return value
    if isinstance(value, str):
        try:
            return PermissionMode(value.lower())
        except ValueError:
            return None
    return None
