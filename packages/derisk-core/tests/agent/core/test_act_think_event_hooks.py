"""Gap #179: 验证 act/think 事件埋点正确接到 base_agent / react_master_agent。

测试方式：mock emit_* 函数，验证：
1. emit_think_start / emit_think_end / emit_act_start / emit_act_end 可 import
2. base_agent.act 中 emit_act_start/end 的代码路径存在（静态检查）
3. react_master_agent.act 中 emit_act_start/end 的代码路径存在（静态检查）
4. base_agent.generate_reply 中 emit_think_start 的代码路径存在（静态检查）
"""
import inspect
from unittest.mock import MagicMock, patch

import pytest


class TestEventEmittersImportable:
    """4 个事件发射函数可正常 import。"""

    def test_emit_think_start_importable(self):
        from derisk.agent.core.event_log import emit_think_start
        assert callable(emit_think_start)

    def test_emit_think_end_importable(self):
        from derisk.agent.core.event_log import emit_think_end
        assert callable(emit_think_end)

    def test_emit_act_start_importable(self):
        from derisk.agent.core.event_log import emit_act_start
        assert callable(emit_act_start)

    def test_emit_act_end_importable(self):
        from derisk.agent.core.event_log import emit_act_end
        assert callable(emit_act_end)


class TestEventHooksWiredInSource:
    """静态检查：emit_act_start/end/think_start 已写入源码。"""

    def test_base_agent_act_emits_act_start_and_end(self):
        from derisk.agent.core import base_agent
        src = inspect.getsource(base_agent)
        # act 方法内调 emit_act_start 和 emit_act_end
        assert "from derisk.agent.core.event_log import emit_act_start" in src
        assert "from derisk.agent.core.event_log import emit_act_end" in src
        assert "emit_act_start(" in src
        assert "emit_act_end(" in src

    def test_base_agent_generate_reply_emits_think_start(self):
        from derisk.agent.core import base_agent
        src = inspect.getsource(base_agent)
        assert "from derisk.agent.core.event_log import emit_think_start" in src
        assert "emit_think_start(" in src

    def test_base_agent_generate_reply_emits_think_end(self):
        from derisk.agent.core import base_agent
        src = inspect.getsource(base_agent)
        assert "from derisk.agent.core.event_log import emit_think_end" in src
        assert "emit_think_end(" in src

    def test_react_master_agent_act_emits_act_start_and_end(self):
        from derisk.agent.expand.react_master_agent import react_master_agent
        src = inspect.getsource(react_master_agent)
        assert "from derisk.agent.core.event_log import emit_act_start" in src
        assert "from derisk.agent.core.event_log import emit_act_end" in src
        assert "emit_act_start(" in src
        assert "emit_act_end(" in src


class TestEmitFunctionsFireAndForget:
    """emit_* 函数本身是 fire-and-forget，无 event loop 时不抛错。"""

    def test_emit_act_start_no_loop_swallowed(self):
        from derisk.agent.core.event_log import emit_act_start
        # 同步上下文，无 event loop
        emit_act_start(conv_id="c1", tool_name="t1", message_id="m1", args={})

    def test_emit_act_end_no_loop_swallowed(self):
        from derisk.agent.core.event_log import emit_act_end
        emit_act_end(conv_id="c1", tool_name="t1", success=True, message_id="m1")

    def test_emit_think_start_no_loop_swallowed(self):
        from derisk.agent.core.event_log import emit_think_start
        emit_think_start(conv_id="c1", message_id="m1", model_name="m", round_index=0)

    def test_emit_think_end_no_loop_swallowed(self):
        from derisk.agent.core.event_log import emit_think_end
        emit_think_end(conv_id="c1", message_id="m1", thinking="t", content="c")

    def test_emit_act_start_empty_conv_skipped(self):
        """空 conv_id → 不调 DAO。"""
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao"
        ) as mock_dao:
            from derisk.agent.core.event_log import emit_act_start
            emit_act_start(conv_id="", tool_name="t1", args={})
            mock_dao.assert_not_called()

    def test_emit_act_start_empty_tool_name_skipped(self):
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao"
        ) as mock_dao:
            from derisk.agent.core.event_log import emit_act_start
            emit_act_start(conv_id="c1", tool_name="", args={})
            mock_dao.assert_not_called()

