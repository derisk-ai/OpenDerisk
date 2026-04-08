"""
DeliverFileTool - 文件交付工具

将文件标记为交付物并生成交付链接。

支持两种执行环境：
- 有沙箱：从沙箱读取文件，上传到 OSS
- 无沙箱：从本地读取文件，上传到 OSS
"""

import logging
import os
from typing import Dict, Any, Optional

from .base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment, ToolSource
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

_DELIVER_FILE_PROMPT = """将文件标记为交付物并生成交付链接。

**使用场景：**
- 生成的报告文件需要交付给用户
- 分析脚本输出的结果文件需要持久化
- 任何需要作为最终交付物的文件

**与 create_file 的区别：**
- `create_file`: 创建新文件并写入内容，is_deliverable=True 时自动标记为交付物
- `deliver_file`: 将已存在的文件标记为交付物（如脚本生成的文件）

**推荐用法：**
```
# 1. 使用 bash 生成报告
bash(command="python3 analyze.py --output ./report.md")

# 2. 查看报告内容确认
read(path="./report.md")

# 3. 标记为交付物
deliver_file(path="./report.md", description="风险分析报告")
```

<privacy_compliance_policy>
遵循"隐藏具体判罚原因""可追溯但不可识别"与"安全指令限制"原则：
1. 拦截原因隐藏：遇到风控、反洗钱、监管等拦截时，禁止解释具体规则，统一以"系统策略限制"等通用技术术语概括。
2. 隐私信息最小化：必须抹去姓名、手机、邮箱、地址等个人隐私信息，只保留用户ID、商户ID、单号、流水号等内部ID用于排查，确保可追踪但不可识别用户身份。
3. 禁止高风险操作与敏感信息泄露：不得执行涉及渗透测试、恶意攻击、漏洞利用等高风险命令；不得暴露、传播或要求用户提供任何关键的 token、密钥、证书、密码等敏感安全凭证。
</privacy_compliance_policy>
"""


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


def _get_mime_type(file_name: str) -> str:
    """根据文件扩展名获取 MIME 类型"""
    import mimetypes

    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"


class DeliverFileTool(SandboxToolBase):
    """沙箱文件交付工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="deliver_file",
            display_name="Deliver File",
            description=_DELIVER_FILE_PROMPT,
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["file", "deliver", "output", "sandbox", "attachment"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "沙箱中文件的绝对路径",
                },
                "description": {
                    "type": "string",
                    "description": "文件描述（可选，用于说明交付物的用途）",
                },
                "file_type": {
                    "type": "string",
                    "enum": ["deliverable", "report", "data", "log", "other"],
                    "default": "deliverable",
                    "description": "文件类型分类：deliverable(交付物), report(报告), data(数据), log(日志), other(其他)",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        """执行文件交付"""
        path = args.get("path")
        description = args.get("description", "")
        file_type = args.get("file_type", "deliverable")

        # 校验参数
        error = _validate_string_param(path, "path", allow_empty=False)
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        error = _validate_string_param(description, "description", allow_empty=True)
        if error:
            return ToolResult.fail(error=error, tool_name=self.name)

        # 检查沙箱可用性，决定执行模式
        client = self._get_sandbox_client(context)
        if client is not None:
            return await self._execute_sandbox(path, description, file_type, client)
        else:
            return await self._execute_local(path, description, file_type, context)

    async def _execute_sandbox(
        self, path: str, description: str, file_type: str, client: Any
    ) -> ToolResult:
        """沙箱模式执行文件交付"""

        # 规范化路径
        from derisk.sandbox.sandbox_utils import (
            normalize_sandbox_path,
            detect_path_kind,
        )

        try:
            sandbox_path = normalize_sandbox_path(client, path)
        except ValueError as exc:
            return ToolResult.fail(error=f"错误: {exc}", tool_name=self.name)

        # 检查文件是否存在
        try:
            path_kind = await detect_path_kind(client, sandbox_path)
            if path_kind == "none":
                return ToolResult.fail(
                    error=f"错误: 文件不存在: {sandbox_path}",
                    tool_name=self.name,
                )
            if path_kind == "dir":
                return ToolResult.fail(
                    error=f"错误: 路径是目录而非文件: {sandbox_path}",
                    tool_name=self.name,
                )
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 检查文件失败: {exc}",
                tool_name=self.name,
            )

        file_name = os.path.basename(sandbox_path)

        if not description or not description.strip():
            description = f"交付文件: {file_name}"

        mime_type = _get_mime_type(file_name)

        # 1. 通过 AgentFileSystem 统一管理文件
        oss_temp_url = None
        oss_object_path = None
        file_metadata = None

        if client.agent_file_system:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                afs = client.agent_file_system

                # 检查文件是否已注册为 DELIVERABLE
                existing_file = await afs.metadata_storage.get_file_by_key(
                    afs.conv_id, file_name
                )
                if (
                    existing_file
                    and existing_file.file_type == FileType.DELIVERABLE.value
                ):
                    logger.info(
                        f"[deliver_file] File already registered as DELIVERABLE: {file_name}"
                    )
                    result_parts = [
                        f"✅ 文件已在交付列表中: {sandbox_path}",
                        f"📋 描述: {existing_file.metadata.get('description', description.strip()) if existing_file.metadata else description.strip()}",
                    ]
                    if existing_file.preview_url:
                        try:
                            from derisk.agent.core.file_system.dattach_utils import (
                                render_dattach,
                            )

                            dattach_content = render_dattach(
                                file_name=file_name,
                                file_url=existing_file.preview_url,
                                file_type=file_type,
                                object_path=existing_file.metadata.get("object_path")
                                if existing_file.metadata
                                else None,
                                preview_url=existing_file.preview_url,
                                download_url=existing_file.download_url
                                or existing_file.preview_url,
                                description=description.strip(),
                            )
                            result_parts.append("\n\n**交付文件:**")
                            result_parts.append(dattach_content)
                        except Exception:
                            result_parts.append(
                                f"\n\n**下载链接:** {existing_file.preview_url}"
                            )
                    return ToolResult.ok(
                        output="\n".join(result_parts), tool_name=self.name
                    )

                # 使用统一的 save_file_from_sandbox 方法
                file_metadata = await afs.save_file_from_sandbox(
                    sandbox_path=sandbox_path,
                    file_type=FileType.DELIVERABLE,
                    is_deliverable=True,
                    description=description.strip(),
                    tool_name="deliver_file",
                    metadata={
                        "file_category": file_type,
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
                        f"[deliver_file] File registered via AFS: "
                        f"file_name={file_name}, object_path={oss_object_path}"
                    )

            except Exception as e:
                logger.warning(f"[deliver_file] Failed to register file via AFS: {e}")

        # 2. 如果 AgentFileSystem 不可用，尝试直接通过 write_chat_file 转存
        if not oss_temp_url:
            try:
                # 先读取文件内容
                file_info = await client.file.read(sandbox_path)
                file_content = getattr(file_info, "content", "")

                if file_content and hasattr(client.file, "write_chat_file"):
                    # 使用 write_chat_file 写入并上传
                    conversation_id = self._get_conversation_id(context)
                    upload_info = await client.file.write_chat_file(
                        conversation_id=conversation_id,
                        path=sandbox_path,
                        data=file_content,
                        overwrite=True,
                    )
                    if upload_info and upload_info.oss_info:
                        oss_temp_url = upload_info.oss_info.temp_url
                        oss_object_path = upload_info.oss_info.object_name
            except Exception as exc:
                logger.warning(f"[deliver_file] Fallback OSS upload failed: {exc}")

        # 3. 构建返回信息
        result_parts = [
            f"✅ 文件已标记为交付物: {sandbox_path}",
            f"📋 描述: {description.strip()}",
            f"📁 类型: {file_type}",
        ]

        # 检查 OSS 是否成功上传
        if not oss_temp_url:
            logger.warning(
                f"[deliver_file] Storage upload failed for {sandbox_path}. "
                f"File exists in sandbox but is not accessible via web URL. "
                f"Please check storage configuration."
            )
            result_parts.append(
                "\n⚠️ **注意：文件已标记，但无法生成可访问的预览/下载链接。**\n"
                "请检查存储配置是否正确。"
            )
        return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)

    async def _execute_local(
        self,
        path: str,
        description: str,
        file_type: str,
        context: Optional[ToolContext],
    ) -> ToolResult:
        """本地模式执行文件交付"""
        import aiofiles
        from pathlib import Path

        # 检查文件是否存在
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult.fail(
                error=f"错误: 文件不存在: {path}",
                tool_name=self.name,
            )
        if file_path.is_dir():
            return ToolResult.fail(
                error=f"错误: 路径是目录而非文件: {path}",
                tool_name=self.name,
            )

        file_name = file_path.name

        if not description or not description.strip():
            description = f"交付文件: {file_name}"

        mime_type = _get_mime_type(file_name)

        # 尝试上传到 OSS
        oss_temp_url = None
        oss_object_path = None

        try:
            from derisk.storage.oss import get_oss_client

            oss_client = get_oss_client()
            if oss_client:
                async with aiofiles.open(path, "rb") as f:
                    file_content = await f.read()

                oss_object_path = f"deliverables/{file_name}"
                oss_temp_url = await oss_client.put_object(
                    object_name=oss_object_path,
                    data=file_content,
                )
                logger.info(f"[deliver_file] Local file uploaded to OSS: {file_name}")
        except Exception as exc:
            logger.warning(f"[deliver_file] Local OSS upload failed: {exc}")

        # 构建返回信息
        result_parts = [
            f"✅ 文件已标记为交付物: {path}",
            f"📋 描述: {description.strip()}",
            f"📁 类型: {file_type}",
        ]

        if not oss_temp_url:
            result_parts.append(
                "\n⚠️ **注意：文件已标记，但无法生成可访问的预览/下载链接。**\n"
                "请检查存储配置是否正确。"
            )
            return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)

        # 生成 d-attach 组件
        try:
            from derisk.agent.core.file_system.dattach_utils import render_dattach

            dattach_content = render_dattach(
                file_name=file_name,
                file_url=oss_temp_url,
                file_type=file_type,
                object_path=oss_object_path,
                preview_url=oss_temp_url,
                download_url=oss_temp_url,
                description=description.strip(),
                mime_type=mime_type,
            )
            result_parts.append("\n\n**交付文件:**")
            result_parts.append(dattach_content)
        except Exception as exc:
            logger.warning(f"[deliver_file] d-attach 渲染失败: {exc}")
            result_parts.append(f"\n\n**下载链接:** {oss_temp_url}")

        if oss_object_path:
            result_parts.append(f"\n**OSS 对象路径:** {oss_object_path}")

        return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)

        # 4. 生成 d-attach 组件
        try:
            from derisk.agent.core.file_system.dattach_utils import render_dattach

            dattach_content = render_dattach(
                file_name=file_name,
                file_url=oss_temp_url,
                file_type=file_type,
                object_path=oss_object_path,
                preview_url=oss_temp_url,
                download_url=oss_temp_url,
                description=description.strip(),
                mime_type=mime_type,
            )
            result_parts.append("\n\n**交付文件:**")
            result_parts.append(dattach_content)
        except Exception as exc:
            logger.warning(f"[deliver_file] d-attach 渲染失败: {exc}")
            result_parts.append(f"\n\n**下载链接:** {oss_temp_url}")

        # 添加 OSS 对象路径（如果有）
        if oss_object_path:
            result_parts.append(f"\n**OSS 对象路径:** {oss_object_path}")

        return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)
