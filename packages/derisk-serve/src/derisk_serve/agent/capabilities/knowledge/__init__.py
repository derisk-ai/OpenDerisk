"""Knowledge capability —— 知识库能力自管目录(RFC-005 Step C / RFC-006 Stage 7)。

知识库是 Consumer:declare 库列表 + consume 检索回注。
register_wrappers 用纯 core 谓词(属性判断)注册,不 import serve 的
KnowledgePackSearchResource 或 ext 的 KnowledgeSpaceResource,避免分层倒置。

RFC-006 Stage 7:register_capability 注册旧实例→KnowledgeCapability(自管理)过渡
provider,facade 遍历旧 ResourcePack 时翻成 Capability 对象(修复旧 wrapper declare
桩)。注:facade 时序 declare 先于 prepare,Knowledge declare 依赖 spaces 元数据(对象
非 str,无法 DataRequirement 占位),故 KnowledgeCapability 不自管 prepare 的重 I/O
(from_legacy 复用旧实例已泄水合的 spaces);execute 保持 v1 action。详见 capability.py。
"""

from .capability import KnowledgeCapability  # noqa: F401
from .resource import KnowledgeCapabilityResource  # noqa: F401

__all__ = ["KnowledgeCapability", "KnowledgeCapabilityResource"]


def register(registry) -> None:
    pass


def _is_knowledge_legacy(sub) -> bool:
    """纯 core 谓词:识别知识库资源(鸭式属性)。

    覆盖三实现:RetrieverResource(有 retriever/knowledge_spaces)、
    KnowledgePackSearchResource(有 knowledge_spaces)、
    KnowledgeSpaceResource(有 space_slug/get_vault)。
    """
    return (
        hasattr(sub, "knowledge_spaces")
        or hasattr(sub, "retriever")
        or hasattr(sub, "space_slug")
    )


def register_wrappers(facade) -> None:
    """注册 knowledge capability 双轨 wrapper 到 facade(纯 core,旧路径)。"""
    from .resource import KnowledgeCapabilityResource
    facade.register_legacy_wrapper(
        _is_knowledge_legacy,
        lambda legacy: KnowledgeCapabilityResource(legacy_instance=legacy),
    )


def build_capability(value, system_app=None):
    """RFC-006 Stage 7:从 config dict 构造 KnowledgeCapability(无 I/O;spaces 走 config)。"""
    return KnowledgeCapability.from_config(value, system_app)


def register_capability(facade) -> None:
    """RFC-006 Stage 7:注册 knowledge config factory + 旧实例→Capability 过渡 provider。"""
    from .capability import KnowledgeCapability
    facade.register_capability_factory("knowledge_pack", build_capability)
    facade.register_legacy_capability_provider(
        _is_knowledge_legacy, KnowledgeCapability.from_legacy
    )

# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "knowledge_pack"


def register_capability_to(registry) -> None:
    registry.register(CAPABILITY_TYPE_KEY, build_capability)
