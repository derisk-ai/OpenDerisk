"""
优化后的数据模型 - 重构版本
核心改进：
1. 单层Stage架构，取消Task和TaskStep层
2. 消除generate_overview和generate_current_stage_detail之间的重复代码
3. 提取通用的格式化辅助方法
4. 使用统一的 WorkEntry 模型（来自 memory.gpts.file_base）
"""

import time
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# 使用统一的 WorkEntry 模型
from derisk.agent.core.memory.gpts.file_base import WorkEntry as BaseWorkEntry


class StageStatus(str, Enum):
    """阶段状态：只有3种"""

    WORKING = "working"  # 工作中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class WorkEntry(BaseWorkEntry):
    """
    工作日志条目（向后兼容层）

    继承自统一的 BaseWorkEntry，添加向后兼容的便捷方法。
    """

    def to_dict(self) -> Dict:
        """序列化为字典（向后兼容格式）"""
        return {
            "timestamp": self.timestamp,
            "tool": self.tool,
            "result": self.result,
            "summary": self.summary,
            "archives": self.archives,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WorkEntry":
        """从字典反序列化（向后兼容）"""
        return cls(
            timestamp=data.get("timestamp", time.time()),
            tool=data.get("tool", ""),
            summary=data.get("summary"),
            result=data.get("result"),
            archives=data.get("archives"),
        )


@dataclass
class Stage:
    """
    阶段：看板的核心单元
    每个阶段有明确的交付物定义，以结论为导向
    """

    stage_id: str  # 阶段唯一标识（如 "s1_research"）
    description: str  # 阶段描述（如 "收集市场数据"）
    status: str = StageStatus.WORKING.value  # 阶段状态

    # 交付物定义
    deliverable_type: str = ""  # 交付物类型（如 "market_data", "analysis_report"）
    deliverable_schema: Dict = field(default_factory=dict)  # JSON Schema格式的结构定义
    deliverable_file: str = ""  # 交付物文件路径（完成后填充）

    # 执行记录
    work_log: List[WorkEntry] = field(default_factory=list)  # 工作日志
    started_at: float = 0.0  # 开始时间
    completed_at: float = 0.0  # 完成时间

    # 依赖关系
    depends_on: List[str] = field(default_factory=list)  # 依赖的前置Stage ID列表

    # 元数据
    reflection: str = ""  # Agent的自我评估（提交时填写）

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "stage_id": self.stage_id,
            "description": self.description,
            "status": self.status,
            "deliverable_type": self.deliverable_type,
            "deliverable_schema": self.deliverable_schema,
            "deliverable_file": self.deliverable_file,
            "work_log": [entry.to_dict() for entry in self.work_log],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "depends_on": self.depends_on,
            "reflection": self.reflection,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Stage":
        """从字典反序列化"""
        work_log_data = data.pop("work_log", [])
        work_log = [WorkEntry(**entry) for entry in work_log_data]
        return cls(work_log=work_log, **data)

    def add_work_entry(self, tool: str, summary: str):
        """添加工作日志条目"""
        entry = WorkEntry(timestamp=time.time(), tool=tool, summary=summary)
        self.work_log.append(entry)

    def is_completed(self) -> bool:
        """判断是否已完成"""
        return self.status == StageStatus.COMPLETED.value

    def is_working(self) -> bool:
        """判断是否工作中"""
        return self.status == StageStatus.WORKING.value


@dataclass
class Kanban:
    """
    看板：线性Stage序列
    代表整个任务的执行计划
    """

    kanban_id: str  # 看板唯一标识
    mission: str  # 用户的原始任务描述
    stages: List[Stage] = field(default_factory=list)  # 阶段列表
    current_stage_index: int = 0  # 当前正在执行的Stage索引
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "kanban_id": self.kanban_id,
            "mission": self.mission,
            "stages": [stage.to_dict() for stage in self.stages],
            "current_stage_index": self.current_stage_index,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Kanban":
        """从字典反序列化"""
        stages_data = data.pop("stages", [])
        stages = [Stage.from_dict(s) for s in stages_data]
        return cls(stages=stages, **data)

    def get_current_stage(self) -> Optional[Stage]:
        """获取当前正在执行的阶段"""
        if 0 <= self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def get_next_stage(self, current_stage_id: str) -> Optional[Stage]:
        """获取指定stage_id的下一个阶段"""
        for i, stage in enumerate(self.stages):
            if stage.stage_id == current_stage_id and i < len(self.stages) - 1:
                return self.stages[i + 1]
        return None

    def get_stage_by_id(self, stage_id: str) -> Optional[Stage]:
        """根据ID查找阶段"""
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    def get_completed_stages(self) -> List[Stage]:
        """获取所有已完成的阶段"""
        return [s for s in self.stages if s.is_completed()]

    def get_pending_stages(self) -> List[Stage]:
        """获取所有待执行的阶段"""
        return [s for s in self.stages[self.current_stage_index + 1 :]]

    def is_all_completed(self) -> bool:
        """判断是否所有阶段都已完成"""
        return all(stage.is_completed() for stage in self.stages)

    def advance_to_next_stage(self) -> bool:
        """推进到下一阶段"""
        if self.current_stage_index < len(self.stages) - 1:
            self.current_stage_index += 1
            next_stage = self.get_current_stage()
            if next_stage:
                next_stage.status = StageStatus.WORKING.value
                next_stage.started_at = time.time()
            return True
        return False

    # ==================== 辅助格式化方法 (消除重复代码) ====================

    @staticmethod
    def _format_timestamp(timestamp: float, format_type: str = "full") -> str:
        """
        统一的时间戳格式化方法

        Args:
            timestamp: Unix时间戳
            format_type: 格式类型 ("full" 或 "time")

        Returns:
            格式化后的时间字符串
        """
        if format_type == "time":
            return time.strftime("%H:%M:%S", time.localtime(timestamp))
        else:  # full
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

    def _format_progress_bar(self) -> str:
        """
        生成进度条

        Returns:
            进度条字符串
        """
        progress_icons = []
        for i, stage in enumerate(self.stages):
            if stage.is_completed():
                icon = "✅"
            elif i == self.current_stage_index:
                icon = "🔄"
            else:
                icon = "⏳"
            progress_icons.append(f"[{icon} {stage.stage_id}]")

        return " -> ".join(progress_icons)

    def _format_completed_stages(self) -> List[str]:
        """
        格式化已完成阶段列表

        Returns:
            格式化后的行列表
        """
        completed = self.get_completed_stages()
        if not completed:
            return []

        lines = ["## Completed Stages"]
        for stage in completed:
            lines.append(f"- **stage_id='{stage.stage_id}'**: {stage.description}")
            lines.append(f"  - Deliverable: `{stage.deliverable_file}`")
            lines.append(
                f"  - Completed at: {self._format_timestamp(stage.completed_at)}"
            )
            if stage.reflection:
                lines.append(f"  - Reflection: {stage.reflection}")
        lines.append("")

        return lines

    def _format_current_stage_summary(self) -> List[str]:
        """
        格式化当前阶段摘要（用于overview）

        Returns:
            格式化后的行列表
        """
        current = self.get_current_stage()
        if not current or current.is_completed():
            return []

        lines = [
            "## Current Stage",
            f"**{current.stage_id}**: {current.description}",
            f"Status: {current.status}",
            "",
        ]

        return lines

    def _format_current_stage_detail(self) -> List[str]:
        """
        格式化当前阶段详细信息（用于detail视图）

        Returns:
            格式化后的行列表
        """
        current = self.get_current_stage()
        if not current:
            return ["No active stage."]

        lines = [
            f"### Current Stage: {current.stage_id}",
            "",
            f"**Description**: {current.description}",
            f"**Status**: {current.status}",
            f"**Deliverable Type**: {current.deliverable_type}",
            "",
            "#### Expected Deliverable Schema",
            "```json",
            self._format_json(current.deliverable_schema),
            "```",
            "",
        ]

        # 依赖关系
        if current.depends_on:
            lines.append("#### Dependencies")
            lines.append(f"This stage depends on: {', '.join(current.depends_on)}")
            lines.append("")

        return lines

    def _format_work_log(self, work_log: List[WorkEntry]) -> List[str]:
        """
        格式化工作日志

        Args:
            work_log: 工作日志列表

        Returns:
            格式化后的行列表
        """
        lines = ["## Work Log"]

        if work_log:
            for i, entry in enumerate(work_log, 1):
                timestamp_str = self._format_timestamp(entry.timestamp, "time")
                lines.append(f"{i}. [{timestamp_str}] `{entry.tool}`: {entry.summary}")
        else:
            lines.append("(No work done yet)")

        lines.append("")
        return lines

    def _format_pending_stages(self) -> List[str]:
        """
        格式化待执行阶段列表

        Returns:
            格式化后的行列表
        """
        pending = self.get_pending_stages()
        if not pending:
            return []

        lines = ["## Pending Stages"]
        for stage in pending:
            lines.append(f"- **{stage.stage_id}**: {stage.description}")
        lines.append("")

        return lines

    @staticmethod
    def _format_json(obj: Any, indent: int = 2) -> str:
        """格式化JSON对象"""
        import json

        return json.dumps(obj, indent=indent, ensure_ascii=False)

    # ==================== 公共生成方法 (使用辅助方法重构) ====================

    def generate_overview(self) -> str:
        """
        生成看板概览（Markdown格式）
        用于注入到Prompt中
        """
        lines = [f"# Kanban Overview", f"Mission: {self.mission}", f"", "## Progress"]

        # 使用辅助方法生成各部分内容
        lines.append(self._format_progress_bar())
        lines.append("")

        lines.extend(self._format_completed_stages())
        lines.extend(self._format_current_stage_summary())
        lines.extend(self._format_pending_stages())

        return "\n".join(lines)

    def generate_current_stage_detail(self) -> str:
        """
        生成当前阶段的详细信息（Markdown格式）
        用于注入到Prompt中
        """
        current = self.get_current_stage()
        if not current:
            return "No active stage."

        lines = []

        # 使用辅助方法生成各部分内容
        lines.extend(self._format_current_stage_detail())
        lines.extend(self._format_work_log(current.work_log))

        return "\n".join(lines)

    def generate_available_deliverables(self) -> str:
        """
        生成可用交付物列表（Markdown格式）
        用于注入到Prompt中
        """
        completed = self.get_completed_stages()
        if not completed:
            return "No deliverables available yet."

        lines = [
            "# Available Deliverables",
            "",
            "You can read the following deliverables using `read_deliverable` tool:",
            "",
        ]

        for stage in completed:
            lines.append(f"- **{stage.stage_id}** ({stage.deliverable_type})")
            lines.append(f"  - File: `{stage.deliverable_file}`")
            lines.append(f"  - Description: {stage.description}")
            lines.append("")

        return "\n".join(lines)


# ==================== 辅助函数 ====================


def create_stage_from_spec(spec: Dict) -> Stage:
    """
    从规格字典创建Stage对象
    用于create_kanban工具
    """
    return Stage(
        stage_id=spec.get("stage_id", ""),
        description=spec.get("description", ""),
        deliverable_type=spec.get("deliverable_type", ""),
        deliverable_schema=spec.get("deliverable_schema", {}),
        depends_on=spec.get("depends_on", []),
        status=StageStatus.WORKING.value
        if spec.get("is_first", False)
        else StageStatus.WORKING.value,
    )


def validate_deliverable_schema(deliverable: Dict, schema: Dict) -> tuple[bool, str]:
    """
    验证交付物是否符合Schema
    返回: (是否有效, 错误信息)
    """
    try:
        from jsonschema import validate, ValidationError

        validate(instance=deliverable, schema=schema)
        return True, "Valid"
    except ValidationError as e:
        return False, str(e)
    except ImportError:
        # 如果没有安装jsonschema，进行简单的类型检查
        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})

        # 检查必填字段
        for field in required_fields:
            if field not in deliverable:
                return False, f"Missing required field: {field}"

        # 检查字段类型
        for field, value in deliverable.items():
            if field in properties:
                expected_type = properties[field].get("type")
                actual_type = type(value).__name__

                type_mapping = {
                    "string": "str",
                    "number": ("int", "float"),
                    "integer": "int",
                    "boolean": "bool",
                    "array": "list",
                    "object": "dict",
                }

                expected_python_type = type_mapping.get(expected_type, expected_type)
                if isinstance(expected_python_type, tuple):
                    if actual_type not in expected_python_type:
                        return (
                            False,
                            f"Field '{field}' type mismatch: expected {expected_type}, got {actual_type}",
                        )
                elif actual_type != expected_python_type:
                    return (
                        False,
                        f"Field '{field}' type mismatch: expected {expected_type}, got {actual_type}",
                    )

        return True, "Valid (basic validation)"
