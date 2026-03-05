"""Agent Decorators for simplified agent definition.

Provides a cleaner, more intuitive way to define agents using decorators,
similar to FastAPI route decorators or Flask route handlers.
"""

import asyncio
import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, Union, get_type_hints

from .enhanced_agent import (
    AgentBase,
    AgentInfo,
    AgentState,
    AgentMessage,
    Decision,
    DecisionType,
    ActionResult,
    ToolRegistry,
    PermissionChecker,
)


@dataclass
class AgentDefinition:
    """Agent definition collected from decorator."""
    name: str
    description: str
    role: str = "assistant"
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    model: str = "inherit"
    max_steps: int = 10
    timeout: int = 300
    permission_ruleset: Optional[Dict[str, Any]] = None
    memory_enabled: bool = True
    memory_scope: str = "session"
    subagents: List[str] = field(default_factory=list)
    can_spawn_team: bool = False
    team_role: str = "worker"
    handler: Optional[Callable] = None
    think_handler: Optional[Callable] = None
    decide_handler: Optional[Callable] = None
    act_handler: Optional[Callable] = None


def agent(
    name: Optional[str] = None,
    description: Optional[str] = None,
    role: str = "assistant",
    tools: Optional[List[str]] = None,
    skills: Optional[List[str]] = None,
    model: str = "inherit",
    max_steps: int = 10,
    timeout: int = 300,
    permission: Optional[Dict[str, Any]] = None,
    memory_enabled: bool = True,
    memory_scope: str = "session",
    subagents: Optional[List[str]] = None,
    can_spawn_team: bool = False,
    team_role: str = "worker",
):
    """Decorator for defining an agent.
    
    Can be used in multiple ways:
    
    1. As a simple decorator:
        @agent(name="my_agent", description="My agent")
        async def my_handler(message: str) -> str:
            return "Response"
    
    2. As a class decorator with method handlers:
        @agent(name="my_agent", description="My agent")
        class MyAgent:
            @think
            async def think(self, message: str) -> AsyncIterator[str]:
                yield "thinking..."
            
            @decide
            async def decide(self, context: dict) -> Decision:
                return Decision(type=DecisionType.RESPONSE, content="Done")
            
            @act
            async def act(self, decision: Decision) -> ActionResult:
                return ActionResult(success=True, output="Done")
    
    3. As a method decorator within a class:
        class MyAgent(AgentBase):
            @agent.method(name="custom_action", tools=["read_file"])
            async def custom_action(self, message: str) -> str:
                return "Result"
    
    Args:
        name: Agent name (defaults to function/class name)
        description: Agent description (defaults to docstring)
        role: Agent role
        tools: List of tool names
        skills: List of skill names
        model: Model to use (inherit, sonnet, opus, haiku)
        max_steps: Maximum execution steps
        timeout: Execution timeout in seconds
        permission: Permission ruleset configuration
        memory_enabled: Whether to enable memory
        memory_scope: Memory scope (session, project, user)
        subagents: List of subagent names this agent can delegate to
        can_spawn_team: Whether this agent can spawn a team
        team_role: Role within a team
    
    Returns:
        Decorated agent class or function
    """
    def decorator(func_or_class):
        if inspect.isclass(func_or_class):
            return _decorate_class(
                func_or_class,
                name=name,
                description=description,
                role=role,
                tools=tools or [],
                skills=skills or [],
                model=model,
                max_steps=max_steps,
                timeout=timeout,
                permission=permission,
                memory_enabled=memory_enabled,
                memory_scope=memory_scope,
                subagents=subagents or [],
                can_spawn_team=can_spawn_team,
                team_role=team_role,
            )
        elif inspect.iscoroutinefunction(func_or_class) or inspect.isfunction(func_or_class):
            return _decorate_function(
                func_or_class,
                name=name,
                description=description,
                role=role,
                tools=tools or [],
                skills=skills or [],
                model=model,
                max_steps=max_steps,
                timeout=timeout,
                permission=permission,
                memory_enabled=memory_enabled,
                memory_scope=memory_scope,
                subagents=subagents or [],
                can_spawn_team=can_spawn_team,
                team_role=team_role,
            )
        else:
            raise ValueError(f"Cannot decorate {type(func_or_class)}")
    
    return decorator


def _decorate_class(
    cls: Type,
    name: Optional[str],
    description: Optional[str],
    **kwargs,
) -> Type[AgentBase]:
    """Decorate a class to create an agent."""
    
    agent_name = name or cls.__name__
    agent_description = description or cls.__doc__ or f"Agent {agent_name}"
    
    think_handler = getattr(cls, '_agent_think', None)
    decide_handler = getattr(cls, '_agent_decide', None)
    act_handler = getattr(cls, '_agent_act', None)
    
    class DecoratedAgent(AgentBase):
        def __init__(self, **init_kwargs):
            info = AgentInfo(
                name=agent_name,
                description=agent_description,
                role=kwargs.get('role', 'assistant'),
                tools=kwargs.get('tools', []),
                skills=kwargs.get('skills', []),
                model=kwargs.get('model', 'inherit'),
                max_steps=kwargs.get('max_steps', 10),
                timeout=kwargs.get('timeout', 300),
                permission_ruleset=kwargs.get('permission'),
                memory_enabled=kwargs.get('memory_enabled', True),
                memory_scope=kwargs.get('memory_scope', 'session'),
                subagents=kwargs.get('subagents', []),
                can_spawn_team=kwargs.get('can_spawn_team', False),
                team_role=kwargs.get('team_role', 'worker'),
            )
            super().__init__(info=info, **init_kwargs)
            self._think_impl = think_handler
            self._decide_impl = decide_handler
            self._act_impl = act_handler
        
        async def think(self, message: str, **kw):
            if self._think_impl:
                async for chunk in self._think_impl(self, message, **kw):
                    yield chunk
            else:
                yield ""
        
        async def decide(self, context: Dict[str, Any], **kw) -> Decision:
            if self._decide_impl:
                return await self._decide_impl(self, context, **kw)
            return Decision(type=DecisionType.RESPONSE, content=context.get("thinking", ""))
        
        async def act(self, decision: Decision, **kw) -> ActionResult:
            if self._act_impl:
                return await self._act_impl(self, decision, **kw)
            return await super().act(decision, **kw)
    
    DecoratedAgent.__name__ = agent_name
    DecoratedAgent.__qualname__ = agent_name
    DecoratedAgent.__doc__ = agent_description
    
    for attr_name, attr_value in cls.__dict__.items():
        if not attr_name.startswith('_') and not hasattr(DecoratedAgent, attr_name):
            setattr(DecoratedAgent, attr_name, attr_value)
    
    return DecoratedAgent


def _decorate_function(
    func: Callable,
    name: Optional[str],
    description: Optional[str],
    **kwargs,
) -> Type[AgentBase]:
    """Decorate a function to create an agent."""
    
    agent_name = name or func.__name__
    agent_description = description or func.__doc__ or f"Agent {agent_name}"
    
    class FunctionAgent(AgentBase):
        def __init__(self, **init_kwargs):
            info = AgentInfo(
                name=agent_name,
                description=agent_description,
                role=kwargs.get('role', 'assistant'),
                tools=kwargs.get('tools', []),
                skills=kwargs.get('skills', []),
                model=kwargs.get('model', 'inherit'),
                max_steps=kwargs.get('max_steps', 10),
                timeout=kwargs.get('timeout', 300),
                permission_ruleset=kwargs.get('permission'),
                memory_enabled=kwargs.get('memory_enabled', True),
                memory_scope=kwargs.get('memory_scope', 'session'),
                subagents=kwargs.get('subagents', []),
                can_spawn_team=kwargs.get('can_spawn_team', False),
                team_role=kwargs.get('team_role', 'worker'),
            )
            super().__init__(info=info, **init_kwargs)
            self._handler = func
        
        async def think(self, message: str, **kw):
            yield ""
        
        async def decide(self, context: Dict[str, Any], **kw) -> Decision:
            message = context.get("message", "")
            
            if kwargs.get('tools'):
                return Decision(
                    type=DecisionType.TOOL_CALL,
                    tool_name=kwargs['tools'][0],
                    tool_args={"query": message},
                )
            
            return Decision(type=DecisionType.RESPONSE, content=message)
        
        async def act(self, decision: Decision, **kw) -> ActionResult:
            if decision.type == DecisionType.TOOL_CALL:
                return await super().act(decision, **kw)
            
            if self._handler:
                try:
                    if inspect.iscoroutinefunction(self._handler):
                        result = await self._handler(decision.content or "")
                    else:
                        result = self._handler(decision.content or "")
                    
                    return ActionResult(success=True, output=str(result))
                except Exception as e:
                    return ActionResult(success=False, output="", error=str(e))
            
            return ActionResult(success=True, output=decision.content or "")
    
    FunctionAgent.__name__ = agent_name
    FunctionAgent.__qualname__ = agent_name
    FunctionAgent.__doc__ = agent_description
    
    return FunctionAgent


def think(func: Callable) -> Callable:
    """Decorator for marking the think method.
    
    Usage:
        @agent(name="my_agent", description="My agent")
        class MyAgent:
            @think
            async def think(self, message: str) -> AsyncIterator[str]:
                yield "thinking..."
    """
    func._agent_think = True
    return func


def decide(func: Callable) -> Callable:
    """Decorator for marking the decide method.
    
    Usage:
        @agent(name="my_agent", description="My agent")
        class MyAgent:
            @decide
            async def decide(self, context: dict) -> Decision:
                return Decision(type=DecisionType.RESPONSE, content="Done")
    """
    func._agent_decide = True
    return func


def act(func: Callable) -> Callable:
    """Decorator for marking the act method.
    
    Usage:
        @agent(name="my_agent", description="My agent")
        class MyAgent:
            @act
            async def act(self, decision: Decision) -> ActionResult:
                return ActionResult(success=True, output="Done")
    """
    func._agent_act = True
    return func


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    requires_permission: bool = True,
):
    """Decorator for defining a tool function.
    
    Usage:
        @tool(name="read_file", description="Read a file")
        async def read_file(path: str, limit: int = 100) -> str:
            with open(path) as f:
                return f.read(limit)
    
    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to docstring)
        parameters: JSON schema for parameters
        requires_permission: Whether this tool requires permission
    """
    def decorator(func: Callable) -> Callable:
        func._tool_metadata = {
            'name': name or func.__name__,
            'description': description or func.__doc__ or f"Tool {name or func.__name__}",
            'parameters': parameters or _infer_parameters(func),
            'requires_permission': requires_permission,
        }
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)
        
        wrapper._tool_metadata = func._tool_metadata
        return wrapper
    
    return decorator


def _infer_parameters(func: Callable) -> Dict[str, Any]:
    """Infer parameter schema from function signature."""
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        if param_name == 'self':
            continue
        
        param_type = hints.get(param_name, str)
        param_desc = f"Parameter {param_name}"
        
        if hasattr(param.annotation, '__metadata__'):
            param_desc = param.annotation.__metadata__[0]
        
        type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        
        json_type = type_mapping.get(param_type, "string")
        
        properties[param_name] = {
            "type": json_type,
            "description": param_desc,
        }
        
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class AgentRegistry:
    """Registry for agents defined via decorators."""
    
    _instance = None
    _agents: Dict[str, Type[AgentBase]] = {}
    _tools: Dict[str, Callable] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register_agent(cls, agent_class: Type[AgentBase]) -> None:
        """Register an agent class."""
        instance = cls()
        instance._agents[agent_class.__name__] = agent_class
    
    @classmethod
    def register_tool(cls, func: Callable) -> None:
        """Register a tool function."""
        instance = cls()
        metadata = getattr(func, '_tool_metadata', {})
        tool_name = metadata.get('name', func.__name__)
        instance._tools[tool_name] = func
    
    @classmethod
    def get_agent(cls, name: str) -> Optional[Type[AgentBase]]:
        """Get an agent class by name."""
        instance = cls()
        return instance._agents.get(name)
    
    @classmethod
    def get_tool(cls, name: str) -> Optional[Callable]:
        """Get a tool function by name."""
        instance = cls()
        return instance._tools.get(name)
    
    @classmethod
    def list_agents(cls) -> List[str]:
        """List all registered agent names."""
        instance = cls()
        return list(instance._agents.keys())
    
    @classmethod
    def list_tools(cls) -> List[str]:
        """List all registered tool names."""
        instance = cls()
        return list(instance._tools.keys())
    
    @classmethod
    def create_agent(
        cls,
        name: str,
        llm_client=None,
        memory=None,
        **kwargs,
    ) -> Optional[AgentBase]:
        """Create an agent instance by name."""
        agent_class = cls.get_agent(name)
        if agent_class:
            return agent_class(
                llm_client=llm_client,
                memory=memory,
                **kwargs,
            )
        return None


def register_all_decorated():
    """Register all decorated agents and tools.
    
    Call this after defining agents to make them available via AgentRegistry.
    """
    import sys
    
    for module_name, module in sys.modules.items():
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            
            if isinstance(attr, type) and issubclass(attr, AgentBase):
                if hasattr(attr, '__name__'):
                    AgentRegistry.register_agent(attr)
            
            if hasattr(attr, '_tool_metadata'):
                AgentRegistry.register_tool(attr)


# Convenience exports
__all__ = [
    'agent',
    'think',
    'decide',
    'act',
    'tool',
    'AgentRegistry',
    'register_all_decorated',
    'AgentDefinition',
]