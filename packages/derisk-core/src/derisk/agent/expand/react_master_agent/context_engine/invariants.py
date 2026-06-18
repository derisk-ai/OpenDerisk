"""InvariantGuard —— 发送前硬不变量门禁（I1–I6）。

在最终 message list 上运行一次（repair 模式生产 / strict 模式测试）。
绝不静默丢有效上下文；repair 幂等。

- I1 无 orphan tool 消息：每条 ``role=tool`` 必有前序 assistant 的 tool_calls 含匹配 id。
- I2 无悬空 tool_call：assistant 声明的每个 tool_call.id 必有后随匹配 tool 结果；
     否则**剥离该 id**（绝不造 ``[result not available]``）。
- I3 无 orphan 头部 tool：首条非 system 消息不得是 tool。
- I4 锚点/首条非 system 为 human（cold handoff 计入 human）。
- I5 相邻重复 human 去重。
- I6 结构有效：无相邻重复 tool 消息；（token 超限仅 flag，由分层处理）。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_TOOL = "tool"
_AI = "ai"
_ASSISTANT = "assistant"
_HUMAN = "human"
_USER = "user"
_SYSTEM = "system"


@dataclass
class GuardReport:
    violations: List[str] = field(default_factory=list)
    repairs: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


class InvariantGuard:
    def check(self, messages: List[Dict[str, Any]]) -> GuardReport:
        """只报告不修改。"""
        report = GuardReport()
        self._scan(messages, report, repair=False)
        return report

    def repair(
        self, messages: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], GuardReport]:
        """返回修复后的新列表 + 报告。幂等。"""
        report = GuardReport()
        repaired = self._scan(messages, report, repair=True)
        return repaired, report

    # ------------------------------------------------------------------ #
    def _scan(
        self, messages: List[Dict[str, Any]], report: GuardReport, repair: bool
    ) -> List[Dict[str, Any]]:
        msgs = [dict(m) for m in messages]  # 浅拷贝，避免改原列表

        # ---- I2: 收集每个 assistant 声明的 tool_call id，以及后随的 tool 结果 id ----
        provided_tool_ids = set()
        for m in msgs:
            if self._role(m) == _TOOL:
                tcid = m.get("tool_call_id")
                if tcid:
                    provided_tool_ids.add(tcid)

        # ---- 逐条处理 ----
        out: List[Dict[str, Any]] = []
        declared_ids_so_far = set()
        for idx, m in enumerate(msgs):
            role = self._role(m)

            if role in (_AI, _ASSISTANT) or (
                role not in (_TOOL, _HUMAN, _USER, _SYSTEM) and m.get("tool_calls")
            ):
                tool_calls = m.get("tool_calls") or []
                if tool_calls:
                    # I2: 剥离没有对应 tool 结果的 tool_call id
                    kept = []
                    for tc in tool_calls:
                        tcid = tc.get("id")
                        if tcid and tcid not in provided_tool_ids:
                            report.violations.append(f"I2 悬空 tool_call: {tcid}")
                            if repair:
                                report.repairs.append(f"I2 剥离悬空 tool_call: {tcid}")
                                continue  # 丢弃该 tc
                        kept.append(tc)
                        if tcid:
                            declared_ids_so_far.add(tcid)
                    if repair:
                        if kept:
                            m["tool_calls"] = kept
                        else:
                            m.pop("tool_calls", None)
                    # assistant 若既无 tool_calls 又无内容 → 丢弃
                    if repair and not m.get("tool_calls"):
                        content = m.get("content")
                        if not (content and str(content).strip()):
                            report.repairs.append("I2 丢弃空 assistant 消息")
                            continue
                out.append(m)

            elif role == _TOOL:
                tcid = m.get("tool_call_id")
                # I1: tool 必须有前序声明
                if not tcid or tcid not in declared_ids_so_far:
                    report.violations.append(
                        f"I1 orphan tool 消息: tool_call_id={tcid}"
                    )
                    if repair:
                        report.repairs.append(f"I1 丢弃 orphan tool: {tcid}")
                        continue  # 丢弃 orphan tool
                # I3: 首条非 system 不得是 tool（出现说明 orphan，已被 I1 兜住）
                out.append(m)

            else:
                out.append(m)

        # ---- I3 / I4: 头部检查 ----
        self._check_head(out, report, repair)

        # ---- I5: 相邻重复 human 去重 ----
        out = self._dedup_adjacent_human(out, report, repair)

        # ---- I6: 相邻重复 tool 去重 ----
        out = self._dedup_adjacent_tool(out, report, repair)

        return out if repair else messages

    # ------------------------------------------------------------------ #
    def _check_head(self, msgs, report, repair):
        # 找到首条非 system
        for m in msgs:
            role = self._role(m)
            if role == _SYSTEM:
                continue
            if role == _TOOL:
                report.violations.append("I3 首条非 system 消息是 tool")
                # repair: I1 已剥离 orphan tool，理论不会到这；保守不再处理
            elif role not in (_HUMAN, _USER):
                # I4: 首条非 system 最好是 human；assistant 起头多数 provider 容忍，仅 flag
                report.violations.append("I4 首条非 system 消息非 human")
            break

    def _dedup_adjacent_human(self, msgs, report, repair):
        if not repair:
            # 仅检测
            prev = None
            for m in msgs:
                role = self._role(m)
                if role in (_HUMAN, _USER):
                    c = self._content_str(m)
                    if prev is not None and c == prev:
                        report.violations.append("I5 相邻重复 human 消息")
                    prev = c
                else:
                    prev = None
            return msgs

        out = []
        prev_human = None
        for m in msgs:
            role = self._role(m)
            if role in (_HUMAN, _USER):
                c = self._content_str(m)
                if prev_human is not None and c == prev_human:
                    report.violations.append("I5 相邻重复 human 消息")
                    report.repairs.append("I5 去重相邻 human")
                    continue
                prev_human = c
            else:
                prev_human = None
            out.append(m)
        return out

    def _dedup_adjacent_tool(self, msgs, report, repair):
        if not repair:
            prev = None
            for m in msgs:
                role = self._role(m)
                if role == _TOOL:
                    key = (m.get("tool_call_id"), self._content_str(m))
                    if prev is not None and key == prev:
                        report.violations.append("I6 相邻重复 tool 消息")
                    prev = key
                else:
                    prev = None
            return msgs

        out = []
        prev_tool = None
        for m in msgs:
            role = self._role(m)
            if role == _TOOL:
                key = (m.get("tool_call_id"), self._content_str(m))
                if prev_tool is not None and key == prev_tool:
                    report.violations.append("I6 相邻重复 tool 消息")
                    report.repairs.append("I6 去重相邻 tool")
                    continue
                prev_tool = key
            else:
                prev_tool = None
            out.append(m)
        return out

    # ------------------------------------------------------------------ #
    @staticmethod
    def _role(m: Dict[str, Any]) -> str:
        return str(m.get("role", "")).lower()

    @staticmethod
    def _content_str(m: Dict[str, Any]) -> str:
        c = m.get("content", "")
        return c if isinstance(c, str) else str(c)
