import logging
import os
import re
from abc import ABC, abstractmethod
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Optional

from openai import BaseModel
from pydantic import Field

from derisk.agent import AgentMessage, Action
from derisk.configs.model_config import LOGDIR

REASONING_LOGGER = logging.getLogger("reasoning")
# 创建TimedRotatingFileHandler，每天午夜轮转
handler = TimedRotatingFileHandler(
    filename=os.path.join(LOGDIR, "reasoning.log"),  # 基础日志文件名
    when="midnight",  # 每天午夜轮转
    interval=1,  # 间隔1天
    backupCount=7,  # 保留7天日志
    encoding="utf-8",  # 编码
    delay=False,  # 立即写入
    utc=False,  # 使用本地时间
)
# 自定义文件名后缀（格式为yyyymmdd）
handler.suffix = "%Y%m%d"
# 更新正则表达式以匹配新后缀格式（确保自动删除旧文件）
handler.extMatch = re.compile(r"^\d{8}$", re.ASCII)

# 设置日志格式
file_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
handler.setFormatter(file_formatter)

# 添加处理器
REASONING_LOGGER.addHandler(handler)

DEFAULT_REASONING_PLANNER_NAME = "DEFAULT"


class ReasoningPlan(BaseModel):
    reason: str = Field(
        None, description="必须执行的具体依据（需关联前置分析或执行结果）"
    )

    intention: str = Field(..., description="新动作目标")
    id: str = Field(..., description="工具ID")
    parameters: dict = Field(None, description="执行参数")


class ReasoningModelOutput(BaseModel):
    """Origin output of the reasoning model"""

    reason: str = Field(None, description="详细解释状态判定和plan拆解依据")

    status: str = Field(
        ...,
        description="planing (仅当需要执行下一步动作时) | done (仅当任务可终结时) | abort (仅当任务异常或无法推进或需要用户提供更多信息时)",
    )

    plans: list[ReasoningPlan] = Field(
        None, description="新动作目标（需对比历史动作确保不重复）"
    )

    plans_brief_description: str = Field(
        None, description="简短介绍要执行的动作，不超过10个字"
    )

    summary: str = Field(
        None,
        description="当done/abort状态时出现，将历史动作总结为自然语言文本，按时间排序，需包含：执行动作(含参数)+核心发现+最终结论(若有)",
    )

    answer: str = Field(
        None, description="当done/abort状态时出现，根据上下文信息给出任务结论"
    )


class ReasoningEngineOutput:
    def __init__(self):
        # 任务是否结束
        self.done: bool = False

        # 任务结论(任务结束时才会有结论)
        self.answer: Optional[str] = None

        # 待执行的动作
        self.actions: Optional[list[Action]] = None

        # 为什么执行这些动作的解释说明
        self.action_reason: Optional[str] = None

        # 简短介绍要执行的动作，不超过10个字
        self.plans_brief_description: Optional[str] = None

        # 调用的模型名
        self.model_name: Optional[str] = None

        # 调用模型的messages
        self.messages: Optional[list[AgentMessage]] = None

        # 给模型的user_prompt
        self.user_prompt: Optional[str] = None

        # 给模型的system_prompt
        self.system_prompt: Optional[str] = None

        # 模型原始输出
        self.model_content: Optional[str] = None

        # 模型thinking原始输出
        self.model_thinking: Optional[str] = None


class ReasoningEngine(ABC):
    _registry: dict[str, "ReasoningEngine"] = {}

    @classmethod
    def register(cls, subclass):
        """
        Reasoning engine register

        Example:
            @ReasoningEngine.register
            def MyEngine(ReasoningEngine):
                ...

        """

        if not issubclass(subclass, cls):
            raise TypeError(f"{subclass.__name__} must be subclass of {cls.__name__}")
        instance = subclass()
        if instance.name in cls._registry:
            raise ValueError(f"Engine {instance.name} already registered!")
        cls._registry[instance.name] = instance
        return subclass

    @classmethod
    def get_reasoning_engine(cls, name) -> Optional["ReasoningEngine"]:
        """
        Get reasoning engine by name

          name:
            reasoning engine name
        """

        return cls._registry.get(name)

    @classmethod
    def get_all_reasoning_engines(cls) -> dict[str, "ReasoningEngine"]:
        """
        Get all reasoning engines
        :return:
        """
        return cls._registry

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the reasoning engine."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the description of the reasoning engine."""

    @abstractmethod
    async def invoke(
        self,
        agent: Any,
        agent_context: Any,
        received_message: AgentMessage,
        current_step_message: AgentMessage,
        step_id: str,
        **kwargs,
    ) -> ReasoningEngineOutput:
        """planning"""
