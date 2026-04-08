"""
DownloadFileTool - 从沙箱下载文件工具

从沙箱中下载文件，返回下载链接
"""

import os
from typing import Dict, Any, Optional
import logging

from .base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment, ToolSource
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

_DOWNLOAD_FILE_PROMPT = """从沙箱中下载文件。返回文件的下载链接。

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

        file_name = os.path.basename(sandbox_path)
        download_url = None
        oss_object_path = None

        # 1. 优先通过 AgentFileSystem 保存并获取 URL
        if hasattr(client, "agent_file_system") and client.agent_file_system:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                afs = client.agent_file_system
                file_metadata = await afs.save_file_from_sandbox(
                    sandbox_path=sandbox_path,
                    file_type=FileType.DELIVERABLE,
                    is_deliverable=False,
                    description=f"下载文件: {file_name}",
                    tool_name="download_file",
                )
                if file_metadata:
                    download_url = file_metadata.preview_url
                    oss_object_path = (
                        file_metadata.metadata.get("object_path")
                        if file_metadata.metadata
                        else None
                    )
                    logger.info(
                        f"[download_file] File registered via AFS: "
                        f"file_name={file_name}, url={download_url}"
                    )
            except Exception as e:
                logger.warning(f"[download_file] AFS save failed: {e}")

        # 2. 回退到 upload_to_oss
        if not download_url:
            try:
                oss_file = await client.file.upload_to_oss(sandbox_path)
                if oss_file and oss_file.temp_url:
                    download_url = oss_file.temp_url
                    oss_object_path = oss_file.object_name
            except Exception as exc:
                logger.warning(f"[download_file] upload_to_oss failed: {exc}")

        # 3. 校验 URL 有效性
        if not download_url or not download_url.startswith(("http://", "https://")):
            return ToolResult.fail(
                error=(
                    f"错误: 文件已存在于沙箱中 ({sandbox_path})，"
                    f"但无法生成可访问的下载链接。请检查存储配置是否正确。"
                ),
                tool_name=self.name,
            )

        # 4. 构建返回信息并渲染 d-attach 组件
        result_parts = [f"✅ 文件下载链接已生成: {sandbox_path}"]
        try:
            from derisk.agent.core.file_system.dattach_utils import render_dattach

            dattach_content = render_dattach(
                file_name=file_name,
                file_url=download_url,
                file_type="download",
                object_path=oss_object_path,
                preview_url=download_url,
                download_url=download_url,
            )
            result_parts.append("\n\n**下载文件:**")
            result_parts.append(dattach_content)
        except Exception:
            result_parts.append(f"\n\n**下载链接:** {download_url}")

        return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)
