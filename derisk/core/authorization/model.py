"""
Authorization Models - Unified Tool Authorization System

This module defines the permission and authorization models:
- Permission actions and authorization modes
- Permission rules and rulesets
- Authorization configuration

Version: 2.0
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
import fnmatch


class PermissionAction(str, Enum):
    """Permission action types."""
    ALLOW = "allow"         # Allow execution
    DENY = "deny"           # Deny execution
    ASK = "ask"             # Ask user for confirmation


class AuthorizationMode(str, Enum):
    """Authorization modes for different security levels."""
    STRICT = "strict"               # Strict mode: follow tool definitions
    MODERATE = "moderate"           # Moderate mode: can override tool definitions
    PERMISSIVE = "permissive"       # Permissive mode: default allow
    UNRESTRICTED = "unrestricted"   # Unrestricted mode: skip all checks


class LLMJudgmentPolicy(str, Enum):
    """LLM judgment policy for authorization decisions."""
    DISABLED = "disabled"           # Disable LLM judgment
    CONSERVATIVE = "conservative"   # Conservative: tend to ask
    BALANCED = "balanced"           # Balanced: neutral judgment
    AGGRESSIVE = "aggressive"       # Aggressive: tend to allow


class PermissionRule(BaseModel):
    """
    Permission rule for fine-grained access control.
    
    Rules are evaluated in priority order (lower number = higher priority).
    The first matching rule determines the action.
    """
    id: str
    name: str
    description: Optional[str] = None
    
    # Matching conditions
    tool_pattern: str = "*"                 # Tool name pattern (supports wildcards)
    category_filter: Optional[str] = None   # Category filter
    risk_level_filter: Optional[str] = None # Risk level filter
    parameter_conditions: Dict[str, Any] = Field(default_factory=dict)
    
    # Action to take when matched
    action: PermissionAction = PermissionAction.ASK
    
    # Priority (lower = higher priority)
    priority: int = 100
    
    # Enabled state
    enabled: bool = True
    
    # Time range for rule activation
    time_range: Optional[Dict[str, str]] = None  # {"start": "09:00", "end": "18:00"}
    
    class Config:
        use_enum_values = True
    
    def matches(
        self,
        tool_name: str,
        tool_metadata: Any,
        arguments: Dict[str, Any],
    ) -> bool:
        """
        Check if this rule matches the given tool and arguments.
        
        Args:
            tool_name: Name of the tool
            tool_metadata: Tool metadata object
            arguments: Tool arguments
            
        Returns:
            True if rule matches, False otherwise
        """
        if not self.enabled:
            return False
        
        # Tool name pattern matching
        if not fnmatch.fnmatch(tool_name, self.tool_pattern):
            return False
        
        # Category filter
        if self.category_filter:
            tool_category = getattr(tool_metadata, 'category', None)
            if tool_category != self.category_filter:
                return False
        
        # Risk level filter
        if self.risk_level_filter:
            auth = getattr(tool_metadata, 'authorization', None)
            if auth:
                risk_level = getattr(auth, 'risk_level', None)
                if risk_level != self.risk_level_filter:
                    return False
        
        # Parameter conditions
        for param_name, condition in self.parameter_conditions.items():
            if param_name not in arguments:
                return False
            
            param_value = arguments[param_name]
            
            # Support multiple condition types
            if isinstance(condition, dict):
                # Range conditions
                if "min" in condition and param_value < condition["min"]:
                    return False
                if "max" in condition and param_value > condition["max"]:
                    return False
                # Pattern matching
                if "pattern" in condition:
                    if not fnmatch.fnmatch(str(param_value), condition["pattern"]):
                        return False
                # Contains check
                if "contains" in condition:
                    if condition["contains"] not in str(param_value):
                        return False
                # Exclude check
                if "excludes" in condition:
                    if condition["excludes"] in str(param_value):
                        return False
            elif isinstance(condition, list):
                # Enumeration values
                if param_value not in condition:
                    return False
            else:
                # Exact match
                if param_value != condition:
                    return False
        
        return True


class PermissionRuleset(BaseModel):
    """
    Permission ruleset - a collection of rules.
    
    Rules are evaluated in priority order. First matching rule wins.
    """
    id: str
    name: str
    description: Optional[str] = None
    
    # Rules list (sorted by priority)
    rules: List[PermissionRule] = Field(default_factory=list)
    
    # Default action when no rule matches
    default_action: PermissionAction = PermissionAction.ASK
    
    class Config:
        use_enum_values = True
    
    def add_rule(self, rule: PermissionRule) -> "PermissionRuleset":
        """Add a rule and maintain priority order."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)
        return self
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        original_len = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < original_len
    
    def check(
        self,
        tool_name: str,
        tool_metadata: Any,
        arguments: Dict[str, Any],
    ) -> PermissionAction:
        """
        Check permission for a tool execution.
        
        Args:
            tool_name: Name of the tool
            tool_metadata: Tool metadata object
            arguments: Tool arguments
            
        Returns:
            Permission action from first matching rule, or default action
        """
        for rule in self.rules:
            if rule.matches(tool_name, tool_metadata, arguments):
                return PermissionAction(rule.action)
        
        return self.default_action
    
    @classmethod
    def from_dict(
        cls,
        config: Dict[str, str],
        id: str = "default",
        name: str = "Default Ruleset",
        **kwargs,
    ) -> "PermissionRuleset":
        """
        Create ruleset from a simple pattern-action dictionary.
        
        Args:
            config: Dictionary mapping tool patterns to actions
            id: Ruleset ID
            name: Ruleset name
            
        Example:
            PermissionRuleset.from_dict({
                "read_*": "allow",
                "write_*": "ask",
                "bash": "deny",
            })
        """
        rules = []
        priority = 10
        
        for pattern, action_str in config.items():
            action = PermissionAction(action_str)
            rules.append(PermissionRule(
                id=f"rule_{priority}",
                name=f"Rule for {pattern}",
                tool_pattern=pattern,
                action=action,
                priority=priority,
            ))
            priority += 10
        
        return cls(id=id, name=name, rules=rules, **kwargs)


class AuthorizationConfig(BaseModel):
    """
    Authorization configuration for an agent or session.
    
    Provides comprehensive authorization settings including:
    - Authorization mode
    - Permission rulesets
    - LLM judgment policy
    - Tool overrides and lists
    - Caching settings
    """
    
    # Authorization mode
    mode: AuthorizationMode = AuthorizationMode.STRICT
    
    # Permission ruleset
    ruleset: Optional[PermissionRuleset] = None
    
    # LLM judgment policy
    llm_policy: LLMJudgmentPolicy = LLMJudgmentPolicy.DISABLED
    llm_prompt: Optional[str] = None
    
    # Tool-level overrides (highest priority after blacklist)
    tool_overrides: Dict[str, PermissionAction] = Field(default_factory=dict)
    
    # Whitelist tools (skip authorization)
    whitelist_tools: List[str] = Field(default_factory=list)
    
    # Blacklist tools (deny execution)
    blacklist_tools: List[str] = Field(default_factory=list)
    
    # Session-level authorization cache
    session_cache_enabled: bool = True
    session_cache_ttl: int = 3600  # seconds
    
    # Authorization timeout
    authorization_timeout: int = 300  # seconds
    
    # User confirmation callback function name
    user_confirmation_callback: Optional[str] = None
    
    class Config:
        use_enum_values = True
    
    def get_effective_action(
        self,
        tool_name: str,
        tool_metadata: Any,
        arguments: Dict[str, Any],
    ) -> PermissionAction:
        """
        Get the effective permission action for a tool.
        
        Priority order:
        1. Blacklist (always deny)
        2. Whitelist (always allow)
        3. Tool overrides
        4. Permission ruleset
        5. Mode-based default
        
        Args:
            tool_name: Name of the tool
            tool_metadata: Tool metadata object
            arguments: Tool arguments
            
        Returns:
            The effective permission action
        """
        # 1. Check blacklist (highest priority)
        if tool_name in self.blacklist_tools:
            return PermissionAction.DENY
        
        # 2. Check whitelist
        if tool_name in self.whitelist_tools:
            return PermissionAction.ALLOW
        
        # 3. Check tool overrides
        if tool_name in self.tool_overrides:
            return PermissionAction(self.tool_overrides[tool_name])
        
        # 4. Check ruleset
        if self.ruleset:
            action = self.ruleset.check(tool_name, tool_metadata, arguments)
            # Only return if not default (ASK) to allow mode-based decision
            if action != PermissionAction.ASK:
                return action
        
        # 5. Mode-based default
        if self.mode == AuthorizationMode.UNRESTRICTED:
            return PermissionAction.ALLOW
        
        elif self.mode == AuthorizationMode.PERMISSIVE:
            # Permissive mode: allow safe/low risk, ask for others
            auth = getattr(tool_metadata, 'authorization', None)
            if auth:
                risk_level = getattr(auth, 'risk_level', 'medium')
                if risk_level in ("safe", "low"):
                    return PermissionAction.ALLOW
            return PermissionAction.ASK
        
        elif self.mode == AuthorizationMode.STRICT:
            # Strict mode: follow tool definition
            auth = getattr(tool_metadata, 'authorization', None)
            if auth:
                requires_auth = getattr(auth, 'requires_authorization', True)
                if not requires_auth:
                    return PermissionAction.ALLOW
            return PermissionAction.ASK
        
        # MODERATE and default: always ask
        return PermissionAction.ASK
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed (not blacklisted)."""
        return tool_name not in self.blacklist_tools
    
    def is_tool_whitelisted(self, tool_name: str) -> bool:
        """Check if a tool is whitelisted."""
        return tool_name in self.whitelist_tools


# Predefined authorization configurations
STRICT_CONFIG = AuthorizationConfig(
    mode=AuthorizationMode.STRICT,
    session_cache_enabled=True,
)

PERMISSIVE_CONFIG = AuthorizationConfig(
    mode=AuthorizationMode.PERMISSIVE,
    session_cache_enabled=True,
)

UNRESTRICTED_CONFIG = AuthorizationConfig(
    mode=AuthorizationMode.UNRESTRICTED,
    session_cache_enabled=False,
)

# Read-only configuration (only allows read operations)
READ_ONLY_CONFIG = AuthorizationConfig(
    mode=AuthorizationMode.STRICT,
    ruleset=PermissionRuleset.from_dict({
        "read*": "allow",
        "glob": "allow",
        "grep": "allow",
        "search*": "allow",
        "list*": "allow",
        "get*": "allow",
        "*": "deny",
    }, id="read_only", name="Read-Only Ruleset"),
)
