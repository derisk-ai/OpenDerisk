"""
Context Lifecycle Management V2 - 改进版

基于 OpenCode 最佳实践重新设计：
1. 加载新Skill时自动淘汰前一个Skill（更可靠）
2. 简化判断逻辑，移除不可靠的目标检测
3. 参考 opencode 的 auto-compact 和 session 管理模式

关键改进：
- 明确的Skill退出触发：加载新Skill = 自动退出旧Skill
- Token预算管理：接近限制时自动压缩
- 简洁的上下文组装
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ============================================================
# 核心枚举和类型
# ============================================================

class ContentType(str, Enum):
    """内容类型"""
    SYSTEM = "system"
    SKILL = "skill"
    TOOL = "tool"
    RESOURCE = "resource"
    MEMORY = "memory"


class ContentState(str, Enum):
    """内容状态"""
    EMPTY = "empty"
    ACTIVE = "active"
    COMPACTED = "compacted"  # 已压缩（摘要形式）
    EVICTED = "evicted"


@dataclass
class ContentSlot:
    """内容槽位"""
    id: str
    content_type: ContentType
    name: str
    content: str
    state: ContentState = ContentState.ACTIVE
    
    token_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    
    summary: Optional[str] = None
    key_results: List[str] = field(default_factory=list)
    
    def touch(self):
        self.last_accessed = time.time()


# ============================================================
# 简化的上下文管理器
# ============================================================

class SimpleContextManager:
    """
    简化的上下文管理器
    
    核心规则（参考opencode）：
    1. 每次只允许一个活跃Skill
    2. 加载新Skill时，自动压缩前一个Skill
    3. Token预算接近限制时，自动压缩最旧内容
    """
    
    def __init__(
        self,
        token_budget: int = 100000,
        auto_compact_threshold: float = 0.9,  # 参考 opencode 的 autoCompact
    ):
        self._token_budget = token_budget
        self._auto_compact_threshold = auto_compact_threshold
        
        # 当前活跃的Skill（最多一个）
        self._active_skill: Optional[ContentSlot] = None
        
        # 已压缩的Skills（摘要形式）
        self._compacted_skills: List[ContentSlot] = []
        
        # 已加载的工具定义
        self._loaded_tools: Dict[str, ContentSlot] = {}
        
        # 系统消息
        self._system_content: Optional[str] = None
        
        # Token跟踪
        self._total_tokens = 0
        
        # 工具使用统计
        self._tool_usage: Dict[str, int] = {}
        
        # 历史记录
        self._history: List[Dict[str, Any]] = []
    
    # ============ Skill 管理 ============
    
    def load_skill(
        self,
        name: str,
        content: str,
        required_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        加载Skill
        
        关键行为：如果已有活跃Skill，自动压缩前一个
        这解决了"任务完成判断不可靠"的问题
        """
        result = {
            "skill_name": name,
            "previous_skill": None,
            "tokens_used": 0,
            "tools_loaded": [],
        }
        
        # 计算Token
        skill_tokens = self._estimate_tokens(content)
        
        # 检查是否需要压缩当前Skill
        if self._active_skill:
            previous = self._active_skill
            result["previous_skill"] = previous.name
            
            # 关键：自动压缩前一个Skill
            self._compact_skill(previous)
            
            logger.info(
                f"[ContextManager] Auto-compacted previous skill: {previous.name}"
            )
        
        # 检查Token预算
        if self._total_tokens + skill_tokens > self._token_budget * self._auto_compact_threshold:
            self._auto_compact()
        
        # 创建新Skill槽位
        self._active_skill = ContentSlot(
            id=f"skill_{name}_{int(time.time())}",
            content_type=ContentType.SKILL,
            name=name,
            content=content,
            token_count=skill_tokens,
        )
        
        self._total_tokens += skill_tokens
        
        # 加载所需工具
        if required_tools:
            for tool_name in required_tools:
                if tool_name not in self._loaded_tools:
                    self.load_tool(tool_name, f"Tool: {tool_name}")
                    result["tools_loaded"].append(tool_name)
        
        result["tokens_used"] = skill_tokens
        
        logger.info(
            f"[ContextManager] Loaded skill: {name}, "
            f"tokens: {skill_tokens}, "
            f"total: {self._total_tokens}/{self._token_budget}"
        )
        
        return result
    
    def _compact_skill(self, skill: ContentSlot, summary: str = "") -> ContentSlot:
        """
        压缩Skill为摘要形式
        
        将完整内容替换为压缩摘要，释放上下文空间
        """
        if not summary:
            summary = f"[{skill.name}] 任务已完成，详细信息已压缩"
        
        # 计算释放的Token
        compact_tokens = self._estimate_tokens(summary)
        freed_tokens = skill.token_count - compact_tokens
        
        # 更新Slot
        skill.state = ContentState.COMPACTED
        skill.summary = summary
        original_content = skill.content
        skill.content = self._create_compact_content(skill.name, summary, skill.key_results)
        skill.token_count = compact_tokens
        
        # 更新总Token
        self._total_tokens -= freed_tokens
        
        # 移动到压缩列表
        self._compacted_skills.append(skill)
        
        # 记录历史
        self._history.append({
            "action": "compact_skill",
            "skill_name": skill.name,
            "tokens_freed": freed_tokens,
            "timestamp": datetime.now().isoformat(),
        })
        
        logger.info(
            f"[ContextManager] Compacted skill: {skill.name}, "
            f"freed: {freed_tokens} tokens"
        )
        
        return skill
    
    def _create_compact_content(
        self,
        name: str,
        summary: str,
        key_results: List[str],
    ) -> str:
        """创建压缩后的内容"""
        lines = [f'<skill-result name="{name}">']
        lines.append(f'<summary>{summary}</summary>')
        
        if key_results:
            lines.append('<key-results>')
            for result in key_results[:5]:
                lines.append(f'  <result>{result}</result>')
            lines.append('</key-results>')
        
        lines.append('</skill-result>')
        
        return '\n'.join(lines)
    
    def complete_current_skill(
        self,
        summary: str,
        key_results: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        完成当前Skill
        
        显式完成，生成压缩摘要
        """
        if not self._active_skill:
            return None
        
        skill = self._active_skill
        skill.key_results = key_results or []
        
        self._compact_skill(skill, summary)
        
        self._active_skill = None
        
        return {
            "skill_name": skill.name,
            "tokens_freed": skill.token_count,
        }
    
    # ============ 工具管理 ============
    
    def load_tool(self, name: str, definition: str) -> bool:
        """加载工具定义"""
        if name in self._loaded_tools:
            self._loaded_tools[name].touch()
            return True
        
        tool_tokens = self._estimate_tokens(definition)
        
        # 检查预算
        if self._total_tokens + tool_tokens > self._token_budget * self._auto_compact_threshold:
            self._auto_compact_tools()
        
        slot = ContentSlot(
            id=f"tool_{name}",
            content_type=ContentType.TOOL,
            name=name,
            content=definition,
            token_count=tool_tokens,
        )
        
        self._loaded_tools[name] = slot
        self._total_tokens += tool_tokens
        
        logger.debug(f"[ContextManager] Loaded tool: {name}")
        return True
    
    def unload_tool(self, name: str) -> bool:
        """卸载工具"""
        if name not in self._loaded_tools:
            return False
        
        slot = self._loaded_tools.pop(name)
        self._total_tokens -= slot.token_count
        
        return True
    
    def record_tool_call(self, tool_name: str) -> None:
        """记录工具调用"""
        self._tool_usage[tool_name] = self._tool_usage.get(tool_name, 0) + 1
    
    # ============ 上下文组装 ============
    
    def build_context_for_llm(
        self,
        user_message: str,
        include_compacted: bool = True,
    ) -> List[Dict[str, str]]:
        """
        构建LLM消息列表
        
        返回可直接传给LLM的消息格式
        参考 opencode 的消息组装方式
        """
        messages = []
        
        # 1. System 消息
        system_parts = []
        
        if self._system_content:
            system_parts.append(self._system_content)
        
        # 添加已压缩的Skills摘要
        if include_compacted and self._compacted_skills:
            system_parts.append("\n\n# Completed Tasks")
            for skill in self._compacted_skills[-5:]:  # 最多保留5个
                system_parts.append(f"\n{skill.content}")
        
        if system_parts:
            messages.append({
                "role": "system",
                "content": "\n".join(system_parts),
            })
        
        # 2. 当前活跃Skill（完整内容）
        if self._active_skill:
            skill_content = f"# Current Task Instructions\n\n{self._active_skill.content}"
            messages.append({
                "role": "system",
                "content": skill_content,
            })
        
        # 3. 工具定义
        if self._loaded_tools:
            tools_content = "# Available Tools\n\n"
            for name, slot in self._loaded_tools.items():
                tools_content += f"{slot.content}\n"
            
            messages.append({
                "role": "system",
                "content": tools_content,
            })
        
        # 4. 用户消息
        messages.append({
            "role": "user",
            "content": user_message,
        })
        
        return messages
    
    def get_skill_context_string(self) -> str:
        """
        获取Skill上下文字符串
        
        用于插入到System Prompt
        """
        parts = []
        
        if self._compacted_skills:
            parts.append("<completed-skills>")
            for skill in self._compacted_skills[-5:]:
                parts.append(skill.content)
            parts.append("</completed-skills>")
        
        if self._active_skill:
            parts.append(f"\n<current-skill name=\"{self._active_skill.name}\">")
            parts.append(self._active_skill.content)
            parts.append("</current-skill>")
        
        return "\n".join(parts)
    
    # ============ Token管理 ============
    
    def get_token_usage(self) -> Dict[str, Any]:
        """获取Token使用情况"""
        return {
            "total": self._total_tokens,
            "budget": self._token_budget,
            "ratio": self._total_tokens / self._token_budget if self._token_budget > 0 else 0,
            "by_type": {
                "skill": (
                    self._active_skill.token_count if self._active_skill else 0
                ) + sum(s.token_count for s in self._compacted_skills),
                "tools": sum(t.token_count for t in self._loaded_tools.values()),
            },
        }
    
    def check_pressure(self) -> float:
        """检查上下文压力"""
        return self._total_tokens / self._token_budget
    
    def _auto_compact(self) -> None:
        """
        自动压缩
        
        当接近Token限制时触发
        参考 opencode 的 autoCompact 机制
        """
        freed = 0
        
        # 1. 压缩最旧的已压缩Skills（完全移除）
        while self._compacted_skills and self.check_pressure() > 0.8:
            old_skill = self._compacted_skills.pop(0)
            self._total_tokens -= old_skill.token_count
            freed += old_skill.token_count
        
        # 2. 卸载不常用工具
        if self.check_pressure() > 0.8:
            self._auto_compact_tools()
        
        if freed > 0:
            logger.warning(
                f"[ContextManager] Auto-compact freed {freed} tokens, "
                f"pressure: {self.check_pressure():.1%}"
            )
    
    def _auto_compact_tools(self) -> None:
        """自动压缩工具"""
        # 按使用频率排序，移除最少使用的
        tools_by_usage = sorted(
            self._loaded_tools.items(),
            key=lambda x: self._tool_usage.get(x[0], 0),
        )
        
        while tools_by_usage and self.check_pressure() > 0.7:
            name, slot = tools_by_usage.pop(0)
            if name not in ["read", "write", "bash"]:  # 保留核心工具
                self.unload_tool(name)
    
    # ============ 工具方法 ============
    
    def _estimate_tokens(self, content: str) -> int:
        """估算Token数量"""
        return len(content) // 4
    
    def set_system_content(self, content: str) -> None:
        """设置系统内容"""
        self._system_content = content
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "token_usage": self.get_token_usage(),
            "active_skill": self._active_skill.name if self._active_skill else None,
            "compacted_skills_count": len(self._compacted_skills),
            "loaded_tools": list(self._loaded_tools.keys()),
            "tool_usage_stats": dict(sorted(
                self._tool_usage.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]),
            "history_count": len(self._history),
        }


# ============================================================
# Agent集成封装
# ============================================================

class AgentContextIntegration:
    """
    Agent上下文集成封装
    
    提供简化的API，集成到现有Agent架构
    """
    
    def __init__(
        self,
        token_budget: int = 100000,
        auto_compact_threshold: float = 0.9,
    ):
        self._manager = SimpleContextManager(
            token_budget=token_budget,
            auto_compact_threshold=auto_compact_threshold,
        )
        
        self._session_id: Optional[str] = None
        self._history: List[Dict[str, Any]] = []
    
    async def initialize(
        self,
        session_id: str,
        system_prompt: str = "",
    ) -> None:
        """初始化会话"""
        self._session_id = session_id
        self._manager.set_system_content(system_prompt)
        
        logger.info(f"[AgentContext] Initialized session: {session_id}")
    
    async def prepare_skill(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        准备Skill执行环境
        
        核心：如果已有活跃Skill，自动压缩
        """
        result = self._manager.load_skill(
            name=skill_name,
            content=skill_content,
            required_tools=required_tools,
        )
        
        # 记录到历史
        self._history.append({
            "action": "load_skill",
            "skill_name": skill_name,
            "previous_skill": result.get("previous_skill"),
            "timestamp": datetime.now().isoformat(),
        })
        
        return result
    
    def build_messages(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        构建消息列表
        
        整合：Context + 历史 + 用户输入
        """
        # 基础消息（Context）
        messages = self._manager.build_context_for_llm(user_message)
        
        # 插入对话历史
        if conversation_history:
            # 找到user消息的位置
            for i, msg in enumerate(messages):
                if msg["role"] == "user":
                    # 在user消息前插入历史
                    messages[i:i] = conversation_history
                    break
        
        return messages
    
    def get_context_for_prompt(self) -> str:
        """获取上下文字符串（用于Prompt构建）"""
        return self._manager.get_skill_context_string()
    
    async def complete_skill(
        self,
        summary: str,
        key_results: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """完成当前Skill"""
        result = self._manager.complete_current_skill(summary, key_results)
        
        if result:
            self._history.append({
                "action": "complete_skill",
                "skill_name": result["skill_name"],
                "timestamp": datetime.now().isoformat(),
            })
        
        return result
    
    def record_tool_call(self, tool_name: str) -> None:
        """记录工具调用"""
        self._manager.record_tool_call(tool_name)
    
    def check_context_pressure(self) -> float:
        """检查上下文压力"""
        return self._manager.check_pressure()
    
    def get_report(self) -> Dict[str, Any]:
        """获取完整报告"""
        return {
            "session_id": self._session_id,
            "manager_stats": self._manager.get_statistics(),
            "history": self._history[-20:],  # 最近20条
        }


# ============================================================
# 使用示例
# ============================================================

async def example_usage():
    """使用示例"""
    
    # 创建集成实例
    integration = AgentContextIntegration(
        token_budget=50000,
        auto_compact_threshold=0.9,
    )
    
    # 初始化
    await integration.initialize(
        session_id="example_session",
        system_prompt="You are a helpful coding assistant.",
    )
    
    # ----- Skill 1: 代码分析 -----
    result = await integration.prepare_skill(
        skill_name="code_analysis",
        skill_content="""
# Code Analysis Skill

Analyze the codebase and identify issues.
""",
        required_tools=["read", "grep"],
    )
    print(f"Loaded skill: code_analysis")
    print(f"Previous skill auto-compacted: {result.get('previous_skill')}")
    
    # 构建消息
    messages = integration.build_messages(
        user_message="分析认证模块的代码",
    )
    print(f"\nMessages for LLM: {len(messages)} parts")
    
    # 模拟工作完成
    await integration.complete_skill(
        summary="分析了3个文件，发现5个问题",
        key_results=["SQL注入风险", "缺少错误处理"],
    )
    
    # ----- Skill 2: 代码修复 -----
    # 关键：加载新Skill时，前一个Skill自动压缩
    result = await integration.prepare_skill(
        skill_name="code_fix",
        skill_content="""
# Code Fix Skill

Fix the identified issues.
""",
        required_tools=["edit", "write"],
    )
    print(f"\nLoaded skill: code_fix")
    print(f"Previous skill auto-compacted: {result.get('previous_skill')}")
    
    # ----- 报告 -----
    report = integration.get_report()
    print(f"\nToken usage: {report['manager_stats']['token_usage']['ratio']:.1%}")
    print(f"History: {len(report['history'])} entries")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())