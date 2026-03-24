"""
交互工具模块 - 已迁移到统一工具框架

提供Agent与用户的交互能力：
- AskUserTool: 统一的用户交互工具（渲染drsk-confirm VIS组件，暂停Agent等待用户响应）
"""

from typing import Any, Dict, List, Optional
import json
import logging
import uuid

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class AskUserTool(ToolBase):
    """
    用户交互工具 - 向用户提问并等待回复（Human-in-the-Loop）

    这是与用户交互的唯一工具，渲染 drsk-confirm VIS 组件，
    触发 Agent 执行循环暂停，等待用户在前端界面中做出选择或输入。

    使用场景：
    - 缺少关键参数需要用户补充
    - 发现歧义需要用户澄清
    - 敏感操作需要用户确认
    - 需要用户做出选择
    - 多种方案需要用户选择
    - 请求人工协助（urgency 参数）
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ask_user",
            display_name="Ask User",
            description=(
                "Ask the user a structured question and wait for their response. "
                "This tool pauses the agent execution and presents an interactive UI "
                "to the user with options to select from or free-text input.\n\n"
                "Use this tool when you need to:\n"
                "- Clarify ambiguous instructions\n"
                "- Get user confirmation before risky operations\n"
                "- Let user choose between multiple approaches\n"
                "- Collect missing required parameters\n"
                "- Request human assistance when stuck (set urgency)\n\n"
                "Example with options:\n"
                '```json\n'
                '{\n'
                '  "questions": [{\n'
                '    "question": "Which database should we use?",\n'
                '    "header": "Database Selection",\n'
                '    "options": [\n'
                '      {"label": "MySQL", "description": "Relational database"},\n'
                '      {"label": "MongoDB", "description": "Document database"}\n'
                '    ]\n'
                '  }]\n'
                '}\n'
                '```\n\n'
                "Example with inline input:\n"
                '```json\n'
                '{\n'
                '  "questions": [{\n'
                '    "question": "Please confirm the edit",\n'
                '    "header": "Content Confirmation",\n'
                '    "options": [\n'
                '      {"label": "Looks good, continue", "description": "Satisfied with current result"},\n'
                '      {"label": "Need changes", "description": "Has adjustment needs", '
                '"requires_input": true, "input_placeholder": "Describe what to change..."}\n'
                '    ]\n'
                '  }]\n'
                '}\n'
                '```'
            ),
            category=ToolCategory.USER_INTERACTION,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["interaction", "ask-user", "human-in-the-loop", "confirm", "question"],
            timeout=600,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": (
                        "List of questions. Each question has:\n"
                        "- question (str, required): The question text\n"
                        "- header (str): Short title\n"
                        "- options (array): Choices, each with label, description, "
                        "requires_input (bool), input_placeholder (str)\n"
                        "- multiple (bool): Allow multi-select"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "The question text"},
                            "header": {"type": "string", "description": "Short title (max 30 chars)"},
                            "options": {
                                "type": "array",
                                "description": "Available choices",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string", "description": "Option label"},
                                        "description": {"type": "string", "description": "Option description"},
                                        "requires_input": {
                                            "type": "boolean",
                                            "description": "Show input box when selected",
                                            "default": False,
                                        },
                                        "input_placeholder": {
                                            "type": "string",
                                            "description": "Input placeholder text",
                                        },
                                        "input_required": {
                                            "type": "boolean",
                                            "description": "Whether input is required",
                                            "default": True,
                                        },
                                    },
                                    "required": ["label"],
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
                "header": {
                    "type": "string",
                    "description": "Overall header displayed above questions",
                },
                "urgency": {
                    "type": "string",
                    "description": "Urgency level when requesting human assistance",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for the question",
                },
            },
            "required": ["questions"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        questions = args.get("questions", [])
        header = args.get("header", "")
        urgency = args.get("urgency", "medium")
        extra_context = args.get("context", "")

        if not questions or not isinstance(questions, list):
            return ToolResult(
                success=False,
                output="",
                error="ask_user requires a non-empty 'questions' parameter",
                tool_name=self.name,
            )

        # Validate each question
        for i, q in enumerate(questions):
            if not isinstance(q, dict) or not q.get("question"):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Question at index {i} is missing 'question' field",
                    tool_name=self.name,
                )

        request_id = str(uuid.uuid4().hex)

        # Build drsk-confirm VIS component data
        vis_data = {
            "header": header or "Needs your confirmation",
            "questions": questions,
            "request_id": request_id,
            "allow_custom_input": True,
        }
        if urgency and urgency != "medium":
            vis_data["urgency"] = urgency
        if extra_context:
            vis_data["context"] = extra_context

        vis_output = f"```drsk-confirm\n{json.dumps(vis_data, indent=2, ensure_ascii=False)}\n```"

        return ToolResult(
            success=True,
            output=vis_output,
            tool_name=self.name,
            metadata={
                "ask_user": True,
                "request_id": request_id,
                "terminate": True,
                "questions": questions,
                "header": header,
                "urgency": urgency,
            },
        )


# 向后兼容别名
QuestionTool = AskUserTool


def register_interaction_tools(
    registry: Any,
    interaction_manager: Optional[Any] = None,
    progress_broadcaster: Optional[Any] = None,
) -> Any:
    """注册用户交互工具到统一框架"""
    from ...registry import ToolRegistry

    registry.register(AskUserTool())

    logger.info("[InteractionTools] 已注册 1 个交互工具: ask_user")

    return registry
