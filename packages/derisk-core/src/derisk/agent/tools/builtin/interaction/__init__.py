"""
交互工具模块 - 已迁移到统一工具框架

提供Agent与用户的交互能力：
- QuestionTool: 提问用户（支持选项、紧急程度）
- ConfirmTool: 确认操作
- NotifyTool: 通知消息
- ProgressTool: 进度更新
- FileSelectTool: 文件选择

已合并：AskHumanTool 功能已合并到 QuestionTool
"""

from typing import Any, Dict, List, Optional
import logging
import asyncio

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class QuestionTool(ToolBase):
    """
    提问用户工具 - 支持结构化问卷和开放式问题

    用途：
    1. 收集用户偏好、澄清模糊指令
    2. 获取实现决策
    3. 请求人工协助（urgency 参数）
    """

    def __init__(self, interaction_manager: Optional[Any] = None):
        self._interaction_manager = interaction_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="question",
            display_name="Ask Question",
            description=(
                "Ask the user a question and wait for their response. "
                "Use this tool when you need to:\n"
                "1. Gather user preferences or clarify ambiguous instructions\n"
                "2. Get decisions on implementation choices\n"
                "3. Offer choices to the user about what direction to take\n"
                "4. Request human assistance when you cannot handle a situation (set urgency)"
            ),
            category=ToolCategory.USER_INTERACTION,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["interaction", "question", "user-input", "ask-human"],
            timeout=600,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "List of questions to ask (can be single question)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Complete question to ask",
                            },
                            "header": {
                                "type": "string",
                                "description": "Very short label (max 30 chars)",
                            },
                            "options": {
                                "type": "array",
                                "description": "Available choices (omit for open-ended question)",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                },
                            },
                            "multiple": {
                                "type": "boolean",
                                "description": "Allow selecting multiple choices",
                                "default": False,
                            },
                        },
                        "required": ["question"],
                    },
                },
                "urgency": {
                    "type": "string",
                    "description": "Urgency level when requesting human assistance",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context when requesting human assistance",
                },
            },
            "required": ["questions"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        questions = args.get("questions", [])
        urgency = args.get("urgency", "medium")
        extra_context = args.get("context", "")

        if not questions:
            return ToolResult(
                success=False, output="", error="至少需要一个提问", tool_name=self.name
            )

        has_options = any(q.get("options") for q in questions)

        if self._interaction_manager:
            try:
                if has_options:
                    response = await self._interaction_manager.ask(
                        questions=questions, context=context
                    )
                else:
                    first_question = questions[0].get("question", "")
                    response = await self._interaction_manager.ask_human(
                        question=first_question,
                        context=extra_context,
                        urgency=urgency,
                        tool_context=context,
                    )
                return ToolResult(
                    success=True,
                    output=response.get("answer", ""),
                    tool_name=self.name,
                    metadata={
                        "responses": response.get("responses", []),
                        "urgency": urgency,
                    },
                )
            except Exception as e:
                logger.error(f"[QuestionTool] 交互管理器调用失败: {e}")

        if has_options:
            options_text = []
            for q in questions:
                header = q.get("header", "Question")
                question_text = q.get("question", "")
                options = q.get("options", [])
                multiple = q.get("multiple", False)

                opts = []
                for i, opt in enumerate(options):
                    label = opt.get("label", f"Option {i + 1}")
                    desc = opt.get("description", "")
                    opts.append(f"  [{i + 1}] {label}: {desc}")

                options_text.append(
                    f"【{header}】\n{question_text}\n"
                    + ("(可多选)\n" if multiple else "")
                    + "\n".join(opts)
                )

            return ToolResult(
                success=True,
                output="[等待用户回答]\n" + "\n\n".join(options_text),
                tool_name=self.name,
                metadata={"requires_user_input": True, "questions": questions},
            )
        else:
            urgency_icons = {"low": "🟢", "medium": "🟡", "high": "🔴"}
            icon = urgency_icons.get(urgency, "🟡")

            first_question = questions[0].get("question", "")
            output = (
                f"{icon} [等待用户回答 - {urgency.upper()}]\n问题: {first_question}"
            )
            if extra_context:
                output += f"\n上下文: {extra_context}"

            return ToolResult(
                success=True,
                output=output,
                tool_name=self.name,
                metadata={
                    "requires_user_input": True,
                    "question": first_question,
                    "urgency": urgency,
                },
            )


class ConfirmTool(ToolBase):
    """确认操作工具 - 已迁移"""

    def __init__(self, interaction_manager: Optional[Any] = None):
        self._interaction_manager = interaction_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="confirm",
            display_name="Confirm Action",
            description=(
                "Ask the user for confirmation before proceeding. "
                "Use this tool when about to perform potentially destructive operations "
                "or when you need explicit user approval."
            ),
            category=ToolCategory.USER_INTERACTION,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            tags=["interaction", "confirm", "approval"],
            timeout=60,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Confirmation message to display",
                },
                "default": {
                    "type": "boolean",
                    "description": "Default value if user doesn't respond",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds for response",
                    "default": 60,
                },
            },
            "required": ["message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        message = args.get("message", "")
        default = args.get("default", False)
        timeout = args.get("timeout", 60)

        if not message:
            return ToolResult(
                success=False, output="", error="确认消息不能为空", tool_name=self.name
            )

        if self._interaction_manager:
            try:
                response = await self._interaction_manager.confirm(
                    message=message, default=default, timeout=timeout, context=context
                )
                return ToolResult(
                    success=True,
                    output=f"用户确认: {'是' if response else '否'}",
                    tool_name=self.name,
                    metadata={"confirmed": response},
                )
            except Exception as e:
                logger.error(f"[ConfirmTool] 交互管理器调用失败: {e}")

        return ToolResult(
            success=True,
            output=f"[等待用户确认] {message}",
            tool_name=self.name,
            metadata={
                "requires_user_confirmation": True,
                "message": message,
                "default": default,
            },
        )


class NotifyTool(ToolBase):
    """通知消息工具 - 已迁移"""

    def __init__(self, interaction_manager: Optional[Any] = None):
        self._interaction_manager = interaction_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="notify",
            display_name="Send Notification",
            description=(
                "Send a notification to the user. "
                "Use this to inform the user about progress, status changes, "
                "or important information without requiring a response."
            ),
            category=ToolCategory.USER_INTERACTION,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["interaction", "notification", "message"],
            timeout=10,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Notification message"},
                "level": {
                    "type": "string",
                    "description": "Notification level",
                    "enum": ["info", "warning", "error", "success"],
                    "default": "info",
                },
                "title": {
                    "type": "string",
                    "description": "Optional title for the notification",
                },
            },
            "required": ["message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        message = args.get("message", "")
        level = args.get("level", "info")
        title = args.get("title", "")

        if not message:
            return ToolResult(
                success=False, output="", error="通知消息不能为空", tool_name=self.name
            )

        if self._interaction_manager:
            try:
                await self._interaction_manager.notify(
                    message=message, level=level, title=title, context=context
                )
            except Exception as e:
                logger.error(f"[NotifyTool] 交互管理器调用失败: {e}")

        level_icons = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}
        icon = level_icons.get(level, "ℹ️")

        output = f"{icon} [{level.upper()}]"
        if title:
            output += f" {title}"
        output += f"\n{message}"

        return ToolResult(
            success=True,
            output=output,
            tool_name=self.name,
            metadata={"level": level, "title": title},
        )


class ProgressTool(ToolBase):
    """进度更新工具 - 已迁移"""

    def __init__(self, progress_broadcaster: Optional[Any] = None):
        self._progress_broadcaster = progress_broadcaster
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="progress",
            display_name="Report Progress",
            description=(
                "Report progress on a long-running task. "
                "Use this to keep the user informed about the status of complex operations."
            ),
            category=ToolCategory.USER_INTERACTION,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["interaction", "progress", "status"],
            timeout=10,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "current": {"type": "integer", "description": "Current progress value"},
                "total": {
                    "type": "integer",
                    "description": "Total value (100 for percentage)",
                },
                "message": {"type": "string", "description": "Progress message"},
                "phase": {
                    "type": "string",
                    "description": "Current phase name",
                    "enum": ["starting", "running", "completed", "error"],
                    "default": "running",
                },
            },
            "required": ["current", "total", "message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        current = args.get("current", 0)
        total = args.get("total", 100)
        message = args.get("message", "")
        phase = args.get("phase", "running")

        if total <= 0:
            return ToolResult(
                success=False, output="", error="总数必须大于0", tool_name=self.name
            )

        percentage = (current / total) * 100

        if self._progress_broadcaster:
            try:
                await self._progress_broadcaster.broadcast(
                    event_type="progress",
                    data={
                        "current": current,
                        "total": total,
                        "percentage": percentage,
                        "message": message,
                        "phase": phase,
                    },
                    context=context,
                )
            except Exception as e:
                logger.error(f"[ProgressTool] 进度广播失败: {e}")

        progress_bar = self._render_progress_bar(percentage)

        return ToolResult(
            success=True,
            output=f"[{phase.upper()}] {progress_bar} {percentage:.1f}%\n{message}",
            tool_name=self.name,
            metadata={
                "current": current,
                "total": total,
                "percentage": percentage,
                "phase": phase,
            },
        )

    def _render_progress_bar(self, percentage: float, width: int = 20) -> str:
        filled = int(percentage / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"


class FileSelectTool(ToolBase):
    """文件选择工具 - 已迁移"""

    def __init__(self, interaction_manager: Optional[Any] = None):
        self._interaction_manager = interaction_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="file_select",
            display_name="Select File",
            description=(
                "Ask user to select a file. Use when you need the user "
                "to choose a specific file for processing."
            ),
            category=ToolCategory.USER_INTERACTION,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["interaction", "file", "selection"],
            timeout=300,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to display"},
                "file_types": {
                    "type": "array",
                    "description": "Allowed file types/extensions",
                    "items": {"type": "string"},
                    "default": ["*"],
                },
                "multiple": {
                    "type": "boolean",
                    "description": "Allow multiple file selection",
                    "default": False,
                },
                "start_dir": {"type": "string", "description": "Starting directory"},
            },
            "required": ["message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        message = args.get("message", "请选择文件")
        file_types = args.get("file_types", ["*"])
        multiple = args.get("multiple", False)
        start_dir = args.get("start_dir", ".")

        if self._interaction_manager:
            try:
                response = await self._interaction_manager.select_file(
                    message=message,
                    file_types=file_types,
                    multiple=multiple,
                    start_dir=start_dir,
                    context=context,
                )
                return ToolResult(
                    success=True,
                    output=str(response.get("files", [])),
                    tool_name=self.name,
                    metadata={"files": response.get("files", [])},
                )
            except Exception as e:
                logger.error(f"[FileSelectTool] 交互管理器调用失败: {e}")

        types_str = ", ".join(file_types) if file_types != ["*"] else "所有类型"
        output = f"[等待用户选择文件]\n{message}\n文件类型: {types_str}"
        if multiple:
            output += " (可多选)"

        return ToolResult(
            success=True,
            output=output,
            tool_name=self.name,
            metadata={
                "requires_file_selection": True,
                "file_types": file_types,
                "multiple": multiple,
            },
        )


def register_interaction_tools(
    registry: Any,
    interaction_manager: Optional[Any] = None,
    progress_broadcaster: Optional[Any] = None,
) -> Any:
    """注册所有用户交互工具到统一框架"""
    from ...registry import ToolRegistry

    registry.register(QuestionTool(interaction_manager))
    registry.register(ConfirmTool(interaction_manager))
    registry.register(NotifyTool(interaction_manager))
    registry.register(ProgressTool(progress_broadcaster))
    registry.register(FileSelectTool(interaction_manager))

    logger.info("[InteractionTools] 已注册 5 个交互工具到统一框架")

    return registry
