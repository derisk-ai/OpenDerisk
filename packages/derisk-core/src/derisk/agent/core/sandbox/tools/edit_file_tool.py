import logging
from typing import Optional

from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool
from derisk.sandbox.base import SandboxBase
from derisk.sandbox.sandbox_utils import normalize_sandbox_path, detect_path_kind
logger = logging.getLogger(__name__)

_EDIT_FILE_PROMPT = """Edit a text file by replacing a unique string or appending new content."""


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


@sandbox_tool(
    name="edit_file",
    description=_EDIT_FILE_PROMPT,
    input_schema={
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
                "description": "Whether to append to the file instead of replacing. "
                               "Defaults to False.",
            }
        },
        "required": ["description", "path"],
    },
    owner="tuyang.yhj"
)
async def execute_edit_file(
    client: SandboxBase,
    description: str,
    path: str,
    old_str: Optional[str] = None,
    new_str: str = "",
    append: bool = True,
) -> str:
    """
    编辑文本文件，支持替换唯一字符串或追加内容。

    Args:
        description: 编辑原因描述
        path: 文件绝对路径
        old_str: 要替换的原字符串。为空字符串或缺省时执行追加
        new_str: 替换或追加内容
        append: 是否追加
    """
    logger.info(f"edit_file: description={description}, path={path}, new_str={new_str}, append={append}")
    error = _validate_required_str(description, "description")
    if error:
        return error

    error = _validate_required_str(path, "path")
    if error:
        return error

    error = _validate_optional_str(old_str, "old_str")
    if error:
        return error

    error = _validate_optional_str(new_str, "new_str")
    if error:
        return error

    if client is None:
        return "错误: 当前任务未初始化沙箱环境，无法编辑文件"

    try:
        sandbox_path = normalize_sandbox_path(client, path)
    except ValueError as exc:
        return f"错误: {exc}"

    path_kind = await detect_path_kind(client, sandbox_path)
    if path_kind == "none":
        return f"错误: 文件不存在: {sandbox_path}"
    if path_kind != "file":
        return f"错误: path 指向目录而不是文件: {sandbox_path}"

    try:
        content = await _read_text_from_sandbox(client, sandbox_path)
    except RuntimeError as exc:
        return f"错误: {exc}"

    append_mode = old_str is None or old_str == ""
    if append_mode:
        if new_str is None:
            return "错误: append 操作需要提供 new_str"
        updated_content = content + new_str
        operation = "append"
    else:
        if old_str == "":
            return "错误: old_str 不能为空字符串"
        occurrences = content.count(old_str)
        if occurrences == 0:
            return "错误: old_str 未在文件中找到"
        if occurrences > 1:
            return "错误: old_str 在文件中出现多次，拒绝替换"
        updated_content = content.replace(old_str, new_str, 1)
        operation = "replace"

    if updated_content == content:
        return "提示: 文件内容未发生变化"

    try:
        await client.file.write(
            path=sandbox_path,
            data=updated_content,
            overwrite=append
        )
    except Exception as exc:  # noqa: BLE001
        return f"错误: 写入文件失败 ({sandbox_path}): {exc}"

    return f"文件已更新: {sandbox_path}，操作: {operation}，描述: {description.strip()}"


if __name__ == "__main__":
    import asyncio

    asyncio.run(execute_edit_file("示例追加", "/tmp/edit_tool_example.txt", new_str="\n追加内容"))
