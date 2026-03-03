"""
Core V2 VIS 协议定义

定义前端 vis_window3 组件所需的数据结构和协议规范
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactType(str, Enum):
    """产物类型"""
    TOOL_OUTPUT = "tool_output"
    LLM_OUTPUT = "llm_output"
    FILE = "file"
    IMAGE = "image"
    CODE = "code"
    REPORT = "report"


@dataclass
class PlanningStep:
    """
    规划窗口步骤
    
    用于展示 Agent 的执行步骤和进度
    """
    step_id: str
    title: str
    status: str = StepStatus.PENDING.value
    result_summary: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    layer_count: int = 0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanningStep":
        return cls(**data)


@dataclass
class RunningArtifact:
    """
    运行窗口产物
    
    用于展示当前步骤的详细输出内容
    """
    artifact_id: str
    type: str
    content: str
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunningArtifact":
        return cls(**data)


@dataclass
class CurrentStep:
    """当前执行步骤信息"""
    step_id: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CurrentStep":
        return cls(**data)


@dataclass
class PlanningWindow:
    """
    规划窗口数据结构
    
    显示所有步骤的列表和当前执行状态
    
    前端展示：
    - 左侧：步骤列表（可折叠）
    - 右侧：步骤详情
    - 状态指示器：pending/running/completed/failed
    """
    steps: List[PlanningStep] = field(default_factory=list)
    current_step_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "current_step_id": self.current_step_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanningWindow":
        steps = [PlanningStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            steps=steps,
            current_step_id=data.get("current_step_id"),
        )


@dataclass
class RunningWindow:
    """
    运行窗口数据结构
    
    显示当前步骤的详细内容和产物
    
    前端展示：
    - 思考过程（可折叠）
    - 主要内容
    - 产物列表（文件、图片、代码等）
    """
    current_step: Optional[CurrentStep] = None
    thinking: Optional[str] = None
    content: Optional[str] = None
    artifacts: List[RunningArtifact] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_step": self.current_step.to_dict() if self.current_step else None,
            "thinking": self.thinking,
            "content": self.content,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunningWindow":
        current_step = None
        if data.get("current_step"):
            current_step = CurrentStep.from_dict(data["current_step"])
        
        artifacts = [
            RunningArtifact.from_dict(a) 
            for a in data.get("artifacts", [])
        ]
        
        return cls(
            current_step=current_step,
            thinking=data.get("thinking"),
            content=data.get("content"),
            artifacts=artifacts,
        )


@dataclass
class VisWindow3Data:
    """
    vis_window3 完整数据结构
    
    这是前端 vis_window3 组件所需的标准数据格式
    
    示例:
        {
            "planning_window": {
                "steps": [
                    {
                        "step_id": "1",
                        "title": "分析需求",
                        "status": "completed",
                        "result_summary": "已完成需求分析"
                    },
                    {
                        "step_id": "2",
                        "title": "执行查询",
                        "status": "running"
                    }
                ],
                "current_step_id": "2"
            },
            "running_window": {
                "current_step": {
                    "step_id": "2",
                    "title": "执行查询",
                    "status": "running"
                },
                "thinking": "正在分析查询条件...",
                "content": "执行 SQL 查询...",
                "artifacts": [
                    {
                        "artifact_id": "result",
                        "type": "tool_output",
                        "title": "查询结果",
                        "content": "..."
                    }
                ]
            }
        }
    """
    planning_window: PlanningWindow = field(default_factory=PlanningWindow)
    running_window: RunningWindow = field(default_factory=RunningWindow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning_window": self.planning_window.to_dict(),
            "running_window": self.running_window.to_dict(),
        }
    
    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisWindow3Data":
        planning_window = PlanningWindow.from_dict(
            data.get("planning_window", {})
        )
        running_window = RunningWindow.from_dict(
            data.get("running_window", {})
        )
        return cls(
            planning_window=planning_window,
            running_window=running_window,
        )


VIS_PROTOCOL_VERSION = "1.0.0"


VIS_WINDOW3_SPEC = {
    "version": VIS_PROTOCOL_VERSION,
    "description": "vis_window3 组件数据协议",
    "components": {
        "planning_window": {
            "description": "规划窗口，展示所有步骤",
            "fields": {
                "steps": "步骤列表",
                "current_step_id": "当前执行步骤ID",
            },
            "step_fields": {
                "step_id": "步骤唯一标识",
                "title": "步骤标题",
                "status": "步骤状态 (pending|running|completed|failed)",
                "result_summary": "结果摘要",
                "agent_name": "执行Agent名称",
                "agent_role": "执行Agent角色",
                "layer_count": "层级深度（用于嵌套展示）",
                "start_time": "开始时间 (ISO 8601)",
                "end_time": "结束时间 (ISO 8601)",
            },
        },
        "running_window": {
            "description": "运行窗口，展示当前步骤详情",
            "fields": {
                "current_step": "当前步骤信息",
                "thinking": "思考过程",
                "content": "主要内容",
                "artifacts": "产物列表",
            },
            "artifact_fields": {
                "artifact_id": "产物唯一标识",
                "type": "产物类型 (tool_output|llm_output|file|image|code|report)",
                "title": "产物标题",
                "content": "产物内容",
                "metadata": "额外元数据",
            },
        },
    },
    "update_modes": {
        "ALL": "全量替换",
        "INCR": "增量更新（仅更新变更部分）",
    },
    "frontend_requirements": [
        "支持 Markdown 渲染",
        "支持代码高亮",
        "支持图片预览",
        "支持文件下载",
        "支持步骤状态实时更新",
        "支持增量数据合并",
    ],
}