"""memory hook 注册测试。"""
from unittest.mock import MagicMock
from derisk.agent.core.v2.memory_hook_setup import register_memory_hooks


def test_register_memory_hooks_adds_4_hooks():
    hook_manager = MagicMock()
    bundle = MagicMock()
    bundle.manager = MagicMock()
    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=bundle,
        reflection_interval=10,
    )
    # append_hooks 应被调用一次，传入 4 个 HookConfig（tier0/1/2/3）
    hook_manager.append_hooks.assert_called_once()
    hooks = hook_manager.append_hooks.call_args[0][0]
    assert len(hooks) == 4


def test_register_skips_if_no_bundle():
    hook_manager = MagicMock()
    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=None,
        reflection_interval=10,
    )
    hook_manager.append_hooks.assert_not_called()
