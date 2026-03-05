from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Union

from derisk._private.pydantic import BaseModel, Field, model_to_dict, field_validator
from derisk.agent.core.action.base import OutputType


class ChatLayout(BaseModel):
    name: str = Field(..., description="this layout name")
    incremental: bool = Field(True, description="this layout is use incremental")
    description: Optional[str] = Field(None, description="this layout description")
    reuse_name: Optional[str] = Field(
        None, description="this layout reuse other name's web layout "
    )


class VisBase(BaseModel):
    uid: str = Field(..., description="vis component uid")
    type: str = Field(..., description="vis data update type")
    message_id: Optional[str] = Field(None, description="vis component message id")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class VisTextContent(VisBase):
    markdown: str = Field(..., description="vis message content")


class VisAttach(VisBase):
    file_type: Optional[str] = Field(default=None, description="attach file type")
    name: Optional[str] = Field(default=None, description="attach file name")
    task_id: Optional[str] = Field(default=None, description="attach file task id")
    description: Optional[str] = Field(
        default=None, description="attach file description"
    )
    logo: Optional[str] = Field(default=None, description="attach file logo")
    url: Optional[str] = Field(default=None, description="attach file url")
    created: Optional[Any] = Field(default=None, description="attach file created time")
    size: Optional[str] = Field(default=None, description="attach file size")
    author: Optional[str] = Field(default=None, description="attach file author")


class VisAttachsContent(VisBase):
    items: List[VisAttach] = Field(default=[], description="vis plan tasks")


class VisAttachContent(VisBase):
    """文件附件内容 - 用于d-attach组件展示单个文件"""

    file_id: str = Field(..., description="文件唯一标识")
    file_name: str = Field(..., description="文件名")
    file_type: str = Field(..., description="文件类型")
    file_size: int = Field(default=0, description="文件大小（字节）")
    oss_url: Optional[str] = Field(default=None, description="OSS访问地址")
    preview_url: Optional[str] = Field(default=None, description="文件预览地址")
    download_url: Optional[str] = Field(default=None, description="文件下载地址")
    mime_type: Optional[str] = Field(default=None, description="MIME类型")
    created_at: Optional[str] = Field(default=None, description="创建时间ISO格式")
    task_id: Optional[str] = Field(default=None, description="关联任务ID")
    description: Optional[str] = Field(default=None, description="文件描述")


class VisAttachListContent(VisBase):
    """文件附件列表内容 - 用于d-attach-list组件展示多个文件

    适用场景：
    1. terminate时交付多个文件
    2. 批量文件展示
    3. 任务完成后的文件汇总
    """

    title: Optional[str] = Field(default="交付文件", description="文件列表标题")
    description: Optional[str] = Field(default=None, description="文件列表描述")
    files: List[VisAttachContent] = Field(default_factory=list, description="文件列表")
    total_count: int = Field(default=0, description="文件总数")
    total_size: int = Field(default=0, description="文件总大小（字节）")
    show_batch_download: bool = Field(default=True, description="是否显示批量下载按钮")


class VisMessageContent(VisBase):
    markdown: str = Field(..., description="vis msg content")
    role: Optional[str] = Field(
        default=None, description="vis message generate agent role"
    )
    name: Optional[str] = Field(
        default=None, description="vis message generate agent name"
    )
    avatar: Optional[str] = Field(
        default=None, description="vis message generate agent avatar"
    )
    model: Optional[str] = Field(
        default=None, description="vis message generate agent model"
    )


class VisTaskContent(BaseModel):
    task_id: str = Field(default=None, description="vis task id")
    task_uid: Optional[str] = Field(default=None, description="vis task uid")
    task_content: Optional[str] = Field(default=None, description="vis task content")
    task_link: Optional[str] = Field(default=None, description="vis task link")
    agent_id: Optional[str] = Field(default=None, description="vis task agent id")
    agent_name: Optional[str] = Field(default=None, description="vis task agent name")
    agent_link: Optional[str] = Field(default=None, description="vis task agent link")
    task_name: Optional[str] = Field(default=None, description="vis task  name")
    avatar: Optional[str] = Field(default=None, description="vis task avatar")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class VisPlanContent(VisBase):
    tasks: List[VisTaskContent] = Field(default=[], description="drsk drsk_plan tasks")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        tasks_dict = []
        for step in self.tasks:
            tasks_dict.append(step.to_dict())
        dict_value = model_to_dict(self, exclude={"tasks"})
        dict_value["tasks"] = tasks_dict
        return dict_value


class VisPlansContent(VisBase):
    round_title: Optional[str] = Field(default=None, description="阶段规划标题")
    round_description: Optional[str] = Field(default=None, description="阶段规划描述")
    tasks: List[VisTaskContent] = Field(default=[], description="vis plan tasks")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        tasks_dict = []
        for step in self.tasks:
            tasks_dict.append(step.to_dict())
        dict_value = model_to_dict(self, exclude={"tasks"})
        dict_value["tasks"] = tasks_dict
        return dict_value


class VisStepContent(VisBase):
    avatar: Optional[str] = Field(default=None, description="vis task avatar")
    status: Optional[str] = Field(default=None, description="vis task status")

    tool_name: Optional[str] = Field(default=None, description="vis task tool name")
    tool_desc: Optional[str] = Field(
        default=None, description="vis task tool description"
    )
    tool_version: Optional[str] = Field(
        default=None, description="vis task tool version"
    )
    tool_author: Optional[str] = Field(default=None, description="vis task tool author")
    need_ask_user: Optional[bool] = Field(
        default=None, description="vis task tool need ask user"
    )
    start_time: Optional[Any] = Field(default=None, description="vis task start time")
    tool_cost: Optional[float] = Field(default=None, description="vis task cost time")
    tool_args: Optional[Any] = Field(default=None, description="vis task tool args")
    out_type: Optional[str] = Field(
        default=OutputType.MARKDOWN, description="tool out type"
    )
    tool_result: Optional[Any] = Field(default=None, description="vis tool result")
    markdown: Optional[Any] = Field(
        default=None, description="vis tool result markdown"
    )

    err_msg: Optional[Any] = Field(
        default=None, description="vis task tool error message"
    )
    progress: Optional[int] = Field(
        default=None, description="vis task tool exceute progress"
    )

    tool_execute_link: Optional[str] = Field(
        default=None, description="vis task tool exceute link"
    )


class StepInfo(BaseModel):
    avatar: Optional[str] = Field(default=None, description="vis task avatar")
    status: Optional[str] = Field(default=None, description="vis task status")
    tool_name: Optional[str] = Field(default=None, description="vis task tool name")
    tool_args: Optional[str] = Field(default=None, description="vis task tool args")
    tool_result: Optional[str] = Field(default=None, description="vis tool result")

    err_msg: Optional[str] = Field(
        default=None, description="vis task tool error message"
    )
    progress: Optional[int] = Field(
        default=None, description="vis task tool  exceute progress"
    )
    tool_execute_link: Optional[str] = Field(
        default=None, description="vis task tool exceute link"
    )

    def to_dict(self):
        return model_to_dict(self)


class VisStepsContent(VisBase):
    steps: Optional[List[StepInfo]] = Field(
        default=None, description="vis task tools exceute info"
    )


class VisThinkingContent(VisBase):
    markdown: str = Field(..., description="vis thinking content")
    think_link: str = Field(None, description="vis thinking link")


class VisNode(VisBase):
    id: str = Field(..., description="id of the node")
    markdown: str = Field(..., description="content of the node")
    node_type: str = Field(None, description="type of the node, user/bot")
    avatar: str = Field(None, description="avatar of the node")
    agent_name: str = Field(None, description="name of the agent")
    title: str = Field(None, description="title of the node")
    status: str = Field(None, description="status of the node")


class VisEdge(VisBase):
    source: str = Field(..., description="source of the edge")
    target: str = Field(..., description="target of the edge")


class VisGraph(VisBase):
    nodes: list[VisNode] = Field(..., description="nodes in the graph")
    edges: list[VisEdge] = Field(..., description="edges in the graph")


class VisSelectContent(VisBase):
    markdown: str = Field(..., description="content of the select option")
    confirm_message: Optional[str] = Field(
        None,
        description="When the user selects this option, a message is simulated to be sent by the user, and this field represents the content of the message.",
    )
    extra: Optional[dict] = Field(
        None,
        description="When the user selects this option, this extended information will be passed to the system.",
    )


class VisConfirm(VisBase):
    markdown: str = Field(..., description="content of the message for user to confirm")
    disabled: bool = Field(
        ..., description="Whether to disable the button, e.g., already confirmed, etc."
    )
    extra: Optional[dict] = Field(
        None,
        description="When the user confirm this message, this extended information will be passed to the system.",
    )


class VisInteract(VisBase):
    title: str = Field(..., description="title of the interact")
    markdown: str = Field(..., description="markdown content")
    interact_type: str = Field(..., description="interact type")
    position: str = Field("tail", description="position of interact")


class VisReference(VisBase):
    reference_url: Optional[str] = Field(
        default=None, description="vis knowledge reference_url"
    )
    reference_name: Optional[str] = Field(
        default=None, description="vis reference name"
    )
    reference_offset: Optional[int] = Field(
        default=None, description="vis reference offset"
    )


class ExecutionRecord(VisBase):
    run_time: Optional[datetime] = None
    run_rounds: Optional[int] = None
    markdown: Optional[str] = None

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class VisSchedule(VisBase):
    duration: Optional[int] = Field(
        None, description="Tracking duration, unit/minute, defualt 30 minutes."
    )
    interval: int = Field(
        None,
        description="Tracking execution interval duration, unit/second，default 60 seconds.",
    )
    intent: str = Field(
        None, description="The target and intention of the current tracking task"
    )
    instruction: str = Field(
        None,
        description="Track the operation instructions of tasks, such as start, stop, update, pause, resume, etc. Based on the current status, if there are no known tasks, it will start by default",
    )
    agent: str = Field(
        None, description="The target and intention of the current tracking task"
    )
    extra_info: Optional[dict] = Field(
        None,
        description="关键参数信息(结合‘代理'、‘工具’定义的需求和已知消息，搜集各种关键参数，如:目标、时间、位置等出现的有真实实际值的参数，确保后续‘agent’能结合'intent'正确运行)",
    )

    tasks: Optional[List[ExecutionRecord]] = None

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        tasks_dict = []
        for step in self.tasks:
            tasks_dict.append(step.to_dict())
        dict_value = model_to_dict(self, exclude={"tasks"})
        dict_value["tasks"] = tasks_dict
        return dict_value


class TodoStatus(str, Enum):
    """Todo状态枚举"""

    PENDING = "pending"  # 待完成
    WORKING = "working"  # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class StatusNotificationLevel(str, Enum):
    """状态通知级别"""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    PROGRESS = "progress"


class VisStatusNotification(VisBase):
    """状态通知内容 - 用于展示系统状态、进度信息"""

    title: str = Field(..., description="通知标题")
    message: str = Field(..., description="通知内容")
    level: StatusNotificationLevel = Field(
        StatusNotificationLevel.INFO, description="通知级别"
    )
    progress: Optional[float] = Field(None, description="进度百分比 (0-100)")
    icon: Optional[str] = Field(None, description="图标名称")
    dismissible: bool = Field(True, description="是否可关闭")
    auto_dismiss: Optional[int] = Field(
        None, description="自动关闭时间(秒), None表示不自动关闭"
    )
    actions: Optional[List[Dict[str, Any]]] = Field(
        None, description="可执行的操作按钮"
    )


class TodoItem(BaseModel):
    id: str = Field(..., description="todo item id")
    title: str = Field(..., description="todo item title")
    status: str = Field(TodoStatus.PENDING, description="todo item status")
    index: int = Field(0, description="todo item order index")

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        """验证状态值，确保是有效的TodoStatus"""
        if isinstance(v, str):
            try:
                return TodoStatus(v.lower())
            except ValueError:
                return TodoStatus.PENDING
        return v


class TodoListContent(VisBase):
    """TodoList内容 - 经典简单样式"""

    mission: Optional[str] = Field(None, description="看板任务描述/名称")
    items: List[TodoItem] = Field(default_factory=list, description="todo列表项")
    current_index: int = Field(0, description="当前执行的todo项索引", ge=0)
    total_count: int = Field(0, description="todo总数量", ge=0)

    @field_validator("current_index")
    @classmethod
    def validate_current_index(cls, v, info):
        items = info.data.get("items", [])
        # 情况1: items 为空 → 强制重置为 0（符合字段 ge=0 约束）
        if not items:
            return 0
        # 情况2: 索引越界（含 v == len(items)）→ 修正为最后一项
        if v >= len(items):
            return len(items) - 1
        return v


# class AgentFile(VisBase):
#     title: Optional[str] = Field(None, description="当前工作项标题")
#     description: Optional[str] = Field(None, description="当前工作项内容描述")
#     status: Optional[str] = Field(None, description="当前工作项状态")
#     start_time: Optional[str] = Field(None, description="当前工作项开始时间")
#     cost: Optional[int] = Field(None, description="当前工作项耗时")
#     markdown: Optional[str] = Field(None, description="当前工作项的模型和Action空间")
#
# class AgentFolder(VisBase):
#     agent_name: Optional[str] = Field(None, description="agent name")
#     description: Optional[str] = Field(None, description="agent description")
#     avatar: Optional[str] = Field(None, description="agent logo")
#     items: Optional[List[Union[AgentFile,'AgentFolder']]] = Field(None, description="工作空间资源管理器")
#
#
