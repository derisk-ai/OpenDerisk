"""ColdSummarizer —— 全量重整 + 单条 handoff + 持久化复用。

- 全量重整：整个 session 落入 cold 的所有单元 → 一次性重整为一条 handoff 文本
  （参考 Claude Code /compact，非分段分块多条）。
- 单条 user handoff：以单条 ``human`` 消息（前缀 ``[历史背景交接...]``）进入 message list，
  置于所有 hot/warm 之前。语义是"背景交接"，不是 AI 历史发言。
- 持久化复用（关键）：content_hash（所有 cold 单元 id 的稳定指纹）→
    命中内存/DB 缓存 → 直接复用，零 LLM；
    未命中（cold 集合跨批变化）→ 重整一次 → 落 gpts_cold_segments。
  中断恢复：新进程内存缓存为空 → 从 DB 读回 handoff，不重新调模型。
- 降级安全：无 LLM / 模型异常 → 截断兜底，不阻塞主流程，degraded 不持久化。
- 系统事件：COMPRESSION_START / COMPRESSION_COMPLETE / COMPRESSION_LLM_FAILED。
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from .layering import LayerBudgetConfig
from .text_utils import extract_text_content
from .timeline import ResultStatus, TimelineUnit, UnitKind

logger = logging.getLogger(__name__)

# summarize_fn(prompt_text, max_tokens) -> summary_text
SummarizeFn = Callable[[str, int], Awaitable[str]]

HANDOFF_PREFIX = "[历史背景交接 —— 以下为更早对话的压缩摘要，仅供背景参考]\n\n"
HANDOFF_BREADCRUMB = "\n\n（如需更早对话的具体细节，可使用检索/历史工具按需查回。）"

_COMPRESSION_PROMPT = """你是上下文压缩器。请把下面这段更早的 Agent 对话历史压缩成一段结构化摘要，\
供后续对话作为背景交接。要点优先于流畅、保留具体值、意图置顶。严格按如下结构输出：

## 用户意图/目标
（置顶，最重要：用户想达成什么）

## 关键决策与约束
（已确定的方案、限制条件）

## 重要技术细节
（文件路径、错误码、配置、关键参数原样保留，不要改写）

## 已尝试/已放弃
（防止后续重复犯错）

## 未完成事项
（还需要继续做的）

不超过 {max_chars} 字。以下是需要压缩的历史：

{content}
"""


@dataclass
class HandoffMessage:
    """单条历史背景交接消息。"""

    content: str  # 已含前缀 / 面包屑的完整正文
    content_hash: str
    source_unit_ids: List[str] = field(default_factory=list)
    original_tokens: int = 0
    compressed_tokens: int = 0
    degraded: bool = False  # True 表示截断兜底（不持久化）

    def to_message(self) -> dict:
        return {"role": "human", "content": self.content}


class ColdSummarizer:
    def __init__(
        self,
        summarize_fn: Optional[SummarizeFn],
        persistence,  # ColdPersistenceAdapter
        config: Optional[LayerBudgetConfig] = None,
        events=None,  # EventEmitter
        max_summary_chars: int = 1200,
    ):
        self.summarize_fn = summarize_fn
        self.persistence = persistence
        self.config = config or LayerBudgetConfig()
        self.events = events
        self.max_summary_chars = max_summary_chars
        self._mem_cache: dict = {}

    async def summarize_cold(
        self,
        cold_batches: List[List[TimelineUnit]],
        conv_id: str,
        session_id: str,
    ) -> Optional[HandoffMessage]:
        cold_units = [u for batch in cold_batches for u in batch]
        if not cold_units:
            return None

        content_hash = self._content_hash(cold_units)
        source_ids = [u.message_id or f"seq:{u.seq}" for u in cold_units]
        original_tokens = sum(max(1, u.tokens) for u in cold_units)

        # 1) 内存缓存
        cached = self._mem_cache.get(content_hash)
        if cached is not None:
            return cached

        # 2) DB 持久化（中断恢复路径：不调模型）
        if self.persistence is not None:
            try:
                loaded = await self.persistence.load_handoff(session_id, content_hash)
            except Exception as e:  # 持久化异常不阻塞
                logger.warning("[ColdSummarizer] load_handoff failed: %s", e)
                loaded = None
            if loaded is not None:
                self._mem_cache[content_hash] = loaded
                return loaded

        # 3) 重整（一次 LLM）
        rendered = self._render_cold(cold_units)
        self._emit(
            "COMPRESSION_START",
            "开始压缩历史上下文",
            f"cold 单元数: {len(cold_units)}, ~{original_tokens} tokens",
            {"units": len(cold_units), "tokens": original_tokens},
        )

        summary_text, degraded = await self._do_summarize(rendered)

        content = HANDOFF_PREFIX + summary_text + HANDOFF_BREADCRUMB
        handoff = HandoffMessage(
            content=content,
            content_hash=content_hash,
            source_unit_ids=source_ids,
            original_tokens=original_tokens,
            compressed_tokens=max(1, len(content) // self.config.chars_per_token),
            degraded=degraded,
        )

        # 4) 缓存 + 持久化（degraded 不持久化，留待健康轮重算）
        self._mem_cache[content_hash] = handoff
        if not degraded and self.persistence is not None:
            try:
                await self.persistence.save_handoff(session_id, conv_id, handoff)
            except Exception as e:
                logger.warning("[ColdSummarizer] save_handoff failed: %s", e)

        if not degraded:
            self._emit(
                "COMPRESSION_COMPLETE",
                "历史上下文压缩完成",
                f"原始 ~{original_tokens} tokens → 摘要 ~{handoff.compressed_tokens} tokens",
                {
                    "original_tokens": original_tokens,
                    "compressed_tokens": handoff.compressed_tokens,
                },
            )
        return handoff

    # ------------------------------------------------------------------ #
    async def _do_summarize(self, rendered: str) -> tuple:
        """返回 (summary_text, degraded)。"""
        if self.summarize_fn is None:
            return self._truncate(rendered), True

        prompt = _COMPRESSION_PROMPT.format(
            max_chars=self.max_summary_chars, content=rendered
        )
        try:
            result = await self.summarize_fn(prompt, self.max_summary_chars)
            text = self._coerce_text(result)
            if not text or not text.strip():
                raise ValueError("empty summary")
            return text.strip(), False
        except Exception as e:
            logger.warning("[ColdSummarizer] LLM summarize failed, degrade: %s", e)
            self._emit(
                "COMPRESSION_LLM_FAILED",
                "历史压缩降级（截断兜底）",
                str(e)[:200],
                {"error": str(e)[:200]},
            )
            return self._truncate(rendered), True

    def _render_cold(self, cold_units: List[TimelineUnit]) -> str:
        """把 cold 单元按时序全量渲染为一段文本（供重整）。"""
        lines: List[str] = []
        for u in cold_units:
            tag = f"[round {u.rounds}]"
            if u.kind == UnitKind.USER:
                txt = extract_text_content(u.user_content)
                lines.append(f"{tag} 用户: {self._clip(txt, 600)}")
            elif u.kind == UnitKind.AI_TEXT:
                lines.append(f"{tag} 助手: {self._clip(u.ai_text or '', 600)}")
            elif u.kind == UnitKind.CALL:
                if u.ai_text and u.ai_text.strip():
                    lines.append(f"{tag} 助手: {self._clip(u.ai_text, 400)}")
                for b in u.calls:
                    arg_keys = ",".join(b.args.keys()) if isinstance(b.args, dict) else ""
                    if b.result_status == ResultStatus.MISSING:
                        res = "(无结果)"
                    elif b.summary:
                        res = self._clip(b.summary, 300)
                    else:
                        res = self._clip(b.result_text or "", 300)
                    status = (
                        "失败" if b.result_status == ResultStatus.ERROR else "成功"
                    )
                    lines.append(
                        f"{tag} 工具调用: {b.tool_name}({arg_keys}) [{status}] -> {res}"
                    )
        return "\n".join(lines)

    @staticmethod
    def _content_hash(cold_units: List[TimelineUnit]) -> str:
        ids = ",".join(u.message_id or f"seq:{u.seq}" for u in cold_units)
        total = sum(max(1, u.tokens) for u in cold_units)
        raw = f"{ids}|{total}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_summary_chars:
            return text
        return text[: self.max_summary_chars] + "\n...(已截断)"

    @staticmethod
    def _clip(text: str, n: int) -> str:
        text = text or ""
        return text if len(text) <= n else text[:n] + "..."

    @staticmethod
    def _coerce_text(result) -> str:
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        # ModelOutput / 其它带 get_text 的对象
        if hasattr(result, "get_text"):
            try:
                return result.get_text()
            except Exception:
                pass
        content = getattr(result, "content", None)
        if isinstance(content, str):
            return content
        return str(result)

    def _emit(self, event_type: str, title: str, description: str, metadata: dict):
        if self.events is not None:
            try:
                self.events.emit(event_type, title, description, metadata)
            except Exception as e:  # 事件失败不影响主流程
                logger.debug("[ColdSummarizer] emit event failed: %s", e)
