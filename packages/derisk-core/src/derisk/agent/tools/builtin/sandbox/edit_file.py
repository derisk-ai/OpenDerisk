"""
EditFileTool - 沙箱内编辑文件工具

编辑文本文件，支持替换唯一字符串或追加内容
"""

from typing import Dict, Any, Optional
import logging

from .base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment, ToolSource
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

_EDIT_FILE_PROMPT = (
    """Edit a text file by replacing a unique string or appending new content."""
)


def _validate_required_str(value: Optional[str], field_name: str) -> Optional[str]:
    """校验必填字符串参数并返回错误信息。"""
    if value is None:
        return f"错误: {field_name} 不能为空"
    if not isinstance(value, str):
        return f"错误: {field_name} 必须是字符串"
    if not value.strip():
        return f"错误: {field_name} 不能为空字符串"
    return None


def _validate_optional_str(value: Optional[str], field_name: str) -> Optional[str]:
    """校验可选字符串参数并返回错误信息。"""
    if value is None or isinstance(value, str):
        return None
    return f"错误: {field_name} 必须是字符串"


async def _read_text_from_sandbox(client, abs_path: str) -> str:
    """读取沙箱文本文件内容。"""
    try:
        file_info = await client.file.read(abs_path)
    except Exception as exc:
        raise RuntimeError(f"读取文件失败: {exc}") from exc

    content = getattr(file_info, "content", None)
    if content is None:
        raise RuntimeError("文件内容为空或无法解析")
    return content


class EditFileTool(SandboxToolBase):
    """沙箱内编辑文件工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="edit_file",
            display_name="Edit File",
            description=_EDIT_FILE_PROMPT,
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["file", "edit", "write", "sandbox"],
            author="tuyang.yhj",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Why I'm making this edit. 注意，这是必填参数",
                },
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit.",
                },
                "old_str": {
                    "type": "string",
                    "description": "Existing string to replace. Must appear exactly once. Leave empty to append instead.",
                },
                "new_str": {
                    "type": "string",
                    "description": "Replacement or appended content. Defaults to empty, which removes old_str when replacing.",
                },
                "append": {
                    "type": "boolean",
                    "description": "Whether to append to the file instead of replacing. Defaults to False.",
                },
            },
            "required": ["description", "path"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        description = args.get("description")
        path = args.get("path")
        old_str = args.get("old_str")
        new_str = args.get("new_str", "")
        append = args.get("append", True)

        logger.info(
            f"edit_file: description={description}, path={path}, new_str={new_str}, append={append}"
        )

        # 校验参数
        error = _validate_required_str(description, "description")
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        error = _validate_required_str(path, "path")
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        error = _validate_optional_str(old_str, "old_str")
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        error = _validate_optional_str(new_str, "new_str")
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        # 检查沙箱可用性
        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法编辑文件",
                tool_name=self.name,
            )

        # 规范化路径
        from derisk.sandbox.sandbox_utils import (
            normalize_sandbox_path,
            detect_path_kind,
        )

        try:
            sandbox_path = normalize_sandbox_path(client, path)
        except ValueError as exc:
            return ToolResult.fail(error=f"错误: {exc}", tool_name=self.name)

        # 检测路径类型
        path_kind = await detect_path_kind(client, sandbox_path)
        if path_kind == "none":
            return ToolResult.fail(
                error=f"错误: 文件不存在: {sandbox_path}", tool_name=self.name
            )
        if path_kind != "file":
            return ToolResult.fail(
                error=f"错误: path 指向目录而不是文件: {sandbox_path}",
                tool_name=self.name,
            )

        # 读取文件内容
        try:
            content = await _read_text_from_sandbox(client, sandbox_path)
        except RuntimeError as exc:
            return ToolResult.fail(error=f"错误: {exc}", tool_name=self.name)

        # 处理编辑逻辑
        append_mode = old_str is None or old_str == ""
        if append_mode:
            if new_str is None:
                return ToolResult.fail(
                    error="错误: append 操作需要提供 new_str", tool_name=self.name
                )
            updated_content = content + new_str
            operation = "append"
        else:
            if old_str == "":
                return ToolResult.fail(
                    error="错误: old_str 不能为空字符串", tool_name=self.name
                )
            occurrences = content.count(old_str)
            if occurrences == 0:
                return ToolResult.fail(
                    error="错误: old_str 未在文件中找到", tool_name=self.name
                )
            if occurrences > 1:
                return ToolResult.fail(
                    error="错误: old_str 在文件中出现多次，拒绝替换",
                    tool_name=self.name,
                )
            updated_content = content.replace(old_str, new_str, 1)
            operation = "replace"

        if updated_content == content:
            return ToolResult.ok(output="提示: 文件内容未发生变化", tool_name=self.name)

        # 写入文件
        try:
            await client.file.write(
                path=sandbox_path, data=updated_content, overwrite=append
            )
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 写入文件失败 ({sandbox_path}): {exc}",
                tool_name=self.name,
            )

        output = f"文件已更新: {sandbox_path}，操作: {operation}，描述: {description.strip()}"
        return ToolResult.ok(output=output, tool_name=self.name)
