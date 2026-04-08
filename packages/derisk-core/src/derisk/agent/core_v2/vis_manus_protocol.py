"""
Manus 双面板可视化协议定义

定义前端 vis_manus 组件所需的数据结构和协议规范
参考 DB-GPT Manus 布局：左面板（执行步骤/思考/产物）+ 右面板（详细输出/6种渲染器）
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class ManusStepType(str, Enum):
    """步骤类型 - 对应不同的工具/动作"""
    READ = "read"
    EDIT = "edit"
    WRITE = "write"
    BASH = "bash"
    GREP = "grep"
    GLOB = "glob"
    TASK = "task"
    SKILL = "skill"
    PYTHON = "python"
    HTML = "html"
    SQL = "sql"
    OTHER = "other"


class ManusStepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class ManusOutputType(str, Enum):
    """输出内容类型"""
    CODE = "code"
    TEXT = "text"
    MARKDOWN = "markdown"
    TABLE = "table"
    CHART = "chart"
    JSON = "json"
    ERROR = "error"
    HTML = "html"
    IMAGE = "image"
    THOUGHT = "thought"
    SQL_QUERY = "sql_query"


class ManusArtifactType(str, Enum):
    """产物类型"""
    FILE = "file"
    TABLE = "table"
    CHART = "chart"
    IMAGE = "image"
    CODE = "code"
    MARKDOWN = "markdown"
    SUMMARY = "summary"
    HTML = "html"


class ManusPanelView(str, Enum):
    """右面板视图类型"""
    EXECUTION = "execution"
    FILES = "files"
    HTML_PREVIEW = "html-preview"
    IMAGE_PREVIEW = "image-preview"
    SKILL_PREVIEW = "skill-preview"
    SUMMARY = "summary"
    DELIVERABLE = "deliverable"


@dataclass
class ManusExecutionStep:
    """执行步骤"""
    id: str
    type: str = ManusStepType.OTHER.value
    title: str = ""
    subtitle: Optional[str] = None
    description: Optional[str] = None
    phase: Optional[str] = None
    status: str = ManusStepStatus.PENDING.value
    output: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusExecutionStep":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ManusThinkingSection:
    """思考分组 - 按阶段分组执行步骤"""
    id: str
    title: str
    content: Optional[str] = None
    is_completed: bool = False
    steps: List[ManusExecutionStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "is_completed": self.is_completed,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusThinkingSection":
        steps = [ManusExecutionStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            content=data.get("content"),
            is_completed=data.get("is_completed", False),
            steps=steps,
        )


@dataclass
class ManusArtifactItem:
    """产物项"""
    id: str
    type: str = ManusArtifactType.FILE.value
    name: str = ""
    content: Any = None
    created_at: Optional[int] = None
    downloadable: bool = False
    mime_type: Optional[str] = None
    size: Optional[int] = None
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusArtifactItem":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ManusTaskFileItem:
    """任务文件项 - AgentFileSystem 中的所有文件"""
    file_id: str
    file_name: str
    file_type: str = ""
    file_size: int = 0
    mime_type: Optional[str] = None
    oss_url: Optional[str] = None
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None
    object_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusTaskFileItem":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ManusDeliverableFile:
    """交付文件 - 获得独立 tab 的明确交付物"""
    file_id: str
    file_name: str
    mime_type: Optional[str] = None
    file_size: int = 0
    content_url: Optional[str] = None
    download_url: Optional[str] = None
    content: Optional[str] = None
    object_path: Optional[str] = None
    render_type: str = "iframe"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusDeliverableFile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ManusExecutionOutput:
    """执行输出"""
    output_type: str = ManusOutputType.TEXT.value
    content: Any = None
    timestamp: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusExecutionOutput":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ManusActiveStepInfo:
    """当前活跃步骤详情"""
    id: str
    type: str = ManusStepType.OTHER.value
    title: str = ""
    subtitle: Optional[str] = None
    status: str = ManusStepStatus.RUNNING.value
    detail: Optional[str] = None
    action: Optional[str] = None
    action_input: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusActiveStepInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ManusLeftPanelData:
    """
    左面板数据结构

    展示：
    - 分组的执行步骤（按阶段）
    - Agent 思考过程
    - 产物卡片列表
    """
    sections: List[ManusThinkingSection] = field(default_factory=list)
    active_step_id: Optional[str] = None
    is_working: bool = False
    user_query: Optional[str] = None
    assistant_text: Optional[str] = None
    model_name: Optional[str] = None
    step_thoughts: Dict[str, str] = field(default_factory=dict)
    artifacts: List[ManusArtifactItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sections": [s.to_dict() for s in self.sections],
            "active_step_id": self.active_step_id,
            "is_working": self.is_working,
            "user_query": self.user_query,
            "assistant_text": self.assistant_text,
            "model_name": self.model_name,
            "step_thoughts": self.step_thoughts,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusLeftPanelData":
        sections = [ManusThinkingSection.from_dict(s) for s in data.get("sections", [])]
        artifacts = [ManusArtifactItem.from_dict(a) for a in data.get("artifacts", [])]
        return cls(
            sections=sections,
            active_step_id=data.get("active_step_id"),
            is_working=data.get("is_working", False),
            user_query=data.get("user_query"),
            assistant_text=data.get("assistant_text"),
            model_name=data.get("model_name"),
            step_thoughts=data.get("step_thoughts", {}),
            artifacts=artifacts,
        )


@dataclass
class ManusRightPanelData:
    """
    右面板数据结构

    展示：
    - 当前步骤详情
    - 输出内容（根据类型切换渲染器）
    - 产物列表
    - 摘要内容
    """
    active_step: Optional[ManusActiveStepInfo] = None
    outputs: List[ManusExecutionOutput] = field(default_factory=list)
    is_running: bool = False
    artifacts: List[ManusArtifactItem] = field(default_factory=list)
    panel_view: str = ManusPanelView.EXECUTION.value
    summary_content: Optional[str] = None
    is_summary_streaming: bool = False
    task_files: List[ManusTaskFileItem] = field(default_factory=list)
    deliverable_files: List[ManusDeliverableFile] = field(default_factory=list)
    # Map from planning_window UID (action_id) to step data for click-to-switch
    steps_map: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_step": self.active_step.to_dict() if self.active_step else None,
            "outputs": [o.to_dict() for o in self.outputs],
            "is_running": self.is_running,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "panel_view": self.panel_view,
            "summary_content": self.summary_content,
            "is_summary_streaming": self.is_summary_streaming,
            "task_files": [f.to_dict() for f in self.task_files],
            "deliverable_files": [f.to_dict() for f in self.deliverable_files],
            "steps_map": self.steps_map,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManusRightPanelData":
        active_step = None
        if data.get("active_step"):
            active_step = ManusActiveStepInfo.from_dict(data["active_step"])
        outputs = [ManusExecutionOutput.from_dict(o) for o in data.get("outputs", [])]
        artifacts = [ManusArtifactItem.from_dict(a) for a in data.get("artifacts", [])]
        task_files = [ManusTaskFileItem.from_dict(f) for f in data.get("task_files", [])]
        deliverable_files = [ManusDeliverableFile.from_dict(f) for f in data.get("deliverable_files", [])]
        return cls(
            active_step=active_step,
            outputs=outputs,
            is_running=data.get("is_running", False),
            artifacts=artifacts,
            panel_view=data.get("panel_view", ManusPanelView.EXECUTION.value),
            summary_content=data.get("summary_content"),
            is_summary_streaming=data.get("is_summary_streaming", False),
            task_files=task_files,
            deliverable_files=deliverable_files,
            steps_map=data.get("steps_map", {}),
        )


@dataclass
class VisManusData:
    """
    vis_manus 完整数据结构

    顶层容器，包含左右两个面板的数据

    示例:
        {
            "left_panel": {
                "sections": [...],
                "active_step_id": "step_2",
                "is_working": true,
                "artifacts": [...]
            },
            "right_panel": {
                "active_step": { "id": "step_2", "type": "bash", ... },
                "outputs": [{ "output_type": "text", "content": "..." }],
                "is_running": true,
                "panel_view": "execution"
            }
        }
    """
    left_panel: ManusLeftPanelData = field(default_factory=ManusLeftPanelData)
    right_panel: ManusRightPanelData = field(default_factory=ManusRightPanelData)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left_panel": self.left_panel.to_dict(),
            "right_panel": self.right_panel.to_dict(),
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisManusData":
        left_panel = ManusLeftPanelData.from_dict(data.get("left_panel", {}))
        right_panel = ManusRightPanelData.from_dict(data.get("right_panel", {}))
        return cls(left_panel=left_panel, right_panel=right_panel)


# Action 名称到步骤类型的映射
ACTION_TO_STEP_TYPE = {
    "shell_interpreter": ManusStepType.BASH,
    "bash": ManusStepType.BASH,
    "execute_skill_script_file": ManusStepType.SKILL,
    "get_skill_resource": ManusStepType.SKILL,
    "load_skill": ManusStepType.SKILL,
    "select_skill": ManusStepType.SKILL,
    "sql_query": ManusStepType.SQL,
    "execute_sql": ManusStepType.SQL,
    "python": ManusStepType.PYTHON,
    "code_action": ManusStepType.PYTHON,
    "read_file": ManusStepType.READ,
    "write_file": ManusStepType.WRITE,
    "edit_file": ManusStepType.EDIT,
    "grep": ManusStepType.GREP,
    "glob": ManusStepType.GLOB,
    "html": ManusStepType.HTML,
    "planning": ManusStepType.TASK,
}


VIS_MANUS_PROTOCOL_VERSION = "1.0.0"
