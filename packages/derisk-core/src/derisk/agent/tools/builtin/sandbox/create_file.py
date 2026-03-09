"""
CreateFileTool - 沙箱内创建文件工具

在沙箱工作空间中创建文件并写入内容
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

_CREATE_FILE_PROMPT = """在沙箱中创建文件并写入内容。

使用说明:
1. 写入完成前不要并发发起后续读/写操作，待收到成功结果后再读取或修改该文件。
2. 不允许再一次 tool call 中同时发起写文件 和 在附件中引用该文件的操作，并发情况下会导致附件引用失败。

隐私合规政策:
- 遵循"隐藏具体判罚原因""可追溯但不可识别"与"安全指令限制"原则
- 拦截原因隐藏：遇到风控、反洗钱、监管等拦截时，禁止解释具体规则，统一以"系统策略限制"等通用技术术语概括
- 隐私信息最小化：必须抹去姓名、手机、邮箱、地址等个人隐私信息
- 禁止高风险操作与敏感信息泄露"""


def _validate_string_param(
    value: Optional[str], field_name: str, allow_empty: bool = False
) -> Optional[str]:
    """简单校验入参类型，并返回错误信息。"""
    if value is None:
        if allow_empty:
            return None
        return f"错误: {field_name} 不能为空"
    if not isinstance(value, str):
        return f"错误: {field_name} 必须是字符串"
    if not allow_empty and not value.strip():
        return f"错误: {field_name} 不能为空字符串"
    return None


class CreateFileTool(SandboxToolBase):
    """沙箱内创建文件工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="create_file",
            display_name="Create File",
            description=_CREATE_FILE_PROMPT,
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["file", "write", "create", "sandbox"],
            author="tuyang.yhj",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "创建文件的原因说明,最多15个字,必填",
                },
                "path": {
                    "type": "string",
                    "description": "文件的绝对路径；且必须在当前的工作空间中",
                },
                "file_text": {
                    "type": "string",
                    "description": "文件内容",
                },
            },
            "required": ["description", "path", "file_text"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        description = args.get("description", "")
        path = args.get("path")
        file_text = args.get("file_text")

        # 校验参数
        error = _validate_string_param(description, "description", allow_empty=True)
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        for key, value in (("path", path), ("file_text", file_text)):
            error = _validate_string_param(value, key, allow_empty=False)
            if error:
                return ToolResult.fail(error=error, tool_name=self.name)

        # 如果 description 为空，使用文件名作为兜底
        if not description or not description.strip():
            description = os.path.basename(path)

        # 检查沙箱可用性
        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法创建文件",
                tool_name=self.name,
            )

        # 规范化路径
        from derisk.sandbox.sandbox_utils import (
            normalize_sandbox_path,
            ensure_directory,
        )

        try:
            sandbox_path = normalize_sandbox_path(client, path)
        except ValueError as exc:
            return ToolResult.fail(error=f"错误: {exc}", tool_name=self.name)

        # 创建目录
        try:
            await ensure_directory(client, sandbox_path)
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 创建目录失败 ({sandbox_path}): {exc}",
                tool_name=self.name,
            )

        # 写入文件
        conversation_id = self._get_conversation_id(context)
        try:
            file_info = await client.file.write_chat_file(
                conversation_id=conversation_id,
                path=sandbox_path,
                data=file_text,
                overwrite=True,
            )
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 沙箱中文件创建失败 ({sandbox_path}): {exc}",
                tool_name=self.name,
            )

        output = f"文件已创建: {sandbox_path}，描述: {description.strip()}, oss地址(附件展示使用):{file_info.oss_info.temp_url}"
        return ToolResult.ok(output=output, tool_name=self.name)
