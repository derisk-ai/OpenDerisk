"""ResourceProtocol 协议本体(RFC-005 §3.3)。

定义资源扩展协议 + Consumer 编排骨架。不包含 LegacyResourceAdapter
(它是存量桥接,依赖 agent 侧 resource_injector,留在 agent/capabilities/)。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .bundle import Contribution, Lifetime

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 协议抽象(RFC-005 §3.3)
# --------------------------------------------------------------------------- #
class ResourceProtocol(ABC):
    """资源扩展协议:定义【数据 → 输入槽】的过程。

    新增一种外部数据源 = 实现一个本类子类,声明 capability_id + declare。
    不动配置态、不动存量资源。

    一个 capability 通常以"自管目录"形式组织(agent/capabilities/{capability}/),
    内含 declare(资源/环境) + 自有工具 + 可选 executor,高内聚、易扩展。
    """

    capability_id: str
    protocol_version: int = 1

    @classmethod
    @abstractmethod
    def declare(cls, config: Any) -> List[Contribution]:
        """声明面【纯函数,无 I/O】。

        需外部数据(schema)时,Contribution.content 带 data_requirement,
        由执行投影预取后回填。
        """

    @classmethod
    def requires(cls, config: Any) -> List[str]:
        """依赖哪些 executor_id。默认空。

        沙箱原生工具 requires=['sandbox'];沙箱-backed 分析工具同。
        """
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        """【可选】消费面:工具执行后反改输入。默认不实现。

        ImageLoader → USER_PART(图片, SESSION)
        RagSearch   → USER_PART(chunks, TURN)
        """
        return []


# --------------------------------------------------------------------------- #
# Consumer 编排骨架(RFC-005 §3.3 / S8)
# --------------------------------------------------------------------------- #
class ConsumerRegistry:
    """capability_id → ResourceProtocol 实例 的注册表(S8)。

    供工具回调链在执行后查 Consumer 并反改输入。RAG/多模态加载器等
    "工具行为修改输入"的资源在此注册,统一走 consume() 路径,不进特例。
    """

    def __init__(self) -> None:
        self._consumers: Dict[str, ResourceProtocol] = {}

    def register(self, resource: ResourceProtocol) -> None:
        self._consumers[resource.capability_id] = resource

    def get(self, capability_id: str) -> Optional[ResourceProtocol]:
        return self._consumers.get(capability_id)

    def has(self, capability_id: str) -> bool:
        return capability_id in self._consumers


async def apply_consumption(
    consumers: ConsumerRegistry,
    facade: Any,
    capability_id: str,
    tool_result: Any,
    conv_id: str,
) -> List[Contribution]:
    """工具执行后,把结果转为对输入的写(S8 编排骨架)。

    若 capability_id 是已注册 Consumer:
    - 调 resource.consume(tool_result) → List[Contribution]
    - SESSION lifetime 写入 facade 会话运行态(跨轮可见)
    - TURN lifetime 仅本轮(透传当轮 user_parts,不入会话存储)
    非 Consumer(capability 未注册)→ 返回空,不反改输入。

    agent 工具回调链在拿到 tool_result 后调用本函数;返回的 Contribution
    由 agent 侧自行并入本轮 user_parts(全链路接入)。

    facade 为鸭子类型:需提供 add_session_part(conv_id, contribution)。
    """
    consumer = consumers.get(capability_id)
    if consumer is None:
        return []
    try:
        contribs = await consumer.consume(tool_result)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"consume failed for capability={capability_id}: {e}"
        )
        return []
    turn_parts: List[Contribution] = []
    for c in contribs:
        if c.lifetime == Lifetime.SESSION:
            facade.add_session_part(conv_id, c)
        elif c.lifetime == Lifetime.TURN:
            turn_parts.append(c)
        # CONFIG_STATIC 的 consume 产物理论不应出现(consume 是运行态),忽略
    return turn_parts