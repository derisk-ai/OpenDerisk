"""Default memory for storing plans and messages."""

from dataclasses import fields
from typing import List, Optional

import pandas as pd

from ...schema import Status
from .base import GptsMessage, GptsMessageMemory, GptsPlan, GptsPlansMemory


class DefaultGptsPlansMemory(GptsPlansMemory):
    """Default memory for storing plans."""

    def __init__(self):
        """Create a memory to store plans."""
        self.df = pd.DataFrame(columns=[field.name for field in fields(GptsPlan)])

    def batch_save(self, plans: list[GptsPlan]):
        """Save plans in batch."""
        new_rows = pd.DataFrame([item.to_dict() for item in plans])
        self.df = pd.concat([self.df, new_rows], ignore_index=True)

    def get_by_conv_id(self, conv_id: str) -> List[GptsPlan]:
        """Get plans by conv_id."""
        result = self.df.query("conv_id==@conv_id")  # noqa: F541
        plans = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            plans.append(GptsPlan.from_dict(row_dict))
        return plans

    def get_plans_by_msg_round(self, conv_id: str, rounds_id: str) -> List[GptsPlan]:
        """Get plans by conv_id and conv round."""
        result = self.df.query(  # noqa
            "conv_id==@conv_id and conv_round_id==@rounds_id"  # noqa
        )
        plans = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            plans.append(GptsPlan.from_dict(row_dict))
        return plans

    def get_by_conv_id_and_num(
        self, conv_id: str, task_ids: List[str]
    ) -> List[GptsPlan]:
        """Get plans by conv_id and task number."""
        task_nums_str = [str(num) for num in task_ids]  # noqa:F841
        result = self.df.query(  # noqa
            "conv_id==@conv_id and sub_task_id in @task_nums_str"  # noqa
        )
        plans = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            plans.append(GptsPlan.from_dict(row_dict))
        return plans

    def get_todo_plans(self, conv_id: str) -> List[GptsPlan]:
        """Get unfinished planning steps."""
        todo_states = [Status.TODO.value, Status.RETRYING.value]  # noqa: F841
        result = self.df.query("conv_id==@conv_id and state in @todo_states")  # noqa
        plans = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            plans.append(GptsPlan.from_dict(row_dict))
        return plans

    def complete_task(self, conv_id: str, task_id: str, result: str):
        """Set the planning step to complete."""
        condition = (self.df["conv_id"] == conv_id) & (
            self.df["sub_task_id"] == task_id
        )
        self.df.loc[condition, "state"] = Status.COMPLETE.value
        self.df.loc[condition, "result"] = result

    def update_task(
        self,
        conv_id: str,
        task_id: str,
        state: str,
        retry_times: int,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        result: Optional[str] = None,
    ):
        """Update the state of the planning step."""
        condition = (self.df["conv_id"] == conv_id) & (
            self.df["sub_task_id"] == task_id
        )
        self.df.loc[condition, "state"] = state
        self.df.loc[condition, "retry_times"] = retry_times
        self.df.loc[condition, "result"] = result

        if agent:
            self.df.loc[condition, "sub_task_agent"] = agent

        if model:
            self.df.loc[condition, "agent_model"] = model

    def remove_by_conv_id(self, conv_id: str):
        """Remove all plans in the conversation."""
        self.df.drop(self.df[self.df["conv_id"] == conv_id].index, inplace=True)

    def get_by_conv_and_content(self, conv_id: str, content: str)-> Optional[GptsPlan] :
        todo_states = [Status.TODO.value, Status.RETRYING.value]  # noqa: F841
        result = self.df.query("conv_id==@conv_id and task_content==@content")  # noqa
        plans = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            plans.append(GptsPlan.from_dict(row_dict))
        return plans[0]

class DefaultGptsMessageMemory(GptsMessageMemory):
    """Default memory for storing messages."""

    def __init__(self):
        """Create a memory to store messages."""
        self.df = pd.DataFrame(columns=[field.name for field in fields(GptsMessage)])

    def append(self, message: GptsMessage):
        """Append a message to the memory."""
        self.df.loc[len(self.df)] = message.to_dict()

    def update(self, message: GptsMessage) -> None:
        pass

    def get_by_agent(self, conv_id: str, agent: str) -> Optional[List[GptsMessage]]:
        """Get all messages sent or received by the agent in the conversation."""
        result = self.df.query(
            "conv_id==@conv_id and (sender==@agent or receiver==@agent)"  # noqa: F541
        )
        messages = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            messages.append(GptsMessage.from_dict(row_dict))
        return messages

    def get_between_agents(
        self,
        conv_id: str,
        agent1: str,
        agent2: str,
        current_goal: Optional[str] = None,
    ) -> List[GptsMessage]:
        """Get all messages between two agents in the conversation."""
        if current_goal:
            result = self.df.query(
                "conv_id==@conv_id and ((sender==@agent1 and receiver==@agent2) or (sender==@agent2 and receiver==@agent1)) and current_goal==@current_goal"
                # noqa
            )
        else:
            result = self.df.query(
                "conv_id==@conv_id and ((sender==@agent1 and receiver==@agent2) or (sender==@agent2 and receiver==@agent1))"
                # noqa
            )
        messages = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            messages.append(GptsMessage.from_dict(row_dict))
        return messages

    def get_by_conv_id(self, conv_id: str) -> List[GptsMessage]:
        """Get all messages in the conversation."""
        result = self.df.query("conv_id==@conv_id")  # noqa: F541
        messages = []
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            messages.append(GptsMessage.from_dict(row_dict))
        return messages

    def get_by_message_id(self, message_id: str) -> Optional[GptsMessage]:
        result = self.df.query("message_id==@message_id")  # noqa: F541
        for row in result.itertuples(index=False, name=None):
            row_dict = dict(zip(self.df.columns, row))
            return GptsMessage.from_dict(row_dict)
        return None

    def get_last_message(self, conv_id: str) -> Optional[GptsMessage]:
        """Get the last message in the conversation."""
        return None

    def delete_by_conv_id(self, conv_id: str) -> None:
        """Delete all messages in the conversation."""
        self.df.drop(self.df[self.df["conv_id"] == conv_id].index, inplace=True)
