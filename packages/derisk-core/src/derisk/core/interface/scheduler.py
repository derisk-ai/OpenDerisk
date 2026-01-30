import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Union, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("schedule")


class Signal(Enum):
    STOP = "STOP"  # 停止
    EMPTY_STOP = "EMPTY_STOP"  # 若调度队列为空则STOP


class Stage(Enum):
    THINK = "THINK"
    ACT = "ACT"
    ANSWER = "ANSWER"


class SchedulePayload(BaseModel):
    conv_id: str = Field(..., description="conv id")
    agent_name: str = Field(..., description="当前Agent的name")
    stage: str = Field(..., description="处理阶段")
    context_index: str = Field(..., description="上下文索引")
    message_id: Optional[str] = Field(None, description="待处理的消息ID")


class Scheduler(ABC):
    @abstractmethod
    async def put(self, payload: Union[SchedulePayload, Signal]):
        """添加一个任务"""

    @abstractmethod
    async def running(self) -> bool:
        """调度队列是否运行中"""

    @abstractmethod
    async def stop(self):
        """停止调度(放入停止信号)"""

    @abstractmethod
    async def schedule(self):
        """开始调度"""
