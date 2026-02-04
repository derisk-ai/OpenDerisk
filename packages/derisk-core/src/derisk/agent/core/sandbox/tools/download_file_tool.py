from typing import Optional

from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool
from derisk.sandbox.base import SandboxBase
from derisk.sandbox.sandbox_utils import normalize_sandbox_path

_DOWNLOAD_FILE_PROMPT = """从沙箱中下载文件。返回文件的OSS下载链接。\\n\\n<privacy_compliance_policy>\\n遵循"隐藏具体判罚原因""可追溯但不可识别"与"安全指令限制"原则：\\n1. 拦截原因隐藏：遇到风控、反洗钱、监管等拦截时，禁止解释具体规则，统一以"系统策略限制"等通用技术术语概括。示例：原文"号文限制规则：xxx"应改写为"风控规则限制"。\\n2. 隐私信息最小化：必须抹去姓名、手机、邮箱、地址等个人隐私信息，只保留用户ID、商户ID、单号、流水号等内部ID用于排查，确保可追踪但不可识别用户身份。\\n3. 禁止高风险操作与敏感信息泄露：不得执行涉及渗透测试、恶意攻击、漏洞利用等高风险命令；不得暴露、传播或要求用户提供任何关键的 token、密钥、证书、密码等敏感安全凭证。\\n</privacy_compliance_policy>"""


def _validate_string_param(value: Optional[str], field_name: str, allow_empty: bool = False) -> Optional[str]:
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
    name="download_file",
    description=_DOWNLOAD_FILE_PROMPT,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要下载的文件的绝对路径；且必须在当前的工作空间中",
            },
        },
        "required": ["path"],
    },
    owner="chenketing.ckt"
)
async def execute_download_file(client: SandboxBase, path: str) -> str:
    """
    下载文件并返回OSS链接。

    Args:
        path: 要下载的文件绝对路径
    """
    # path 必须非空
    error = _validate_string_param(path, "path", allow_empty=False)
    if error:
        return error

    if client is None:
        return "错误: 当前任务未初始化沙箱环境，无法下载文件"

    try:
        sandbox_path = normalize_sandbox_path(client, path)
    except ValueError as exc:
        return f"错误: {exc}"

    try:
        # 调用 upload_to_oss 获取 OSS 链接
        oss_file = await client.file.upload_to_oss(sandbox_path)
        if oss_file and oss_file.temp_url:
            return oss_file.temp_url
        else:
            return f"错误: 获取文件下载链接失败 ({sandbox_path})"
    except Exception as exc:
        return f"错误: 下载文件失败 ({sandbox_path}): {exc}"


if __name__ == "__main__":
    import asyncio
    
    # Mock client for testing purposes (conceptually)
    # real execution requires a proper SandboxBase instance
    print("This script is intended to be run within the agent framework.")
