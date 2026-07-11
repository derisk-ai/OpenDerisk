"""RFC-005 S14 SandboxResource(沙箱 Capability 输入投影)单测。

覆盖:
- declare_env 产 SYSTEM Contribution(env 文本,USER/SESSION scope)
- local/remote provider 的系统信息差异
- 无 sandbox_client 不崩
- env Contribution 的 cache_scope/lifetime 语义
"""

from derisk.core.interface.resource.bundle import CacheScope, Contribution, Lifetime, Slot
from derisk.agent.capabilities.sandbox.resource import SandboxResource
from derisk.agent.capabilities.sandbox.env import get_system_info


# --------------------------------------------------------------------------- #
# 假 sandbox_client
# --------------------------------------------------------------------------- #
class _FakeSandboxClient:
    def __init__(self, provider="local", skill_dir="/home/ubuntu/.derisk/skills"):
        self.provider = lambda: provider
        self.skill_dir = skill_dir


# --------------------------------------------------------------------------- #
# declare_env 基本产出
# --------------------------------------------------------------------------- #
def test_declare_env_produces_system_contribution():
    res = SandboxResource(_FakeSandboxClient("local"), work_dir="/pilot/data")
    contribs = res.declare_env()
    assert len(contribs) == 1
    c = contribs[0]
    assert c.slot == Slot.SYSTEM
    assert c.capability_id == "sandbox"
    assert "/pilot/data" in c.content
    assert "环境信息" in c.content


def test_declare_env_scope_lifetime_semantics():
    """沙箱 env:本会话环境 → SESSION lifetime、ENV cache_scope。"""
    res = SandboxResource(_FakeSandboxClient("local"))
    c = res.declare_env()[0]
    assert c.lifetime == Lifetime.SESSION
    assert c.cache_scope == CacheScope.ENV


# --------------------------------------------------------------------------- #
# local vs remote provider
# --------------------------------------------------------------------------- #
def test_local_provider_system_info():
    res = SandboxResource(_FakeSandboxClient("local"))
    info = get_system_info(res.sandbox_client)
    assert "本地沙箱" in info


def test_remote_provider_system_info():
    res = SandboxResource(_FakeSandboxClient("docker"))
    info = get_system_info(res.sandbox_client)
    assert "Ubuntu" in info


# --------------------------------------------------------------------------- #
# skill_dir 进 env
# --------------------------------------------------------------------------- #
def test_skill_dir_in_env_text():
    res = SandboxResource(_FakeSandboxClient("local", skill_dir="/sandbox/skills"))
    c = res.declare_env()[0]
    assert "/sandbox/skills" in c.content


# --------------------------------------------------------------------------- #
# 无 sandbox_client 不崩
# --------------------------------------------------------------------------- #
def test_no_sandbox_client_works():
    res = SandboxResource(None, work_dir="/workspace")
    c = res.declare_env()[0]
    assert "/workspace" in c.content
    # 无系统信息行,但有 env 框架
    assert "环境信息" in c.content


# --------------------------------------------------------------------------- #
# requires 声明依赖共享 sandbox executor(RFC-006 Stage 2)
# --------------------------------------------------------------------------- #
def test_requires_sandbox_executor():
    res = SandboxResource(_FakeSandboxClient())
    assert res.requires() == ["sandbox"]


# --------------------------------------------------------------------------- #
# 协议兼容:class declare 默认空
# --------------------------------------------------------------------------- #
def test_class_declare_default_empty():
    """ResourceProtocol.declare 类方法兼容默认空(SandboxResource 用 declare_env 实例)。"""
    assert SandboxResource.declare(None) == []
