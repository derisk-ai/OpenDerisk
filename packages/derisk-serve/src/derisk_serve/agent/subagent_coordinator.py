"""SubagentCoordinator: 子 Agent 完成监听器。

跟踪 pending_subagents，全 done 则触发主 resume。
设计成可插拔 backend：LocalSubagentBackend（单进程 asyncio.create_task），
未来加 DistributedSubagentBackend（RPC 队列派发到其他机器）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from derisk.agent.core.subagent_handle import (
    SubAgentHandle,
    SubAgentMode,
    SubAgentStatus,
)

logger = logging.getLogger(__name__)


class SubagentCoordinator:
    """子 Agent 完成监听器：跟踪 pending_subagents，全 done 则触发主 resume。

    Usage:
        coordinator = SubagentCoordinator(agent_chat=self)
        await coordinator.register_subagent(main_conv_id, sub_conv_id, mode)
        # ... 子 agent 跑完后 ...
        await coordinator.on_subagent_done(main_conv_id, sub_conv_id, result)
    """

    def __init__(self, agent_chat: Any):
        """Args:
            agent_chat: AgentChat 实例，提供 gpts_conversations / aggregation_chat 等依赖。
        """
        self._agent_chat = agent_chat

    # ---- pending_subagents 持久化（gpts_conversations.extra JSON）----

    async def _read_pending(self, main_conv_id: str) -> List[SubAgentHandle]:
        """从 gpts_conversations.extra 读取 pending_subagents 列表。"""
        conv = self._agent_chat.gpts_conversations.get_by_conv_id(main_conv_id)
        if not conv or not getattr(conv, "extra", None):
            return []
        try:
            extra = json.loads(conv.extra) if isinstance(conv.extra, str) else conv.extra
        except (json.JSONDecodeError, TypeError):
            return []
        pending_list = extra.get("pending_subagents", []) if isinstance(extra, dict) else []
        return [SubAgentHandle.from_dict(item) for item in pending_list]

    async def _write_pending(
        self, main_conv_id: str, handles: List[SubAgentHandle]
    ) -> None:
        """写入 pending_subagents 列表到 gpts_conversations.extra。"""
        conv = self._agent_chat.gpts_conversations.get_by_conv_id(main_conv_id)
        if not conv:
            logger.warning(f"[subagent-coordinator] conv {main_conv_id} not found")
            return
        try:
            extra = json.loads(conv.extra) if isinstance(conv.extra, str) else (conv.extra or {})
        except (json.JSONDecodeError, TypeError):
            extra = {}
        if not isinstance(extra, dict):
            extra = {}
        extra["pending_subagents"] = [h.to_dict() for h in handles]
        # 直接 update extra 字段
        session = self._agent_chat.gpts_conversations.get_raw_session()
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsEntity
        session.query(GptsConversationsEntity).filter(
            GptsConversationsEntity.conv_id == main_conv_id
        ).update(
            {GptsConversationsEntity.extra: json.dumps(extra, ensure_ascii=False)},
            synchronize_session="fetch",
        )
        session.commit()
        session.close()

    # ---- 公开接口 ----

    async def register_subagent(
        self,
        main_conv_id: str,
        sub_conv_id: str,
        mode: SubAgentMode,
    ) -> SubAgentHandle:
        """注册一个子 agent 到 pending 列表。"""
        handle = SubAgentHandle(
            sub_conv_id=sub_conv_id,
            main_conv_id=main_conv_id,
            mode=mode,
            status=SubAgentStatus.RUNNING,
            started_at=time.time(),
        )
        handles = await self._read_pending(main_conv_id)
        handles.append(handle)
        await self._write_pending(main_conv_id, handles)
        logger.info(
            f"[subagent-coordinator] registered subagent {sub_conv_id} "
            f"(mode={mode.value}) for main {main_conv_id}"
        )
        return handle

    async def on_subagent_done(
        self, main_conv_id: str, sub_conv_id: str, result: str
    ) -> None:
        """子 agent 成功完成：标记 DONE，若全部完成则触发主 resume。"""
        handles = await self._read_pending(main_conv_id)
        for h in handles:
            if h.sub_conv_id == sub_conv_id:
                h.status = SubAgentStatus.DONE
                h.result = result
                h.finished_at = time.time()
                break
        await self._write_pending(main_conv_id, handles)
        logger.info(
            f"[subagent-coordinator] subagent {sub_conv_id} done for main {main_conv_id}"
        )
        if all(h.is_terminal() for h in handles):
            await self._trigger_main_resume(main_conv_id, handles)

    async def on_subagent_failed(
        self, main_conv_id: str, sub_conv_id: str, error: str
    ) -> None:
        """子 agent 失败：标记 FAILED，若全部完成则触发主 resume（带错误）。"""
        handles = await self._read_pending(main_conv_id)
        for h in handles:
            if h.sub_conv_id == sub_conv_id:
                h.status = SubAgentStatus.FAILED
                h.error = error
                h.finished_at = time.time()
                break
        await self._write_pending(main_conv_id, handles)
        logger.warning(
            f"[subagent-coordinator] subagent {sub_conv_id} failed for main {main_conv_id}: {error}"
        )
        if all(h.is_terminal() for h in handles):
            await self._trigger_main_resume(main_conv_id, handles)

    async def _rebuild_subagent_transcript(
        self, sub_conv_id: str, max_messages: int = 5
    ) -> str:
        """Tier 3.3: 扫描子 agent 的 gpts_messages，重建崩溃前的 thinking chain。

        提取最近 N 条消息的 thinking + action_report，合成为可读的进展摘要，
        让主 agent resume 时能拿到子 agent 崩溃前的部分成果。

        Args:
            sub_conv_id: 子 agent 会话 ID
            max_messages: 最多回溯多少条消息（避免超长摘要）

        Returns:
            重建的 transcript 字符串；无消息返回空字符串。
        """
        try:
            from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
            dao = GptsMessagesDao()
            messages = await dao.get_by_conv_id(sub_conv_id)
        except Exception as e:
            logger.warning(
                f"[subagent-coordinator] failed to load transcript for sub={sub_conv_id}: {e}"
            )
            return ""

        if not messages:
            return ""

        # 取最近 N 条，按时间正序输出
        recent = list(messages)[-max_messages:]
        lines = []
        for msg in recent:
            sender = getattr(msg, "sender_name", None) or "?"
            thinking = getattr(msg, "thinking", None) or ""
            content = getattr(msg, "content", None) or ""
            # action_report 是 JSON 字符串，含 tool 调用结果
            action_report_raw = getattr(msg, "action_report", None)

            # 提取 thinking（截断到 200 字符避免超长）
            if thinking:
                t = thinking.strip()[:200]
                lines.append(f"    [{sender} think] {t}")

            # 提取 action_report 里的 tool 调用
            if action_report_raw:
                try:
                    if isinstance(action_report_raw, str):
                        reports = json.loads(action_report_raw)
                    else:
                        reports = action_report_raw
                    if isinstance(reports, list):
                        for r in reports:
                            tool_name = r.get("name") or r.get("action") or "?"
                            success = r.get("is_exe_success", True)
                            content_short = (r.get("content") or "")[:150]
                            mark = "✓" if success else "✗"
                            lines.append(
                                f"    [{sender} tool {mark} {tool_name}] {content_short}"
                            )
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass
            elif content and not thinking:
                # 没有 thinking 也没有 action_report，用 content 兜底
                c = content.strip()[:150]
                if c:
                    lines.append(f"    [{sender}] {c}")

        return "\n".join(lines)

    async def _trigger_main_resume(
        self, main_conv_id: str, handles: List[SubAgentHandle]
    ) -> None:
        """所有子 agent 完成：把结果作为 user message 注入，触发主 resume。

        主会话此时应在 WAITING 状态（由 agent_chat turn-end 决策写入）。
        调 aggregation_chat 时传 gpts_conversations=[entity]，让 aggregation_chat
        内部检测到 WAITING → is_retry_chat=True，走 _inner_chat 的 retry 恢复路径。

        Tier 3.3: 对 FAILED 且无 result 的子 agent，扫描其 gpts_messages 重建
        thinking chain，让主 agent 拿到崩溃前的部分进展。
        """
        results_lines = []
        for h in handles:
            if h.status == SubAgentStatus.DONE:
                results_lines.append(f"  - 子对话 {h.sub_conv_id} 完成：\n{h.result or '(空结果)'}")
            elif h.status == SubAgentStatus.FAILED:
                # Tier 3.3: 尝试重建崩溃前的 transcript
                transcript = await self._rebuild_subagent_transcript(h.sub_conv_id)
                if transcript:
                    results_lines.append(
                        f"  - 子对话 {h.sub_conv_id} 崩溃前部分进展：\n{transcript}\n"
                        f"    失败原因：{h.error or '(未知错误)'}"
                    )
                else:
                    results_lines.append(f"  - 子对话 {h.sub_conv_id} 失败：{h.error or '(未知错误)'}")
        synthesized = "子 agent 全部完成：\n" + "\n".join(results_lines)

        logger.info(
            f"[subagent-coordinator] triggering main resume for {main_conv_id} "
            f"({len(handles)} subagents)"
        )
        # 清空 pending 列表（resume 后不再 pending）
        await self._write_pending(main_conv_id, [])

        # 读 main conv entity，拿 gpts_name(app_code) 与 state
        try:
            conv = self._agent_chat.gpts_conversations.get_by_conv_id(main_conv_id)
            if not conv:
                logger.warning(
                    f"[subagent-coordinator] main conv {main_conv_id} not found; cannot resume"
                )
                return
            # 触发 retry：传 gpts_conversations=[conv]，让 aggregation_chat 内部检测 WAITING → is_retry_chat=True
            await self._agent_chat.aggregation_chat(
                conv_id=main_conv_id,
                agent_conv_id=main_conv_id,
                gpts_name=conv.gpts_name,
                user_query=synthesized,
                user_code=conv.user_code,
                sys_code=conv.sys_code,
                gpts_conversations=[conv],
            )
        except Exception as e:
            logger.exception(
                f"[subagent-coordinator] failed to trigger main resume for {main_conv_id}: {e}"
            )

    async def recover_main(self, main_conv_id: str) -> None:
        """启动恢复：扫 main 的 pending_subagents，按子状态 + 心跳决策。

        用于 PR 4 的 RecoveryDaemon 启动时恢复。

        Tier 3.2/3.3: 对 RUNNING 状态的子 agent，按 lease 状态判断：
        - lease 已过期 → 子 agent 真死 → 标记 FAILED + 重建 transcript → 触发 main resume
        - lease 未过期 → 子 agent 在另一进程跑 → 注册监听等子完成
        """
        handles = await self._read_pending(main_conv_id)
        if not handles:
            return

        # Tier 3.2: 对 RUNNING 子 agent 检查 lease 是否过期
        from derisk_serve.agent.heartbeat import is_lease_expired
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao
        dao = GptsConversationsDao()
        modified = False
        for h in handles:
            if h.status != SubAgentStatus.RUNNING:
                continue
            try:
                wid, expires_at = await asyncio.to_thread(dao.get_lease_holder, h.sub_conv_id)
                if is_lease_expired(expires_at):
                    # 子 agent 真死（lease 过期）→ 标记 FAILED
                    logger.warning(
                        f"[subagent-coordinator] recover_main: sub={h.sub_conv_id} "
                        f"lease expired (holder={wid}), marking FAILED"
                    )
                    h.status = SubAgentStatus.FAILED
                    h.error = f"subagent crashed (lease expired, last holder={wid})"
                    h.finished_at = time.time()
                    modified = True
            except Exception as e:
                logger.warning(
                    f"[subagent-coordinator] recover_main: failed to check lease for "
                    f"sub={h.sub_conv_id}: {e}"
                )

        if modified:
            await self._write_pending(main_conv_id, handles)

        all_done = all(h.is_terminal() for h in handles)
        if all_done:
            await self._trigger_main_resume(main_conv_id, handles)
            return

        # 还有未完成的子 agent（lease 仍新鲜，在另一进程跑）→ 注册监听等子完成
        logger.info(
            f"[subagent-coordinator] recover_main: {main_conv_id} has "
            f"{sum(1 for h in handles if not h.is_terminal())} still-running subagents"
        )


# ---- PR 2 Tier 1.4: 全局 coordinator 单例（供 SubAgent 工具访问）----

_global_coordinator: Optional["SubagentCoordinator"] = None


def set_subagent_coordinator(coordinator: Optional["SubagentCoordinator"]) -> None:
    """注册全局 coordinator（由 AgentChat 启动时调用）。"""
    global _global_coordinator
    _global_coordinator = coordinator


def get_subagent_coordinator() -> Optional["SubagentCoordinator"]:
    """获取全局 coordinator。未注册返回 None。"""
    return _global_coordinator
