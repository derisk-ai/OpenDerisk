"""
Improved Session Compaction with content protection and shared memory support.

Features:
1. Content protection (code blocks, thinking chains, file paths)
2. Shared memory reload mechanism (Claude Code style)
3. Smart summary generation with key info extraction
4. Auto-compaction trigger strategies
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from derisk.agent import Agent, AgentMessage
from derisk.core import LLMClient, HumanMessage, SystemMessage, ModelMessage

logger = logging.getLogger(__name__)


class CompactionTrigger(str, Enum):
    """压缩触发方式"""
    MANUAL = "manual"
    THRESHOLD = "threshold"
    ADAPTIVE = "adaptive"
    SCHEDULED = "scheduled"


class CompactionStrategy(str, Enum):
    """压缩策略"""
    SUMMARIZE = "summarize"
    TRUNCATE_OLD = "truncate_old"
    HYBRID = "hybrid"
    IMPORTANCE_BASED = "importance_based"


@dataclass
class CompactionConfig:
    """压缩配置"""
    DEFAULT_CONTEXT_WINDOW: int = 128000
    DEFAULT_THRESHOLD_RATIO: float = 0.80
    SUMMARY_MESSAGES_TO_KEEP: int = 5
    RECENT_MESSAGES_KEEP: int = 3
    CHARS_PER_TOKEN: int = 4
    
    # 内容保护配置
    CODE_BLOCK_PROTECTION: bool = True
    THINKING_CHAIN_PROTECTION: bool = True
    FILE_PATH_PROTECTION: bool = True
    MAX_PROTECTED_BLOCKS: int = 10
    
    # 共享记忆配置
    RELOAD_SHARED_MEMORY: bool = True
    
    # 自适应触发配置
    ADAPTIVE_CHECK_INTERVAL: int = 5
    ADAPTIVE_GROWTH_THRESHOLD: float = 0.15
    
    # 智能摘要配置
    ENABLE_KEY_INFO_EXTRACTION: bool = True
    KEY_INFO_MIN_IMPORTANCE: float = 0.6
    
    COMPACTION_PROMPT_TEMPLATE: str = """You are a session compaction assistant. Your task is to summarize the conversation history into a condensed format while preserving essential information.

Please summarize the following conversation history. Your summary should:
1. Capture the main goals and intents discussed
2. Preserve key decisions and conclusions reached
3. Maintain important context for continuing the task
4. Be concise but comprehensive
5. Include any critical values, results, or findings
6. Preserve code snippets and their purposes
7. Remember user preferences and constraints

{key_info_section}

Conversation History:
{history}

Please provide your summary in the following format:
<summary>
[Your detailed summary here]
</summary>

<key_points>
- Key point 1
- Key point 2
- ...
</key_points>

<remaining_tasks>
[If there are pending tasks, list them here]
</remaining_tasks>

<code_references>
[List any important code snippets or file references to remember]
</code_references>
"""


@dataclass
class TokenEstimate:
    """Token 估算结果"""
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    usable_context: int = 0


@dataclass
class CompactionResult:
    """压缩结果"""
    success: bool
    original_messages: List[AgentMessage]
    compacted_messages: List[AgentMessage]
    summary_content: Optional[str] = None
    tokens_saved: int = 0
    messages_removed: int = 0
    error_message: Optional[str] = None
    protected_content_count: int = 0
    shared_memory_reloaded: bool = False


@dataclass
class ProtectedContent:
    """受保护的内容"""
    content_type: str  # code, thinking, file_path
    content: str
    source_message_index: int
    importance: float = 0.5


@dataclass
class KeyInfo:
    """关键信息"""
    category: str  # fact, decision, constraint, preference, action
    content: str
    importance: float = 0.0
    source: str = ""


class ContentProtector:
    """内容保护器 - 保护重要内容不被压缩"""
    
    CODE_BLOCK_PATTERN = r'```[\s\S]*?```'
    THINKING_CHAIN_PATTERN = r'<(?:thinking|scratch_pad|reasoning)>[\s\S]*?</(?:thinking|scratch_pad|reasoning)>'
    FILE_PATH_PATTERN = r'["\']?(?:/[\w\-./]+|(?:\.\.?/)?[\w\-./]+\.[\w]+)["\']?'
    URL_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'
    
    # 关键内容标记
    IMPORTANT_MARKERS = [
        "important:", "critical:", "注意:", "重要:", "关键:",
        "must:", "should:", "必须:", "应该:",
        "remember:", "note:", "记住:", "注意:",
        "todo:", "fixme:", "hack:", "bug:",
    ]
    
    def __init__(self, config: Optional[CompactionConfig] = None):
        self.config = config or CompactionConfig()
    
    def extract_protected_content(
        self,
        messages: List[AgentMessage],
    ) -> Tuple[List[ProtectedContent], List[AgentMessage]]:
        """从消息中提取需要保护的内容
        
        Returns:
            Tuple[List[ProtectedContent], List[AgentMessage]]: 
                (受保护内容列表, 清理后的消息索引)
        """
        protected = []
        
        for idx, msg in enumerate(messages):
            content = msg.content or ""
            
            # 提取代码块
            if self.config.CODE_BLOCK_PROTECTION:
                code_blocks = re.findall(self.CODE_BLOCK_PATTERN, content)
                for block in code_blocks[:3]:
                    protected.append(ProtectedContent(
                        content_type="code",
                        content=block,
                        source_message_index=idx,
                        importance=self._calculate_importance(block),
                    ))
            
            # 提取思考链
            if self.config.THINKING_CHAIN_PROTECTION:
                thinking_chains = re.findall(self.THINKING_CHAIN_PATTERN, content, re.IGNORECASE)
                for chain in thinking_chains[:2]:
                    protected.append(ProtectedContent(
                        content_type="thinking",
                        content=chain,
                        source_message_index=idx,
                        importance=0.7,
                    ))
            
            # 提取文件路径
            if self.config.FILE_PATH_PROTECTION:
                file_paths = set(re.findall(self.FILE_PATH_PATTERN, content))
                for path in list(file_paths)[:5]:
                    if len(path) > 3 and not path.startswith("http"):
                        protected.append(ProtectedContent(
                            content_type="file_path",
                            content=path,
                            source_message_index=idx,
                            importance=0.3,
                        ))
        
        # 按重要性排序并限制数量
        protected.sort(key=lambda x: x.importance, reverse=True)
        protected = protected[:self.config.MAX_PROTECTED_BLOCKS]
        
        return protected, messages
    
    def _calculate_importance(self, content: str) -> float:
        """计算内容重要性"""
        importance = 0.5
        
        content_lower = content.lower()
        for marker in self.IMPORTANT_MARKERS:
            if marker in content_lower:
                importance += 0.1
        
        # 代码行数加权
        line_count = content.count("\n") + 1
        if line_count > 20:
            importance += 0.1
        if line_count > 50:
            importance += 0.1
        
        # 包含函数定义
        if "def " in content or "function " in content or "class " in content:
            importance += 0.15
        
        return min(importance, 1.0)
    
    def format_protected_content(
        self,
        protected: List[ProtectedContent],
    ) -> str:
        """格式化受保护的内容为文本"""
        if not protected:
            return ""
        
        sections = {
            "code": [],
            "thinking": [],
            "file_path": [],
        }
        
        for item in protected:
            sections[item.content_type].append(item.content)
        
        result = ""
        
        if sections["code"]:
            result += "\n## Protected Code Blocks\n"
            for i, code in enumerate(sections["code"][:5], 1):
                result += f"\n### Code Block {i}\n{code}\n"
        
        if sections["thinking"]:
            result += "\n## Key Reasoning\n"
            for thinking in sections["thinking"][:2]:
                result += f"\n{thinking}\n"
        
        if sections["file_path"]:
            result += "\n## Referenced Files\n"
            paths = list(set(sections["file_path"]))
            for path in paths[:10]:
                result += f"- {path}\n"
        
        return result


class KeyInfoExtractor:
    """关键信息提取器"""
    
    KEY_INFO_PATTERNS = {
        "decision": [
            r"(?:decided|decision|决定|确定)[：:]\s*(.+)",
            r"(?:chose|selected|选择)[：:]\s*(.+)",
        ],
        "constraint": [
            r"(?:constraint|限制|约束|requirement|要求)[：:]\s*(.+)",
            r"(?:must|should|需要|必须)\s+(.+)",
        ],
        "preference": [
            r"(?:prefer|preference|更喜欢|偏好)[：:]\s*(.+)",
            r"(?:like|喜欢)\s+(.+)",
        ],
        "action": [
            r"(?:action|动作|execute|执行)[：:]\s*(.+)",
            r"(?:ran|executed|运行)\s+(.+)",
        ],
    }
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
    
    async def extract(
        self,
        messages: List[AgentMessage],
    ) -> List[KeyInfo]:
        """从消息中提取关键信息"""
        key_infos = []
        
        for msg in messages:
            content = msg.content or ""
            
            # 使用规则提取
            rule_infos = self._extract_by_rules(content, msg.role or "unknown")
            key_infos.extend(rule_infos)
        
        # 如果有LLM，使用LLM增强提取
        if self.llm_client and len(messages) > 5:
            llm_infos = await self._extract_by_llm(messages)
            key_infos.extend(llm_infos)
        
        # 去重和排序
        seen = set()
        unique_infos = []
        for info in key_infos:
            if info.content not in seen:
                seen.add(info.content)
                unique_infos.append(info)
        
        unique_infos.sort(key=lambda x: x.importance, reverse=True)
        return unique_infos[:20]
    
    def _extract_by_rules(
        self,
        content: str,
        role: str,
    ) -> List[KeyInfo]:
        """使用规则提取关键信息"""
        infos = []
        
        for category, patterns in self.KEY_INFO_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    info_content = match.group(1).strip()
                    if len(info_content) > 5 and len(info_content) < 500:
                        infos.append(KeyInfo(
                            category=category,
                            content=info_content,
                            importance=0.6 if role == "user" else 0.5,
                            source=role,
                        ))
        
        return infos
    
    async def _extract_by_llm(
        self,
        messages: List[AgentMessage],
    ) -> List[KeyInfo]:
        """使用LLM提取关键信息"""
        if not self.llm_client:
            return []
        
        try:
            content_preview = "\n".join([
                f"[{m.role}]: {(m.content or '')[:200]}"
                for m in messages[-10:]
            ])
            
            prompt = f"""Extract key information from this conversation snippet.

For each key information, identify:
1. Category: fact (事实), decision (决策), constraint (约束), preference (偏好), action (动作)
2. Content: the key information (concise)
3. Importance: 0.0-1.0

Conversation:
{content_preview}

Output in JSON format:
{{
  "key_infos": [
    {{"category": "decision", "content": "...", "importance": 0.8}},
    ...
  ]
}}
"""
            model_messages = [
                SystemMessage(content="You are a key information extractor."),
                HumanMessage(content=prompt),
            ]
            
            from .llm_utils import call_llm
            result_text = await call_llm(self.llm_client, prompt, system_prompt="You are a key information extractor.")
            
            if result_text:
                # 解析JSON
                json_match = re.search(r'\{[\s\S]*\}', result_text)
                if json_match:
                    data = json.loads(json_match.group())
                    return [
                        KeyInfo(
                            category=info.get("category", "fact"),
                            content=info.get("content", ""),
                            importance=info.get("importance", 0.5),
                        )
                        for info in data.get("key_infos", [])
                    ]
        except Exception as e:
            logger.warning(f"LLM key info extraction failed: {e}")
        
        return []
    
    def format_key_infos(
        self,
        key_infos: List[KeyInfo],
        min_importance: float = 0.5,
    ) -> str:
        """格式化关键信息"""
        filtered = [i for i in key_infos if i.importance >= min_importance]
        
        if not filtered:
            return ""
        
        by_category: Dict[str, List[KeyInfo]] = {}
        for info in filtered:
            if info.category not in by_category:
                by_category[info.category] = []
            by_category[info.category].append(info)
        
        result = "\n### Key Information\n"
        
        category_names = {
            "decision": "决策",
            "constraint": "约束",
            "preference": "偏好",
            "fact": "事实",
            "action": "动作",
        }
        
        for category, infos in by_category.items():
            result += f"\n**{category_names.get(category, category)}:**\n"
            for info in infos[:5]:
                result += f"- {info.content}\n"
        
        return result


class TokenEstimator:
    """Token 估算器"""
    
    def __init__(self, chars_per_token: int = 4):
        self.chars_per_token = chars_per_token
    
    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return len(text) // self.chars_per_token
    
    def estimate_messages(self, messages: List[Any]) -> TokenEstimate:
        input_tokens = 0
        cached_tokens = 0
        output_tokens = 0
        
        for msg in messages:
            if isinstance(msg, AgentMessage):
                content = msg.content or ""
                tokens = self.estimate(content)
                if msg.role in ["user", "human"]:
                    input_tokens += tokens
                elif msg.role in ["assistant", "agent"]:
                    output_tokens += tokens
                else:
                    input_tokens += tokens
            elif isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    tokens = self.estimate(content)
                    role = msg.get("role", "")
                    if role in ["assistant", "agent"]:
                        output_tokens += tokens
                    else:
                        input_tokens += tokens
        
        return TokenEstimate(
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + cached_tokens + output_tokens,
        )


@dataclass
class CompactionSummary:
    """压缩摘要消息"""
    content: str
    original_message_count: int
    timestamp: float = field(default_factory=lambda: __import__('time').time())
    metadata: Dict[str, Any] = field(default_factory=dict)
    protected_content: Optional[str] = None
    key_infos: Optional[str] = None
    
    def to_message(self) -> AgentMessage:
        formatted_content = f"""[Session Summary - Previous {self.original_message_count} messages compacted]

{self.content}
{self.protected_content or ""}
{self.key_infos or ""}
[End of Summary]"""
        
        msg = AgentMessage(
            content=formatted_content,
            role="system",
        )
        msg.context = {
            "is_compaction_summary": True,
            **self.metadata,
        }
        return msg


class ImprovedSessionCompaction:
    """改进的会话压缩器"""
    
    def __init__(
        self,
        context_window: int = CompactionConfig.DEFAULT_CONTEXT_WINDOW,
        threshold_ratio: float = CompactionConfig.DEFAULT_THRESHOLD_RATIO,
        recent_messages_keep: int = CompactionConfig.RECENT_MESSAGES_KEEP,
        llm_client: Optional[LLMClient] = None,
        shared_memory_loader: Optional[Callable[[], Awaitable[str]]] = None,
        config: Optional[CompactionConfig] = None,
    ):
        self.context_window = context_window
        self.threshold_ratio = threshold_ratio
        self.usable_context = int(context_window * threshold_ratio)
        self.recent_messages_keep = recent_messages_keep
        self.llm_client = llm_client
        self.shared_memory_loader = shared_memory_loader
        self.config = config or CompactionConfig()
        
        self.token_estimator = TokenEstimator(self.config.CHARS_PER_TOKEN)
        self.content_protector = ContentProtector(self.config)
        self.key_info_extractor = KeyInfoExtractor(llm_client)
        
        self._compaction_history: List[CompactionResult] = []
        self._message_count_since_last = 0
        self._last_token_count = 0
    
    def set_llm_client(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.key_info_extractor.llm_client = llm_client
    
    def set_shared_memory_loader(
        self,
        loader: Callable[[], Awaitable[str]],
    ):
        self.shared_memory_loader = loader
    
    def is_overflow(
        self,
        messages: List[AgentMessage],
        estimated_output_tokens: int = 500,
    ) -> Tuple[bool, TokenEstimate]:
        estimate = self.token_estimator.estimate_messages(messages)
        estimate.output_tokens = estimated_output_tokens
        estimate.total_tokens = estimate.input_tokens + estimate.cached_tokens + estimate.output_tokens
        estimate.usable_context = self.usable_context
        
        return estimate.total_tokens > self.usable_context, estimate
    
    def should_compact_adaptive(
        self,
        messages: List[AgentMessage],
    ) -> Tuple[bool, str]:
        """自适应判断是否应该压缩"""
        self._message_count_since_last += 1
        
        if self._message_count_since_last < self.config.ADAPTIVE_CHECK_INTERVAL:
            return False, "check_interval_not_reached"
        
        estimate = self.token_estimator.estimate_messages(messages)
        
        if self._last_token_count > 0:
            growth = (estimate.total_tokens - self._last_token_count) / max(self._last_token_count, 1)
            
            if growth > self.config.ADAPTIVE_GROWTH_THRESHOLD:
                return True, f"rapid_growth_{growth:.2%}"
        
        self._last_token_count = estimate.total_tokens
        self._message_count_since_last = 0
        
        if estimate.total_tokens > self.usable_context:
            return True, "threshold_exceeded"
        
        return False, "no_compaction_needed"
    
    def _select_messages_to_compact(
        self,
        messages: List[AgentMessage],
    ) -> Tuple[List[AgentMessage], List[AgentMessage]]:
        if len(messages) <= self.recent_messages_keep:
            return [], messages
        
        split_idx = len(messages) - self.recent_messages_keep
        
        # Adjust split point to avoid breaking tool-call atomic groups.
        # A group is: assistant(tool_calls) followed by one or more tool(tool_call_id).
        # If split lands inside a group, move split earlier to keep the whole group intact.
        while split_idx > 0:
            msg = messages[split_idx]
            role = msg.role or ""
            is_tool_msg = role == "tool"
            is_tool_assistant = (
                role == "assistant"
                and hasattr(msg, 'tool_calls') and msg.tool_calls
            )
            if not is_tool_assistant:
                ctx = getattr(msg, 'context', None)
                if isinstance(ctx, dict) and ctx.get('tool_calls'):
                    is_tool_assistant = True
            
            if is_tool_msg or is_tool_assistant:
                split_idx -= 1
            else:
                break
        
        to_compact = messages[:split_idx]
        to_keep = messages[split_idx:]
        
        return to_compact, to_keep
    
    def _format_messages_for_summary(
        self,
        messages: List[AgentMessage],
    ) -> str:
        lines = []
        for msg in messages:
            role = msg.role or "unknown"
            content = msg.content or ""
            
            if role == "system" and msg.context and msg.context.get("is_compaction_summary"):
                continue
            
            # Flatten tool-call assistant messages into readable text
            tool_calls = getattr(msg, 'tool_calls', None)
            if not tool_calls and msg.context:
                tool_calls = msg.context.get('tool_calls')
            if role == "assistant" and tool_calls:
                tc_descriptions = []
                for tc in (tool_calls if isinstance(tool_calls, list) else []):
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    name = func.get("name", "unknown_tool")
                    args = func.get("arguments", "")
                    if isinstance(args, str) and len(args) > 300:
                        args = args[:300] + "..."
                    tc_descriptions.append(f"  - {name}({args})")
                tc_text = "\n".join(tc_descriptions)
                display = f"[assistant]: Called tools:\n{tc_text}"
                if content:
                    display = f"[assistant]: {content}\nCalled tools:\n{tc_text}"
                lines.append(display)
                continue
            
            # Flatten tool response messages into readable text
            tool_call_id = None
            if msg.context:
                tool_call_id = msg.context.get('tool_call_id')
            if not tool_call_id:
                tool_call_id = getattr(msg, 'tool_call_id', None)
            if role == "tool" and tool_call_id:
                if len(content) > 1500:
                    content = content[:1500] + "... [truncated]"
                lines.append(f"[tool result ({tool_call_id})]: {content}")
                continue
            
            if len(content) > 1500:
                content = content[:1500] + "... [truncated]"
            
            lines.append(f"[{role}]: {content}")
        
        return "\n\n".join(lines)
    
    async def _generate_summary(
        self,
        messages: List[AgentMessage],
        key_infos: Optional[List[KeyInfo]] = None,
    ) -> Optional[str]:
        if not self.llm_client:
            return self._generate_simple_summary(messages, key_infos)
        
        try:
            history_text = self._format_messages_for_summary(messages)
            
            key_info_section = ""
            if key_infos:
                key_info_section = self.key_info_extractor.format_key_infos(
                    key_infos,
                    self.config.KEY_INFO_MIN_IMPORTANCE,
                )
            
            prompt = self.config.COMPACTION_PROMPT_TEMPLATE.format(
                history=history_text,
                key_info_section=key_info_section,
            )
            
            model_messages = [
                SystemMessage(content="You are a helpful assistant specialized in summarizing conversations while preserving critical technical information."),
                HumanMessage(content=prompt),
            ]
            
            from .llm_utils import call_llm
            result = await call_llm(self.llm_client, prompt, system_prompt="You are a helpful assistant specialized in summarizing conversations while preserving critical technical information.")
            
            if result:
                return result.strip()
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return self._generate_simple_summary(messages, key_infos)
    
    def _generate_simple_summary(
        self,
        messages: List[AgentMessage],
        key_infos: Optional[List[KeyInfo]] = None,
    ) -> str:
        tool_calls = []
        user_inputs = []
        assistant_responses = []
        
        for msg in messages:
            role = msg.role or "unknown"
            content = msg.content or ""
            
            if "tool" in role or "action" in role:
                tool_calls.append(content[:100])
            elif role in ["user", "human"]:
                user_inputs.append(content[:300])
            elif role in ["assistant", "agent"]:
                assistant_responses.append(content[:300])
        
        summary_parts = []
        
        if user_inputs:
            summary_parts.append("User Queries:")
            for q in user_inputs[-5:]:
                summary_parts.append(f"  - {q[:150]}...")
        
        if tool_calls:
            summary_parts.append(f"\nTool Executions: {len(tool_calls)} tool calls made")
        
        if assistant_responses:
            summary_parts.append("\nKey Responses:")
            for r in assistant_responses[-3:]:
                summary_parts.append(f"  - {r[:200]}...")
        
        if key_infos:
            summary_parts.append(self.key_info_extractor.format_key_infos(key_infos, 0.3))
        
        return "\n".join(summary_parts) if summary_parts else "Previous conversation history"
    
    async def compact(
        self,
        messages: List[AgentMessage],
        force: bool = False,
    ) -> CompactionResult:
        if not messages:
            return CompactionResult(
                success=True,
                original_messages=[],
                compacted_messages=[],
                tokens_saved=0,
                messages_removed=0,
            )
        
        if not force:
            should_compact, estimate = self.is_overflow(messages)
            if not should_compact:
                return CompactionResult(
                    success=True,
                    original_messages=messages,
                    compacted_messages=messages,
                    tokens_saved=0,
                    messages_removed=0,
                )
        
        logger.info(f"Starting improved session compaction for {len(messages)} messages")
        
        # 1. 提取受保护的内容
        protected_content, _ = self.content_protector.extract_protected_content(messages)
        logger.info(f"Extracted {len(protected_content)} protected content blocks")
        
        # 2. 提取关键信息
        key_infos = []
        if self.config.ENABLE_KEY_INFO_EXTRACTION:
            to_compact, _ = self._select_messages_to_compact(messages)
            key_infos = await self.key_info_extractor.extract(to_compact)
            logger.info(f"Extracted {len(key_infos)} key info items")
        
        # 3. 选择要压缩的消息
        to_compact, to_keep = self._select_messages_to_compact(messages)
        
        if not to_compact:
            return CompactionResult(
                success=True,
                original_messages=messages,
                compacted_messages=messages,
                tokens_saved=0,
                messages_removed=0,
            )
        
        # 4. 生成摘要
        summary_content = await self._generate_summary(to_compact, key_infos)
        
        if not summary_content:
            return CompactionResult(
                success=False,
                original_messages=messages,
                compacted_messages=messages,
                error_message="Failed to generate summary",
            )
        
        # 5. 格式化受保护的内容
        protected_text = self.content_protector.format_protected_content(protected_content)
        
        # 6. 创建摘要消息
        summary = CompactionSummary(
            content=summary_content,
            original_message_count=len(to_compact),
            protected_content=protected_text if protected_text else None,
            metadata={
                "compacted_roles": list(set(m.role for m in to_compact)),
                "compaction_timestamp": datetime.now().isoformat(),
                "protected_content_count": len(protected_content),
            },
        )
        
        # 7. 构建新的消息列表
        compacted_messages = []
        
        # 系统消息
        system_messages = [m for m in to_compact if m.role == "system"]
        compacted_messages.extend(system_messages)
        
        # 共享记忆重载（如果有）
        shared_memory_content = None
        shared_memory_reloaded = False
        if self.config.RELOAD_SHARED_MEMORY and self.shared_memory_loader:
            try:
                shared_memory_content = await self.shared_memory_loader()
                if shared_memory_content:
                    shared_msg = AgentMessage(
                        content=f"[Shared Memory]\n{shared_memory_content}",
                        role="system",
                    )
                    shared_msg.context = {"is_shared_memory": True}
                    compacted_messages.append(shared_msg)
                    shared_memory_reloaded = True
                    logger.info("Shared memory reloaded during compaction")
            except Exception as e:
                logger.warning(f"Failed to reload shared memory: {e}")
        
        # 摘要消息
        summary_msg = summary.to_message()
        compacted_messages.append(summary_msg)
        
        # 最近消息
        compacted_messages.extend(to_keep)
        
        # 计算节省的 token
        original_tokens = self.token_estimator.estimate_messages(messages).total_tokens
        new_tokens = self.token_estimator.estimate_messages(compacted_messages).total_tokens
        tokens_saved = original_tokens - new_tokens
        
        result = CompactionResult(
            success=True,
            original_messages=messages,
            compacted_messages=compacted_messages,
            summary_content=summary_content,
            tokens_saved=tokens_saved,
            messages_removed=len(to_compact) - len(system_messages),
            protected_content_count=len(protected_content),
            shared_memory_reloaded=shared_memory_reloaded,
        )
        
        self._compaction_history.append(result)
        self._last_token_count = new_tokens
        self._message_count_since_last = 0
        
        logger.info(
            f"Compaction completed: removed {result.messages_removed} messages, "
            f"saved ~{tokens_saved} tokens, "
            f"protected {len(protected_content)} blocks, "
            f"current message count: {len(compacted_messages)}"
        )
        
        return result
    
    def get_compaction_history(self) -> List[CompactionResult]:
        return self._compaction_history.copy()
    
    def clear_history(self):
        self._compaction_history.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        if not self._compaction_history:
            return {
                "total_compactions": 0,
                "total_tokens_saved": 0,
                "total_messages_removed": 0,
                "total_protected_content": 0,
            }
        
        return {
            "total_compactions": len(self._compaction_history),
            "total_tokens_saved": sum(r.tokens_saved for r in self._compaction_history),
            "total_messages_removed": sum(r.messages_removed for r in self._compaction_history),
            "total_protected_content": sum(r.protected_content_count for r in self._compaction_history),
            "context_window": self.context_window,
            "threshold_ratio": self.threshold_ratio,
        }


SessionCompaction = ImprovedSessionCompaction