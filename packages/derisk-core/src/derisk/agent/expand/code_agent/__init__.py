"""Code Assistant Agent Module.

A professional sub-agent for code generation and execution in sandbox environments.

Usage:
    from derisk.agent.expand.code_assistant_agent import CodeAssistantAgent
    
    # Create agent with Chinese prompts (default)
    agent = CodeAssistantAgent(prompt_language="zh")
    
    # Create agent with English prompts
    agent = CodeAssistantAgent(prompt_language="en")
"""

from .agent import CodeAssistantAgent, CodeLanguage, ExecutionResult
from .actions import CodeAction


__all__ = [
    "CodeAssistantAgent",
    "CodeAction",
    "CodeLanguage",
    "ExecutionResult",
]