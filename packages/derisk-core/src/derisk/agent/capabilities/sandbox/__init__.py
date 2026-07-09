"""Sandbox capability —— 沙箱能力自管目录(RFC-005 S14/S20)。

自管内容:
- resource.py: SandboxResource(declare env + 沙箱工具归属)
- env.py: env 文本构建逻辑
- tools/: 沙箱委托类工具实现(bash/read/write/edit/deliver_file/download_file)
  (注:工具实现暂留 tools/builtin/,Step4 自声明 capability_id 后归属语义达成;
   物理搬迁为低优先后续)

自注册:本目录被 CapabilityRegistry.discover() 扫描时,register() 把沙箱
capability 的资源实例工厂登记。注意 SandboxResource 需运行时 sandbox_client,
故注册的是工厂而非实例——实际 declare_env/declare_tools 由 react_master_agent
按运行时 sandbox_manager 构造 SandboxResource 调用。
"""

from .resource import SANDBOX_DELEGATED_TOOLS, SandboxResource  # noqa: F401
from .env import build_env_text, get_system_info  # noqa: F401

__all__ = [
    "SANDBOX_DELEGATED_TOOLS",
    "SandboxResource",
    "build_env_text",
    "get_system_info",
]


def register(registry) -> None:
    """沙箱 capability 自注册(被 CapabilityRegistry.discover 调用)。

    SandboxResource 依赖运行时 sandbox_client,此处登记一个标记/工厂,
    实际实例由 react_master_agent._build_sandbox_capability 构造。
    保持 register() 签名统一以支持自动发现模式。
    """
    # 当前 react_master_agent 直接构造 SandboxResource(因需 sandbox_client),
    # 此处无需注册实例。保留 register 占位以符合 capability 目录约定,
    # 供 registry.discover() 扫描时不报错。
    pass