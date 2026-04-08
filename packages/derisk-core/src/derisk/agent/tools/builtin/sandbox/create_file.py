"""
CreateFileTool - 沙箱内创建文件工具

在沙箱工作空间中创建文件并写入内容，支持交付物标记和 d-attach 渲染
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

**内容大小限制：**
- 单次写入内容不得超过 2000 字符，超过会导致输出中断
- 大文件请分多次调用：先用 create_file 写入前 3000 字符，再用 edit_file(append=True) 追加剩余内容

**交付物标记：**
- is_deliverable=True（默认）时，文件会自动标记为交付物，无需再调用 deliver_file
- 仅当文件是中间过程文件（不需要交付给用户）时，设置 is_deliverable=False

**安全约束：**
- 写入完成后再读取/修改，禁止并发操作
- 禁止同一次调用中写入并引用该文件

<privacy_compliance_policy>
遵循"隐藏具体判罚原因""可追溯但不可识别"与"安全指令限制"原则：
1. 拦截原因隐藏：遇到风控、反洗钱、监管等拦截时，禁止解释具体规则，统一以"系统策略限制"等通用技术术语概括
2. 隐私信息最小化：必须抹去姓名、手机、邮箱、地址等个人隐私信息，只保留用户ID、商户ID、单号、流水号等内部ID用于排查
3. 禁止高风险操作与敏感信息泄露：不得执行涉及渗透测试、恶意攻击、漏洞利用等高风险命令
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
            tags=["file", "write", "create", "sandbox", "deliverable"],
            author="tuyang.yhj",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "创建文件的原因说明，最多 15 个字，必填",
                },
                "path": {
                    "type": "string",
                    "description": "文件的绝对路径；且必须在当前的工作空间中",
                },
                "file_text": {
                    "type": "string",
                    "description": "文件内容",
                },
                "is_deliverable": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否将文件标记为交付物（默认 True），标记后可在任务结束时自动交付给用户",
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
        is_deliverable = args.get("is_deliverable", True)

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

        # 1. 先写入沙箱文件
        try:
            await client.file.write(
                path=sandbox_path,
                data=file_text,
                overwrite=True,
            )
            logger.info(f"[create_file] File written to sandbox: {sandbox_path}")
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 沙箱中文件创建失败 ({sandbox_path}): {exc}",
                tool_name=self.name,
            )

        # 构建返回信息
        result_parts = [f"✅ 文件已创建: {sandbox_path}，描述: {description.strip()}"]

        # 2. 通过 AgentFileSystem 统一管理文件（OSS 转存 + 元数据记录）
        oss_temp_url = None
        oss_object_path = None
        file_metadata = None

        if client.agent_file_system:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                afs = client.agent_file_system

                # 使用统一的 save_file_from_sandbox 方法
                file_metadata = await afs.save_file_from_sandbox(
                    sandbox_path=sandbox_path,
                    file_type=FileType.DELIVERABLE
                    if is_deliverable
                    else FileType.WRITE_FILE,
                    file_content=file_text,
                    is_deliverable=is_deliverable,
                    description=description.strip(),
                    tool_name="create_file",
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
                        f"[create_file] File registered via AFS: "
                        f"file_name={file_metadata.file_name}, "
                        f"object_path={oss_object_path}, "
                        f"is_deliverable={is_deliverable}"
                    )

            except Exception as e:
                logger.warning(f"[create_file] Failed to register file via AFS: {e}")

        # 3. 如果 AgentFileSystem 不可用，尝试直接通过 write_chat_file 转存
        if not oss_temp_url:
            conversation_id = self._get_conversation_id(context)
            try:
                file_info = await client.file.write_chat_file(
                    conversation_id=conversation_id,
                    path=sandbox_path,
                    data=file_text,
                    overwrite=True,
                )
                if file_info and file_info.oss_info:
                    oss_temp_url = file_info.oss_info.temp_url
                    oss_object_path = file_info.oss_info.object_name
            except Exception as exc:
                logger.warning(f"[create_file] Fallback OSS upload failed: {exc}")

        # 4. 检查 OSS 是否成功
        if not oss_temp_url:
            logger.warning(
                f"[create_file] Storage upload failed for {sandbox_path}. "
                f"File was created in sandbox but is not accessible via web URL. "
                f"Please check storage configuration."
            )
            result_parts.append(
                f"\n⚠️ **注意：文件已创建，但无法生成可访问的预览/下载链接。**"
                f"\n请检查存储配置是否正确。"
            )
            return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)

        # 5. 渲染 d-attach 组件
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

        # 添加 OSS 对象路径（如果有）
        if oss_object_path:
            result_parts.append(f"\n**OSS 对象路径:** {oss_object_path}")

        return ToolResult.ok(output="\n".join(result_parts), tool_name=self.name)
