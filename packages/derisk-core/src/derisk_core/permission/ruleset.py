from enum import Enum
from typing import Any, Dict, Optional

import fnmatch
from pydantic import BaseModel, Field


class PermissionAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionRule(BaseModel):
    tool_pattern: str
    action: PermissionAction
    message: Optional[str] = None


class PermissionRuleset(BaseModel):
    rules: Dict[str, PermissionRule] = Field(default_factory=dict)
    default_action: PermissionAction = PermissionAction.ASK

    def check(self, tool_name: str, context: Optional[Dict[str, Any]] = None) -> PermissionAction:
        if tool_name in self.rules:
            return self.rules[tool_name].action

        for pattern, rule in self.rules.items():
            if self._match_pattern(pattern, tool_name):
                return rule.action

        return self.default_action

    def add_rule(self, pattern: str, action: PermissionAction, message: Optional[str] = None):
        self.rules[pattern] = PermissionRule(
            tool_pattern=pattern,
            action=action,
            message=message
        )

    @staticmethod
    def _match_pattern(pattern: str, name: str) -> bool:
        return fnmatch.fnmatch(name, pattern)

    def merge(self, other: 'PermissionRuleset') -> 'PermissionRuleset':
        merged = PermissionRuleset(
            rules={**self.rules, **other.rules},
            default_action=other.default_action
        )
        return merged