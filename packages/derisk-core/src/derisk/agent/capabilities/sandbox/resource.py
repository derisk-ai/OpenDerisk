"""SandboxResource —— 沙箱作为 Capability 的输入投影(RFC-005 S14/S20)。

沙箱的输入投影:declare env 信息进 SYSTEM 槽;沙箱委托类工具归 sandbox 能力。
执行投影(沙箱作为 Executor):选B 方案,工具执行体自处理沙箱/本地切换,
走 ToolDispatcher builtin 回调,不另建 SandboxExecutor(后续需要再包装)。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.tool_entry import (
    BUILTIN_EXECUTOR_ID,
    ToolEntry,
)
from derisk.core.interface.resource.protocol import ResourceProtocol
from .env import build_env_text

logger = logging.getLogger(__name__)

# 沙箱启用时,这些"统一工具"(委托沙箱实现的文件/脚本类工具)归 sandbox 能力。
# 无沙箱时它们是本地默认工具(走 builtin)。见 tools/builtin/sandbox/__init__.py 注释:
# shell_exec/view/create_file/edit_file 已统一到 bash/read/write/edit,自动委托沙箱。
# 注:Step4 工具自声明 capability_id 后,本白名单将改为读 metadata,届时删除。
SANDBOX_DELEGATED_TOOLS = frozenset({
    "bash", "read", "write", "edit",
    "deliver_file", "download_file",
})


class SandboxResource(ResourceProtocol):
    """沙箱能力的输入投影:declare env + 沙箱工具归属。

    capability_id="sandbox"。
    """

    capability_id = "sandbox"
    protocol_version = 1

    def __init__(self, sandbox_client: Any, work_dir: Optional[str] = None):
        """sandbox_client: SandboxBase 实例(只读其静态属性)。
        work_dir: 工作目录(可选,来自 sandbox_manager)。
        """
        self.sandbox_client = sandbox_client
        self.work_dir = work_dir or "/workspace"

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        """declare 不通过类调;通过实例 declare_env 调(因依赖 sandbox_client)。"""
        return []

    def declare_env(self) -> List[Contribution]:
        """实例方法:产 env 信息的 SYSTEM Contribution。"""
        env_text = build_env_text(self.sandbox_client, self.work_dir)
        if not env_text:
            return []
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.SYSTEM,
                content=env_text,
                lifetime=Lifetime.SESSION,
                cache_scope=CacheScope.ENV,
                order=0,
            )
        ]

    def declare_tools(self, tools: Dict[str, Any]) -> List[ToolEntry]:
        """沙箱启用时,把委托沙箱的文件/脚本类工具归 sandbox 能力(S20)。

        有沙箱时这些工具(bash/read/write/edit/deliver_file/download_file)实质是
        沙箱工具,故 capability_id=sandbox;无沙箱时它们是本地默认工具(走 builtin)。

        executor_id 保持 BUILTIN_EXECUTOR_ID——工具执行体已自处理沙箱/本地切换
        (从 ToolContext 取 sandbox_manager),ToolDispatcher 走 builtin 回调即可。

        Args:
            tools: {tool_name: tool} 候选工具。仅 SANDBOX_DELEGATED_TOOLS 中的被声明。
                (Step4 后改为读 tool.metadata.capability_id == "sandbox")

        Returns:
            ToolEntry 列表(capability_id=sandbox)。
        """
        entries: List[ToolEntry] = []
        for name, tool in tools.items():
            # S20/Step4: 读工具自声明的 capability_id(ToolMetadata.capability_id)
            # 判定归属,不再靠工具名白名单。无沙箱时不调本方法,工具走 builtin。
            tool_cap = getattr(getattr(tool, "metadata", None), "capability_id", None)
            if tool_cap != self.capability_id:
                continue
            entries.append(
                ToolEntry(
                    tool_name=name,
                    tool=tool,
                    capability_id=self.capability_id,
                    executor_id=BUILTIN_EXECUTOR_ID,
                    description=getattr(tool, "description", "") or "",
                )
            )
        return entries

    def requires(self, config: Any = None) -> List[str]:
        """沙箱 env/工具声明依赖共享 SandboxExecutor(RFC-006 Stage 2)。

        SandboxExecutor 由接入层(react_master._get_resource_facade)注入
        executor_provider["sandbox"];capability 经此 requires 引用,触发
        registry.acquire → prepare(client 就绪校验)。注:当前 sandbox resource
        经 extra_static_contribs 旁路注入,不进 _build_static_bundle 的 sub 遍历,
        故本 requires 暂不触发 acquire;留作语义正确,供将来 sandbox 作 sub 时用。
        """
        return ["sandbox"]