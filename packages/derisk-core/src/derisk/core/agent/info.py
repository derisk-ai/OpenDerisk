"""
Agent Info Models - Unified Tool Authorization System

This module defines agent configuration models:
- Agent modes and capabilities
- Tool selection policies
- Agent info with complete configuration
- Predefined agent templates

Version: 2.0
"""

from typing import Dict, Any, List, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field
from enum import Enum

if TYPE_CHECKING:
    from ..tools.metadata import ToolMetadata, ToolCategory
    from ..authorization.model import AuthorizationConfig


class AgentMode(str, Enum):
    """Agent execution modes."""
    PRIMARY = "primary"        # Main interactive agent
    SUBAGENT = "subagent"      # Delegated sub-agent
    UTILITY = "utility"        # Utility/helper agent
    SUPERVISOR = "supervisor"  # Supervisor/orchestrator agent


class AgentCapability(str, Enum):
    """Agent capabilities for filtering and matching."""
    CODE_ANALYSIS = "code_analysis"        # Can analyze code
    CODE_GENERATION = "code_generation"    # Can generate code
    FILE_OPERATIONS = "file_operations"    # Can perform file operations
    SHELL_EXECUTION = "shell_execution"    # Can execute shell commands
    WEB_BROWSING = "web_browsing"          # Can browse the web
    DATA_ANALYSIS = "data_analysis"        # Can analyze data
    PLANNING = "planning"                  # Can create plans
    REASONING = "reasoning"                # Can perform complex reasoning


class ToolSelectionPolicy(BaseModel):
    """
    Policy for selecting which tools an agent can use.
    
    Provides multiple filtering mechanisms:
    - Category inclusion/exclusion
    - Tool name inclusion/exclusion
    - Preferred tools ordering
    - Maximum tool limit
    """
    # Category filters
    included_categories: List[str] = Field(default_factory=list)
    excluded_categories: List[str] = Field(default_factory=list)
    
    # Tool name filters
    included_tools: List[str] = Field(default_factory=list)
    excluded_tools: List[str] = Field(default_factory=list)
    
    # Preferred tools (shown first in tool list)
    preferred_tools: List[str] = Field(default_factory=list)
    
    # Maximum number of tools (None = no limit)
    max_tools: Optional[int] = None
    
    def filter_tools(self, tools: List["ToolMetadata"]) -> List["ToolMetadata"]:
        """
        Filter tools based on this policy.
        
        Args:
            tools: List of tool metadata to filter
            
        Returns:
            Filtered and ordered list of tools
        """
        filtered = []
        
        for tool in tools:
            # Category exclusion
            if self.excluded_categories:
                if tool.category in self.excluded_categories:
                    continue
            
            # Category inclusion
            if self.included_categories:
                if tool.category not in self.included_categories:
                    continue
            
            # Tool name exclusion
            if self.excluded_tools:
                if tool.name in self.excluded_tools:
                    continue
            
            # Tool name inclusion
            if self.included_tools:
                if tool.name not in self.included_tools:
                    continue
            
            filtered.append(tool)
        
        # Sort by preference
        if self.preferred_tools:
            def sort_key(t: "ToolMetadata") -> int:
                try:
                    return self.preferred_tools.index(t.name)
                except ValueError:
                    return len(self.preferred_tools)
            
            filtered.sort(key=sort_key)
        
        # Apply max limit
        if self.max_tools is not None:
            filtered = filtered[:self.max_tools]
        
        return filtered
    
    def allows_tool(self, tool_name: str, tool_category: Optional[str] = None) -> bool:
        """
        Check if a specific tool is allowed by this policy.
        
        Args:
            tool_name: Name of the tool
            tool_category: Category of the tool (optional)
            
        Returns:
            True if tool is allowed, False otherwise
        """
        # Check tool exclusion
        if self.excluded_tools and tool_name in self.excluded_tools:
            return False
        
        # Check tool inclusion
        if self.included_tools and tool_name not in self.included_tools:
            return False
        
        # Check category exclusion
        if tool_category and self.excluded_categories:
            if tool_category in self.excluded_categories:
                return False
        
        # Check category inclusion
        if tool_category and self.included_categories:
            if tool_category not in self.included_categories:
                return False
        
        return True


class AgentInfo(BaseModel):
    """
    Agent configuration and information.
    
    Provides comprehensive agent configuration including:
    - Basic identification
    - LLM configuration
    - Tool and authorization settings
    - Prompt templates
    - Multi-agent collaboration
    """
    
    # ========== Basic Information ==========
    name: str                                      # Agent name
    description: str = ""                          # Agent description
    mode: AgentMode = AgentMode.PRIMARY            # Agent mode
    version: str = "1.0.0"                         # Version
    hidden: bool = False                           # Hidden from UI
    
    # ========== LLM Configuration ==========
    model_id: Optional[str] = None                 # Model identifier
    provider_id: Optional[str] = None              # Provider identifier
    temperature: float = 0.7                       # Temperature setting
    max_tokens: Optional[int] = None               # Max output tokens
    
    # ========== Execution Configuration ==========
    max_steps: int = 100                           # Maximum execution steps
    timeout: int = 3600                            # Execution timeout (seconds)
    
    # ========== Tool Configuration ==========
    tool_policy: Optional[ToolSelectionPolicy] = None
    tools: List[str] = Field(default_factory=list)  # Explicit tool list
    
    # ========== Authorization Configuration ==========
    # New unified authorization field
    authorization: Optional[Dict[str, Any]] = None
    # Legacy permission field (for backward compatibility)
    permission: Optional[Dict[str, str]] = None
    
    # ========== Capabilities ==========
    capabilities: List[AgentCapability] = Field(default_factory=list)
    
    # ========== Display Configuration ==========
    color: Optional[str] = None                    # UI color
    icon: Optional[str] = None                     # UI icon
    
    # ========== Prompt Configuration ==========
    system_prompt: Optional[str] = None            # Inline system prompt
    system_prompt_file: Optional[str] = None       # System prompt file path
    user_prompt_template: Optional[str] = None     # User prompt template
    
    # ========== Context Configuration ==========
    context_window_size: Optional[int] = None      # Context window size
    memory_enabled: bool = True                    # Enable memory
    memory_type: str = "conversation"              # Memory type
    
    # ========== Multi-Agent Configuration ==========
    subagents: List[str] = Field(default_factory=list)  # Available subagents
    collaboration_mode: str = "sequential"         # sequential/parallel/adaptive
    
    # ========== Metadata ==========
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    
    class Config:
        use_enum_values = True
    
    def get_effective_authorization(self) -> Dict[str, Any]:
        """
        Get effective authorization configuration.
        
        Merges new authorization field with legacy permission field.
        
        Returns:
            Authorization configuration dictionary
        """
        # Start with default configuration
        config: Dict[str, Any] = {
            "mode": "strict",
            "session_cache_enabled": True,
        }
        
        # Apply authorization if present
        if self.authorization:
            config.update(self.authorization)
        
        # Apply legacy permission as ruleset
        if self.permission:
            # Convert legacy format to ruleset
            from ..authorization.model import PermissionRuleset
            ruleset = PermissionRuleset.from_dict(
                self.permission,
                id=f"{self.name}_legacy",
                name=f"Legacy rules for {self.name}",
            )
            config["ruleset"] = ruleset.model_dump()
        
        return config
    
    def get_openai_tools(
        self,
        registry: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        Get OpenAI-format tool list for this agent.
        
        Args:
            registry: Tool registry to use (optional)
            
        Returns:
            List of OpenAI function calling specifications
        """
        if registry is None:
            from ..tools.base import tool_registry
            registry = tool_registry
        
        tools = []
        
        # Get all tools from registry
        all_tools = registry.list_all()
        
        # Apply tool policy
        if self.tool_policy:
            all_tools = self.tool_policy.filter_tools(all_tools)
        
        # Filter by explicit tool list
        if self.tools:
            all_tools = [t for t in all_tools if t.metadata.name in self.tools]
        
        # Generate OpenAI specs
        for tool in all_tools:
            tools.append(tool.metadata.get_openai_spec())
        
        return tools
    
    def has_capability(self, capability: AgentCapability) -> bool:
        """Check if agent has a specific capability."""
        return capability in self.capabilities
    
    def can_use_tool(self, tool_name: str, tool_category: Optional[str] = None) -> bool:
        """
        Check if agent can use a specific tool.
        
        Args:
            tool_name: Name of the tool
            tool_category: Category of the tool
            
        Returns:
            True if agent can use the tool
        """
        # Check explicit tool list first
        if self.tools:
            return tool_name in self.tools
        
        # Check tool policy
        if self.tool_policy:
            return self.tool_policy.allows_tool(tool_name, tool_category)
        
        # Default: allow all tools
        return True


# ============ Predefined Agent Templates ============

PRIMARY_AGENT_TEMPLATE = AgentInfo(
    name="primary",
    description="Primary interactive coding agent",
    mode=AgentMode.PRIMARY,
    capabilities=[
        AgentCapability.CODE_ANALYSIS,
        AgentCapability.CODE_GENERATION,
        AgentCapability.FILE_OPERATIONS,
        AgentCapability.SHELL_EXECUTION,
        AgentCapability.REASONING,
    ],
    authorization={
        "mode": "strict",
        "session_cache_enabled": True,
        "whitelist_tools": ["read", "glob", "grep"],
    },
    max_steps=100,
    timeout=3600,
)

PLAN_AGENT_TEMPLATE = AgentInfo(
    name="plan",
    description="Planning agent with read-only access",
    mode=AgentMode.UTILITY,
    capabilities=[
        AgentCapability.CODE_ANALYSIS,
        AgentCapability.PLANNING,
        AgentCapability.REASONING,
    ],
    tool_policy=ToolSelectionPolicy(
        excluded_categories=["shell"],
        excluded_tools=["write", "edit", "bash"],
    ),
    authorization={
        "mode": "strict",
        "whitelist_tools": ["read", "glob", "grep", "search"],
        "blacklist_tools": ["write", "edit", "bash", "shell"],
    },
    max_steps=50,
    timeout=1800,
)

SUBAGENT_TEMPLATE = AgentInfo(
    name="subagent",
    description="Delegated sub-agent with limited scope",
    mode=AgentMode.SUBAGENT,
    capabilities=[
        AgentCapability.CODE_ANALYSIS,
        AgentCapability.CODE_GENERATION,
    ],
    authorization={
        "mode": "moderate",
        "session_cache_enabled": True,
    },
    max_steps=30,
    timeout=900,
)

EXPLORE_AGENT_TEMPLATE = AgentInfo(
    name="explore",
    description="Exploration agent for codebase analysis",
    mode=AgentMode.UTILITY,
    capabilities=[
        AgentCapability.CODE_ANALYSIS,
        AgentCapability.REASONING,
    ],
    tool_policy=ToolSelectionPolicy(
        included_tools=["read", "glob", "grep", "search", "list"],
    ),
    authorization={
        "mode": "permissive",
        "whitelist_tools": ["read", "glob", "grep", "search", "list"],
    },
    max_steps=20,
    timeout=600,
)


def create_agent_from_template(
    template: AgentInfo,
    name: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> AgentInfo:
    """
    Create an agent from a template with optional overrides.
    
    Args:
        template: Template AgentInfo to copy from
        name: Override name (optional)
        overrides: Dictionary of field overrides
        
    Returns:
        New AgentInfo instance
    """
    # Copy template data
    data = template.model_dump()
    
    # Apply name override
    if name:
        data["name"] = name
    
    # Apply other overrides
    if overrides:
        data.update(overrides)
    
    return AgentInfo.model_validate(data)


# Template registry for easy access
AGENT_TEMPLATES: Dict[str, AgentInfo] = {
    "primary": PRIMARY_AGENT_TEMPLATE,
    "plan": PLAN_AGENT_TEMPLATE,
    "subagent": SUBAGENT_TEMPLATE,
    "explore": EXPLORE_AGENT_TEMPLATE,
}


def get_agent_template(name: str) -> Optional[AgentInfo]:
    """Get an agent template by name."""
    return AGENT_TEMPLATES.get(name)


def list_agent_templates() -> List[str]:
    """List available agent template names."""
    return list(AGENT_TEMPLATES.keys())
