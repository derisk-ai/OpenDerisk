"""TimelineAssembler —— 唯一 join + 唯一排序。

把 ``gpts_messages``（消息骨架）与 ``gpts_work_log``（工具结果）按
``(message_id, tool_call_id)`` 关联成一条全局有序、原子化的时间线。

join 规则（每个 tool_call）：
  1. tool_call_id 主键命中 WorkEntry（最稳健，message 内可区分多 tool_call）
  2. message_id + 工具名 兜底（tool_call_id 缺失的旧数据）
  3. 工具名顺序定位 兜底（按出现次序消费）
  4. 都 miss → ResultStatus.MISSING，**永不渲染成 tool 消息**
     （根除 ``[result not available]`` 死循环）

排序：``order_key = (rounds, created_at, seq)``。不含会在授权恢复时 re-baseline
的不可靠字段。
"""

import logging
from typing import Any, Dict, List, Optional

from .text_utils import (
    DEFAULT_CHARS_PER_TOKEN,
    build_user_content,
    estimate_tokens_text,
    extract_text_content,
)
from .timeline import (
    ResultStatus,
    Timeline,
    TimelineUnit,
    ToolCallBinding,
    UnitKind,
)

logger = logging.getLogger(__name__)

_USER_MESSAGE_TOOL = "__user_message__"


class TimelineAssembler:
    """唯一真相源：把 messages + work_logs join 成 Timeline。"""

    def __init__(self, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN):
        self.chars_per_token = chars_per_token

    # ------------------------------------------------------------------ #
    # 公共入口
    # ------------------------------------------------------------------ #
    def assemble(
        self,
        messages: List[Any],
        work_logs_by_conv: Dict[str, List[Any]],
        current_conv_id: str,
        session_id: str,
        subagent_goal_id: Optional[str] = None,
    ) -> Timeline:
        """装配时间线。

        Args:
            messages: 整个 session 的 GptsMessage 列表（顺序不要求）。
            work_logs_by_conv: {conv_id: List[WorkEntry]}。
            current_conv_id: 当前轮 conv_id。
            session_id: 会话 id。
            subagent_goal_id: 若为子 Agent 视角，只保留匹配该 goal 的单元。
        """
        # 1) 为每个 conv 构建 join 索引（一次）
        lookups = {
            conv_id: self._build_lookups(entries)
            for conv_id, entries in work_logs_by_conv.items()
        }

        # 2) 单遍构建单元（保留原始出现序作为 seq 兜底）
        units: List[TimelineUnit] = []
        seq = 0
        for msg in messages:
            unit = self._message_to_unit(msg, lookups)
            if unit is None:
                continue
            unit.seq = seq
            seq += 1
            units.append(unit)

        # 3) 子 Agent 视角过滤（过滤后若丢失全部 USER 则回退不过滤）
        if subagent_goal_id:
            filtered = self._filter_by_goal(units, subagent_goal_id)
            has_user = any(u.kind == UnitKind.USER for u in filtered)
            if filtered and has_user:
                units = filtered
            else:
                logger.warning(
                    "[TimelineAssembler] subagent_goal_id=%s 过滤后无 USER 单元，回退不过滤",
                    subagent_goal_id,
                )

        # 4) 单次排序
        units.sort(key=lambda u: u.sort_key)

        return Timeline(
            units=units,
            current_conv_id=current_conv_id,
            session_id=session_id,
        )

    # ------------------------------------------------------------------ #
    # join 索引
    # ------------------------------------------------------------------ #
    def _build_lookups(self, entries: List[Any]) -> Dict[str, Any]:
        """从一个 conv 的 work_log 构建 join 索引。

        返回 dict：
          - by_tcid: {tool_call_id: WorkEntry}
          - by_msgid_name: {(message_id, tool_name): [WorkEntry,...]}
          - by_name: {tool_name: [WorkEntry,...]}（顺序定位兜底）
          - name_cursor: {tool_name: int}
        """
        by_tcid: Dict[str, Any] = {}
        by_msgid_name: Dict[Any, List[Any]] = {}
        by_name: Dict[str, List[Any]] = {}

        for entry in entries or []:
            tool = getattr(entry, "tool", "") or ""
            if tool == _USER_MESSAGE_TOOL:
                continue
            tc_id = getattr(entry, "tool_call_id", None)
            if tc_id:
                by_tcid[tc_id] = entry
            mid = getattr(entry, "message_id", None)
            if mid:
                by_msgid_name.setdefault((mid, tool), []).append(entry)
            if tool:
                by_name.setdefault(tool, []).append(entry)

        return {
            "by_tcid": by_tcid,
            "by_msgid_name": by_msgid_name,
            "by_name": by_name,
            "name_cursor": {},
            "msgid_name_cursor": {},
        }

    # ------------------------------------------------------------------ #
    # 单条 message -> 单元
    # ------------------------------------------------------------------ #
    def _message_to_unit(
        self, msg: Any, lookups: Dict[str, Dict[str, Any]]
    ) -> Optional[TimelineUnit]:
        role = (
            getattr(msg, "role", None) or getattr(msg, "sender", None) or ""
        ).lower()
        conv_id = getattr(msg, "conv_id", "") or ""
        message_id = getattr(msg, "message_id", None)
        rounds = getattr(msg, "rounds", 0) or 0
        created_at = self._created_at_epoch(msg)
        goal_id = getattr(msg, "goal_id", None)
        current_goal = getattr(msg, "current_goal", None)

        base = dict(
            conv_id=conv_id,
            message_id=message_id,
            rounds=rounds,
            created_at=created_at,
            goal_id=goal_id,
            current_goal=current_goal,
        )

        # 用户输入
        if role in ("human", "user"):
            content = build_user_content(msg)
            if not content:
                return None
            unit = TimelineUnit(kind=UnitKind.USER, user_content=content, **base)
            unit.tokens = estimate_tokens_text(
                extract_text_content(content), self.chars_per_token
            )
            return unit

        # system / 旧 tool 消息：跳过（tool 结果绑在 CALL 内，不独立存在）
        if role in ("system", "tool"):
            return None

        # 其余视为 AI 消息（兼容自定义 agent role，如 "BAIZE(DERISK)"）
        ai_text = extract_text_content(getattr(msg, "content", None)) or ""
        tool_calls = getattr(msg, "tool_calls", None)

        if tool_calls:
            conv_lookup = lookups.get(conv_id) or {}
            bindings = [
                self._bind_tool_call(tc, message_id, conv_lookup) for tc in tool_calls
            ]
            bindings = [b for b in bindings if b is not None]
            unit = TimelineUnit(
                kind=UnitKind.CALL, ai_text=ai_text, calls=bindings, **base
            )
            unit.tokens = self._call_unit_tokens(ai_text, bindings)
            return unit

        if ai_text and ai_text.strip():
            unit = TimelineUnit(kind=UnitKind.AI_TEXT, ai_text=ai_text, **base)
            unit.tokens = estimate_tokens_text(ai_text, self.chars_per_token)
            return unit

        return None

    def _bind_tool_call(
        self, tc: Dict[str, Any], message_id: Optional[str], lookup: Dict[str, Any]
    ) -> Optional[ToolCallBinding]:
        tc_id = tc.get("id")
        func = tc.get("function", {}) or {}
        tool_name = func.get("name", "") if isinstance(func, dict) else ""
        args = self._parse_args(func.get("arguments") if isinstance(func, dict) else None)

        if not tc_id:
            # 无 id 的 tool_call 无法稳健绑定，尽量用顺序兜底定位
            tc_id = f"__noid__{tool_name}__{message_id or ''}"

        entry = self._resolve_entry(tc.get("id"), tool_name, message_id, lookup)

        binding = ToolCallBinding(
            tool_call_id=tc_id,
            tool_name=tool_name,
            args=args,
        )
        if entry is None:
            binding.result_status = ResultStatus.MISSING
            return binding

        result = getattr(entry, "result", None)
        archive = getattr(entry, "full_result_archive", None)
        success = getattr(entry, "success", True)
        binding.result_text = result if result is not None else ""
        binding.full_result_archive = archive
        binding.summary = getattr(entry, "summary", None)
        binding.work_entry = entry
        binding.result_status = ResultStatus.OK if success else ResultStatus.ERROR
        binding.tokens = getattr(entry, "tokens", 0) or estimate_tokens_text(
            binding.result_text or "", self.chars_per_token
        )
        return binding

    def _resolve_entry(
        self,
        tc_id: Optional[str],
        tool_name: str,
        message_id: Optional[str],
        lookup: Dict[str, Any],
    ) -> Optional[Any]:
        # 1) tool_call_id 主键
        if tc_id:
            entry = lookup.get("by_tcid", {}).get(tc_id)
            if entry is not None:
                return entry

        # 2) (message_id, tool_name) 兜底（按出现次序消费）
        if message_id and tool_name:
            key = (message_id, tool_name)
            candidates = lookup.get("by_msgid_name", {}).get(key)
            if candidates:
                cursor = lookup.setdefault("msgid_name_cursor", {})
                idx = cursor.get(key, 0)
                if idx < len(candidates):
                    cursor[key] = idx + 1
                    return candidates[idx]

        # 3) 工具名顺序定位兜底
        if tool_name:
            candidates = lookup.get("by_name", {}).get(tool_name)
            if candidates:
                cursor = lookup.setdefault("name_cursor", {})
                idx = cursor.get(tool_name, 0)
                if idx < len(candidates):
                    cursor[tool_name] = idx + 1
                    return candidates[idx]

        return None

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _call_unit_tokens(
        self, ai_text: str, bindings: List[ToolCallBinding]
    ) -> int:
        total = estimate_tokens_text(ai_text or "", self.chars_per_token)
        for b in bindings:
            total += b.tokens or estimate_tokens_text(
                b.result_text or "", self.chars_per_token
            )
            # tool_call 声明本身（name + args）也占 token
            total += estimate_tokens_text(
                (b.tool_name or "") + str(b.args), self.chars_per_token
            )
        return max(1, total)

    @staticmethod
    def _parse_args(raw: Any) -> Dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            import json

            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {"_raw": raw}
            except Exception:
                return {"_raw": raw}
        return {"_raw": str(raw)}

    @staticmethod
    def _created_at_epoch(msg: Any) -> float:
        created = getattr(msg, "created_at", None)
        if created is None:
            return 0.0
        # datetime
        if hasattr(created, "timestamp"):
            try:
                return float(created.timestamp())
            except Exception:
                return 0.0
        try:
            return float(created)
        except Exception:
            return 0.0

    @staticmethod
    def _filter_by_goal(
        units: List[TimelineUnit], goal_id: str
    ) -> List[TimelineUnit]:
        """保留 goal_id 匹配的单元（USER 单元若无 goal_id 也保留为锚点候选）。"""
        result: List[TimelineUnit] = []
        for u in units:
            if u.goal_id == goal_id or u.current_goal == goal_id:
                result.append(u)
            elif u.kind == UnitKind.USER and not u.goal_id:
                # 无归属的用户输入保留（可能是主 Agent 的起始输入）
                result.append(u)
        return result
