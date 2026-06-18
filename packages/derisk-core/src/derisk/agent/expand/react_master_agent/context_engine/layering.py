"""BudgetLayerer —— 无状态分层 + 剪枝 + 批量量化。

每步从权威源纯函数推导 hot/warm/cold，不维护会漂移的长生命周期状态。

确定性多遍（每步重算，纯内存，零 LLM）：
  - Pass-1 tentative 分层：newest→oldest 累计 token，≤hot→HOT、≤hot+warm→WARM、超→COLD。
  - Pass-2 warm 剪枝（与 cold 解耦）：仅作用 warm 工具单元，只打标记、不改 layer、不进 cold。
      去重 / 删被覆盖写 / 删空结果；保护 preserve_tools。
  - Pass-3 单次再平衡：剪枝腾出预算后把边界 cold 上提回 warm（仅一次）。
  - Pass-4 cold 批量量化：cold 单元数取整到 cold_batch_units 整数倍，sub-批余量回 warm。
      作用：cold 集合只在攒够整批时变化 → 重整频率=每批一次。

守恒律：任一单元要么 hot/warm 输出、要么进 cold handoff、要么是被剪枝的冗余副本。
锚点永不淘汰：当前轮 user 输入逐字保留（强制 HOT）。
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .segmenter import Segmenter
from .timeline import Segment, TimelineUnit, ToolCallBinding, UnitKind
from .text_utils import DEFAULT_CHARS_PER_TOKEN

logger = logging.getLogger(__name__)


class Layer(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass
class LayerBudgetConfig:
    """分层预算与剪枝配置 —— 全引擎唯一来源（经参数扫描）。"""

    # 预算比例（hot/warm/cold，合计约 0.80，其余留给 system+tools）
    hot_ratio: float = 0.50
    warm_ratio: float = 0.22
    cold_ratio: float = 0.10
    chars_per_token: int = DEFAULT_CHARS_PER_TOKEN

    # warm 剪枝
    warm_tool_result_max_length: int = 400  # 字符
    warm_prune_duplicate_tools: bool = True
    warm_prune_superseded_writes: bool = True
    warm_prune_empty_results: bool = True
    warm_preserve_tools: List[str] = field(
        default_factory=lambda: ["view", "read", "read_file", "ask_user"]
    )
    warm_write_tools: List[str] = field(
        default_factory=lambda: ["edit", "write", "create_file", "edit_file", "write_file"]
    )
    warm_read_tools: List[str] = field(
        default_factory=lambda: ["view", "read", "read_file"]
    )
    # preserve_tools_patterns: {tool: [arg-substring...]} 命中则强制不沉 cold
    preserve_tools_patterns: Dict[str, List[str]] = field(default_factory=dict)

    # 空结果判定
    empty_result_markers: List[str] = field(
        default_factory=lambda: ["", "ok", "done", "success", "[]", "{}", "null", "none"]
    )

    # cold 批量量化
    cold_batch_units: int = 8

    def budgets(self, context_window: int) -> Dict[str, int]:
        return {
            "hot": int(context_window * self.hot_ratio),
            "warm": int(context_window * self.warm_ratio),
            "cold": int(context_window * self.cold_ratio),
            "total": context_window,
        }


@dataclass
class LayerPlan:
    """分层结果。"""

    hot: List[TimelineUnit] = field(default_factory=list)
    warm: List[TimelineUnit] = field(default_factory=list)  # 已剪枝（打标）
    cold: List[List[TimelineUnit]] = field(default_factory=list)  # 批次，oldest-first
    layer_tokens: Dict[str, int] = field(default_factory=dict)
    pruned_unit_message_ids: List[str] = field(default_factory=list)
    cold_unit_message_ids: List[str] = field(default_factory=list)

    @property
    def cold_units_flat(self) -> List[TimelineUnit]:
        return [u for batch in self.cold for u in batch]


class BudgetLayerer:
    """无状态分层器。layer() 是纯函数：无 IO / 无 LLM / 无事件。"""

    def __init__(self, config: Optional[LayerBudgetConfig] = None):
        self.config = config or LayerBudgetConfig()

    def layer(
        self, segments: List[Segment], context_window: int, current_conv_id: str = ""
    ) -> LayerPlan:
        cfg = self.config
        budgets = cfg.budgets(context_window)
        flat = Segmenter.flatten(segments)  # oldest -> newest

        # ---------- Pass-1: tentative 分层 newest -> oldest ----------
        hot: List[TimelineUnit] = []
        warm: List[TimelineUnit] = []
        cold: List[TimelineUnit] = []
        cum = 0
        for u in reversed(flat):
            cum += max(1, u.tokens)
            forced = self._is_preserved(u) or self._is_anchor(u, current_conv_id)
            if cum <= budgets["hot"]:
                hot.insert(0, u)
            elif cum <= budgets["hot"] + budgets["warm"]:
                warm.insert(0, u)
            else:
                if forced:
                    # 锚点 / preserve_tools 永不沉 cold，强制提到 warm
                    warm.insert(0, u)
                else:
                    cold.insert(0, u)

        # ---------- Pass-2: warm 剪枝（只打标，不改 layer，不进 cold） ----------
        # hot 单元作为"更新副本"的上下文参与去重/覆盖判定，但只剪 warm。
        pruned_ids = self._prune_warm(warm, hot)

        # ---------- Pass-3: 单次再平衡（剪枝腾出预算后边界 cold 上提回 warm） ----------
        self._rebalance_once(hot, warm, cold, budgets)

        # ---------- Pass-4: cold 批量量化 ----------
        cold_batches, warm_tail = self._quantize_cold(cold)
        if warm_tail:
            # sub-批余量（最新的）回 warm，置于 warm 头部（仍是更旧的）
            warm = warm_tail + warm

        # ---------- 记账 ----------
        layer_tokens = {
            "hot": sum(max(1, u.tokens) for u in hot),
            "warm": sum(max(1, u.tokens) for u in warm),
            "cold": sum(max(1, u.tokens) for u in (u for b in cold_batches for u in b)),
        }
        cold_ids = [
            u.message_id or f"seq:{u.seq}"
            for b in cold_batches
            for u in b
        ]

        return LayerPlan(
            hot=hot,
            warm=warm,
            cold=cold_batches,
            layer_tokens=layer_tokens,
            pruned_unit_message_ids=pruned_ids,
            cold_unit_message_ids=cold_ids,
        )

    # ------------------------------------------------------------------ #
    # Pass-2 warm 剪枝
    # ------------------------------------------------------------------ #
    def _prune_warm(
        self, warm: List[TimelineUnit], hot: Optional[List[TimelineUnit]] = None
    ) -> List[str]:
        cfg = self.config
        pruned_ids: List[str] = []
        hot = hot or []

        # warm binding（可被剪）+ hot binding（仅作"更新副本"上下文，不剪）
        warm_bindings: List[ToolCallBinding] = []
        for u in warm:
            if u.kind == UnitKind.CALL:
                warm_bindings.extend(u.calls)
        hot_bindings: List[ToolCallBinding] = []
        for u in hot:
            if u.kind == UnitKind.CALL:
                hot_bindings.extend(u.calls)
        # 上下文序列：warm 在前、hot 在后（hot 更新）
        call_bindings = warm_bindings + hot_bindings
        warm_set = set(id(b) for b in warm_bindings)

        # --- 去重：同 (tool_name, args) 旧副本剪掉，保留最新（含 hot 作为最新副本） ---
        if cfg.warm_prune_duplicate_tools:
            last_index: Dict[tuple, int] = {}
            for idx, b in enumerate(call_bindings):
                if b.tool_name in cfg.warm_preserve_tools:
                    continue
                key = (b.tool_name, self._args_key(b.args))
                last_index[key] = idx
            for idx, b in enumerate(call_bindings):
                if b.tool_name in cfg.warm_preserve_tools or b.pruned:
                    continue
                if id(b) not in warm_set:  # 只剪 warm
                    continue
                key = (b.tool_name, self._args_key(b.args))
                if last_index.get(key, idx) != idx:
                    b.pruned = True

        # --- 删被覆盖写：write(path) 后又有 read(path)/write(path) → 写单元截断占位 ---
        if cfg.warm_prune_superseded_writes:
            read_or_write_paths_after: List[tuple] = []  # (index, path, is_write, is_read)
            for idx, b in enumerate(call_bindings):
                path = self._extract_path(b.args)
                if not path:
                    continue
                is_write = b.tool_name in cfg.warm_write_tools
                is_read = b.tool_name in cfg.warm_read_tools
                if is_write or is_read:
                    read_or_write_paths_after.append((idx, path, is_write, is_read))
            for i, (idx, path, is_write, is_read) in enumerate(read_or_write_paths_after):
                if not is_write or call_bindings[idx].pruned:
                    continue
                if id(call_bindings[idx]) not in warm_set:  # 只标 warm
                    continue
                # 后面是否还有对同 path 的 read/write
                superseded = any(
                    p == path
                    for (jdx, p, jw, jr) in read_or_write_paths_after[i + 1 :]
                )
                if superseded:
                    call_bindings[idx].superseded_content = True

        # --- 删空结果：ok/done/空 → pruned（保护 preserve_tools） ---
        if cfg.warm_prune_empty_results:
            markers = {m.lower() for m in cfg.empty_result_markers}
            for b in warm_bindings:
                if b.tool_name in cfg.warm_preserve_tools or b.pruned:
                    continue
                from .timeline import ResultStatus

                if b.result_status != ResultStatus.OK:
                    continue
                text = (b.result_text or "").strip().lower()
                if text in markers:
                    b.pruned = True

        # 收集被剪枝单元的 message_id（用于 cleanup hints）
        for u in warm:
            if u.kind == UnitKind.CALL and u.calls:
                if all(b.pruned for b in u.calls) and not (
                    u.ai_text and u.ai_text.strip()
                ):
                    pruned_ids.append(u.message_id or f"seq:{u.seq}")

        return pruned_ids

    # ------------------------------------------------------------------ #
    # Pass-3 单次再平衡
    # ------------------------------------------------------------------ #
    def _rebalance_once(
        self,
        hot: List[TimelineUnit],
        warm: List[TimelineUnit],
        cold: List[TimelineUnit],
        budgets: Dict[str, int],
    ) -> None:
        """剪枝后 warm 占用下降，把最新的 cold 单元上提回 warm（仅一次，不迭代）。"""
        if not cold:
            return
        warm_used = sum(
            max(1, self._effective_tokens(u)) for u in warm
        )
        warm_budget = budgets["warm"]
        # 从 cold 末尾（最新）开始上提
        while cold:
            candidate = cold[-1]
            need = max(1, candidate.tokens)
            if warm_used + need > warm_budget:
                break
            cold.pop()
            warm.insert(0, candidate)
            warm_used += need

    # ------------------------------------------------------------------ #
    # Pass-4 cold 批量量化
    # ------------------------------------------------------------------ #
    def _quantize_cold(self, cold: List[TimelineUnit]):
        """把 cold 切成 cold_batch_units 的整数倍批次。

        余量（最新的 sub-批，不足一整批的尾部）回 warm，避免 cold 集合
        每步抖动 —— 只有攒够整批时 cold 才变化，从而重整频率=每批一次。
        """
        n = self.config.cold_batch_units
        if n <= 0 or not cold:
            return ([cold] if cold else []), []

        full_count = (len(cold) // n) * n
        full = cold[:full_count]
        remainder = cold[full_count:]  # 最新的余量，回 warm

        batches: List[List[TimelineUnit]] = [
            full[i : i + n] for i in range(0, len(full), n)
        ]
        return batches, remainder

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _effective_tokens(self, u: TimelineUnit) -> int:
        """渲染后的有效 token（剪枝后的 warm 单元更小）。粗略用原 tokens。"""
        return u.tokens

    def _is_anchor(self, u: TimelineUnit, current_conv_id: str) -> bool:
        return (
            u.kind == UnitKind.USER
            and current_conv_id
            and u.conv_id == current_conv_id
        )

    def _is_preserved(self, u: TimelineUnit) -> bool:
        patterns = self.config.preserve_tools_patterns
        if not patterns or u.kind != UnitKind.CALL:
            return False
        for b in u.calls:
            subs = patterns.get(b.tool_name)
            if subs:
                args_str = str(b.args)
                if any(s in args_str for s in subs):
                    return True
        return False

    @staticmethod
    def _args_key(args: Dict) -> str:
        try:
            import json

            return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        except Exception:
            return str(args)

    @staticmethod
    def _extract_path(args: Dict) -> Optional[str]:
        if not isinstance(args, dict):
            return None
        for k in ("path", "file_path", "filename", "file", "file_key"):
            v = args.get(k)
            if v:
                return str(v)
        return None
