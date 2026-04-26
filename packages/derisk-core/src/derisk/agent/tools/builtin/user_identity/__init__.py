"""
用户身份工具模块

提供 Agent 查询当前用户身份和权限的能力：
- GetUserInfoTool: 获取当前用户基本信息（姓名、邮箱、角色等）
- GetUserPermissionsTool: 获取当前用户角色和权限详情
"""

from typing import Any, Dict, List, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...context import ToolContext
from ...metadata import ToolMetadata
from ...result import ToolResult


def _extract_user_context(context) -> Optional[Dict[str, Any]]:
    """从工具执行上下文中提取 user_context。

    context 可能是 ToolContext 实例，也可能是普通 dict（来自 ToolAction._execute_tool）。
    """
    if context is None:
        return None
    if isinstance(context, dict):
        return context.get("user_context")
    return getattr(context, "user_context", None)


class GetUserInfoTool(ToolBase):
    """获取当前用户基本信息工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_user_info",
            display_name="Get User Info",
            description=(
                "获取当前用户的基本身份信息，包括用户名、邮箱、角色和头像。"
                "当用户询问'我是谁'、'我的信息是什么'、'告诉我关于我自己'等问题时，"
                "调用此工具获取当前用户的身份信息。\n\n"
                "无需任何参数，直接调用即可返回当前登录用户的信息。"
                "如果用户管理系统未启用，将返回提示信息。"
            ),
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["user", "identity", "info", "user-info"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        user_ctx = _extract_user_context(context)

        if not user_ctx:
            return ToolResult.ok(
                output="用户管理未启用，无法获取当前用户信息。",
                tool_name=self.name,
            )

        rbac_enabled = user_ctx.get("rbac_enabled", True)
        name = user_ctx.get("name") or user_ctx.get("user_id", "未知")
        email = user_ctx.get("email")
        avatar_url = user_ctx.get("avatar_url")
        roles = user_ctx.get("roles", [])

        lines = [f"当前用户：{name}"]
        if roles:
            lines.append(f"角色：{', '.join(roles)}")
        else:
            role = user_ctx.get("role", "未知")
            lines.append(f"角色：{role}")

        if email:
            lines.append(f"邮箱：{email}")
        else:
            lines.append("邮箱：未设置")

        if avatar_url:
            lines.append(f"头像：{avatar_url}")
        else:
            lines.append("头像：未设置")

        if not rbac_enabled:
            lines.append("\n（用户管理系统未启用，当前为管理员模式）")

        return ToolResult.ok(
            output="\n".join(lines),
            tool_name=self.name,
        )


class GetUserPermissionsTool(ToolBase):
    """获取当前用户权限详情工具"""

    # 资源类型的中文名称映射
    RESOURCE_TYPE_NAMES: Dict[str, str] = {
        "agent": "Agent 应用",
        "tool": "工具",
        "knowledge": "知识库",
        "model": "模型",
        "system": "系统管理",
    }

    # 操作的中文名称映射
    ACTION_NAMES: Dict[str, str] = {
        "read": "查看",
        "chat": "对话",
        "write": "编辑",
        "execute": "执行",
        "admin": "管理",
        "delete": "删除",
        "create": "创建",
        "update": "更新",
    }

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_user_permissions",
            display_name="Get User Permissions",
            description=(
                "获取当前用户的角色和权限详情，包括拥有的角色、各资源的操作权限，"
                "以及不能执行的操作。"
                "当用户询问'我能做什么'、'我的权限是什么'、'我可以使用什么'等问题时，"
                "调用此工具获取权限信息。\n\n"
                "无需任何参数，直接调用即可。"
                "如果用户管理系统未启用，将返回管理员模式提示。"
            ),
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["user", "permissions", "rbac", "auth"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        user_ctx = _extract_user_context(context)

        if not user_ctx:
            return ToolResult.ok(
                output="用户管理未启用，当前拥有全部权限（管理员模式）。",
                tool_name=self.name,
            )

        rbac_enabled = user_ctx.get("rbac_enabled", True)

        if not rbac_enabled:
            name = user_ctx.get("name") or user_ctx.get("user_id", "未知")
            return ToolResult.ok(
                output=(
                    f"当前用户：{name}\n"
                    f"角色：管理员（RBAC 未启用）\n"
                    f"权限：拥有全部权限（管理员模式）"
                ),
                tool_name=self.name,
            )

        name = user_ctx.get("name") or user_ctx.get("user_id", "未知")
        roles = user_ctx.get("roles", [])
        permissions_map = user_ctx.get("permissions_map", {})

        lines = [f"当前用户：{name}"]

        # 角色信息
        if roles:
            lines.append(f"角色：{', '.join(roles)}")
        else:
            lines.append("角色：未分配")

        # 权限详情
        if permissions_map:
            lines.append("")
            lines.append("权限详情：")
            for resource_type, actions in permissions_map.items():
                resource_name = self.RESOURCE_TYPE_NAMES.get(
                    resource_type, resource_type
                )
                action_names = [
                    self.ACTION_NAMES.get(a, a) for a in actions
                ]
                lines.append(f"  - {resource_name}：{', '.join(action_names)}")
        else:
            lines.append("")
            lines.append("权限：未分配任何权限")

        # 权限摘要（如果有）
        permissions_summary = user_ctx.get("permissions_summary")
        if permissions_summary:
            lines.append("")
            lines.append(f"权限摘要：{permissions_summary}")

        return ToolResult.ok(
            output="\n".join(lines),
            tool_name=self.name,
        )


def register_user_identity_tools(registry: Any) -> None:
    """注册用户身份工具到统一框架"""
    registry.register(GetUserInfoTool(), source=ToolSource.SYSTEM)
    registry.register(GetUserPermissionsTool(), source=ToolSource.SYSTEM)