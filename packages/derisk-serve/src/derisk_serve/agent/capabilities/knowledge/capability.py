"""KnowledgeCapability —— 知识库自管理资源能力(RFC-006 Stage 7/8)。

知识库是 Consumer:declare 库列表 SYSTEM + consume 检索结果回注(TURN)。

prepare 自管 hydrate:按 _knowledge_ids 调 KnowledgeService.get_knowledge_space 水合
空间元数据(name/desc)存 _spaces,供 declare 渲染。facade 时序已改 prepare 先于 declare
(RFC-006 Stage 8),declare 能读到 prepare 产出的 _spaces。若 from_legacy 已带完整 spaces
(旧实例构造期已 hydrate)或 config 已带 name/desc,则 prepare 免 I/O。

execute 不收编:knowledge_search 是 v1 KnowledgeSearch action(_init_actions 派发,经
retriever.retrieve I/O),收编需改 v1/v2 shadowing + Action 派发,风险高。本轮
KnowledgeCapability 自管 prepare/declare/consume,execute 保持 v1 action。
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
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

logger = logging.getLogger(__name__)


class KnowledgeCapability(Capability):
    """知识库自管理能力:declare 库列表 + consume 检索回注。

    capability_id="knowledge";executor_id="knowledge"(单例)。
    """

    capability_id = "knowledge"

    def __init__(
        self,
        spaces: Optional[List[dict]] = None,
        description: str = "",
        knowledge_ids: Optional[List[Any]] = None,
    ):
        self._spaces = spaces
        self._description = description
        self._knowledge_ids = knowledge_ids or []
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "KnowledgeCapability":
        value = value or {}
        knowledges = value.get("knowledges") or []
        spaces = [
            {
                "name": k.get("name", ""),
                "knowledge_id": k.get("knowledge_id"),
                "desc": k.get("description") or k.get("desc") or "",
            }
            for k in knowledges
        ]
        knowledge_ids = [k.get("knowledge_id") for k in knowledges if k.get("knowledge_id")]
        return cls(spaces=spaces or None, knowledge_ids=knowledge_ids)

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "KnowledgeCapability":
        """从旧 RetrieverResource/KnowledgePackSearchResource 实例构造(过渡期)。

        优先读 description(已渲染好的库列表串);回退读 knowledge_spaces 元数据。
        旧实例构造期已泄水合(get_knowledge_spaces_info),无新增 I/O。
        """
        desc = getattr(legacy_instance, "description", "") or ""
        if not isinstance(desc, str):
            desc = ""
        spaces = None
        kspaces = getattr(legacy_instance, "knowledge_spaces", None)
        if kspaces:
            spaces = []
            for ks in kspaces:
                spaces.append(
                    {
                        "name": getattr(ks, "name", "") or "",
                        "knowledge_id": getattr(ks, "knowledge_id", None),
                        "desc": getattr(ks, "desc", "") or "",
                    }
                )
        return cls(spaces=spaces, description=desc)

    @property
    def executor_id(self) -> str:
        return "knowledge"

    def declare(self, config: Any = None) -> List[Contribution]:
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

    def _render_spaces(self) -> str:
        if self._spaces is not None:
            lines = []
            for i, sp in enumerate(self._spaces):
                lines.append(
                    f"{i+1}. name:{sp.get('name','')}, "
                    f"knowledge_id:{sp.get('knowledge_id','')}, "
                    f"知识库描述:{sp.get('desc','')}"
                )
            return "\n".join(lines) if lines else ""
        return self._description or ""

    def requires(self, config: Any = None) -> List[str]:
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
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

    async def prepare(self) -> None:
        """hydrate 知识库空间元数据(name/desc),供 declare 渲染库列表。

        若 _spaces 已带 name/desc(from_legacy 复用旧实例,或 config 已完整)则免 I/O。
        否则按 _knowledge_ids 调 KnowledgeService.get_knowledge_space 水合(异步)。
        facade 时序已改 prepare 先于 declare(RFC-006 Stage 8),故 declare 能读到本方法产出。
        无 knowledge_ids 或 service 不可用时,保留现有 _spaces/_description(可能为空)。
        """
        if self._spaces and all(sp.get("name") for sp in self._spaces):
            self._status = ExecutorStatus.READY
            return
        if not self._knowledge_ids:
            self._status = ExecutorStatus.READY
            return
        try:
            import asyncio

            from derisk_app.knowledge.request.request import KnowledgeSpaceRequest
            from derisk_app.knowledge.service import KnowledgeService

            hydrated: List[dict] = []
            for kid in self._knowledge_ids:
                spaces = await asyncio.to_thread(
                    lambda k=kid: KnowledgeService().get_knowledge_space(
                        KnowledgeSpaceRequest(knowledge_id=k)
                    )
                )
                if not spaces:
                    continue
                sp = spaces[0]
                hydrated.append(
                    {
                        "name": getattr(sp, "name", "") or "",
                        "knowledge_id": getattr(sp, "knowledge_id", kid),
                        "desc": getattr(sp, "desc", "") or "",
                    }
                )
            if hydrated:
                # from_config 已带部分 spaces(config 元数据)与 hydrate 合并取并集
                self._spaces = hydrated + [
                    s for s in (self._spaces or []) if s.get("knowledge_id") not in {h["knowledge_id"] for h in hydrated}
                ]
            self._status = ExecutorStatus.READY
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[knowledge-capability] hydrate spaces failed: {e}")
            self._status = ExecutorStatus.READY  # 降级:用现有 _spaces/_description

    async def execute(self, call: ExecutorCall) -> Any:
        raise NotImplementedError(
            "KnowledgeCapability.execute 未收编 —— knowledge_search 暂走 v1 action"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED