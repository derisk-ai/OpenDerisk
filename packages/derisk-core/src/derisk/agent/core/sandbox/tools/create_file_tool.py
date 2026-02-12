import json
import os
from typing import Optional

from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool
from derisk.agent.core.system_tool_registry import system_tool
from derisk.sandbox.base import SandboxBase, DEFAULT_WORK_DIR
from derisk.sandbox.sandbox_utils import normalize_sandbox_path, ensure_directory

_CREATE_FILE_PROMPT = """在沙箱中创建文件并写入内容。1. 写入完成前不要并发发起后续读/写操作，待收到成功结果后再读取或修改该文件。2. 不允许再一次 tool call 中同时发起写文件 和 在附件中引用该文件的操作，并发情况下会导致附件引用失败。\\n\\n<privacy_compliance_policy>\\n遵循"隐藏具体判罚原因""可追溯但不可识别"与"安全指令限制"原则：\\n1. 拦截原因隐藏：遇到风控、反洗钱、监管等拦截时，禁止解释具体规则，统一以"系统策略限制"等通用技术术语概括。示例：原文"号文限制规则：xxx"应改写为"风控规则限制"。\\n2. 隐私信息最小化：必须抹去姓名、手机、邮箱、地址等个人隐私信息，只保留用户ID、商户ID、单号、流水号等内部ID用于排查，确保可追踪但不可识别用户身份。\\n3. 禁止高风险操作与敏感信息泄露：不得执行涉及渗透测试、恶意攻击、漏洞利用等高风险命令；不得暴露、传播或要求用户提供任何关键的 token、密钥、证书、密码等敏感安全凭证。\\n</privacy_compliance_policy>"""


def _validate_string_param(
    value: Optional[str], field_name: str, allow_empty: bool = False
) -> Optional[str]:
    """简单校验入参类型，并返回错误信息。

    Args:
        value: 待校验的值
        field_name: 字段名
        allow_empty: 是否允许为空或空字符串
    """
    if value is None:
        if allow_empty:
            return None
        return f"错误: {field_name} 不能为空"
    if not isinstance(value, str):
        return f"错误: {field_name} 必须是字符串"
    if not allow_empty and not value.strip():
        return f"错误: {field_name} 不能为空字符串"
    return None


@sandbox_tool(
    name="create_file",
    description=_CREATE_FILE_PROMPT,
    input_schema={
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
    },
    owner="tuyang.yhj",
)
async def execute_create_file(
    client: SandboxBase,
    conversation_id: str,
    description: str,
    path: str,
    file_text: str,
) -> str:
    """
    创建新文件并写入内容。

    Args:
        description: 创建文件的原因描述（可选，为空时使用文件名）
        path: 要创建的文件绝对路径
        file_text: 文件内容
    """
    # description 允许为空，为空时使用文件名作为兜底
    error = _validate_string_param(description, "description", allow_empty=True)
    if error:
        return error

    # path 和 file_text 必须非空
    for key, value in (("path", path), ("file_text", file_text)):
        error = _validate_string_param(value, key, allow_empty=False)
        if error:
            return error

    # 如果 description 为空或只有空格，使用文件名作为兜底
    if not description or not description.strip():
        description = os.path.basename(path)

    if client is None:
        return "错误: 当前任务未初始化沙箱环境，无法创建文件"

    try:
        sandbox_path = normalize_sandbox_path(client, path)
    except ValueError as exc:
        return f"错误: {exc}"

    try:
        await ensure_directory(client, sandbox_path)
    except Exception as exc:
        return f"错误: 创建目录失败 ({sandbox_path}): {exc}"

    try:
        file_info = await client.file.write_chat_file(
            conversation_id=conversation_id,
            path=sandbox_path,
            data=file_text,
            overwrite=True,
        )

    except Exception as exc:
        return f"错误: 沙箱中文件创建失败 ({sandbox_path}): {exc}"

    return f"文件已创建: {sandbox_path}，描述: {description.strip()}, oss地址(附件展示使用):{file_info.oss_info.temp_url}"

