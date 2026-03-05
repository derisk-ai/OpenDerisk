"""
Plan Agent - Unified Tool Authorization System

This module implements the Plan Agent:
- PlanAgent: Read-only agent for analysis and planning

The PlanAgent is restricted to read-only operations and is used for:
- Code analysis
- Planning and strategy
- Exploration without modification

Version: 2.0
"""

import logging
from typing import Dict, Any, Optional, AsyncIterator, List

from ..base import AgentBase, AgentState
from ..info import AgentInfo, AgentCapability, ToolSelectionPolicy, PLAN_AGENT_TEMPLATE
from ...tools.base import ToolRegistry, ToolResult, tool_registry
from ...authorization.engine import AuthorizationEngine, get_authorization_engine
from ...interaction.gateway import InteractionGateway, get_interaction_gateway

logger = logging.getLogger(__name__)


class PlanAgent(AgentBase):
    """
    Read-only planning agent.
    
    This agent is restricted to read-only operations:
    - Can read files, search, and analyze
    - Cannot write files, execute shell commands, or make modifications
    
    Use this agent for:
    - Initial analysis of a codebase
    - Planning complex tasks
    - Exploration without risk of modification
    
    Example:
        agent = PlanAgent()
        
        async for chunk in agent.run("Analyze this codebase structure"):
            print(chunk, end="")
    """
    
    # Read-only tools whitelist
    READ_ONLY_TOOLS = frozenset([
        "read", "read_file",
        "glob", "glob_search",
        "grep", "grep_search", "search",
        "list", "list_directory",
        "analyze", "analyze_code",
    ])
    
    # Forbidden tools blacklist
    FORBIDDEN_TOOLS = frozenset([
        "write", "write_file",
        "edit", "edit_file",
        "bash", "bash_execute", "shell",
        "delete", "remove",
        "move", "rename",
        "create",
    ])
    
    def __init__(
        self,
        info: Optional[AgentInfo] = None,
        tool_registry: Optional[ToolRegistry] = None,
        auth_engine: Optional[AuthorizationEngine] = None,
        interaction_gateway: Optional[InteractionGateway] = None,
        llm_call: Optional[Any] = None,
    ):
        """
        Initialize the plan agent.
        
        Args:
            info: Agent configuration (uses PLAN_AGENT_TEMPLATE if not provided)
            tool_registry: Tool registry
            auth_engine: Authorization engine
            interaction_gateway: Interaction gateway
            llm_call: LLM call function for reasoning
        """
        # Use template if no info provided
        if info is None:
            info = PLAN_AGENT_TEMPLATE.model_copy()
        
        # Ensure read-only policy is enforced
        if info.tool_policy is None:
            info.tool_policy = ToolSelectionPolicy(
                included_tools=list(self.READ_ONLY_TOOLS),
                excluded_tools=list(self.FORBIDDEN_TOOLS),
            )
        
        super().__init__(
            info=info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
        )
        
        self._llm_call = llm_call
        self._analysis_results: List[Dict[str, Any]] = []
    
    @property
    def analysis_results(self) -> List[Dict[str, Any]]:
        """Get collected analysis results."""
        return self._analysis_results.copy()
    
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """
        Thinking phase for planning.
        
        Analyzes the request and plans approach.
        
        Args:
            message: Analysis request
            **kwargs: Additional arguments
            
        Yields:
            Thinking output chunks
        """
        yield f"[Planning] Analyzing request: {message[:100]}...\n"
        yield "[Planning] Identifying relevant areas to explore...\n"
    
    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """
        Decision phase for planning.
        
        Decides what to analyze or explore next.
        
        Args:
            message: Current context
            **kwargs: Additional arguments
            
        Returns:
            Decision to read/analyze or respond
        """
        # If we have an LLM, use it for decisions
        if self._llm_call:
            try:
                messages = [
                    {"role": "system", "content": self._get_plan_system_prompt()},
                    {"role": "user", "content": message},
                ]
                tools = self.get_openai_tools()
                response = await self._llm_call(messages, tools, None)
                
                # Check for tool calls
                tool_calls = response.get("tool_calls", [])
                if tool_calls:
                    tc = tool_calls[0]
                    tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                    arguments = tc.get("arguments", {}) if isinstance(tc, dict) else getattr(tc, "arguments", {})
                    
                    # Verify tool is allowed
                    if tool_name in self.FORBIDDEN_TOOLS:
                        return {
                            "type": "error",
                            "error": f"Tool '{tool_name}' is not allowed for planning agent",
                        }
                    
                    return {
                        "type": "tool_call",
                        "tool": tool_name,
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    }
                
                # Direct response
                content = response.get("content", "")
                if content:
                    return {"type": "response", "content": content}
                
                return {"type": "complete"}
                
            except Exception as e:
                return {"type": "error", "error": str(e)}
        
        # Without LLM, just complete after initial analysis
        return {"type": "complete", "message": "Analysis planning complete"}
    
    async def act(self, action: Dict[str, Any], **kwargs) -> Any:
        """
        Action phase for planning.
        
        Executes read-only operations.
        
        Args:
            action: Decision from decide()
            **kwargs: Additional arguments
            
        Returns:
            Action result
        """
        action_type = action.get("type", "")
        
        if action_type == "tool_call":
            tool_name = action.get("tool", "")
            
            # Double-check tool is allowed
            if tool_name in self.FORBIDDEN_TOOLS:
                return ToolResult.error_result(f"Tool '{tool_name}' is forbidden for planning agent")
            
            arguments = action.get("arguments", {})
            result = await self.execute_tool(tool_name, arguments)
            
            # Store analysis results
            if result.success:
                self._analysis_results.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "output": result.output[:1000],  # Truncate for storage
                })
            
            return result
        
        return action.get("content", action.get("message", ""))
    
    def _get_plan_system_prompt(self) -> str:
        """Get system prompt for planning."""
        return """You are a planning and analysis agent.

Your role is to:
- Analyze code and project structure
- Create plans for complex tasks
- Explore and understand codebases

IMPORTANT: You can ONLY use read-only tools:
- read_file / read - Read file contents
- glob / glob_search - Find files by pattern
- grep / grep_search - Search file contents
- analyze_code - Analyze code structure

You CANNOT use any modification tools (write, edit, bash, shell, etc.)

When analyzing:
1. Start by understanding the project structure
2. Read relevant files
3. Summarize your findings
4. Provide actionable recommendations
"""
    
    def reset(self) -> None:
        """Reset agent state."""
        super().reset()
        self._analysis_results.clear()


def create_plan_agent(
    name: str = "planner",
    llm_call: Optional[Any] = None,
    **kwargs,
) -> PlanAgent:
    """
    Factory function to create a PlanAgent.
    
    Args:
        name: Agent name
        llm_call: LLM call function
        **kwargs: Additional arguments
        
    Returns:
        Configured PlanAgent
    """
    info = AgentInfo(
        name=name,
        description="Read-only planning and analysis agent",
        capabilities=[
            AgentCapability.CODE_ANALYSIS,
            AgentCapability.PLANNING,
            AgentCapability.REASONING,
        ],
        tool_policy=ToolSelectionPolicy(
            included_tools=list(PlanAgent.READ_ONLY_TOOLS),
            excluded_tools=list(PlanAgent.FORBIDDEN_TOOLS),
        ),
        authorization={
            "mode": "strict",
            "whitelist_tools": list(PlanAgent.READ_ONLY_TOOLS),
            "blacklist_tools": list(PlanAgent.FORBIDDEN_TOOLS),
        },
        max_steps=50,
        timeout=1800,
    )
    
    return PlanAgent(
        info=info,
        llm_call=llm_call,
        **kwargs,
    )
