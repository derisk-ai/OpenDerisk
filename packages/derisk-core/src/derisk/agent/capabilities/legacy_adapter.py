"""LegacyResourceAdapter —— 存量资源桥接(过渡,迁完删)。

把现有 ``Resource`` 实例(零修改)桥接成 Contribution,内部仍调用现有
``ResourceInjector`` / ``ToolPack.from_resource``,保证存量输出字节不变。

设计取舍:不在 ``Resource`` 基类上加 declare(避免动核心)。新协议用适配器
包裹存量资源;新资源直接继承 ResourceProtocol(在各自 capability 自管目录)。

存量所有 Resource 迁到原生 declare 后,本模块可删。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from derisk.core.interface.input import (
    CacheScope,
    Contribution,
    InputBundle,
    Lifetime,
    Slot,
)

logger = logging.getLogger(__name__)

# 现有 PromptAssembler 的 section_separator(prompt_assembler.py),桥接沿用保字节等价。
LEGACY_SECTION_SEPARATOR = "\n\n---\n\n"

# 现有 inject_all 产出的资源层,在 system 中属于哪个 cache_scope:
# 资源声明(DB schema/app 列表等)与用户绑定、跨会话稳定 → USER。
LEGACY_RESOURCE_CACHE_SCOPE = CacheScope.USER


class LegacyResourceAdapter:
    """把现有 ResourceContext 桥接成 InputBundle。

    存量等价保证:
    - system 内容 ≡ ``ResourceInjector.inject_all(ctx)`` 的输出(同字符串)。
    - tools 内容 ≡ 该 ctx 下 ``ToolPack.from_resource`` 解析出的工具集。

    用法::

        adapter = LegacyResourceAdapter()
        bundle = await adapter.from_context(ctx, resource_root=agent.resource)
        frozen = bundle.freeze(config_hash=...)
    """

    def __init__(self, injector: Optional[Any] = None):
        # 延迟导入:resource_injector 在 prompt_assembly 旧件,避免顶层循环
        if injector is None:
            from derisk.agent.shared.prompt_assembly.resource_injector import (
                ResourceInjector,
            )
            injector = ResourceInjector()
        self.injector = injector

    async def from_context(
        self,
        ctx: Any,
        resource_root: Optional[Any] = None,
        capability_prefix: str = "legacy",
    ) -> InputBundle:
        """从存量 ResourceContext 构造 InputBundle。

        Args:
            ctx: 现有 ResourceContext(由 from_v1_agent 构建)。
            resource_root: agent.resource(ResourcePack 或单 Resource),
                用于解析工具(ToolPack.from_resource)。可为 None。
            capability_prefix: 生成的 Contribution.capability_id 前缀。

        Returns:
            InputBundle,system 槽含资源层(单条 USER scope Contribution,
            text==inject_all 输出),tools 槽含工具声明(原始 BaseTool 引用)。
        """
        bundle = InputBundle()

        # ---- system: 整个资源层作为一条 USER scope Contribution(等价 inject_all)----
        resource_prompt = await self.injector.inject_all(ctx)
        if resource_prompt:
            bundle.add(
                Contribution(
                    capability_id=f"{capability_prefix}:resources",
                    slot=Slot.SYSTEM,
                    content=resource_prompt,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=LEGACY_RESOURCE_CACHE_SCOPE,
                    order=0,
                )
            )

        # ---- tools: ToolPack.from_resource 解析,等价 function_calling_params 工具部分 ----
        if resource_root is not None:
            for tool in self._iter_tools(resource_root):
                bundle.add(
                    Contribution(
                        capability_id=f"{capability_prefix}:tool:{getattr(tool, 'name', 'unknown')}",
                        slot=Slot.TOOLS,
                        content=tool,            # 保留原始 BaseTool 引用,provider 层再转 schema
                        lifetime=Lifetime.CONFIG_STATIC,
                        cache_scope=CacheScope.NONE,
                        order=0,
                    )
                )

        return bundle

    @staticmethod
    def _iter_tools(resource_root: Any) -> List[Any]:
        """等价 ``ToolPack.from_resource(resource_root)[0].sub_resources``。"""
        try:
            from derisk.agent.resource import ToolPack  # 延迟导入避免循环

            packs = ToolPack.from_resource(resource_root)
            tools: List[Any] = []
            for pack in packs:
                for t in pack.sub_resources:
                    tools.append(t)
            return tools
        except Exception as e:  # pragma: no cover - 防御性
            logger.warning(f"LegacyResourceAdapter tool resolve failed: {e}")
            return []

    @staticmethod
    def legacy_separator() -> str:
        """现 PromptAssembler section_separator,供降级 merge_to_str 保字节等价。"""
        return LEGACY_SECTION_SEPARATOR