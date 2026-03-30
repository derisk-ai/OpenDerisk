"""Agent Info Configuration Model - Inspired by opencode/openclaw design patterns."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union, Callable, Type
from derisk._private.pydantic import BaseModel, Field, field_validator, model_validator

from derisk.agent.core.agent_alias import AgentAliasManager


class AgentMode(str, Enum):
    """Agent running mode."""

    PRIMARY = "primary"
    SUBAGENT = "subagent"
    ALL = "all"


class PermissionAction(str, Enum):
    """Permission action types."""

    ASK = "ask"
    ALLOW = "allow"
    DENY = "deny"


@dataclasses.dataclass
class PermissionRule:
    """A single permission rule."""

    action: PermissionAction
    pattern: str
    permission: str

    def matches(self, tool_name: str, command: Optional[str] = None) -> bool:
        """Check if this rule matches the given tool/command."""
        import fnmatch

        if self.permission == "*":
            return True
        if fnmatch.fnmatch(tool_name, self.pattern):
            return True
        if command and fnmatch.fnmatch(command, self.pattern):
            return True
        return False


class PermissionRuleset:
    """
    Permission ruleset - inspired by opencode permission system.

    Supports hierarchical permission rules with pattern matching.
    Rules are evaluated in order, last matching rule wins.
    """

    def __init__(self, rules: Optional[List[PermissionRule]] = None):
        self._rules: List[PermissionRule] = rules or []

    def check(self, tool_name: str, command: Optional[str] = None) -> PermissionAction:
        """Check permission for a tool/command."""
        result = PermissionAction.ASK  # default

        for rule in self._rules:
            if rule.matches(tool_name, command):
                result = rule.action

        return result

    def is_allowed(self, tool_name: str, command: Optional[str] = None) -> bool:
        """Check if action is allowed."""
        action = self.check(tool_name, command)
        return action == PermissionAction.ALLOW

    def is_denied(self, tool_name: str, command: Optional[str] = None) -> bool:
        """Check if action is denied."""
        action = self.check(tool_name, command)
        return action == PermissionAction.DENY

    def needs_ask(self, tool_name: str, command: Optional[str] = None) -> bool:
        """Check if action needs user confirmation."""
        action = self.check(tool_name, command)
        return action == PermissionAction.ASK

    def add_rule(self, rule: PermissionRule) -> "PermissionRuleset":
        """Add a permission rule."""
        self._rules.append(rule)
        return self

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "PermissionRuleset":
        """Create PermissionRuleset from configuration dict."""
        rules: List[PermissionRule] = []

        def _parse_rules(permission: str, value: Any, prefix: str = ""):
            if isinstance(value, str):
                pattern = f"{prefix}{permission}" if prefix else permission
                rules.append(
                    PermissionRule(
                        action=PermissionAction(value),
                        pattern=pattern,
                        permission=permission,
                    )
                )
            elif isinstance(value, dict):
                for k, v in value.items():
                    new_prefix = f"{prefix}{k}." if prefix else f"{k}."
                    _parse_rules(k, v, new_prefix.rstrip("."))

        for key, value in config.items():
            _parse_rules(key, value)

        return cls(rules)

    @classmethod
    def merge(cls, *rulesets: "PermissionRuleset") -> "PermissionRuleset":
        """Merge multiple rulesets, later ones override earlier ones."""
        all_rules: List[PermissionRule] = []
        for ruleset in rulesets:
            if ruleset:
                all_rules.extend(ruleset._rules)
        return cls(all_rules)

    def __iter__(self):
        return iter(self._rules)

    def some(self, predicate: Callable[[PermissionRule], bool]) -> bool:
        """Check if any rule matches predicate."""
        return any(predicate(rule) for rule in self._rules)


class AgentInfo(BaseModel):
    """
    Agent configuration model - inspired by opencode Agent.Info design.

    This provides a declarative way to define agent behavior,
    separate from the implementation class.
    """

    name: str = Field(..., description="Agent identifier name")
    description: Optional[str] = Field(default=None, description="Agent description")
    mode: AgentMode = Field(
        default=AgentMode.PRIMARY, description="Agent mode: primary, subagent, or all"
    )

    llm_model_config: Dict[str, Any] = Field(
        default_factory=dict, description="Model configuration: {provider_id, model_id}"
    )

    prompt: Optional[str] = Field(default=None, description="Custom system prompt")
    prompt_file: Optional[str] = Field(default=None, description="Path to prompt file")

    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_steps: Optional[int] = Field(
        default=None, ge=1, description="Maximum agentic iterations"
    )

    tools: Dict[str, bool] = Field(
        default_factory=dict,
        description="Tool enablement config: {tool_name: true/false}",
    )

    permission: Dict[str, Any] = Field(
        default_factory=lambda: {"*": "ask"}, description="Permission rules config"
    )

    hidden: bool = Field(default=False, description="Hide from UI")
    color: Optional[str] = Field(default=None, description="UI color theme")

    options: Dict[str, Any] = Field(
        default_factory=dict, description="Additional provider-specific options"
    )

    native: bool = Field(default=True, description="Is this a native built-in agent")
    variant: Optional[str] = Field(default=None, description="Agent variant identifier")

    _permission_ruleset: Optional[PermissionRuleset] = None

    @model_validator(mode="after")
    def build_permission(self) -> "AgentInfo":
        """Build permission ruleset after validation."""
        if self.permission:
            self._permission_ruleset = PermissionRuleset.from_config(self.permission)
        return self

    @property
    def permission_ruleset(self) -> PermissionRuleset:
        """Get prepared permission ruleset."""
        if self._permission_ruleset is None:
            self._permission_ruleset = PermissionRuleset.from_config(self.permission)
        return self._permission_ruleset

    def check_permission(
        self, tool_name: str, command: Optional[str] = None
    ) -> PermissionAction:
        """Check permission for a tool/command."""
        return self.permission_ruleset.check(tool_name, command)

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a tool is enabled for this agent."""
        if tool_name in self.tools:
            return self.tools[tool_name]
        if "*" in self.tools:
            return self.tools["*"]
        return True  # default enabled

    @classmethod
    def from_markdown(cls, content: str) -> "AgentInfo":
        """
        Parse agent config from markdown with YAML frontmatter.

        Example:
        ```markdown
        ---
        name: code-reviewer
        description: Reviews code for quality
        mode: subagent
        tools:
          write: false
          edit: false
        ---
        You are a code reviewer...
        ```
        """
        import yaml

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                prompt = parts[2].strip()

                if frontmatter:
                    frontmatter["prompt"] = prompt
                    return cls(**frontmatter)

        return cls(name="unknown", prompt=content)

    def to_markdown(self) -> str:
        """Export agent config as markdown with frontmatter."""
        import yaml

        config = self.model_dump(
            exclude={"prompt", "native", "_permission_ruleset"}, exclude_none=True
        )
        frontmatter = yaml.dump(config, default_flow_style=False)

        return f"---\n{frontmatter}---\n\n{self.prompt or ''}"


class AgentRegistry:
    """
    Agent registry - manages agent definitions.

    Inspired by opencode state pattern for lazy-loaded agent configs.
    """

    _instance: Optional["AgentRegistry"] = None
    _agents: Dict[str, AgentInfo] = {}

    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        return cls()

    def register(self, agent_info: AgentInfo) -> "AgentRegistry":
        """Register an agent definition."""
        self._agents[agent_info.name] = agent_info

        # 自动注册别名（如果Agent有历史名称）
        aliases = AgentAliasManager.get_aliases_for(agent_info.name)
        for alias in aliases:
            logger.debug(f"Auto-registered alias: {alias} -> {agent_info.name}")

        return self

    def unregister(self, name: str) -> "AgentRegistry":
        """Unregister an agent definition."""
        self._agents.pop(name, None)
        return self

    def get(self, name: str) -> Optional[AgentInfo]:
        """Get agent info by name (支持别名解析)"""
        resolved_name = AgentAliasManager.resolve_alias(name)
        return self._agents.get(resolved_name)

    def list(
        self, mode: Optional[AgentMode] = None, include_hidden: bool = False
    ) -> List[AgentInfo]:
        """List all registered agents."""
        results = []
        for agent in self._agents.values():
            if not include_hidden and agent.hidden:
                continue
            if mode and agent.mode != mode and agent.mode != AgentMode.ALL:
                continue
            results.append(agent)
        return results

    def list_primary(self) -> List[AgentInfo]:
        """List all primary agents."""
        return self.list(mode=AgentMode.PRIMARY)

    def list_subagents(self) -> List[AgentInfo]:
        """List all subagents."""
        return self.list(mode=AgentMode.SUBAGENT)

    @classmethod
    def register_defaults(cls) -> "AgentRegistry":
        """Register default built-in agents."""
        registry = cls.get_instance()

        default_permission = {"*": "allow", "ask_user": "deny"}

        registry.register(
            AgentInfo(
                name="build",
                description="Default agent with full tool access for development work",
                mode=AgentMode.PRIMARY,
                permission={
                    **default_permission,
                    "ask_user": "allow",
                },
                native=True,
            )
        )

        registry.register(
            AgentInfo(
                name="plan",
                description="Planning agent with read-only access for analysis",
                mode=AgentMode.PRIMARY,
                permission={
                    **default_permission,
                    "edit": {"*": "deny"},
                    "write": {"*": "deny"},
                },
                tools={"write": False, "edit": False},
                native=True,
            )
        )

        registry.register(
            AgentInfo(
                name="general",
                description="General-purpose subagent for multi-step tasks",
                mode=AgentMode.SUBAGENT,
                permission=default_permission,
                native=True,
            )
        )

        registry.register(
            AgentInfo(
                name="explore",
                description="Fast read-only agent for codebase exploration",
                mode=AgentMode.SUBAGENT,
                permission={
                    "*": "deny",
                    "glob": "allow",
                    "grep": "allow",
                    "read": "allow",
                    "bash": "allow",
                },
                tools={"write": False, "edit": False},
                native=True,
            )
        )

        return registry


def create_agent_info(
    name: str, description: str, mode: AgentMode = AgentMode.PRIMARY, **kwargs
) -> AgentInfo:
    """Factory function to create AgentInfo."""
    return AgentInfo(name=name, description=description, mode=mode, **kwargs)
