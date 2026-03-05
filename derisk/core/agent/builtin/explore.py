"""
Explore Subagent - Unified Tool Authorization System

This module implements the Explore Subagent:
- ExploreSubagent: Focused exploration agent for codebase analysis

The ExploreSubagent is designed for:
- Quick, focused exploration tasks
- Finding specific code patterns
- Answering "where is X?" questions

Version: 2.0
"""

import logging
from typing import Dict, Any, Optional, AsyncIterator, List

from ..base import AgentBase, AgentState
from ..info import AgentInfo, AgentMode, AgentCapability, ToolSelectionPolicy, EXPLORE_AGENT_TEMPLATE
from ...tools.base import ToolRegistry, ToolResult, tool_registry
from ...authorization.engine import AuthorizationEngine, get_authorization_engine
from ...interaction.gateway import InteractionGateway, get_interaction_gateway

logger = logging.getLogger(__name__)


class ExploreSubagent(AgentBase):
    """
    Focused exploration subagent.
    
    This agent is optimized for quick, targeted exploration:
    - Find specific files or patterns
    - Answer "where is X?" questions
    - Explore codebase structure
    
    It's designed to be spawned as a subagent for parallel exploration tasks.
    
    Example:
        agent = ExploreSubagent()
        
        async for chunk in agent.run("Find all files that define authentication"):
            print(chunk, end="")
    """
    
    # Exploration tools
    EXPLORATION_TOOLS = frozenset([
        "read", "read_file",
        "glob", "glob_search",
        "grep", "grep_search", "search",
        "list", "list_directory",
    ])
    
    def __init__(
        self,
        info: Optional[AgentInfo] = None,
        tool_registry: Optional[ToolRegistry] = None,
        auth_engine: Optional[AuthorizationEngine] = None,
        interaction_gateway: Optional[InteractionGateway] = None,
        llm_call: Optional[Any] = None,
        thoroughness: str = "medium",
    ):
        """
        Initialize the explore subagent.
        
        Args:
            info: Agent configuration
            tool_registry: Tool registry
            auth_engine: Authorization engine
            interaction_gateway: Interaction gateway
            llm_call: LLM call function
            thoroughness: Exploration depth ("quick", "medium", "very thorough")
        """
        if info is None:
            info = EXPLORE_AGENT_TEMPLATE.model_copy()
        
        # Ensure exploration-only tools
        if info.tool_policy is None:
            info.tool_policy = ToolSelectionPolicy(
                included_tools=list(self.EXPLORATION_TOOLS),
            )
        
        # Adjust max steps based on thoroughness
        if thoroughness == "quick":
            info.max_steps = 10
            info.timeout = 300
        elif thoroughness == "very thorough":
            info.max_steps = 50
            info.timeout = 1200
        else:  # medium
            info.max_steps = 20
            info.timeout = 600
        
        super().__init__(
            info=info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
        )
        
        self._llm_call = llm_call
        self._thoroughness = thoroughness
        self._findings: List[Dict[str, Any]] = []
    
    @property
    def findings(self) -> List[Dict[str, Any]]:
        """Get exploration findings."""
        return self._findings.copy()
    
    @property
    def thoroughness(self) -> str:
        """Get thoroughness level."""
        return self._thoroughness
    
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """
        Thinking phase for exploration.
        
        Determines search strategy.
        
        Args:
            message: Exploration query
            **kwargs: Additional arguments
            
        Yields:
            Thinking output
        """
        yield f"[Explore] Query: {message[:100]}\n"
        yield f"[Explore] Thoroughness: {self._thoroughness}\n"
        yield "[Explore] Determining search strategy...\n"
    
    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """
        Decision phase for exploration.
        
        Decides what to search for next.
        
        Args:
            message: Current context
            **kwargs: Additional arguments
            
        Returns:
            Search action or response
        """
        # If we have findings and this is not the first step, summarize
        if self._current_step > 1 and self._findings:
            summary = self._summarize_findings()
            return {"type": "response", "content": summary}
        
        # If we have an LLM, use it to decide search strategy
        if self._llm_call:
            try:
                messages = [
                    {"role": "system", "content": self._get_explore_system_prompt()},
                    {"role": "user", "content": message},
                ]
                tools = self.get_openai_tools()
                response = await self._llm_call(messages, tools, None)
                
                tool_calls = response.get("tool_calls", [])
                if tool_calls:
                    tc = tool_calls[0]
                    tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                    arguments = tc.get("arguments", {}) if isinstance(tc, dict) else getattr(tc, "arguments", {})
                    
                    return {
                        "type": "tool_call",
                        "tool": tool_name,
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    }
                
                content = response.get("content", "")
                if content:
                    return {"type": "response", "content": content}
                    
            except Exception as e:
                logger.warning(f"[ExploreSubagent] LLM call failed: {e}")
        
        # Default behavior: try grep with the query
        return {
            "type": "tool_call",
            "tool": "grep",
            "arguments": {
                "pattern": self._extract_search_pattern(message),
                "path": ".",
            },
        }
    
    async def act(self, action: Dict[str, Any], **kwargs) -> Any:
        """
        Action phase for exploration.
        
        Executes search operations.
        
        Args:
            action: Decision from decide()
            **kwargs: Additional arguments
            
        Returns:
            Action result
        """
        action_type = action.get("type", "")
        
        if action_type == "tool_call":
            tool_name = action.get("tool", "")
            arguments = action.get("arguments", {})
            
            result = await self.execute_tool(tool_name, arguments)
            
            # Store findings
            if result.success and result.output:
                self._findings.append({
                    "tool": tool_name,
                    "query": arguments,
                    "result": result.output[:2000],
                    "step": self._current_step,
                })
            
            return result
        
        return action.get("content", "")
    
    def _extract_search_pattern(self, message: str) -> str:
        """Extract a search pattern from natural language query."""
        # Simple extraction - in production, LLM would do this better
        keywords = ["find", "search", "where", "locate", "look for"]
        
        lower_msg = message.lower()
        for keyword in keywords:
            if keyword in lower_msg:
                idx = lower_msg.index(keyword)
                remainder = message[idx + len(keyword):].strip()
                # Take first few words as pattern
                words = remainder.split()[:5]
                if words:
                    return " ".join(words)
        
        # Fall back to first significant words
        words = [w for w in message.split() if len(w) > 3][:3]
        return " ".join(words) if words else message[:50]
    
    def _summarize_findings(self) -> str:
        """Summarize exploration findings."""
        if not self._findings:
            return "No findings from exploration."
        
        summary_parts = [f"## Exploration Findings ({len(self._findings)} results)\n"]
        
        for i, finding in enumerate(self._findings[:10], 1):
            tool = finding.get("tool", "unknown")
            result = finding.get("result", "")[:500]
            summary_parts.append(f"\n### Finding {i} ({tool})\n```\n{result}\n```\n")
        
        if len(self._findings) > 10:
            summary_parts.append(f"\n... and {len(self._findings) - 10} more findings\n")
        
        return "\n".join(summary_parts)
    
    def _get_explore_system_prompt(self) -> str:
        """Get system prompt for exploration."""
        return f"""You are an exploration subagent.

Your task is to find specific code, files, or patterns in a codebase.
Thoroughness level: {self._thoroughness}

Available tools:
- glob / glob_search - Find files by pattern (e.g., "**/*.py")
- grep / grep_search - Search file contents
- read / read_file - Read file contents
- list - List directory contents

Strategy:
1. First use glob to find relevant files
2. Then use grep to search within those files
3. Read specific files for details

Be efficient and focused. Return findings quickly.
"""
    
    def reset(self) -> None:
        """Reset agent state."""
        super().reset()
        self._findings.clear()


class CodeSubagent(ExploreSubagent):
    """
    Code-focused subagent.
    
    Specialized for code analysis and understanding.
    Inherits from ExploreSubagent with additional code analysis capabilities.
    """
    
    # Additional code analysis tools
    CODE_TOOLS = frozenset([
        "read", "read_file",
        "glob", "glob_search",
        "grep", "grep_search",
        "analyze", "analyze_code",
    ])
    
    def __init__(
        self,
        info: Optional[AgentInfo] = None,
        **kwargs,
    ):
        if info is None:
            info = AgentInfo(
                name="code-subagent",
                description="Code analysis subagent",
                mode=AgentMode.SUBAGENT,
                capabilities=[
                    AgentCapability.CODE_ANALYSIS,
                    AgentCapability.REASONING,
                ],
                tool_policy=ToolSelectionPolicy(
                    included_tools=list(self.CODE_TOOLS),
                ),
                max_steps=30,
                timeout=900,
            )
        
        super().__init__(info=info, **kwargs)


def create_explore_subagent(
    name: str = "explorer",
    thoroughness: str = "medium",
    llm_call: Optional[Any] = None,
    **kwargs,
) -> ExploreSubagent:
    """
    Factory function to create an ExploreSubagent.
    
    Args:
        name: Agent name
        thoroughness: Exploration depth ("quick", "medium", "very thorough")
        llm_call: LLM call function
        **kwargs: Additional arguments
        
    Returns:
        Configured ExploreSubagent
    """
    info = AgentInfo(
        name=name,
        description=f"Exploration subagent ({thoroughness})",
        mode=AgentMode.SUBAGENT,
        capabilities=[
            AgentCapability.CODE_ANALYSIS,
            AgentCapability.REASONING,
        ],
        tool_policy=ToolSelectionPolicy(
            included_tools=list(ExploreSubagent.EXPLORATION_TOOLS),
        ),
        authorization={
            "mode": "permissive",
            "whitelist_tools": list(ExploreSubagent.EXPLORATION_TOOLS),
        },
    )
    
    return ExploreSubagent(
        info=info,
        thoroughness=thoroughness,
        llm_call=llm_call,
        **kwargs,
    )
