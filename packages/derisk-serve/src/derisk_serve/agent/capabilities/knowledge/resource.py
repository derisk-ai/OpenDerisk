"""KnowledgeResource —— 知识库 capability 输入投影(RFC-005 Step C)。

知识库是 Consumer:declare 产库列表声明(纯,从实例已构造的 knowledge_spaces/
description 属性),检索结果回注输入走 consume(chunks/summary → USER_PART/TURN)。

三实现并存(RetrieverResource 旧 RAG / KnowledgePackSearchResource 主力 /
KnowledgeSpaceResource ext VaultFS),本 capability 包装统一为:
- declare:库列表 SYSTEM(CONFIG_STATIC/USER),从 description 属性读(纯)。
- consume:检索结果 → USER_PART(TURN)。由 KnowledgeExecutor 包装 rag Service/
  VaultFS 异步检索;consume 接收检索结果转 Contribution。
- retrieve 工具(knowledge_search)由 builtin 路径注入,执行体调 executor。

双轨:包装旧 RetrieverResource/KnowledgePackSearchResource/KnowledgeSpaceResource
实例(由 build_resource 构建进 ResourcePack),declare 委托 description 属性。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

logger = logging.getLogger(__name__)


class KnowledgeCapabilityResource(ResourceProtocol):
    """知识库 capability:declare 库列表 + consume 检索回注。

    capability_id="knowledge"。
    """

    capability_id = "knowledge"
    protocol_version = 1

    def __init__(self, legacy_instance: Any = None, spaces: Optional[List[dict]] = None):
        self._legacy = legacy_instance
        self._spaces = spaces

    def declare(self, config: Any = None) -> List[Contribution]:
        """实例 declare:委托 declare_spaces 产知识库列表 SYSTEM Contribution。"""
        return self.declare_spaces()

    def declare_spaces(self) -> List[Contribution]:
        """实例方法:产知识库列表 SYSTEM Contribution(纯,读 description 属性)。"""
        text = self._render_spaces()
        if not text:
            return []
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.SYSTEM,
                content=text,
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.USER,
                order=50,
            )
        ]

    async def consume(self, call_result: Any) -> List[Contribution]:
        """检索结果回注输入(chunks/summary → USER_PART/TURN)。

        call_result = 检索结果文本(chunks 拼接或 summary_content)。
        作为本轮 user 临时上下文(TURN),不跨轮。
        """
        if not call_result:
            return []
        content = call_result if isinstance(call_result, str) else str(call_result)
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.USER_PART,
                content=f"<knowledge-context>\n{content}\n</knowledge-context>",
                lifetime=Lifetime.TURN,
                cache_scope=CacheScope.NONE,
            )
        ]

    def _render_spaces(self) -> str:
        """从显式 spaces 或 legacy.description 读知识库列表(纯,无 I/O)。"""
        if self._spaces is not None:
            lines = []
            for i, sp in enumerate(self._spaces):
                lines.append(
                    f"{i+1}. name:{sp.get('name','')}, "
                    f"knowledge_id:{sp.get('knowledge_id','')}, "
                    f"知识库描述:{sp.get('desc','')}"
                )
            return "\n".join(lines) if lines else ""
        if self._legacy is None:
            return ""
        try:
            desc = getattr(self._legacy, "description", "") or ""
            return desc if isinstance(desc, str) else ""
        except Exception as e:  # noqa: BLE001
            # 某些 legacy 实例 description 可能在未初始化时报错
            logger.debug(f"[knowledge] read description failed: {e}")
            return ""

    def requires(self, config: Any = None) -> List[str]:
        # 检索 executor(若用 KnowledgeExecutor)可选;本轮检索走 builtin,暂空
        return []