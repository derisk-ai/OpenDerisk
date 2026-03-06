"""
Production Agent - Unified Tool Authorization System

This module implements the production-ready agent:
- ProductionAgent: Full-featured agent with LLM integration

The ProductionAgent implements the Think-Decide-Act loop with:
- LLM-based reasoning and decision making
- Tool selection and execution
- Streaming output support
- Memory management

Version: 2.0
"""

import json
import logging
from typing import Dict, Any, Optional, AsyncIterator, List, Callable, Awaitable

from .base import AgentBase, AgentState
from .info import AgentInfo, AgentCapability, PRIMARY_AGENT_TEMPLATE
from ..tools.base import ToolRegistry, ToolResult, tool_registry
from ..tools.metadata import ToolMetadata
from ..authorization.engine import AuthorizationEngine, get_authorization_engine
from ..interaction.gateway import InteractionGateway, get_interaction_gateway

logger = logging.getLogger(__name__)


# Type alias for LLM call function
LLMCallFunc = Callable[
    [List[Dict[str, Any]], List[Dict[str, Any]], Optional[Dict[str, Any]]],
    Awaitable[Dict[str, Any]]
]

# Type alias for streaming LLM call function
LLMStreamFunc = Callable[
    [List[Dict[str, Any]], List[Dict[str, Any]], Optional[Dict[str, Any]]],
    AsyncIterator[str]
]


class ProductionAgent(AgentBase):
    """
    Production-ready agent with LLM integration.
    
    Implements the full Think-Decide-Act loop using an LLM for:
    - Analyzing user requests
    - Deciding which tools to use
    - Generating responses
    
    The agent requires an LLM call function to be provided, which allows
    flexibility in using different LLM providers (OpenAI, Claude, etc.)
    
    Example:
        async def call_llm(messages, tools, options):
            # Call your LLM here
            response = await openai.chat.completions.create(
                model="gpt-4",
                messages=messages,
                tools=tools,
            )
            return response.choices[0].message
        
        agent = ProductionAgent(
            info=AgentInfo(name="assistant"),
            llm_call=call_llm,
        )
        
        async for chunk in agent.run("Hello!"):
            print(chunk, end="")
    """
    
    def __init__(
        self,
        info: Optional[AgentInfo] = None,
        llm_call: Optional[LLMCallFunc] = None,
        llm_stream: Optional[LLMStreamFunc] = None,
        tool_registry: Optional[ToolRegistry] = None,
        auth_engine: Optional[AuthorizationEngine] = None,
        interaction_gateway: Optional[InteractionGateway] = None,
        system_prompt: Optional[str] = None,
    ):
        """
        Initialize the production agent.
        
        Args:
            info: Agent configuration (uses PRIMARY_AGENT_TEMPLATE if not provided)
            llm_call: Function to call LLM (non-streaming)
            llm_stream: Function to call LLM (streaming)
            tool_registry: Tool registry to use
            auth_engine: Authorization engine
            interaction_gateway: Interaction gateway
            system_prompt: Override system prompt
        """
        super().__init__(
            info=info or PRIMARY_AGENT_TEMPLATE,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
        )
        
        self._llm_call = llm_call
        self._llm_stream = llm_stream
        self._system_prompt = system_prompt
        
        # Last LLM response (for decision making)
        self._last_llm_response: Optional[Dict[str, Any]] = None
        
        # Thinking buffer (for streaming think output)
        self._thinking_buffer: List[str] = []
    
    # ========== Properties ==========
    
    @property
    def system_prompt(self) -> str:
        """Get the system prompt for this agent."""
        if self._system_prompt:
            return self._system_prompt
        
        if self.info.system_prompt:
            return self.info.system_prompt
        
        # Default system prompt
        return self._get_default_system_prompt()
    
    def _get_default_system_prompt(self) -> str:
        """Generate default system prompt based on agent info."""
        capabilities = ", ".join([c.value for c in self.info.capabilities]) if self.info.capabilities else "general assistance"
        
        return f"""You are {self.info.name}, an AI assistant.

Description: {self.info.description or 'A helpful AI assistant'}

Your capabilities include: {capabilities}

Guidelines:
- Be helpful, accurate, and concise
- Use tools when they can help accomplish the task
- Ask for clarification when needed
- Explain your reasoning when making complex decisions
"""
    
    # ========== LLM Integration ==========
    
    def set_llm_call(self, llm_call: LLMCallFunc) -> None:
        """Set the LLM call function."""
        self._llm_call = llm_call
    
    def set_llm_stream(self, llm_stream: LLMStreamFunc) -> None:
        """Set the streaming LLM call function."""
        self._llm_stream = llm_stream
    
    async def _call_llm(
        self,
        include_tools: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """
        Call the LLM with current messages.
        
        Args:
            include_tools: Whether to include tools in the call
            **options: Additional LLM options
            
        Returns:
            LLM response message
        """
        if not self._llm_call:
            raise RuntimeError("No LLM call function configured. Set llm_call in constructor or use set_llm_call().")
        
        # Build messages with system prompt
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self._messages)
        
        # Get tools
        tools = self.get_openai_tools() if include_tools else []
        
        # Call LLM
        response = await self._llm_call(messages, tools, options)
        
        self._last_llm_response = response
        return response
    
    async def _stream_llm(
        self,
        include_tools: bool = False,
        **options,
    ) -> AsyncIterator[str]:
        """
        Stream LLM response.
        
        Args:
            include_tools: Whether to include tools
            **options: Additional LLM options
            
        Yields:
            Response chunks
        """
        if not self._llm_stream:
            # Fall back to non-streaming
            response = await self._call_llm(include_tools=include_tools, **options)
            content = response.get("content", "")
            if content:
                yield content
            return
        
        # Build messages with system prompt
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self._messages)
        
        # Get tools
        tools = self.get_openai_tools() if include_tools else []
        
        # Stream from LLM
        async for chunk in self._llm_stream(messages, tools, options):
            yield chunk
    
    # ========== Think-Decide-Act Implementation ==========
    
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """
        Thinking phase - analyze the request.
        
        In ProductionAgent, thinking uses the LLM to analyze the situation.
        For streaming, we use the llm_stream function if available.
        
        Args:
            message: Current context/message
            **kwargs: Additional arguments
            
        Yields:
            Thinking output chunks
        """
        self._thinking_buffer.clear()
        
        # If we have streaming, use it for thinking output
        if self._llm_stream and kwargs.get("stream_thinking", True):
            # Add thinking prompt
            thinking_messages = self._messages.copy()
            
            # Stream the response
            async for chunk in self._stream_llm(include_tools=True):
                self._thinking_buffer.append(chunk)
                yield chunk
        else:
            # Non-streaming: just call LLM and don't yield thinking
            # The response will be used in decide()
            pass
    
    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """
        Decision phase - decide on next action.
        
        Analyzes the LLM response to determine:
        - Should we respond directly?
        - Should we call a tool?
        - Is the task complete?
        
        Args:
            message: Current context/message
            **kwargs: Additional arguments
            
        Returns:
            Decision dictionary
        """
        # If thinking didn't call LLM (non-streaming mode), call it now
        if self._last_llm_response is None:
            try:
                await self._call_llm(include_tools=True)
            except Exception as e:
                return {"type": "error", "error": str(e)}
        
        response = self._last_llm_response
        
        if response is None:
            return {"type": "error", "error": "No LLM response available"}
        
        # Check for tool calls
        tool_calls = response.get("tool_calls", [])
        
        if tool_calls:
            # Extract first tool call
            tool_call = tool_calls[0]
            
            # Handle different tool call formats
            if isinstance(tool_call, dict):
                tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
                arguments = tool_call.get("arguments", {})
                
                # Parse arguments if string
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": arguments}
            else:
                # Assume it's an object with attributes
                tool_name = getattr(tool_call, "name", "") or getattr(getattr(tool_call, "function", None), "name", "")
                arguments = getattr(tool_call, "arguments", {})
                
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": arguments}
            
            return {
                "type": "tool_call",
                "tool": tool_name,
                "arguments": arguments,
                "tool_call_id": tool_call.get("id") if isinstance(tool_call, dict) else getattr(tool_call, "id", None),
            }
        
        # Check for content (direct response)
        content = response.get("content", "")
        
        # Join thinking buffer if we have it
        if self._thinking_buffer and not content:
            content = "".join(self._thinking_buffer)
        
        if content:
            # Detect if this is a final response or needs continuation
            # For now, assume any content response is final
            return {
                "type": "response",
                "content": content,
            }
        
        # No content and no tool calls - task might be complete
        finish_reason = response.get("finish_reason", "")
        
        if finish_reason == "stop":
            return {"type": "complete", "message": "Task completed"}
        
        # Unclear state
        return {"type": "error", "error": "Unable to determine next action from LLM response"}
    
    async def act(self, action: Dict[str, Any], **kwargs) -> Any:
        """
        Action phase - execute the decision.
        
        For tool calls, executes the tool with authorization.
        
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
            
            # Execute tool with authorization
            result = await self.execute_tool(tool_name, arguments)
            
            # Clear last LLM response so next iteration calls LLM fresh
            self._last_llm_response = None
            
            return result
        
        elif action_type == "response":
            # Direct response - nothing to execute
            return action.get("content", "")
        
        elif action_type == "complete":
            return action.get("message", "Complete")
        
        else:
            return f"Unknown action type: {action_type}"
    
    # ========== Convenience Methods ==========
    
    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Simple chat interface (non-streaming).
        
        Runs the agent and collects all output.
        
        Args:
            message: User message
            session_id: Session ID
            
        Returns:
            Complete response string
        """
        output = []
        async for chunk in self.run(message, session_id=session_id):
            output.append(chunk)
        return "".join(output)
    
    @classmethod
    def create_with_openai(
        cls,
        api_key: str,
        model: str = "gpt-4",
        info: Optional[AgentInfo] = None,
        **kwargs,
    ) -> "ProductionAgent":
        """
        Create a ProductionAgent configured for OpenAI.
        
        This is a convenience factory method. In production, you might
        want to configure the LLM call function more carefully.
        
        Args:
            api_key: OpenAI API key
            model: Model to use
            info: Agent configuration
            **kwargs: Additional arguments for ProductionAgent
            
        Returns:
            Configured ProductionAgent
        """
        try:
            import openai
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")
        
        client = openai.AsyncOpenAI(api_key=api_key)
        
        async def llm_call(
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            options: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            options = options or {}
            
            call_args = {
                "model": model,
                "messages": messages,
            }
            
            if tools:
                call_args["tools"] = tools
            
            call_args.update(options)
            
            response = await client.chat.completions.create(**call_args)
            message = response.choices[0].message
            
            # Convert to dict
            result: Dict[str, Any] = {
                "role": message.role,
                "content": message.content or "",
                "finish_reason": response.choices[0].finish_reason,
            }
            
            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in message.tool_calls
                ]
            
            return result
        
        async def llm_stream(
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            options: Optional[Dict[str, Any]] = None,
        ) -> AsyncIterator[str]:
            options = options or {}
            
            call_args = {
                "model": model,
                "messages": messages,
                "stream": True,
            }
            
            # Note: streaming with tools is complex, skip tools for streaming
            call_args.update(options)
            
            response = await client.chat.completions.create(**call_args)
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        return cls(
            info=info,
            llm_call=llm_call,
            llm_stream=llm_stream,
            **kwargs,
        )
    
    @classmethod
    def create_with_anthropic(
        cls,
        api_key: str,
        model: str = "claude-3-sonnet-20240229",
        info: Optional[AgentInfo] = None,
        **kwargs,
    ) -> "ProductionAgent":
        """
        Create a ProductionAgent configured for Anthropic Claude.
        
        Args:
            api_key: Anthropic API key
            model: Model to use
            info: Agent configuration
            **kwargs: Additional arguments for ProductionAgent
            
        Returns:
            Configured ProductionAgent
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package required. Install with: pip install anthropic")
        
        client = anthropic.AsyncAnthropic(api_key=api_key)
        
        async def llm_call(
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            options: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            options = options or {}
            
            # Extract system message
            system_content = ""
            user_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                else:
                    user_messages.append(msg)
            
            call_args = {
                "model": model,
                "max_tokens": options.get("max_tokens", 4096),
                "messages": user_messages,
            }
            
            if system_content:
                call_args["system"] = system_content
            
            if tools:
                # Convert OpenAI tool format to Anthropic format
                anthropic_tools = []
                for tool in tools:
                    func = tool.get("function", {})
                    anthropic_tools.append({
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    })
                call_args["tools"] = anthropic_tools
            
            response = await client.messages.create(**call_args)
            
            # Convert to our format
            result: Dict[str, Any] = {
                "role": "assistant",
                "content": "",
                "finish_reason": response.stop_reason,
            }
            
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    result["content"] += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    })
            
            if tool_calls:
                result["tool_calls"] = tool_calls
            
            return result
        
        return cls(
            info=info,
            llm_call=llm_call,
            **kwargs,
        )


# Factory function for easy creation
def create_production_agent(
    name: str = "assistant",
    description: str = "A helpful AI assistant",
    llm_call: Optional[LLMCallFunc] = None,
    **kwargs,
) -> ProductionAgent:
    """
    Factory function to create a ProductionAgent.
    
    Args:
        name: Agent name
        description: Agent description
        llm_call: LLM call function
        **kwargs: Additional arguments for ProductionAgent
        
    Returns:
        Configured ProductionAgent
    """
    info = AgentInfo(
        name=name,
        description=description,
        capabilities=[
            AgentCapability.CODE_ANALYSIS,
            AgentCapability.CODE_GENERATION,
            AgentCapability.FILE_OPERATIONS,
            AgentCapability.REASONING,
        ],
    )
    
    return ProductionAgent(
        info=info,
        llm_call=llm_call,
        **kwargs,
    )
