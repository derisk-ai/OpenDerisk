"""MemoryCapabilityResource —— 记忆 capability(RFC-005 Step D)。

MemoryResource 是纯配置载体(get_prompt 空,真逻辑在 _memory_bundle/longterm_manager)。
记忆是 Consumer:检索结果回注输入(memory_context → USER_PART/SESSION)。

迁移要点:
- declare:空或产记忆策略声明(资源不产 system,记忆 static_block 由 react_master
  的 memory_pipeline.static_block 路径进快照身份层后,非资源 declare)。
- consume:接管检索回注(memory_context → USER_PART/SESSION)。当前检索逻辑在
  react_master 内联,本 consume 提供协议接口,agent_chat/react_master 收口后接入。
- executor:LongTermMemoryManager(在 _memory_bundle),本轮不包装(记忆走另一路径)。

双轨:包装旧 MemoryResource 实例(由 build_resource 构建进 ResourcePack),
走原生 declare(空)脱离 legacy 桥接。
"""

from __future__ import annotations

import logging
from typing import Any, List

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

logger = logging.getLogger(__name__)


class MemoryCapabilityResource(ResourceProtocol):
    """记忆 capability:declare 空(配置载体)+ consume 检索回注接口。

    capability_id="memory"。
    """

    capability_id = "memory"
    protocol_version = 1

    def __init__(self, legacy_instance: Any = None):
        self._legacy = legacy_instance

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        # 记忆资源不产 system 声明(static_block 走 memory_pipeline 独立路径)
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        """检索结果回注输入(memory_context → USER_PART/SESSION)。

        call_result = 记忆检索文本(从 LongTermMemoryManager.retrieve_relevant_memories
        或 memory_pipeline.consume_prefetch 得到)。作为会话级上下文(SESSION,
        跨轮参考但整会话存活)——对齐现 <memory-context> fence 语义。
        """
        if not call_result:
            return []
        content = call_result if isinstance(call_result, str) else str(call_result)
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.USER_PART,
                content=f"<memory-context>\n{content}\n</memory-context>",
                lifetime=Lifetime.SESSION,
                cache_scope=CacheScope.NONE,
            )
        ]

    def requires(self, config: Any = None) -> List[str]:
        # 记忆 executor(LongTermMemoryManager)本轮不包装成独立 executor(走 memory_pipeline)
        return []