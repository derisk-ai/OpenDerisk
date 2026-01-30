import logging
from typing import Optional

from derisk.agent import Agent

logger = logging.getLogger("context")


class ChatContextKey:
    """Agent会话级别的上下文key"""
    GPTS_APP_CODE: str = "gpts_app_code"  # 当前对话的主Agent(应用)app_code
    CONV_SESSION_ID: str = "conv_session_id"
    CONV_ID: str = "conv_id"


class TaskContextKey:
    """子任务级别的上下文Key"""
    AGENT_APP_CODE: str = "agent_app_code"  # 当前Agent的ID
    TASK_ID: str = "task_id"  # received_message.message_id
    SYSTEM_PROMPT: str = "system_prompt"  # 系统提示词 格式: str
    QUERY: str = "query"  # 接收到的用户(或主Agent)消息
    SUB_AGENTS: str = "sub_agents"  # 子Agent 格式: [{app_code,name,description}]
    MCPS: str = "mcps"  # MCP工具 格式: [{mcp_name, tools:[{tool_name, tool_description, prompt}]}]
    TOOLS: str = "tools"  # 除mcp外的工具 格式: [{tool_name, tool_description, prompt}]
    WORKFLOWS: str = "workflows"  # 工作流 格式: [{WorkflowResourceParameter, prompt}]
    KNOWLEDGE: str = "knowledge"  # 知识 格式: {id,description,parameters}

    _HISTORY_MESSAGES: list[dict] = "_history_messages"  # 消息历史(调用模型后会将CURRENT_STEP_MESSAGES append进来) 格式: [{AgentMessage.to_dict()}]
    _NEXT_STEP_MESSAGES: list[dict] = "_next_step_messages"  # 下一轮次需要传递给模型的消息 格式: [AgentMessage.to_dict()]


class StepContextKey:
    """Agent Step级别的上下文key"""
    MESSAGE_ID: str = "message_id"  # 当前轮次的message_id
    STEP_COUNTER: str = "step_counter"  # 当前Agent第几轮循环
    ACTION_REPORTS: str = "action_reports"  # 当前轮次的action_reports 格式: [ActionOutput.to_dict]

    CURRENT_STEP_MESSAGES: list[dict] = "current_step_messages"  # 当前轮次需要传递给模型的消息 格式: [AgentMessage.to_dict()]


def keys(ks) -> list[str]:
    """取出上下文key"""
    return [value for name, value in ks.__dict__.items() if value and isinstance(value, str) and not name.startswith("__")]


class ContextWindow:
    @classmethod
    async def create(cls, agent: Agent, task_id: str, ctx: dict = None):
        cache = await cls.cache(agent)
        if not cache:
            return
        cache.context_windows[task_id] = cache.context_windows.get(task_id, {})

    @classmethod
    async def get_current(cls, agent: Agent, task_id: str) -> Optional[dict]:
        """Get the current context window.

        Returns:
            Optional[dict]: The current context window
        """
        cache = await cls.cache(agent)
        current = cache.context_windows.get(task_id)
        if current is None:
            cache.context_windows[task_id] = {}
        return current

    @classmethod
    async def cache(cls, agent: Agent):
        from derisk.agent.core.memory.gpts.gpts_memory import ConversationCache
        cache: ConversationCache = await agent.memory.gpts_memory.cache(agent.agent_context.conv_id)
        return cache
