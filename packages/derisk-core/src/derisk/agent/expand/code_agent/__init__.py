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
from .prompt import (
    CODE_ASSISTANT_CHECK_RESULT_SYSTEM_MESSAGE_CN,
    CODE_ASSISTANT_CHECK_RESULT_SYSTEM_MESSAGE_EN,
    CODE_ASSISTANT_PROFILE_CONSTRAINTS_CN,
    CODE_ASSISTANT_PROFILE_CONSTRAINTS_EN,
    CODE_ASSISTANT_PROFILE_DESC_CN,
    CODE_ASSISTANT_PROFILE_DESC_EN,
    CODE_ASSISTANT_PROFILE_GOAL_CN,
    CODE_ASSISTANT_PROFILE_GOAL_EN,
    CODE_ASSISTANT_PROFILE_NAME_CN,
    CODE_ASSISTANT_PROFILE_NAME_EN,
    CODE_ASSISTANT_PROFILE_ROLE_CN,
    CODE_ASSISTANT_PROFILE_ROLE_EN,
    get_check_result_system_message,
    get_execution_failed_message,
    get_profile_constraints,
    get_profile_desc,
    get_profile_goal,
    get_profile_name,
    get_profile_role,
    get_timeout_message,
)

__all__ = [
    "CodeAssistantAgent",
    "CodeAction",
    "CodeLanguage",
    "ExecutionResult",
    "CODE_ASSISTANT_PROFILE_NAME_CN",
    "CODE_ASSISTANT_PROFILE_ROLE_CN",
    "CODE_ASSISTANT_PROFILE_GOAL_CN",
    "CODE_ASSISTANT_PROFILE_CONSTRAINTS_CN",
    "CODE_ASSISTANT_PROFILE_DESC_CN",
    "CODE_ASSISTANT_CHECK_RESULT_SYSTEM_MESSAGE_CN",
    "CODE_ASSISTANT_PROFILE_NAME_EN",
    "CODE_ASSISTANT_PROFILE_ROLE_EN",
    "CODE_ASSISTANT_PROFILE_GOAL_EN",
    "CODE_ASSISTANT_PROFILE_CONSTRAINTS_EN",
    "CODE_ASSISTANT_PROFILE_DESC_EN",
    "CODE_ASSISTANT_CHECK_RESULT_SYSTEM_MESSAGE_EN",
    "get_profile_name",
    "get_profile_role",
    "get_profile_goal",
    "get_profile_constraints",
    "get_profile_desc",
    "get_check_result_system_message",
    "get_execution_failed_message",
    "get_timeout_message",
]