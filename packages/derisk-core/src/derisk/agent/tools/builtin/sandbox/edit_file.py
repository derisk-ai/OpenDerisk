"""
EditFileTool - 沙箱内编辑文件工具

编辑文本文件，支持替换唯一字符串或追加内容，支持交付物标记和 d-attach 渲染
"""

from typing import Dict, Any, Optional
import os
import logging

from .base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment, ToolSource
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

_EDIT_FILE_PROMPT = """文件写入工具，用于在沙箱中写入或编辑文本文件。

**核心功能：**
- 追加写入（默认）：在文件末尾追加新内容
- 替换写入：查找并替换文件中的唯一字符串

**内容大小限制：**
- 单次写入内容不得超过 2000 字符，超过会导致输出中断
- 大文件请分多次调用 edit_file(append=True) 追加写入

**使用场景：**
- 创建新文件内容：append=True，new_str 为完整内容
- 追加内容到文件：append=True，new_str 为追加内容
- 替换文件中的内容：append=False，提供 old_str 和 new_str

**交付物标记：**
- is_deliverable=True（默认）时，编辑后的文件会更新交付状态
"""


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
            tags=["file", "edit", "write", "sandbox", "deliverable"],
            author="tuyang.yhj",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "编辑原因描述，说明为什么要进行此操作（必填）",
                },
                "path": {
                    "type": "string",
                    "description": "文件的绝对路径",
                },
                "new_str": {
                    "type": "string",
                    "description": "要写入的内容。追加模式下为追加的文本；替换模式下为替换后的新文本",
                },
                "append": {
                    "type": "boolean",
                    "default": True,
                    "description": "写入模式：True=追加模式（默认），在文件末尾添加内容；False=替换模式，查找并替换指定字符串",
                },
                "old_str": {
                    "type": "string",
                    "description": "【仅替换模式】要被替换的原字符串，必须在文件中唯一出现。追加模式下忽略此参数",
                },
                "is_deliverable": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否将文件标记为交付物（默认 True），标记后可在任务结束时自动交付给用户",
                },
            },
            "required": ["description", "path"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        description = args.get("description")
        path = args.get("path")
        new_str = args.get("new_str", "")
        append = args.get("append", True)
        old_str = args.get("old_str")
        is_deliverable = args.get("is_deliverable", True)

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

        # 1. 先写入沙箱文件
        try:
            await client.file.write(
                path=sandbox_path,
                data=updated_content,
                overwrite=True,
            )
            logger.info(f"[edit_file] File updated in sandbox: {sandbox_path}")
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 写入文件失败 ({sandbox_path}): {exc}",
                tool_name=self.name,
            )

        result_parts = [
            f"✅ 文件已更新: {sandbox_path}，操作: {operation}，描述: {description.strip()}"
        ]

        # 2. 通过 AgentFileSystem 统一管理文件（OSS 转存 + 元数据记录）
        oss_temp_url = None
        oss_object_path = None

        if client.agent_file_system:
            try:
                afs = client.agent_file_system

                # 使用 update_file_from_sandbox 方法更新文件
                file_metadata = await afs.update_file_from_sandbox(
                    sandbox_path=sandbox_path,
                    file_content=updated_content,
                    metadata={
                        "description": description.strip() if description else "",
                        "is_deliverable": is_deliverable,
                        "operation": operation,
                    },
                )

                # 从元数据获取 OSS 信息
                if file_metadata:
                    oss_temp_url = file_metadata.preview_url
                    oss_object_path = (
                        file_metadata.metadata.get("object_path")
                        if file_metadata.metadata
                        else None
                    )
                    logger.info(
                        f"[edit_file] File updated via AFS: "
                        f"file_name={file_metadata.file_name}, "
                        f"object_path={oss_object_path}"
                    )

            except Exception as e:
                logger.warning(f"[edit_file] Failed to update file via AFS: {e}")

        # 3. 如果 AgentFileSystem 不可用，尝试直接通过 write_chat_file 转存
        if not oss_temp_url:
            conversation_id = self._get_conversation_id(context)
            try:
                file_info = await client.file.write_chat_file(
                    conversation_id=conversation_id,
                    path=sandbox_path,
                    data=updated_content,
                    overwrite=True,
                )
                if file_info and file_info.oss_info:
                    oss_temp_url = file_info.oss_info.temp_url
                    oss_object_path = file_info.oss_info.object_name
            except Exception as exc:
                logger.warning(f"[edit_file] Fallback OSS upload failed: {exc}")

        # 4. 检查 OSS 是否成功
        if not oss_temp_url:
            logger.warning(
                f"[edit_file] OSS upload failed for {sandbox_path}. "
                f"File was updated in sandbox but is not accessible via web URL."
            )

        # 5. 渲染 d-attach 组件
        if oss_temp_url:
            file_name = os.path.basename(sandbox_path)
            try:
                from derisk.agent.core.file_system.dattach_utils import render_dattach

                dattach_content = render_dattach(
                    file_name=file_name,
                    file_url=oss_temp_url,
                    file_type="deliverable",
                    object_path=oss_object_path,
                    preview_url=oss_temp_url,
                    download_url=oss_temp_url,
                )
                result_parts.append(f"\n\n**附件展示:**")
                result_parts.append(dattach_content)
            except Exception:
                result_parts.append(f"\n\n**下载链接:** {oss_temp_url}")

        if oss_object_path:
            result_parts.append(f"\n**OSS 对象路径:** {oss_object_path}")

        return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)
