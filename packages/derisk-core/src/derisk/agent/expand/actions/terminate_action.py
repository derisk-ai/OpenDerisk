from typing import Optional

from derisk.agent import BlankAction, Resource
from derisk.agent.core.action.base import ToolCall
from derisk.agent.resource import FunctionTool, ToolParameter


class Terminate(BlankAction, FunctionTool):
    name = "terminate"
    """Terminate action.
Terminate
    It is a special action to terminate the conversation, at same time, it can be a
    tool to return the final answer.
    """

    @classmethod
    def get_action_description(cls) -> str:
        return """\终止任务并输出最终答案。

    **调用时机**：所有阶段完成，准备交付最终成果。

    **终止要求**：
    1. 读取所有阶段的交付物
    2. 整合成完整、可读的最终答案
    3. 包含关键数据、图表路径、文件路径等
    4. 输出到output参数，而非过程描述

    **output格式**：
    - 使用Markdown格式
    - 包含执行摘要（Executive Summary）
    - 列出核心发现（Key Findings）
    - 提供详细交付物的文件路径
    - 确保用户可以直接使用这些信息"""

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional["Action"] = None,
        resource: Optional[Resource] = None,
        **kwargs,
    ) -> Optional["Action"]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """
        if tool_call.name == cls.name:
            final_anwser = tool_call.args.get('output') if tool_call.args else None
            return cls(action_uid=tool_call.tool_call_id, action_input=final_anwser, terminate=True)
        else:
            return None

    @property
    def description(self):
        return self.get_action_description()

    @property
    def args(self):
        return {
            "output": ToolParameter(
                type="string",
                name="output",
                description=(
                    "Final answer to the task, or the reason why you think it "
                    "is impossible to complete the task"
                ),
            ),
        }

    @property
    def concurrency(self):
        return "exclusive"

    def execute(self, *args, **kwargs):
        if "output" in kwargs:
            return kwargs["output"]
        if "final_answer" in kwargs:
            return kwargs["final_answer"]
        return args[0] if args else "terminate unknown"


    async def async_execute(self, *args, **kwargs):
        return self.execute(*args, **kwargs)
