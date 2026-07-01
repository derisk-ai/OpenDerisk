"""LLM-driven MemoryProcessor implementation.

Concrete subclass of `MemoryProcessor` (see processor.py). Uses a derisk
LLMClient to:
- extract key memories (preference / decision / fact / todo) from a convo
- consolidate new memories against existing ones (dedup + merge + upgrade)
- score importance 0.0-1.0
- extract knowledge-graph triples

The LLM is expected to return JSON; we parse defensively (strip ```json
fences, fall back to {} on failure so callers can skip gracefully).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from derisk.core import (
    ChatPromptTemplate,
    HumanPromptTemplate,
    LLMClient,
    ModelMessage,
    ModelRequest,
)

from .processor import (
    ConsolidationResult,
    ExtractedMemory,
    MemoryProcessor,
)

logger = logging.getLogger(__name__)


def _parse_json_lenient(text: str) -> Any:
    """Parse JSON from LLM output, tolerating ```json fences and trailing prose."""
    if not text:
        return None
    s = text.strip()
    # strip ```json ... ``` fences
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    # try direct parse
    try:
        return json.loads(s)
    except Exception:
        pass
    # try to locate the first {...} or [...] span
    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        end = s.rfind(closer)
        if start != -1 and end != -1 and end > start:
            snippet = s[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception:
                continue
    return None


class LLMMemoryProcessor(MemoryProcessor):
    """LLM-backed memory processor.

    Constructed with an LLMClient (typically the agent's own
    `llm_config.llm_client`). All four abstract methods are implemented
    with prompt → LLM generate → JSON parse.
    """

    # --- prompt templates ---

    _EXTRACT_PROMPT = """你是一个记忆抽取器。从下面的对话中抽取值得长期记忆的信息，分成 4 类：
- preference: 用户偏好、习惯、口味、工作方式
- decision: 用户做出的决定、选择、承诺
- fact: 关于用户、项目、环境的事实信息（身份、角色、配置、结构等）
- todo: 待办、后续行动、悬而未决的事项

只抽取有长期价值的内容，忽略一次性的临时指令和寒暄。

写入记忆时，对相关概念、人名、项目名、技术栈使用 [[wikilink]] 双链语法
（如 "用户偏好 [[React]] 组件化开发"、"负责 [[场景空间]] 模块"）。这会让空间
自动构建记忆间的 graph 关系，便于后续检索和合并。

对话内容：
{conversation}

请以 JSON 输出，格式：
{{
  "memories": [
    {{"room": "preference|decision|fact|todo", "content": "记忆内容（简洁陈述句，可含 [[wikilink]]）", "importance": 0.0-1.0}}
  ]
}}

如果对话中没有值得记忆的内容，返回 {{"memories": []}}。"""

    _CONSOLIDATE_PROMPT = """你是一个记忆整理器。给定一批【现有记忆】和一批【新抽取记忆】，请去重、合并、升级。

规则：
1. 新记忆与现有记忆语义重复 → 不新增，标记 existing_id 为 "updated"（content 可合并升级）
2. 新记忆是现有记忆的细化/补充 → 合并进现有记忆，标记 existing_id 为 "updated"
3. 新记忆完全是新信息 → 标记为 "new"
4. 现有记忆已被新记忆推翻/过期 → 标记 existing_id 为 "discarded"

【现有记忆】：
{existing_json}

【新抽取记忆】：
{new_json}

请以 JSON 输出，格式：
{{
  "new_memories": [{{"room": "...", "content": "...", "importance": 0.0-1.0}}],
  "updated_memories": [{{"existing_id": "...", "content": "合并后的新内容", "reason": "..."}}],
  "discarded_ids": ["existing_id_1", "existing_id_2"]
}}

如果无需任何变更，所有数组留空。"""

    _IMPORTANCE_PROMPT = """给下面这段记忆内容打重要性分数 (0.0-1.0)。
- 0.9-1.0: 核心身份/关键决策/不可恢复的事实
- 0.6-0.8: 偏好/习惯/重要事实
- 0.3-0.5: 一般信息/待办
- 0.0-0.2: 琐碎/临时信息

记忆内容：
{content}

上下文（可选）：
{context}

只输出一个 0.0 到 1.0 之间的小数，不要其他文字。"""

    _TRIPLES_PROMPT = """从下面这段内容中抽取知识图谱三元组 (subject, predicate, object)。
只抽取明确陈述的事实关系，不要臆测。predicate 用英文小写蛇形（如 uses, prefers, owns, role_of）。

内容：
{content}

请以 JSON 输出，格式：
{{
  "triples": [
    {{"subject": "...", "predicate": "...", "object": "..."}}
  ]
}}

如果没有明确的三元组，返回 {{"triples": []}}。"""

    def __init__(self, llm_client: LLMClient, model: Optional[str] = None):
        self._llm_client = llm_client
        self._model = model

    # ----- internal helper -----

    async def _call_llm(self, prompt_text: str, **fmt_kwargs) -> str:
        prompt = ChatPromptTemplate(
            messages=[HumanPromptTemplate.from_template(prompt_text)]
        )
        pass_kwargs = {k: v for k, v in fmt_kwargs.items() if k in prompt.input_variables}
        messages = prompt.format_messages(**pass_kwargs)
        model_messages = ModelMessage.from_base_messages(messages)
        model = self._model
        if not model:
            model = await self._get_model()
        req = ModelRequest.build_request(model, messages=model_messages)
        out = await self._llm_client.generate(req)
        if not out.success:
            raise ValueError(f"LLM call failed: {out.error}")
        return out.text

    async def _get_model(self) -> str:
        models = await self._llm_client.models()
        if not models:
            raise ValueError("No models available on LLMClient.")
        return models[0].model

    # ----- MemoryProcessor impl -----

    async def extract_key_content(
        self,
        conversation: str,
        extraction_prompt: Optional[str] = None,
    ) -> List[ExtractedMemory]:
        prompt = extraction_prompt or self._EXTRACT_PROMPT
        try:
            text = await self._call_llm(prompt, conversation=conversation)
        except Exception as e:
            logger.warning("[LLMMemoryProcessor] extract_key_content LLM call failed: %s", e)
            return []
        data = _parse_json_lenient(text) or {}
        items = data.get("memories") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        result: List[ExtractedMemory] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            content = (it.get("content") or "").strip()
            if not content:
                continue
            room = (it.get("room") or "general").strip()
            try:
                importance = float(it.get("importance", 0.5))
            except (TypeError, ValueError):
                importance = 0.5
            result.append(ExtractedMemory(
                content=content,
                room=room,
                importance=max(0.0, min(1.0, importance)),
            ))
        return result

    async def consolidate_memories(
        self,
        existing: List[Any],
        new: List[ExtractedMemory],
        consolidation_threshold: float = 0.7,
    ) -> ConsolidationResult:
        existing_json = json.dumps(
            [
                {
                    "id": getattr(e, "id", None) or (e.metadata or {}).get("id", "") if hasattr(e, "metadata") else "",
                    "content": getattr(e, "content", str(e)),
                    "room": getattr(e, "room", "general"),
                }
                for e in existing
            ],
            ensure_ascii=False,
            indent=2,
        )
        new_json = json.dumps(
            [
                {"room": m.room, "content": m.content, "importance": m.importance}
                for m in new
            ],
            ensure_ascii=False,
            indent=2,
        )
        try:
            text = await self._call_llm(
                self._CONSOLIDATE_PROMPT,
                existing_json=existing_json,
                new_json=new_json,
            )
        except Exception as e:
            logger.warning("[LLMMemoryProcessor] consolidate_memories LLM call failed: %s", e)
            # 兜底：全部当新增
            return ConsolidationResult(new_memories=list(new))
        data = _parse_json_lenient(text) or {}
        if not isinstance(data, dict):
            return ConsolidationResult(new_memories=list(new))

        new_mems: List[ExtractedMemory] = []
        for it in data.get("new_memories", []) or []:
            if not isinstance(it, dict):
                continue
            content = (it.get("content") or "").strip()
            if not content:
                continue
            try:
                importance = float(it.get("importance", 0.5))
            except (TypeError, ValueError):
                importance = 0.5
            new_mems.append(ExtractedMemory(
                content=content,
                room=(it.get("room") or "general").strip(),
                importance=max(0.0, min(1.0, importance)),
            ))

        updated: List[Dict[str, Any]] = []
        for it in data.get("updated_memories", []) or []:
            if isinstance(it, dict) and it.get("existing_id") and it.get("content"):
                updated.append({
                    "existing_id": it["existing_id"],
                    "content": it["content"],
                    "reason": it.get("reason", ""),
                })

        discarded = [
            d for d in (data.get("discarded_ids") or [])
            if isinstance(d, str)
        ]

        return ConsolidationResult(
            new_memories=new_mems,
            updated_memories=updated,
            discarded_ids=discarded,
        )

    async def score_importance(
        self,
        content: str,
        context: Optional[str] = None,
    ) -> float:
        try:
            text = await self._call_llm(
                self._IMPORTANCE_PROMPT,
                content=content,
                context=context or "",
            )
        except Exception as e:
            logger.warning("[LLMMemoryProcessor] score_importance LLM call failed: %s", e)
            return 0.5
        m = re.search(r"([01](?:\.\d+)?|0?\.\d+)", text.strip())
        if not m:
            return 0.5
        try:
            return max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            return 0.5

    async def extract_triples(
        self,
        content: str,
    ) -> List[Dict[str, Any]]:
        try:
            text = await self._call_llm(self._TRIPLES_PROMPT, content=content)
        except Exception as e:
            logger.warning("[LLMMemoryProcessor] extract_triples LLM call failed: %s", e)
            return []
        data = _parse_json_lenient(text) or {}
        triples = data.get("triples") if isinstance(data, dict) else None
        if not isinstance(triples, list):
            return []
        result: List[Dict[str, Any]] = []
        for t in triples:
            if not isinstance(t, dict):
                continue
            s = (t.get("subject") or "").strip()
            p = (t.get("predicate") or "").strip()
            o = (t.get("object") or "").strip()
            if s and p and o:
                result.append({"subject": s, "predicate": p, "object": o})
        return result
