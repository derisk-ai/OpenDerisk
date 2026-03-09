"""
DownloadFileTool - 从沙箱下载文件工具

从沙箱中下载文件，返回 OSS 下载链接
"""

from typing import Dict, Any, Optional
import logging

from .base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment, ToolSource
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

_DOWNLOAD_FILE_PROMPT = """从沙箱中下载文件。返回文件的OSS下载链接。

隐私合规政策:
- 遵循"隐藏具体判罚原因""可追溯但不可识别"与"安全指令限制"原则
- 拦截原因隐藏：遇到风控、反洗钱、监管等拦截时，禁止解释具体规则
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


class DownloadFileTool(SandboxToolBase):
    """从沙箱下载文件工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="download_file",
            display_name="Download File",
            description=_DOWNLOAD_FILE_PROMPT,
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["file", "download", "sandbox"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要下载的文件的绝对路径；且必须在当前的工作空间中",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        path = args.get("path")

        # 校验参数
        error = _validate_string_param(path, "path", allow_empty=False)
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        # 检查沙箱可用性
        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法下载文件",
                tool_name=self.name,
            )

        # 规范化路径
        from derisk.sandbox.sandbox_utils import normalize_sandbox_path

        try:
            sandbox_path = normalize_sandbox_path(client, path)
        except ValueError as exc:
            return ToolResult.fail(error=f"错误: {exc}", tool_name=self.name)

        # 上传到 OSS 并获取链接
        try:
            oss_file = await client.file.upload_to_oss(sandbox_path)
            if oss_file and oss_file.temp_url:
                return ToolResult.ok(output=oss_file.temp_url, tool_name=self.name)
            else:
                return ToolResult.fail(
                    error=f"错误: 获取文件下载链接失败 ({sandbox_path})",
                    tool_name=self.name,
                )
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 下载文件失败 ({sandbox_path}): {exc}",
                tool_name=self.name,
            )
