"""
HistoryMessageBuilder - Convert SessionHistory + WorkLog to Native Message List

This module transforms the conversation history from text-based placeholders
to native OpenAI-compatible Message List format, allowing LLMs to understand
the conversation as actual context rather than background text.

Architecture Comparison:
    Before (Text-based):
        system_prompt = "... {session_history} ..."
        messages = [{"role": "system", "content": system_prompt}]

    After (Message List):
        messages = [
            {"role": "system", "content": "You are..."},
            # Historical conversations (cross-turn)
            {"role": "user", "content": "Previous question 1"},
            {"role": "assistant", "content": "Previous answer 1", "tool_calls": [...]},
            {"role": "tool", "tool_call_id": "xxx", "content": "..."},
            # Current conversation
            {"role": "user", "content": "Current question"},
        ]

Key Design:
    - Hot Layer: Complete message chain with full tool_calls
    - Warm Layer: Summary system message + compressed tool messages
    - Cold Layer: Single system summary message

References:
    - session_history.py: SessionConversation, SessionHistoryManager
    - work_log.py: WorkLogManager, WorkEntry
    - compaction_pipeline.py: UnifiedCompactionPipeline
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .session_history import SessionConversation, SessionHistoryManager

logger = logging.getLogger(__name__)


@dataclass
class HistoryMessageBuilderConfig:
    """Configuration for HistoryMessageBuilder"""

    max_history_tokens: int = 70000
    hot_layer_ratio: float = 0.6
    warm_layer_ratio: float = 0.3
    cold_layer_ratio: float = 0.1
    compressed_tool_content_max_length: int = 500
    summary_max_length: int = 1000
    include_tool_call_ids: bool = True
    include_archived_references: bool = True

    # Warm 层智能剪枝配置
    warm_enable_llm_pruning: bool = True
    warm_prune_error_after_turns: int = 4
    warm_prune_duplicate_tools: bool = True
    warm_prune_superseded_writes: bool = True
    warm_preserve_tools: List[str] = field(
        default_factory=lambda: ["view", "read", "ask_user"]
    )
    warm_write_tools: List[str] = field(
        default_factory=lambda: ["edit", "write", "create_file", "edit_file"]
    )
    warm_read_tools: List[str] = field(default_factory=lambda: ["read", "view", "cat"])

    chars_per_token: int = 4


class HistoryMessageBuilder:
    """
    Convert SessionHistory + WorkLog to Native Message List for LLM API.

    This is the core component that transforms the conversation history from
    text-based placeholders to native Message List format.

    Usage:
        builder = HistoryMessageBuilder(config=config)

        # Build messages for LLM
        messages = await builder.build_messages(
            session_history_manager=session_history_manager,
            current_conv_id=current_conv_id,
            max_tokens=70000,
        )

        # The messages can be directly passed to LLM API
        llm_response = await llm_client.chat(messages=messages)
    """

    def __init__(
        self,
        config: Optional[HistoryMessageBuilderConfig] = None,
    ):
        self.config = config or HistoryMessageBuilderConfig()

    async def build_messages(
        self,
        session_history_manager: "SessionHistoryManager",
        current_conv_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build Message List from SessionHistory + WorkLog.

        This is the main entry point that orchestrates the conversion from
        SessionConversation objects to native LLM Message List format.

        Args:
            session_history_manager: The SessionHistoryManager containing
                hot_conversations, warm_summaries, and cold_archive_refs
            current_conv_id: The current conversation ID to exclude from history
            max_tokens: Maximum tokens for history (defaults to config.max_history_tokens)

        Returns:
            List of message dictionaries in OpenAI-compatible format:
            [
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "...", "tool_calls": [...]},
                {"role": "tool", "tool_call_id": "...", "content": "..."},
                ...
            ]
        """
        max_tokens = max_tokens or self.config.max_history_tokens
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        hot_budget = int(max_tokens * self.config.hot_layer_ratio)
        warm_budget = int(max_tokens * self.config.warm_layer_ratio)
        cold_budget = int(max_tokens * self.config.cold_layer_ratio)

        logger.info(
            f"[HistoryMessageBuilder] Building messages, max_tokens={max_tokens}, "
            f"hot_budget={hot_budget}, warm_budget={warm_budget}"
        )

        cold_messages, cold_tokens = await self._build_cold_layer_messages(
            session_history_manager
        )
        if cold_messages:
            messages.extend(cold_messages)
            total_tokens += cold_tokens
            logger.info(
                f"[HistoryMessageBuilder] Cold layer: {len(cold_messages)} messages, ~{cold_tokens} tokens"
            )

        warm_messages, warm_tokens = await self._build_warm_layer_messages(
            session_history_manager,
            current_conv_id,
            max_tokens=warm_budget,
        )
        if warm_messages:
            messages.extend(warm_messages)
            total_tokens += warm_tokens
            logger.info(
                f"[HistoryMessageBuilder] Warm layer: {len(warm_messages)} messages, ~{warm_tokens} tokens"
            )

        hot_messages, hot_tokens = await self._build_hot_layer_messages(
            session_history_manager,
            current_conv_id,
            max_tokens=hot_budget,
        )
        if hot_messages:
            messages.extend(hot_messages)
            total_tokens += hot_tokens
            logger.info(
                f"[HistoryMessageBuilder] Hot layer: {len(hot_messages)} messages, ~{hot_tokens} tokens"
            )

        logger.info(
            f"[HistoryMessageBuilder] Built {len(messages)} messages, ~{total_tokens} tokens"
        )

        return messages

    async def _build_hot_layer_messages(
        self,
        manager: "SessionHistoryManager",
        current_conv_id: Optional[str],
        max_tokens: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Build Hot Layer messages: Complete message chains with full tool_calls.

        Hot Layer contains the most recent conversations with complete details:
        - Full user questions
        - Full assistant responses with tool_calls
        - Full tool results

        This gives LLM the most context for recent conversations.
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        # Iterate in reverse order (oldest first for hot layer)
        for conv_id, conv in list(manager.hot_conversations.items()):
            if conv_id == current_conv_id:
                continue

            conv_messages, conv_tokens = self._build_full_conv_messages(conv)

            # Check token budget
            if total_tokens + conv_tokens > max_tokens:
                logger.debug(
                    f"Hot layer token budget reached: {total_tokens}/{max_tokens}"
                )
                break

            messages.extend(conv_messages)
            total_tokens += conv_tokens

        return messages, total_tokens

    async def _build_warm_layer_messages(
        self,
        manager: "SessionHistoryManager",
        current_conv_id: Optional[str],
        max_tokens: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Build Warm Layer messages: Summary + compressed tool calls with smart pruning.

        Warm Layer contains older conversations that have been compressed:
        - Summary as system message
        - Key tool calls with compressed results
        - Cache check to prevent redundant compression
        - Smart pruning (dedup, error cleanup, write superseding)
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        for conv_id, conv in manager.warm_summaries.items():
            if conv_id == current_conv_id:
                continue

            # Check cache
            if conv.warm_compressed_content:
                try:
                    cached_messages = json.loads(conv.warm_compressed_content)
                    conv_tokens = self._estimate_tokens(cached_messages)
                    if total_tokens + conv_tokens <= max_tokens:
                        messages.extend(cached_messages)
                        total_tokens += conv_tokens
                        logger.debug(
                            f"[HistoryMessageBuilder] Using cached warm content for {conv_id}"
                        )
                        continue
                except Exception as e:
                    logger.warning(f"Failed to parse cached warm content: {e}")

            # Build messages if no cache
            conv_messages, conv_tokens = self._build_summary_conv_messages(conv)

            # Apply smart pruning
            current_turn = getattr(conv, "total_rounds", 0) or 0
            conv_messages = await self._smart_prune_messages(
                conv_messages,
                token_budget=max_tokens - total_tokens,
                current_turn=current_turn,
                llm_client=None,  # LLM pruning is optional
            )
            conv_tokens = self._estimate_tokens(conv_messages)

            # Check token budget
            if total_tokens + conv_tokens > max_tokens:
                logger.debug(
                    f"Warm layer token budget reached: {total_tokens}/{max_tokens}"
                )
                break

            messages.extend(conv_messages)
            total_tokens += conv_tokens

            # Cache the compressed content
            try:
                conv.warm_compressed_content = json.dumps(conv_messages)
            except Exception:
                pass

        return messages, total_tokens

    async def _build_cold_layer_messages(
        self,
        manager: "SessionHistoryManager",
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Build Cold Layer messages: Single system summary message.

        Cold Layer contains the oldest archived conversations:
        - Single system message with high-level summary
        - References to archived chapters if available

        This provides minimal context that conversation history exists.
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        if not manager.cold_archive_refs:
            return messages, total_tokens

        # Build a summary of cold archives
        cold_count = len(manager.cold_archive_refs)
        summary_content = (
            f"[历史对话归档] 有 {cold_count} 个更早的对话已被归档。\n"
            f"这些对话涉及更早的问题和解答，如需回溯可使用历史回溯工具查询。\n"
        )

        messages.append(
            {
                "role": "system",
                "content": summary_content,
                "is_cold_archive_summary": True,
            }
        )

        total_tokens = len(summary_content) // 4  # Rough token estimate

        return messages, total_tokens

    def _build_full_conv_messages(
        self,
        conv: "SessionConversation",
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Build complete message chain from a Hot Layer SessionConversation.

        This preserves:
        - Full user question
        - Full assistant response
        - Full tool_calls with arguments
        - Full tool results

        Returns:
            Tuple of (messages list, estimated tokens)
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        # Add conversation header as system message
        header = self._build_conversation_header(conv, is_hot=True)
        messages.append(
            {
                "role": "system",
                "content": header,
            }
        )
        total_tokens += len(header) // 4

        # Add user question
        user_msg = {
            "role": "user",
            "content": conv.user_query,
        }
        messages.append(user_msg)
        total_tokens += len(conv.user_query) // 4

        # Check if this conversation has tool calls
        if conv.has_tool_calls and conv.work_entries:
            # Build tool call chain
            for entry in conv.work_entries:
                # Generate tool_call_id if not present
                tool_call_id = getattr(entry, "tool_call_id", None)
                if not tool_call_id:
                    tool_call_id = f"tc_{uuid.uuid4().hex[:8]}"

                # Assistant message with tool_calls
                assistant_msg = {
                    "role": "assistant",
                    "content": "",  # Usually empty when tool_calls present
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": entry.tool,
                                "arguments": json.dumps(
                                    entry.args or {}, ensure_ascii=False
                                ),
                            },
                        }
                    ],
                }
                messages.append(assistant_msg)
                total_tokens += self._estimate_tool_call_tokens(entry)

                # Tool result message
                tool_result = entry.result or entry.summary or ""
                if (
                    entry.full_result_archive
                    and self.config.include_archived_references
                ):
                    # Include archive reference for large results
                    tool_result = (
                        f"[内容已归档: {entry.full_result_archive}]\n"
                        f"摘要: {entry.summary or tool_result[:500]}"
                    )

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result,
                }
                messages.append(tool_msg)
                total_tokens += len(tool_result) // 4

        # Add final answer if present
        if conv.final_answer:
            final_msg = {
                "role": "assistant",
                "content": conv.final_answer,
            }
            messages.append(final_msg)
            total_tokens += len(conv.final_answer) // 4

        return messages, total_tokens

    def _build_summary_conv_messages(
        self,
        conv: "SessionConversation",
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Build summary message chain from a Warm Layer SessionConversation.

        This compresses the conversation:
        - Summary as system message
        - Key tool calls with compressed results

        Returns:
            Tuple of (messages list, estimated tokens)
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        # Build summary system message
        summary_parts = [
            f"[历史对话摘要] {conv.conv_id}",
            f"时间: {datetime.fromtimestamp(conv.created_at).strftime('%Y-%m-%d %H:%M')}",
            f"用户问题: {conv.user_query[:200]}",
        ]

        if conv.summary:
            summary_parts.append(
                f"\n摘要:\n{conv.summary[: self.config.summary_max_length]}"
            )

        if conv.key_takeaways:
            summary_parts.append("\n关键结论:")
            for takeaway in conv.key_takeaways[:3]:
                summary_parts.append(f"  - {takeaway}")

        summary_content = "\n".join(summary_parts)
        messages.append(
            {
                "role": "system",
                "content": summary_content,
                "is_history_summary": True,
            }
        )
        total_tokens += len(summary_content) // 4

        # Add compressed tool calls if present
        if conv.has_tool_calls and conv.work_entries:
            # Only include key tool calls
            key_entries = conv.work_entries[:5]  # Limit to 5 most important

            for entry in key_entries:
                tool_call_id = (
                    getattr(entry, "tool_call_id", None) or f"tc_{uuid.uuid4().hex[:8]}"
                )

                # Compressed assistant message
                assistant_msg = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": entry.tool,
                                "arguments": json.dumps(
                                    entry.args or {}, ensure_ascii=False
                                ),
                            },
                        }
                    ],
                }
                messages.append(assistant_msg)

                # Compressed tool result
                compressed_result = self._compress_tool_result(entry)
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": compressed_result,
                }
                messages.append(tool_msg)
                total_tokens += len(compressed_result) // 4

        return messages, total_tokens

    def _build_conversation_header(
        self,
        conv: "SessionConversation",
        is_hot: bool = True,
    ) -> str:
        """Build header for a conversation."""
        layer_name = "热数据" if is_hot else "温数据"
        time_str = datetime.fromtimestamp(conv.created_at).strftime("%Y-%m-%d %H:%M")

        header = f"\n=== 历史对话 [{conv.conv_id}] ({layer_name}) ===\n"
        header += f"时间: {time_str}\n"

        if not conv.has_tool_calls:
            header += "(纯模型输出)\n"

        return header

    def _compress_tool_result(self, entry: Any) -> str:
        """
        Compress tool result for Warm/Cold layer.

        The compression strategy:
        1. If archived, reference the archive
        2. Otherwise, use summary or truncate
        """
        if entry.full_result_archive:
            return (
                f"[已压缩] 工具: {entry.tool}\n"
                f"归档: {entry.full_result_archive}\n"
                f"摘要: {entry.summary or '无'}"
            )

        result = entry.result or entry.summary or ""
        if len(result) > self.config.compressed_tool_content_max_length:
            return (
                f"[已压缩] 工具: {entry.tool}\n"
                f"{result[: self.config.compressed_tool_content_max_length]}..."
            )

        return result

    def _estimate_tool_call_tokens(self, entry: Any) -> int:
        """Estimate tokens for a tool call."""
        # Tool name + arguments
        tokens = len(entry.tool) // 4
        if entry.args:
            tokens += len(json.dumps(entry.args, ensure_ascii=False)) // 4
        return tokens

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate tokens for a list of messages."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                total_chars += len(json.dumps(tool_calls, ensure_ascii=False))
        return max(1, total_chars // self.config.chars_per_token)

    def _prune_duplicate_tools(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        去重：相同工具+相同参数的调用只保留最新的

        OpenCode DCP 策略：
        - 通过签名（tool_name + args）判断重复
        - 只保留最新的调用结果
        - 保护特定工具不去重
        """
        if not self.config.warm_prune_duplicate_tools:
            return messages

        seen_signatures: Dict[str, str] = {}
        tool_call_id_to_keep: set = set()

        for i, msg in enumerate(messages):
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    func_name = tc.get("function", {}).get("name", "")
                    args = tc.get("function", {}).get("arguments", "")

                    if func_name in self.config.warm_preserve_tools:
                        tool_call_id_to_keep.add(tc.get("id"))
                        continue

                    signature = f"{func_name}:{args}"
                    tool_call_id_to_keep.add(tc.get("id"))
                    if signature in seen_signatures:
                        old_id = seen_signatures[signature]
                        if old_id in tool_call_id_to_keep:
                            tool_call_id_to_keep.remove(old_id)
                    seen_signatures[signature] = tc.get("id")

        pruned_messages: List[Dict[str, Any]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                tc_id = tool_calls[0].get("id")
                if tc_id in tool_call_id_to_keep:
                    pruned_messages.append(msg)
                    if i + 1 < len(messages) and messages[i + 1].get("role") == "tool":
                        pruned_messages.append(messages[i + 1])
                        i += 1
            elif msg.get("role") != "tool":
                pruned_messages.append(msg)

            i += 1

        return pruned_messages

    def _prune_error_tools(
        self,
        messages: List[Dict[str, Any]],
        current_turn: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        清理错误工具调用：N 轮后移除失败的调用

        OpenCode DCP 策略：
        - 保留错误消息（用于调试）
        - 只移除失败的输入参数
        """
        threshold = self.config.warm_prune_error_after_turns
        pruned_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                is_error = (
                    "error" in content.lower()
                    or "failed" in content.lower()
                    or "exception" in content.lower()
                )

                if is_error and current_turn > threshold:
                    pruned_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": msg.get("tool_call_id"),
                            "content": "[错误工具调用已清理]",
                        }
                    )
                else:
                    pruned_messages.append(msg)
            else:
                pruned_messages.append(msg)

        return pruned_messages

    def _prune_superseded_writes(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        清理被覆盖的写入操作

        OpenCode DCP 策略：
        - 当写入操作之后有读取同一文件的操作
        - 清理写入操作的输入参数（文件内容）
        - 保留写入操作的记录，只清理大内容

        示例：
        [1] edit("config.json", "修改内容...") → 写入
        [2] read("config.json") → 读取
        → [1] 的参数可清理为 "[写入内容已清理，后续已读取]"
        """
        if not self.config.warm_prune_superseded_writes:
            return messages

        write_tools = set(self.config.warm_write_tools)
        read_tools = set(self.config.warm_read_tools)
        written_files: Dict[str, int] = {}

        for i, msg in enumerate(messages):
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                continue

            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")

                try:
                    args = (
                        json.loads(args_str) if isinstance(args_str, str) else args_str
                    )
                except Exception:
                    continue

                file_path = str(args.get("path", args.get("file_path", "")))

                if func_name in write_tools and file_path:
                    written_files[file_path] = i

                elif func_name in read_tools and file_path:
                    if file_path in written_files:
                        write_idx = written_files[file_path]
                        if 0 <= write_idx < len(messages):
                            write_msg = messages[write_idx]
                            tool_calls_write = write_msg.get("tool_calls", [])
                            if tool_calls_write:
                                for tc_write in tool_calls_write:
                                    args_write = tc_write.get("function", {}).get(
                                        "arguments", "{}"
                                    )
                                    try:
                                        args_dict = (
                                            json.loads(args_write)
                                            if isinstance(args_write, str)
                                            else args_write
                                        )
                                        new_args = dict(args_dict)
                                        if (
                                            "content" in new_args
                                            and len(str(new_args.get("content", "")))
                                            > 200
                                        ):
                                            new_args["content"] = (
                                                f"[写入内容已清理，后续已读取文件: {file_path}]"
                                            )
                                            tc_write["function"]["arguments"] = (
                                                json.dumps(new_args, ensure_ascii=False)
                                            )
                                    except Exception:
                                        pass
                        del written_files[file_path]

        return messages

    async def _llm_evaluate_message_value(
        self,
        messages: List[Dict[str, Any]],
        llm_client: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        LLM 评估消息价值，清理低价值消息

        评估标准：
        - 是否包含关键决策信息
        - 是否包含重要的技术细节
        - 是否与当前任务相关

        返回：保留的高价值消息
        """
        if not self.config.warm_enable_llm_pruning or not llm_client:
            return messages

        if len(messages) < 4:
            return messages

        messages_text = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 50:
                messages_text.append(f"[{i}] {role}: {content[:200]}...")

        if not messages_text:
            return messages

        prompt = f"""分析以下对话片段，判断每条消息的价值。

消息列表:
{chr(10).join(messages_text)}

请返回一个 JSON 数组，包含应该保留的消息索引，格式如: [0, 2, 4]

保留标准：
1. 包含关键决策或结论
2. 包含重要的技术细节（文件路径、错误信息、配置值）
3. 用户的明确指令或问题
4. 重要的工具调用结果

应该清理的：
1. 重复的确认信息
2. 过长的中间过程（可压缩）
3. 与主要任务无关的对话

只返回 JSON 数组，不要其他内容。"""

        try:
            response = await llm_client.async_call(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100,
            )

            response_content = response.content
            if isinstance(response_content, list):
                result_text = response_content[-1].get("text", "")
            else:
                result_text = response_content.get_text()

            import re

            match = re.search(r"\[.*?\]", result_text)
            if match:
                indices_to_keep = json.loads(match.group())
                return [messages[i] for i in indices_to_keep if i < len(messages)]
        except Exception as e:
            logger.warning(f"LLM message evaluation failed: {e}")

        return messages

    async def _smart_prune_messages(
        self,
        messages: List[Dict[str, Any]],
        token_budget: int,
        current_turn: int = 0,
        llm_client: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        智能剪枝：整合去重、错误清理、写入覆盖、LLM评估、Token预算控制

        执行顺序：
        1. 去重 (_prune_duplicate_tools)
        2. 写入覆盖清理 (_prune_superseded_writes)
        3. 错误清理 (_prune_error_tools)
        4. LLM 价值评估 (_llm_evaluate_message_value) - 可选
        5. Token 预算控制
        """
        pruned = self._prune_duplicate_tools(messages)
        pruned = self._prune_superseded_writes(pruned)
        pruned = self._prune_error_tools(pruned, current_turn)

        if self.config.warm_enable_llm_pruning and llm_client:
            pruned = await self._llm_evaluate_message_value(pruned, llm_client)

        current_tokens = self._estimate_tokens(pruned)
        if current_tokens > token_budget:
            final_messages = []
            for msg in reversed(pruned):
                if current_tokens <= token_budget:
                    final_messages.insert(0, msg)
                else:
                    current_tokens -= self._estimate_tokens([msg])
            pruned = final_messages

        return pruned


# =============================================================================
# Integration Helper Functions
# =============================================================================


async def build_history_messages_for_llm(
    session_history_manager: "SessionHistoryManager",
    current_conv_id: Optional[str] = None,
    max_tokens: int = 70000,
    config: Optional[HistoryMessageBuilderConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to build history messages for LLM.

    This is the recommended entry point for integrating HistoryMessageBuilder
    into the Agent's LLM call flow.

    Usage:
        from derisk.agent.core.memory.message_builder import build_history_messages_for_llm

        # In your Agent's message building logic:
        history_messages = await build_history_messages_for_llm(
            session_history_manager=self._session_history_manager,
            current_conv_id=self.conv_id,
            max_tokens=70000,
        )

        # Prepend to your message list
        all_messages = history_messages + current_messages

    Args:
        session_history_manager: The SessionHistoryManager instance
        current_conv_id: Current conversation ID to exclude
        max_tokens: Maximum tokens for history
        config: Optional configuration

    Returns:
        List of message dictionaries ready for LLM API
    """
    builder = HistoryMessageBuilder(config=config)
    return await builder.build_messages(
        session_history_manager=session_history_manager,
        current_conv_id=current_conv_id,
        max_tokens=max_tokens,
    )
