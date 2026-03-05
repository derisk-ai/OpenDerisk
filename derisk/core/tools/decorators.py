"""
Tool Decorators - Unified Tool Authorization System

This module provides decorators for quick tool definition:
- @tool: Main decorator for creating tools
- @shell_tool: Shell command tool decorator
- @file_read_tool: File read tool decorator
- @file_write_tool: File write tool decorator

Version: 2.0
"""

from typing import Callable, Optional, Dict, Any, List, Union
from functools import wraps
import asyncio
import inspect

from .base import ToolBase, ToolResult, tool_registry
from .metadata import (
    ToolMetadata,
    ToolParameter,
    ToolCategory,
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)


def tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.CUSTOM,
    parameters: Optional[List[ToolParameter]] = None,
    *,
    authorization: Optional[AuthorizationRequirement] = None,
    timeout: int = 60,
    tags: Optional[List[str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    auto_register: bool = True,
):
    """
    Decorator for creating tools from functions.
    
    The decorated function should accept keyword arguments matching
    the defined parameters, plus an optional 'context' parameter.
    
    Args:
        name: Tool name (unique identifier)
        description: Tool description
        category: Tool category
        parameters: List of parameter definitions
        authorization: Authorization requirements
        timeout: Execution timeout in seconds
        tags: Tool tags for filtering
        examples: Usage examples
        metadata: Additional metadata
        auto_register: Whether to auto-register the tool
        
    Returns:
        Decorated function wrapped as a tool
        
    Example:
        @tool(
            name="read_file",
            description="Read file content",
            category=ToolCategory.FILE_SYSTEM,
            parameters=[
                ToolParameter(name="path", type="string", description="File path"),
            ],
            authorization=AuthorizationRequirement(
                requires_authorization=False,
                risk_level=RiskLevel.SAFE,
            ),
        )
        async def read_file(path: str, context: dict = None) -> str:
            with open(path) as f:
                return f.read()
    """
    def decorator(func: Callable) -> ToolBase:
        # Build metadata
        tool_metadata = ToolMetadata(
            id=name,
            name=name,
            description=description,
            category=category,
            parameters=parameters or [],
            authorization=authorization or AuthorizationRequirement(),
            timeout=timeout,
            tags=tags or [],
            examples=examples or [],
            metadata=metadata or {},
        )
        
        # Create tool class
        class FunctionTool(ToolBase):
            """Tool created from function."""
            
            def __init__(self):
                super().__init__(tool_metadata)
                self._func = func
            
            def _define_metadata(self) -> ToolMetadata:
                return tool_metadata
            
            async def execute(
                self,
                arguments: Dict[str, Any],
                context: Optional[Dict[str, Any]] = None,
            ) -> ToolResult:
                try:
                    # Prepare arguments
                    kwargs = dict(arguments)
                    
                    # Add context if function accepts it
                    sig = inspect.signature(self._func)
                    if 'context' in sig.parameters:
                        kwargs['context'] = context
                    
                    # Execute function
                    if asyncio.iscoroutinefunction(self._func):
                        result = await self._func(**kwargs)
                    else:
                        result = self._func(**kwargs)
                    
                    # Wrap result
                    if isinstance(result, ToolResult):
                        return result
                    
                    return ToolResult.success_result(
                        str(result) if result is not None else "",
                    )
                    
                except Exception as e:
                    return ToolResult.error_result(str(e))
        
        # Create instance
        tool_instance = FunctionTool()
        
        # Auto-register
        if auto_register:
            tool_registry.register(tool_instance)
        
        # Preserve original function reference
        tool_instance._original_func = func
        
        return tool_instance
    
    return decorator


def shell_tool(
    name: str,
    description: str,
    dangerous: bool = False,
    parameters: Optional[List[ToolParameter]] = None,
    **kwargs,
):
    """
    Decorator for shell command tools.
    
    Automatically sets:
    - Category: SHELL
    - Authorization: requires_authorization=True
    - Risk level: HIGH if dangerous, MEDIUM otherwise
    - Risk categories: [SHELL_EXECUTE]
    
    Args:
        name: Tool name
        description: Tool description
        dangerous: Whether this is a dangerous operation
        parameters: Additional parameters
        **kwargs: Additional arguments for @tool
        
    Example:
        @shell_tool(
            name="run_tests",
            description="Run project tests",
        )
        async def run_tests(context: dict = None) -> str:
            # Execute tests
            ...
    """
    auth = AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.HIGH if dangerous else RiskLevel.MEDIUM,
        risk_categories=[RiskCategory.SHELL_EXECUTE],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.SHELL,
        parameters=parameters,
        authorization=auth,
        **kwargs,
    )


def file_read_tool(
    name: str,
    description: str,
    parameters: Optional[List[ToolParameter]] = None,
    **kwargs,
):
    """
    Decorator for file read tools.
    
    Automatically sets:
    - Category: FILE_SYSTEM
    - Authorization: requires_authorization=False
    - Risk level: SAFE
    - Risk categories: [READ_ONLY]
    
    Args:
        name: Tool name
        description: Tool description
        parameters: Additional parameters
        **kwargs: Additional arguments for @tool
        
    Example:
        @file_read_tool(
            name="read_config",
            description="Read configuration file",
        )
        async def read_config(path: str) -> str:
            ...
    """
    auth = AuthorizationRequirement(
        requires_authorization=False,
        risk_level=RiskLevel.SAFE,
        risk_categories=[RiskCategory.READ_ONLY],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.FILE_SYSTEM,
        parameters=parameters,
        authorization=auth,
        **kwargs,
    )


def file_write_tool(
    name: str,
    description: str,
    dangerous: bool = False,
    parameters: Optional[List[ToolParameter]] = None,
    **kwargs,
):
    """
    Decorator for file write tools.
    
    Automatically sets:
    - Category: FILE_SYSTEM
    - Authorization: requires_authorization=True
    - Risk level: HIGH if dangerous, MEDIUM otherwise
    - Risk categories: [FILE_WRITE]
    
    Args:
        name: Tool name
        description: Tool description
        dangerous: Whether this is a dangerous operation
        parameters: Additional parameters
        **kwargs: Additional arguments for @tool
        
    Example:
        @file_write_tool(
            name="write_file",
            description="Write content to file",
        )
        async def write_file(path: str, content: str) -> str:
            ...
    """
    auth = AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.HIGH if dangerous else RiskLevel.MEDIUM,
        risk_categories=[RiskCategory.FILE_WRITE],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.FILE_SYSTEM,
        parameters=parameters,
        authorization=auth,
        **kwargs,
    )


def network_tool(
    name: str,
    description: str,
    dangerous: bool = False,
    parameters: Optional[List[ToolParameter]] = None,
    **kwargs,
):
    """
    Decorator for network tools.
    
    Automatically sets:
    - Category: NETWORK
    - Authorization: requires_authorization=True
    - Risk level: MEDIUM (HIGH if dangerous)
    - Risk categories: [NETWORK_OUTBOUND]
    
    Args:
        name: Tool name
        description: Tool description
        dangerous: Whether this is a dangerous operation
        parameters: Additional parameters
        **kwargs: Additional arguments for @tool
    """
    auth = AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.HIGH if dangerous else RiskLevel.LOW,
        risk_categories=[RiskCategory.NETWORK_OUTBOUND],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.NETWORK,
        parameters=parameters,
        authorization=auth,
        **kwargs,
    )


def data_tool(
    name: str,
    description: str,
    read_only: bool = True,
    parameters: Optional[List[ToolParameter]] = None,
    **kwargs,
):
    """
    Decorator for data processing tools.
    
    Automatically sets:
    - Category: DATA
    - Authorization: based on read_only flag
    - Risk level: SAFE if read_only, MEDIUM otherwise
    - Risk categories: [READ_ONLY] or [DATA_MODIFY]
    
    Args:
        name: Tool name
        description: Tool description
        read_only: Whether this is read-only
        parameters: Additional parameters
        **kwargs: Additional arguments for @tool
    """
    if read_only:
        auth = AuthorizationRequirement(
            requires_authorization=False,
            risk_level=RiskLevel.SAFE,
            risk_categories=[RiskCategory.READ_ONLY],
        )
    else:
        auth = AuthorizationRequirement(
            requires_authorization=True,
            risk_level=RiskLevel.MEDIUM,
            risk_categories=[RiskCategory.DATA_MODIFY],
        )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.DATA,
        parameters=parameters,
        authorization=auth,
        **kwargs,
    )


def agent_tool(
    name: str,
    description: str,
    parameters: Optional[List[ToolParameter]] = None,
    **kwargs,
):
    """
    Decorator for agent collaboration tools.
    
    Automatically sets:
    - Category: AGENT
    - Authorization: requires_authorization=False (internal)
    - Risk level: LOW
    
    Args:
        name: Tool name
        description: Tool description
        parameters: Additional parameters
        **kwargs: Additional arguments for @tool
    """
    auth = AuthorizationRequirement(
        requires_authorization=False,
        risk_level=RiskLevel.LOW,
        risk_categories=[],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.AGENT,
        parameters=parameters,
        authorization=auth,
        **kwargs,
    )


def interaction_tool(
    name: str,
    description: str,
    parameters: Optional[List[ToolParameter]] = None,
    **kwargs,
):
    """
    Decorator for user interaction tools.
    
    Automatically sets:
    - Category: INTERACTION
    - Authorization: requires_authorization=False (user-initiated)
    - Risk level: SAFE
    
    Args:
        name: Tool name
        description: Tool description
        parameters: Additional parameters
        **kwargs: Additional arguments for @tool
    """
    auth = AuthorizationRequirement(
        requires_authorization=False,
        risk_level=RiskLevel.SAFE,
        risk_categories=[],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.INTERACTION,
        parameters=parameters,
        authorization=auth,
        **kwargs,
    )
