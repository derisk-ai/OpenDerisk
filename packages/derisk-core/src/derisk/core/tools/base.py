"""
Tool Base and Registry - Unified Tool Authorization System

This module implements:
- ToolResult: Result of tool execution
- ToolBase: Abstract base class for all tools
- ToolRegistry: Singleton registry for tool management
- Global registry instance and registration decorator

Version: 2.0
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, AsyncIterator, Callable, TypeVar
from dataclasses import dataclass, field
import asyncio
import logging

from .metadata import ToolMetadata, ToolCategory, RiskLevel, RiskCategory, AuthorizationRequirement

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """
    Result of tool execution.
    
    Attributes:
        success: Whether execution was successful
        output: Output content (string representation)
        error: Error message if failed
        metadata: Additional metadata about the execution
    """
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def success_result(cls, output: str, **metadata: Any) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)
    
    @classmethod
    def error_result(cls, error: str, output: str = "", **metadata: Any) -> "ToolResult":
        """Create an error result."""
        return cls(success=False, output=output, error=error, metadata=metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class ToolBase(ABC):
    """
    Abstract base class for all tools.
    
    All tools must inherit from this class and implement:
    - _define_metadata(): Define tool metadata
    - execute(): Execute the tool
    
    Optional methods to override:
    - _do_initialize(): Custom initialization logic
    - cleanup(): Resource cleanup
    - execute_stream(): Streaming execution
    """
    
    def __init__(self, metadata: Optional[ToolMetadata] = None):
        """
        Initialize the tool.
        
        Args:
            metadata: Optional pre-defined metadata. If not provided,
                     _define_metadata() will be called.
        """
        self._metadata = metadata
        self._initialized = False
        self._execution_count = 0
    
    @property
    def metadata(self) -> ToolMetadata:
        """
        Get tool metadata (lazy initialization).
        
        Returns:
            ToolMetadata instance
        """
        if self._metadata is None:
            self._metadata = self._define_metadata()
        return self._metadata
    
    @property
    def name(self) -> str:
        """Get tool name."""
        return self.metadata.name
    
    @property
    def description(self) -> str:
        """Get tool description."""
        return self.metadata.description
    
    @property
    def category(self) -> ToolCategory:
        """Get tool category."""
        return ToolCategory(self.metadata.category)
    
    @abstractmethod
    def _define_metadata(self) -> ToolMetadata:
        """
        Define tool metadata (subclass must implement).
        
        Example:
            return ToolMetadata(
                id="bash",
                name="bash",
                description="Execute bash commands",
                category=ToolCategory.SHELL,
                parameters=[
                    ToolParameter(
                        name="command",
                        type="string",
                        description="The bash command to execute",
                        required=True,
                    ),
                ],
                authorization=AuthorizationRequirement(
                    requires_authorization=True,
                    risk_level=RiskLevel.HIGH,
                    risk_categories=[RiskCategory.SHELL_EXECUTE],
                ),
            )
        """
        pass
    
    async def initialize(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize the tool.
        
        Args:
            context: Initialization context
            
        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True
        
        try:
            await self._do_initialize(context)
            self._initialized = True
            logger.debug(f"[{self.name}] Initialized successfully")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Initialization failed: {e}")
            return False
    
    async def _do_initialize(self, context: Optional[Dict[str, Any]] = None):
        """
        Actual initialization logic (subclass can override).
        
        Args:
            context: Initialization context
        """
        pass
    
    async def cleanup(self):
        """
        Cleanup resources (subclass can override).
        """
        pass
    
    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Execute the tool (subclass must implement).
        
        Args:
            arguments: Tool arguments
            context: Execution context containing:
                - session_id: Session identifier
                - agent_name: Agent name
                - user_id: User identifier
                - workspace: Working directory
                - env: Environment variables
                - timeout: Execution timeout
                
        Returns:
            ToolResult with execution outcome
        """
        pass
    
    async def execute_safe(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Safe execution with parameter validation, timeout, and error handling.
        
        Args:
            arguments: Tool arguments
            context: Execution context
            
        Returns:
            ToolResult with execution outcome
        """
        # Parameter validation
        errors = self.metadata.validate_arguments(arguments)
        if errors:
            return ToolResult.error_result(
                error="Parameter validation failed: " + "; ".join(errors),
            )
        
        # Ensure initialization
        if not self._initialized:
            if not await self.initialize(context):
                return ToolResult.error_result(
                    error=f"Tool initialization failed",
                )
        
        # Get timeout
        timeout = self.metadata.timeout
        if context and "timeout" in context:
            timeout = context["timeout"]
        
        # Execute with timeout and error handling
        try:
            self._execution_count += 1
            
            if timeout and timeout > 0:
                result = await asyncio.wait_for(
                    self.execute(arguments, context),
                    timeout=timeout
                )
            else:
                result = await self.execute(arguments, context)
            
            return result
            
        except asyncio.TimeoutError:
            return ToolResult.error_result(
                error=f"Tool execution timed out after {timeout} seconds",
            )
        except Exception as e:
            logger.exception(f"[{self.name}] Execution error")
            return ToolResult.error_result(
                error=f"Tool execution error: {str(e)}",
            )
    
    async def execute_stream(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        Streaming execution (subclass can override).
        
        Yields output chunks as they become available.
        Default implementation calls execute() and yields the result.
        
        Args:
            arguments: Tool arguments
            context: Execution context
            
        Yields:
            Output chunks
        """
        result = await self.execute_safe(arguments, context)
        if result.success:
            yield result.output
        else:
            yield f"Error: {result.error}"
    
    def get_openai_spec(self) -> Dict[str, Any]:
        """Get OpenAI function calling specification."""
        return self.metadata.get_openai_spec()


class ToolRegistry:
    """
    Tool Registry - Singleton pattern.
    
    Manages tool registration, discovery, and execution.
    Provides indexing by category and tags for efficient lookup.
    """
    
    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, ToolBase]
    _categories: Dict[str, List[str]]
    _tags: Dict[str, List[str]]
    _initialized: bool
    
    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._categories = {}
            cls._instance._tags = {}
            cls._instance._initialized = False
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Get the singleton instance."""
        return cls()
    
    @classmethod
    def reset(cls):
        """Reset the registry (mainly for testing)."""
        if cls._instance is not None:
            cls._instance._tools.clear()
            cls._instance._categories.clear()
            cls._instance._tags.clear()
    
    def register(self, tool: ToolBase) -> "ToolRegistry":
        """
        Register a tool.
        
        Args:
            tool: Tool instance to register
            
        Returns:
            Self for chaining
        """
        name = tool.metadata.name
        
        if name in self._tools:
            logger.warning(f"[ToolRegistry] Tool '{name}' already exists, overwriting")
            self.unregister(name)
        
        self._tools[name] = tool
        
        # Index by category
        category = tool.metadata.category
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(name)
        
        # Index by tags
        for tag in tool.metadata.tags:
            if tag not in self._tags:
                self._tags[tag] = []
            self._tags[tag].append(name)
        
        logger.info(f"[ToolRegistry] Registered tool: {name} (category={category})")
        return self
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.
        
        Args:
            name: Tool name to unregister
            
        Returns:
            True if tool was unregistered
        """
        if name not in self._tools:
            return False
        
        tool = self._tools.pop(name)
        
        # Clean up category index
        category = tool.metadata.category
        if category in self._categories and name in self._categories[category]:
            self._categories[category].remove(name)
        
        # Clean up tag index
        for tag in tool.metadata.tags:
            if tag in self._tags and name in self._tags[tag]:
                self._tags[tag].remove(name)
        
        logger.info(f"[ToolRegistry] Unregistered tool: {name}")
        return True
    
    def get(self, name: str) -> Optional[ToolBase]:
        """
        Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool instance or None
        """
        return self._tools.get(name)
    
    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
    
    def list_all(self) -> List[ToolBase]:
        """
        List all registered tools.
        
        Returns:
            List of tool instances
        """
        return list(self._tools.values())
    
    def list_names(self) -> List[str]:
        """
        List all registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def list_by_category(self, category: str) -> List[ToolBase]:
        """
        List tools by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of matching tools
        """
        names = self._categories.get(category, [])
        return [self._tools[name] for name in names if name in self._tools]
    
    def list_by_tag(self, tag: str) -> List[ToolBase]:
        """
        List tools by tag.
        
        Args:
            tag: Tag to filter by
            
        Returns:
            List of matching tools
        """
        names = self._tags.get(tag, [])
        return [self._tools[name] for name in names if name in self._tools]
    
    def get_openai_tools(
        self,
        filter_func: Optional[Callable[[ToolBase], bool]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get OpenAI function calling specifications for all tools.
        
        Args:
            filter_func: Optional filter function
            
        Returns:
            List of OpenAI tool specifications
        """
        tools = []
        for tool in self._tools.values():
            if filter_func and not filter_func(tool):
                continue
            tools.append(tool.metadata.get_openai_spec())
        return tools
    
    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            context: Execution context
            
        Returns:
            Tool execution result
        """
        tool = self.get(name)
        if not tool:
            return ToolResult.error_result(f"Tool not found: {name}")
        
        return await tool.execute_safe(arguments, context)
    
    def get_metadata(self, name: str) -> Optional[ToolMetadata]:
        """
        Get tool metadata by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool metadata or None
        """
        tool = self.get(name)
        return tool.metadata if tool else None
    
    def count(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)
    
    def categories(self) -> List[str]:
        """Get list of categories with registered tools."""
        return [cat for cat, tools in self._categories.items() if tools]
    
    def tags(self) -> List[str]:
        """Get list of tags used by registered tools."""
        return [tag for tag, tools in self._tags.items() if tools]


# Global tool registry instance
tool_registry = ToolRegistry.get_instance()


def register_tool(tool: ToolBase) -> ToolBase:
    """
    Decorator/function to register a tool.
    
    Can be used as a decorator on a tool class or called directly.
    
    Example:
        @register_tool
        class MyTool(ToolBase):
            ...
            
        # Or directly:
        register_tool(MyTool())
    """
    if isinstance(tool, type):
        # Used as class decorator
        instance = tool()
        tool_registry.register(instance)
        return tool
    else:
        # Called with instance
        tool_registry.register(tool)
        return tool


T = TypeVar('T', bound=ToolBase)


def get_tool(name: str) -> Optional[ToolBase]:
    """Get a tool from the global registry."""
    return tool_registry.get(name)


def list_tools() -> List[str]:
    """List all registered tool names."""
    return tool_registry.list_names()


async def execute_tool(
    name: str,
    arguments: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Execute a tool from the global registry."""
    return await tool_registry.execute(name, arguments, context)
