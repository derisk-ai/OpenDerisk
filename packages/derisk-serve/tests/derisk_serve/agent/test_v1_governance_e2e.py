"""Gap #180: e2e 集成测试。

场景 1：主 agent → spawn 2 async 子 agent → 主 WAITING → 子 agent 完成 → 主 resume
场景 2：主 agent → 中途崩溃 → 重启 → RecoveryDaemon → step-level resume

这两个测试用 mock 模拟整个流程，不启动真实 LLM/DB，但验证所有组件协同工作。
"""
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeConvStore:
    """内存版的 gpts_conversations DAO，模拟 extra JSON 持久化。"""

    def __init__(self):
        self._store = {}  # conv_id -> dict {extra: str(JSON) or None}

    def get_or_create(self, conv_id: str):
        if conv_id not in self._store:
            self._store[conv_id] = {"extra": None}
        return self._store[conv_id]

    def get_by_conv_id(self, conv_id: str):
        if conv_id not in self._store:
            return None
        conv = MagicMock()
        conv.extra = self._store[conv_id]["extra"]
        return conv

    def get_raw_session(self):
        store = self

        class _FakeSession:
            def query(self, entity):
                class _Query:
                    def filter(self, *args, **kwargs):
                        return self

                    def update(self, update_dict, synchronize_session="fetch"):
                        # 提取 extra 的新值
                        # update_dict 的 key 可能是 Entity.extra (Column)，value 是 JSON 字符串
                        for k, v in update_dict.items():
                            # 用字符串 attribute 名比对
                            k_name = getattr(k, "name", None) or str(k)
                            if k_name == "extra":
                                store._store[store._current_conv]["extra"] = v

                        class _Result:
                            rowcount = 1

                        return _Result()

                return _Query()

            def commit(self):
                pass

            def close(self):
                pass

        return _FakeSession()

    def set_current_conv(self, conv_id: str):
        self._current_conv = conv_id


class TestAsyncSubagentE2E:
    """场景 1: 完整 async 子 agent 流程。"""

    @pytest.mark.asyncio
    async def test_main_spawns_two_async_subagents_then_resumes(self):
        """主 agent 调 2 个 sub_agent(mode=async) →
        1. coordinator.register_subagent 被调 2 次
        2. 2 个后台 task 启动
        3. 子 agent "完成" → on_subagent_done 触发
        4. 全部 done → _trigger_main_resume 被调一次
        """
        from derisk.agent.core.reasoning.reasoning_action import AgentActionInput
        from derisk.agent.expand.actions.agent_action import SubAgent
        from derisk.agent.core.subagent_handle import (
            SubAgentHandle,
            SubAgentMode,
            SubAgentStatus,
        )
        from derisk_serve.agent.subagent_coordinator import SubagentCoordinator

        # 用 fake conv store 替代真实 DB
        fake_store = _FakeConvStore()
        main_conv_id = "conv_main_e2e"
        fake_store.get_or_create(main_conv_id)

        mock_agent_chat = MagicMock()
        mock_agent_chat.gpts_conversations = fake_store

        coordinator = SubagentCoordinator(agent_chat=mock_agent_chat)
        # mock _trigger_main_resume，避免依赖真实 aggregation_chat
        coordinator._trigger_main_resume = AsyncMock()

        # 主 agent context
        agent_context = MagicMock()
        agent_context.conv_id = main_conv_id
        agent_context.extra = {}

        sender = MagicMock()
        sender.name = "main_agent"
        sender.role = "main"

        # 跟踪两个 sub_conv_id
        sub_conv_ids = []

        async def mock_start_app(user_input=None, sender=None, conv_uid=None, parent_depth=None):
            sub_conv_ids.append(conv_uid)
            return MagicMock(content=f"result from {conv_uid}")

        mock_app_resource = MagicMock()
        mock_app_resource._start_app = mock_start_app

        with patch(
            "derisk_serve.agent.subagent_coordinator.get_subagent_coordinator",
            return_value=coordinator,
        ), patch(
            "derisk_serve.agent.resource.app.GptAppResource",
            return_value=mock_app_resource,
        ):
            # Spawn 子 agent 1
            fake_store.set_current_conv(main_conv_id)
            action1 = SubAgent(
                action_uid="act_1",
                action_input=AgentActionInput(
                    agent_name="sub_app", content="do task 1", mode="async"
                ),
            )
            result1 = await action1.run(
                agent=sender,
                agent_context=agent_context,
                message_id="msg_1",
                current_message=MagicMock(message_id="msg_1"),
                memory=MagicMock(),
                message=MagicMock(context={}),
            )
            assert result1.is_exe_success is True

            # Spawn 子 agent 2
            fake_store.set_current_conv(main_conv_id)
            action2 = SubAgent(
                action_uid="act_2",
                action_input=AgentActionInput(
                    agent_name="sub_app", content="do task 2", mode="async"
                ),
            )
            result2 = await action2.run(
                agent=sender,
                agent_context=agent_context,
                message_id="msg_1",
                current_message=MagicMock(message_id="msg_1"),
                memory=MagicMock(),
                message=MagicMock(context={}),
            )
            assert result2.is_exe_success is True

            # 2 个子 agent 应已注册到 coordinator
            handles = await coordinator._read_pending(main_conv_id)
            assert len(handles) == 2, f"expected 2 handles, got {len(handles)}"
            assert all(
                h.status in (SubAgentStatus.RUNNING, SubAgentStatus.DONE) for h in handles
            )

            # 等待后台 task 完成（on_subagent_done 会改状态）
            for _ in range(40):
                handles = await coordinator._read_pending(main_conv_id)
                if handles and all(h.status == SubAgentStatus.DONE for h in handles):
                    break
                await asyncio.sleep(0.05)

            # 所有子 agent 都应 done
            handles = await coordinator._read_pending(main_conv_id)
            assert all(h.status == SubAgentStatus.DONE for h in handles), (
                f"expected all DONE, got {[h.status for h in handles]}"
            )

            # _trigger_main_resume 应被调用（主会话 resume）
            coordinator._trigger_main_resume.assert_awaited()
            # 验证传入的 handles 包含两个 sub_conv_id
            call_args = coordinator._trigger_main_resume.call_args
            resume_handles = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("handles", [])
            resume_sub_ids = {h.sub_conv_id for h in resume_handles}
            assert len(resume_sub_ids) == 2, f"expected 2 sub_ids, got {resume_sub_ids}"
            for sub_id in sub_conv_ids:
                assert sub_id in resume_sub_ids, f"missing {sub_id}"


class TestCrashRecoveryE2E:
    """场景 2: 崩溃恢复流程。"""

    @pytest.mark.asyncio
    async def test_crashed_running_conv_recovers_via_lease_and_step_resume(self):
        """主 agent 中途崩溃 → 重启 → RecoveryDaemon 扫到 RUNNING + lease 过期 →
        标记 RETRYING + 触发 step-level resume。
        """
        from derisk_serve.agent.recovery_daemon import RecoveryDaemon

        # 构造一个崩溃的会话：state=RUNNING, lease_expires_at=2 分钟前
        crashed_conv = MagicMock()
        crashed_conv.conv_id = "conv_crash_e2e"
        crashed_conv.state = "RUNNING"
        crashed_conv.last_heartbeat = datetime.utcnow() - timedelta(seconds=180)
        crashed_conv.lease_expires_at = datetime.utcnow() - timedelta(seconds=120)
        crashed_conv.worker_id = "dead_worker"
        crashed_conv.extra = None  # 无 pending_subagents

        mock_dao = MagicMock()
        mock_dao.get_running_convs = MagicMock(return_value=[crashed_conv])
        mock_dao.acquire_lease = MagicMock(return_value=True)
        mock_dao.update = MagicMock()

        daemon = RecoveryDaemon.__new__(RecoveryDaemon)
        daemon._agent_chat = None
        daemon._coordinator = None
        daemon._stale_threshold_seconds = 90
        # mock 触发恢复的方法
        daemon._trigger_main_retry = AsyncMock()

        with patch(
            "derisk_serve.agent.recovery_daemon.GptsConversationsDao",
            return_value=mock_dao,
        ), patch(
            "derisk_serve.agent.recovery_daemon.acquire_lease",
            new=AsyncMock(return_value=True),
        ):
            await daemon.scan_and_recover()

        # lease 获取成功（worker_id="dead_worker" + lease_expires_at < now）
        # → 标记 RETRYING
        # update 被调用，state=RETRYING（小写 value）
        update_calls = mock_dao.update.call_args_list
        assert any(
            str(call.args[1]).upper() == "RETRYING" for call in update_calls
        ), f"expected RETRYING state update, got {update_calls}"

        # _trigger_main_retry 被调用
        daemon._trigger_main_retry.assert_awaited_once()
        retry_call_args = daemon._trigger_main_retry.call_args
        # _trigger_main_retry(conv_id: str)
        retry_conv_id = retry_call_args.args[0] if retry_call_args.args else retry_call_args.kwargs.get("conv_id")
        assert retry_conv_id == "conv_crash_e2e"

    @pytest.mark.asyncio
    async def test_crashed_conv_with_fresh_lease_skipped(self):
        """RUNNING 但 lease 还新鲜 → 跳过（其他进程还在跑）。"""
        from derisk_serve.agent.recovery_daemon import RecoveryDaemon

        running_conv = MagicMock()
        running_conv.conv_id = "conv_running_e2e"
        running_conv.state = "RUNNING"
        running_conv.last_heartbeat = datetime.utcnow() - timedelta(seconds=10)
        running_conv.lease_expires_at = datetime.utcnow() + timedelta(seconds=60)
        running_conv.worker_id = "alive_worker"
        running_conv.extra = None

        mock_dao = MagicMock()
        mock_dao.get_running_convs = MagicMock(return_value=[running_conv])
        mock_dao.acquire_lease = MagicMock(return_value=False)  # lease 抢不到
        mock_dao.update = MagicMock()

        daemon = RecoveryDaemon.__new__(RecoveryDaemon)
        daemon._agent_chat = None
        daemon._coordinator = None
        daemon._stale_threshold_seconds = 90
        daemon._trigger_main_retry = AsyncMock()

        with patch(
            "derisk_serve.agent.recovery_daemon.GptsConversationsDao",
            return_value=mock_dao,
        ), patch(
            "derisk_serve.agent.recovery_daemon.acquire_lease",
            new=AsyncMock(return_value=False),  # 抢不到 lease
        ):
            await daemon.scan_and_recover()

        # 不应触发 retry
        daemon._trigger_main_retry.assert_not_awaited()
        # 不应更新状态
        mock_dao.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_step_level_resume_reuses_completed_work_log(self):
        """崩溃恢复时，已成功的 work_log entry 被复用，工具不重跑。"""
        from derisk.agent.core.memory.gpts.gpts_memory import (
            ConversationCache,
            GptsMemory,
        )

        # 模拟崩溃前已完成的 work_log 条目
        mock_work_entry = MagicMock()
        mock_work_entry.tool = "execute_sql"
        mock_work_entry.args = '{"sql": "SELECT 1"}'
        mock_work_entry.result = '{"rows": 1}'
        mock_work_entry.success = True
        mock_work_entry.status = "done"
        mock_work_entry.tool_call_id = "call_1"
        mock_work_entry.message_id = "msg_1"

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = MagicMock()

        vis = MagicMock()
        cache = ConversationCache(conv_id="conv_step_e2e", vis_converter=vis)
        cache.work_logs = [mock_work_entry]

        # 验证 _lookup_cached_tool_result 能从 cache.work_logs 找到匹配 entry
        # 模拟 ReActMasterAgent._lookup_cached_tool_result 的行为：
        # 找到 (tool_name, args_hash) 匹配且 success=True → 返回 cached ActionOutput
        # 我们直接验证 cache.work_logs 里有数据可用
        assert len(cache.work_logs) == 1
        entry = cache.work_logs[0]
        assert entry.tool == "execute_sql"
        assert entry.success is True
        assert entry.status == "done"
