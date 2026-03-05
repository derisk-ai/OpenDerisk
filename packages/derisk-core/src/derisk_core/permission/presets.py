from .ruleset import PermissionAction, PermissionRule, PermissionRuleset

PRIMARY_PERMISSION = PermissionRuleset(
    rules={
        "*": PermissionRule(tool_pattern="*", action=PermissionAction.ALLOW),
        "*.env": PermissionRule(tool_pattern="*.env", action=PermissionAction.ASK, message="需要确认才能访问 .env 文件"),
        "*.secret*": PermissionRule(tool_pattern="*.secret*", action=PermissionAction.ASK),
        "bash:rm": PermissionRule(tool_pattern="bash:rm", action=PermissionAction.ASK, message="删除操作需要确认"),
        "doom_loop": PermissionRule(tool_pattern="doom_loop", action=PermissionAction.ASK),
    },
    default_action=PermissionAction.ALLOW
)

READONLY_PERMISSION = PermissionRuleset(
    rules={
        "read": PermissionRule(tool_pattern="read", action=PermissionAction.ALLOW),
        "glob": PermissionRule(tool_pattern="glob", action=PermissionAction.ALLOW),
        "grep": PermissionRule(tool_pattern="grep", action=PermissionAction.ALLOW),
        "write": PermissionRule(tool_pattern="write", action=PermissionAction.DENY, message="只读模式不允许写入"),
        "edit": PermissionRule(tool_pattern="edit", action=PermissionAction.DENY, message="只读模式不允许编辑"),
        "bash": PermissionRule(tool_pattern="bash", action=PermissionAction.ASK, message="只读模式执行命令需要确认"),
    },
    default_action=PermissionAction.DENY
)

EXPLORE_PERMISSION = PermissionRuleset(
    rules={
        "read": PermissionRule(tool_pattern="read", action=PermissionAction.ALLOW),
        "glob": PermissionRule(tool_pattern="glob", action=PermissionAction.ALLOW),
        "grep": PermissionRule(tool_pattern="grep", action=PermissionAction.ALLOW),
    },
    default_action=PermissionAction.DENY
)

SANDBOX_PERMISSION = PermissionRuleset(
    rules={
        "read": PermissionRule(tool_pattern="read", action=PermissionAction.ALLOW),
        "write": PermissionRule(tool_pattern="write", action=PermissionAction.ALLOW),
        "bash": PermissionRule(tool_pattern="bash", action=PermissionAction.ALLOW),
        "*.env": PermissionRule(tool_pattern="*.env", action=PermissionAction.DENY, message="沙箱中禁止访问敏感文件"),
    },
    default_action=PermissionAction.DENY
)