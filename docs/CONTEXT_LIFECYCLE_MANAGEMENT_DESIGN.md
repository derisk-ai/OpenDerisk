# Agent上下文生命周期管理设计

## 问题分析

### 当前痛点
1. **Skill占用问题**：Skill加载后内容一直保留在上下文中，多Skill任务时上下文空间被撑满
2. **工具列表膨胀**：所有MCP工具和自定义工具默认加载，消耗大量token
3. **无主动清理机制**：缺少资源使用后的主动释放策略
4. **上下文混乱风险**：多个Skill先后执行可能产生逻辑冲突

### 社区参考
- [Anthropic Skills](https://github.com/anthropics/skills): 渐进式加载指导
- OpenCode: Compaction机制 + Permission Ruleset
- OpenClaw: 上下文分片管理

---

## 整体架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    Context Lifecycle Manager                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │SkillLifecycle│  │ToolLifecycle │  │ContextSlot   │        │
│  │  Manager     │  │  Manager     │  │  Manager     │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                  Context Slot Registry                    │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │ │
│  │  │ Slot 0  │ │ Slot 1  │ │ Slot 2  │ │ Slot N  │      │ │
│  │  │ System  │ │ Skill A │ │ Skill B │ │ Tools   │      │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                  Eviction & Compaction                    │ │
│  │  - LRU Eviction  - Priority-based  - Token Budget        │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件设计

### 1. ContextSlot - 上下文槽位

```python
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

class SlotType(str, Enum):
    """槽位类型"""
    SYSTEM = "system"        # 系统级，不可驱逐
    SKILL = "skill"          # Skill内容
    TOOL = "tool"            # 工具定义
    RESOURCE = "resource"    # 资源内容
    MEMORY = "memory"        # 记忆内容

class SlotState(str, Enum):
    """槽位状态"""
    EMPTY = "empty"
    ACTIVE = "active"
    DORMANT = "dormant"      # 休眠状态
    EVICTED = "evicted"      # 已驱逐

class EvictionPolicy(str, Enum):
    """驱逐策略"""
    LRU = "lru"              # 最近最少使用
    LFU = "lfu"              # 最不经常使用
    PRIORITY = "priority"    # 优先级驱动
    MANUAL = "manual"        # 手动控制

@dataclass
class ContextSlot:
    """上下文槽位"""
    slot_id: str
    slot_type: SlotType
    state: SlotState = SlotState.EMPTY
    
    # 内容
    content: Optional[str] = None
    content_hash: Optional[str] = None
    token_count: int = 0
    
    # 元数据
    source_name: Optional[str] = None  # skill名称或工具名称
    source_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 生命周期
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    
    # 驱逐策略
    eviction_policy: EvictionPolicy = EvictionPolicy.LRU
    priority: int = 5  # 1-10, 10最高
    sticky: bool = False  # 是否固定不被驱逐
    
    # 退出摘要
    exit_summary: Optional[str] = None  # 退出时的摘要

    def touch(self):
        """更新访问时间和计数"""
        self.last_accessed = datetime.now()
        self.access_count += 1
    
    def should_evict(self, policy: EvictionPolicy) -> bool:
        """判断是否应该被驱逐"""
        if self.sticky or self.slot_type == SlotType.SYSTEM:
            return False
        return True
```

### 2. SkillLifecycleManager - Skill生命周期管理器

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class ExitTrigger(str, Enum):
    """退出触发器"""
    TASK_COMPLETE = "task_complete"      # 任务完成
    ERROR_OCCURRED = "error_occurred"    # 发生错误
    TIMEOUT = "timeout"                  # 超时
    MANUAL = "manual"                    # 手动退出
    CONTEXT_PRESSURE = "context_pressure"  # 上下文压力
    NEW_SKILL_LOAD = "new_skill_load"    # 新Skill加载

@dataclass
class SkillExitResult:
    """Skill退出结果"""
    skill_name: str
    exit_trigger: ExitTrigger
    summary: str                    # 执行摘要
    key_outputs: List[str]          # 关键输出
    next_skill_hint: Optional[str] = None  # 下一个Skill提示
    tokens_freed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

class SkillLifecycleManager:
    """
    Skill生命周期管理器
    
    职责:
    1. 管理Skill的加载、激活、休眠、退出
    2. 生成Skill退出摘要
    3. 协调多个Skill之间的上下文切换
    """
    
    def __init__(
        self,
        context_slot_manager: 'ContextSlotManager',
        summary_generator: Optional[Callable] = None,
        max_active_skills: int = 3,
    ):
        self._slot_manager = context_slot_manager
        self._summary_generator = summary_generator
        self._max_active_skills = max_active_skills
        
        self._active_skills: Dict[str, ContextSlot] = {}
        self._skill_history: List[SkillExitResult] = []
        self._skill_manifest: Dict[str, SkillManifest] = {}
    
    async def load_skill(
        self,
        skill_name: str,
        skill_content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextSlot:
        """
        加载Skill到上下文
        
        策略:
        1. 检查是否已存在
        2. 检查活跃Skill数量，必要时驱逐
        3. 分配槽位并加载
        """
        # 检查是否已加载
        if skill_name in self._active_skills:
            slot = self._active_skills[skill_name]
            slot.touch()
            return slot
        
        # 检查活跃数量限制
        if len(self._active_skills) >= self._max_active_skills:
            await self._evict_lru_skill()
        
        # 分配槽位
        slot = await self._slot_manager.allocate(
            slot_type=SlotType.SKILL,
            content=skill_content,
            source_name=skill_name,
            metadata=metadata or {},
            eviction_policy=EvictionPolicy.LRU,
        )
        
        self._active_skills[skill_name] = slot
        
        logger.info(
            f"[SkillLifecycle] Loaded skill '{skill_name}', "
            f"active: {len(self._active_skills)}/{self._max_active_skills}"
        )
        
        return slot
    
    async def activate_skill(self, skill_name: str) -> Optional[ContextSlot]:
        """激活休眠的Skill"""
        slot = self._slot_manager.get_slot_by_name(skill_name, SlotType.SKILL)
        if slot and slot.state == SlotState.DORMANT:
            slot.state = SlotState.ACTIVE
            slot.touch()
            self._active_skills[skill_name] = slot
            return slot
        return None
    
    async def exit_skill(
        self,
        skill_name: str,
        trigger: ExitTrigger = ExitTrigger.TASK_COMPLETE,
        summary: Optional[str] = None,
        key_outputs: Optional[List[str]] = None,
    ) -> SkillExitResult:
        """
        Skill主动退出
        
        核心机制:
        1. 生成执行摘要（如果没有提供）
        2. 保留关键信息到压缩形式
        3. 清除Skill详细内容
        4. 更新历史记录
        """
        if skill_name not in self._active_skills:
            logger.warning(f"[SkillLifecycle] Skill '{skill_name}' not active")
            return SkillExitResult(
                skill_name=skill_name,
                exit_trigger=trigger,
                summary="Skill not active",
                key_outputs=[],
            )
        
        slot = self._active_skills.pop(skill_name)
        
        # 生成摘要
        if not summary:
            summary = await self._generate_summary(slot)
        
        # 创建压缩后的槽位
        compact_content = self._create_compact_representation(
            skill_name=skill_name,
            summary=summary,
            key_outputs=key_outputs or [],
        )
        
        # 计算释放的token
        tokens_freed = slot.token_count - len(compact_content) // 4
        
        # 更新槽位
        slot.content = compact_content
        slot.token_count = len(compact_content) // 4
        slot.state = SlotState.DORMANT
        slot.exit_summary = summary
        
        # 记录历史
        result = SkillExitResult(
            skill_name=skill_name,
            exit_trigger=trigger,
            summary=summary,
            key_outputs=key_outputs or [],
            tokens_freed=tokens_freed,
        )
        self._skill_history.append(result)
        
        logger.info(
            f"[SkillLifecycle] Skill '{skill_name}' exited, "
            f"tokens freed: {tokens_freed}, trigger: {trigger}"
        )
        
        return result
    
    async def _generate_summary(self, slot: ContextSlot) -> str:
        """生成Skill执行摘要"""
        if self._summary_generator:
            return await self._summary_generator(slot)
        
        # 默认摘要模板
        return f"[Skill {slot.source_name} Completed]\n" \
               f"- Tasks performed: {slot.access_count} operations\n" \
               f"- Duration: {(datetime.now() - slot.created_at).seconds}s"
    
    def _create_compact_representation(
        self,
        skill_name: str,
        summary: str,
        key_outputs: List[str],
    ) -> str:
        """创建压缩表示，只保留关键信息"""
        lines = [
            f"<skill-result name=\"{skill_name}\">",
            f"<summary>{summary}</summary>",
        ]
        
        if key_outputs:
            lines.append("<key-outputs>")
            for output in key_outputs[:5]:  # 最多保留5个关键输出
                lines.append(f"  - {output}")
            lines.append("</key-outputs>")
        
        lines.append("</skill-result>")
        
        return "\n".join(lines)
    
    async def _evict_lru_skill(self) -> Optional[SkillExitResult]:
        """驱逐最近最少使用的Skill"""
        if not self._active_skills:
            return None
        
        # 找到LRU的Skill
        lru_skill = min(
            self._active_skills.items(),
            key=lambda x: x[1].last_accessed
        )
        
        return await self.exit_skill(
            skill_name=lru_skill[0],
            trigger=ExitTrigger.CONTEXT_PRESSURE,
        )
    
    def get_active_skills(self) -> List[str]:
        """获取当前活跃的Skill列表"""
        return list(self._active_skills.keys())
    
    def get_skill_history(self) -> List[SkillExitResult]:
        """获取Skill执行历史"""
        return self._skill_history.copy()
```

### 3. ToolLifecycleManager - 工具生命周期管理器

```python
from typing import Set, Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class ToolCategory(str, Enum):
    """工具类别"""
    SYSTEM = "system"          # 系统工具，常驻
    BUILTIN = "builtin"        # 内置工具
    MCP = "mcp"                # MCP工具
    CUSTOM = "custom"          # 自定义工具
    INTERACTION = "interaction"  # 交互工具

@dataclass
class ToolManifest:
    """工具清单"""
    name: str
    category: ToolCategory
    description: str
    parameters_schema: Dict[str, Any]
    auto_load: bool = False    # 是否自动加载
    load_priority: int = 5     # 加载优先级
    dependencies: List[str] = field(default_factory=list)

class ToolLifecycleManager:
    """
    工具生命周期管理器
    
    核心功能:
    1. 按需加载工具定义到上下文
    2. 工具使用后可选择性退出
    3. 批量工具管理
    """
    
    DEFAULT_ALWAYS_LOADED = {
        "think", "question", "confirm", "notify", "progress"
    }
    
    def __init__(
        self,
        context_slot_manager: 'ContextSlotManager',
        tool_registry: 'ToolRegistry',
        max_tool_definitions: int = 20,
    ):
        self._slot_manager = context_slot_manager
        self._tool_registry = tool_registry
        self._max_tool_definitions = max_tool_definitions
        
        # 工具清单
        self._tool_manifests: Dict[str, ToolManifest] = {}
        
        # 已加载的工具
        self._loaded_tools: Set[str] = set(self.DEFAULT_ALWAYS_LOADED)
        
        # 工具使用统计
        self._tool_usage: Dict[str, int] = {}
    
    def register_tool_manifest(self, manifest: ToolManifest):
        """注册工具清单"""
        self._tool_manifests[manifest.name] = manifest
        
        if manifest.auto_load:
            # 标记为需要自动加载
            pass
    
    async def ensure_tools_loaded(
        self,
        tool_names: List[str],
    ) -> Dict[str, bool]:
        """
        确保指定工具已加载
        
        策略:
        1. 检查已加载列表
        2. 按优先级加载缺失的工具
        3. 必要时驱逐不常用工具
        """
        results = {}
        tools_to_load = []
        
        for name in tool_names:
            if name in self._loaded_tools:
                results[name] = True
            else:
                tools_to_load.append(name)
        
        if not tools_to_load:
            return results
        
        # 检查是否需要驱逐
        projected_count = len(self._loaded_tools) + len(tools_to_load)
        if projected_count > self._max_tool_definitions:
            await self._evict_unused_tools(
                count=projected_count - self._max_tool_definitions
            )
        
        # 加载工具
        for name in tools_to_load:
            loaded = await self._load_tool_definition(name)
            results[name] = loaded
        
        return results
    
    async def _load_tool_definition(self, tool_name: str) -> bool:
        """加载工具定义到上下文"""
        manifest = self._tool_manifests.get(tool_name)
        if not manifest:
            # 从registry获取
            tool = self._tool_registry.get(tool_name)
            if not tool:
                logger.warning(f"[ToolLifecycle] Tool '{tool_name}' not found")
                return False
            
            manifest = ToolManifest(
                name=tool_name,
                category=ToolCategory.CUSTOM,
                description=tool.metadata.description,
                parameters_schema=tool.metadata.parameters,
            )
        
        # 创建槽位
        content = self._format_tool_definition(manifest)
        
        slot = await self._slot_manager.allocate(
            slot_type=SlotType.TOOL,
            content=content,
            source_name=tool_name,
            metadata={"category": manifest.category.value},
            eviction_policy=EvictionPolicy.LFU,
            priority=manifest.load_priority,
        )
        
        self._loaded_tools.add(tool_name)
        logger.debug(f"[ToolLifecycle] Loaded tool: {tool_name}")
        
        return True
    
    def _format_tool_definition(self, manifest: ToolManifest) -> str:
        """格式化工具定义为紧凑形式"""
        import json
        
        return json.dumps({
            "name": manifest.name,
            "description": manifest.description[:200],  # 限制描述长度
            "parameters": manifest.parameters_schema,
        }, ensure_ascii=False)
    
    async def unload_tools(
        self,
        tool_names: List[str],
        keep_system: bool = True,
    ) -> List[str]:
        """
        卸载工具
        
        策略:
        1. 保留系统工具（如果keep_system=True）
        2. 记录使用统计
        3. 从上下文移除
        """
        unloaded = []
        
        for name in tool_names:
            if keep_system and name in self.DEFAULT_ALWAYS_LOADED:
                continue
            
            if name in self._loaded_tools:
                await self._slot_manager.evict(
                    slot_type=SlotType.TOOL,
                    source_name=name,
                )
                self._loaded_tools.discard(name)
                unloaded.append(name)
        
        logger.info(f"[ToolLifecycle] Unloaded tools: {unloaded}")
        return unloaded
    
    async def _evict_unused_tools(self, count: int):
        """驱逐不常用的工具"""
        # 按使用频率排序，排除系统工具
        candidates = [
            name for name in self._loaded_tools
            if name not in self.DEFAULT_ALWAYS_LOADED
        ]
        
        candidates.sort(key=lambda x: self._tool_usage.get(x, 0))
        
        to_evict = candidates[:count]
        await self.unload_tools(to_evict, keep_system=False)
    
    def record_tool_usage(self, tool_name: str):
        """记录工具使用"""
        self._tool_usage[tool_name] = self._tool_usage.get(tool_name, 0) + 1
    
    def get_loaded_tools(self) -> Set[str]:
        """获取已加载的工具列表"""
        return self._loaded_tools.copy()
```

### 4. ContextSlotManager - 上下文槽位管理器

```python
from typing import Optional, List, Dict, Any
from collections import OrderedDict
import hashlib
import logging

logger = logging.getLogger(__name__)

class ContextSlotManager:
    """
    上下文槽位管理器
    
    核心职责:
    1. 分配和管理上下文槽位
    2. Token预算管理
    3. 驱逐策略执行
    4. 槽位状态追踪
    """
    
    def __init__(
        self,
        max_slots: int = 50,
        token_budget: int = 100000,  # 默认100k token预算
        default_eviction_policy: EvictionPolicy = EvictionPolicy.LRU,
    ):
        self._max_slots = max_slots
        self._token_budget = token_budget
        self._default_policy = default_eviction_policy
        
        # 槽位存储 {slot_id: ContextSlot}
        self._slots: OrderedDict[str, ContextSlot] = OrderedDict()
        
        # 名称索引 {source_name: slot_id}
        self._name_index: Dict[str, str] = {}
        
        # Token使用统计
        self._total_tokens = 0
        self._tokens_by_type: Dict[SlotType, int] = {}
    
    async def allocate(
        self,
        slot_type: SlotType,
        content: str,
        source_name: Optional[str] = None,
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        eviction_policy: Optional[EvictionPolicy] = None,
        priority: int = 5,
        sticky: bool = False,
    ) -> ContextSlot:
        """
        分配槽位
        
        策略:
        1. 检查Token预算
        2. 检查槽位数量限制
        3. 执行驱逐（如果需要）
        4. 创建并注册槽位
        """
        content_tokens = self._estimate_tokens(content)
        
        # 检查预算
        if self._total_tokens + content_tokens > self._token_budget:
            await self._evict_for_budget(content_tokens)
        
        # 检查数量限制
        if len(self._slots) >= self._max_slots:
            await self._evict_for_slots()
        
        # 创建槽位
        slot_id = self._generate_slot_id()
        slot = ContextSlot(
            slot_id=slot_id,
            slot_type=slot_type,
            state=SlotState.ACTIVE,
            content=content,
            content_hash=self._hash_content(content),
            token_count=content_tokens,
            source_name=source_name,
            source_id=source_id,
            metadata=metadata or {},
            eviction_policy=eviction_policy or self._default_policy,
            priority=priority,
            sticky=sticky,
        )
        
        # 注册
        self._slots[slot_id] = slot
        if source_name:
            self._name_index[source_name] = slot_id
        
        # 更新统计
        self._total_tokens += content_tokens
        self._tokens_by_type[slot_type] = \
            self._tokens_by_type.get(slot_type, 0) + content_tokens
        
        logger.debug(
            f"[SlotManager] Allocated slot {slot_id} "
            f"for {source_name or 'unnamed'}, tokens: {content_tokens}"
        )
        
        return slot
    
    def get_slot(self, slot_id: str) -> Optional[ContextSlot]:
        """获取槽位"""
        slot = self._slots.get(slot_id)
        if slot:
            slot.touch()
        return slot
    
    def get_slot_by_name(
        self,
        name: str,
        slot_type: Optional[SlotType] = None
    ) -> Optional[ContextSlot]:
        """按名称获取槽位"""
        slot_id = self._name_index.get(name)
        if slot_id:
            slot = self._slots.get(slot_id)
            if slot and (slot_type is None or slot.slot_type == slot_type):
                slot.touch()
                return slot
        return None
    
    async def evict(
        self,
        slot_type: Optional[SlotType] = None,
        source_name: Optional[str] = None,
        slot_id: Optional[str] = None,
    ) -> Optional[ContextSlot]:
        """驱逐指定槽位"""
        target_slot = None
        
        if slot_id:
            target_slot = self._slots.get(slot_id)
        elif source_name:
            target_slot = self.get_slot_by_name(source_name, slot_type)
        
        if not target_slot:
            return None
        
        if target_slot.sticky:
            logger.warning(f"[SlotManager] Cannot evict sticky slot: {target_slot.slot_id}")
            return None
        
        return await self._do_evict(target_slot)
    
    async def _do_evict(self, slot: ContextSlot) -> ContextSlot:
        """执行驱逐"""
        # 更新统计
        self._total_tokens -= slot.token_count
        self._tokens_by_type[slot.slot_type] -= slot.token_count
        
        # 从索引移除
        if slot.source_name:
            self._name_index.pop(slot.source_name, None)
        
        # 标记状态
        slot.state = SlotState.EVICTED
        
        # 从存储移除
        evicted_slot = self._slots.pop(slot.slot_id)
        
        logger.info(
            f"[SlotManager] Evicted slot {slot.slot_id} "
            f"({slot.source_name}), freed {slot.token_count} tokens"
        )
        
        return evicted_slot
    
    async def _evict_for_budget(self, required_tokens: int):
        """为预算驱逐"""
        tokens_needed = self._total_tokens + required_tokens - self._token_budget
        
        # 按驱逐策略排序
        candidates = [
            s for s in self._slots.values()
            if s.should_evict(self._default_policy)
        ]
        
        candidates.sort(
            key=lambda s: (s.priority, s.last_accessed.timestamp())
        )
        
        freed = 0
        for slot in candidates:
            if freed >= tokens_needed:
                break
            await self._do_evict(slot)
            freed += slot.token_count
    
    async def _evict_for_slots(self):
        """为槽位数量驱逐"""
        candidates = [
            s for s in self._slots.values()
            if s.should_evict(self._default_policy)
        ]
        
        candidates.sort(
            key=lambda s: (s.priority, s.last_accessed.timestamp())
        )
        
        if candidates:
            await self._do_evict(candidates[0])
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_slots": len(self._slots),
            "max_slots": self._max_slots,
            "total_tokens": self._total_tokens,
            "token_budget": self._token_budget,
            "tokens_by_type": dict(self._tokens_by_type),
            "slots_by_type": {
                t.value: len([s for s in self._slots.values() if s.slot_type == t])
                for t in SlotType
            },
        }
    
    def _estimate_tokens(self, content: str) -> int:
        """估算token数量"""
        # 简单估算：字符数/4
        return len(content) // 4
    
    def _hash_content(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _generate_slot_id(self) -> str:
        """生成槽位ID"""
        import uuid
        return f"slot_{uuid.uuid4().hex[:8]}"
```

### 5. ContextLifecycleOrchestrator - 上下文生命周期编排器

```python
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class ContextLifecycleOrchestrator:
    """
    上下文生命周期编排器
    
    统一协调Skill和工具的生命周期管理
    """
    
    def __init__(
        self,
        token_budget: int = 100000,
        max_active_skills: int = 3,
        max_tool_definitions: int = 20,
    ):
        # 核心组件
        self._slot_manager = ContextSlotManager(token_budget=token_budget)
        self._skill_manager = SkillLifecycleManager(
            context_slot_manager=self._slot_manager,
            max_active_skills=max_active_skills,
        )
        self._tool_manager = ToolLifecycleManager(
            context_slot_manager=self._slot_manager,
            tool_registry=None,  # 需要注入
            max_tool_definitions=max_tool_definitions,
        )
        
        # 状态追踪
        self._session_id: Optional[str] = None
        self._initialized = False
    
    async def initialize(
        self,
        session_id: str,
        initial_tools: Optional[List[str]] = None,
    ):
        """初始化"""
        self._session_id = session_id
        self._initialized = True
        
        # 加载初始工具
        if initial_tools:
            await self._tool_manager.ensure_tools_loaded(initial_tools)
        
        logger.info(f"[Orchestrator] Initialized for session: {session_id}")
    
    async def prepare_skill_context(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        准备Skill执行的上下文环境
        
        流程:
        1. 加载Skill内容
        2. 确保所需工具可用
        3. 返回执行所需的所有信息
        """
        # 加载Skill
        slot = await self._skill_manager.load_skill(
            skill_name=skill_name,
            skill_content=skill_content,
        )
        
        # 加载工具
        loaded_tools = {}
        if required_tools:
            loaded_tools = await self._tool_manager.ensure_tools_loaded(required_tools)
        
        return {
            "skill_slot": slot,
            "loaded_tools": loaded_tools,
            "active_skills": self._skill_manager.get_active_skills(),
            "context_stats": self._slot_manager.get_statistics(),
        }
    
    async def complete_skill(
        self,
        skill_name: str,
        task_summary: str,
        key_outputs: Optional[List[str]] = None,
        next_skill_hint: Optional[str] = None,
    ) -> SkillExitResult:
        """
        完成Skill执行并退出
        
        策略:
        1. 生成摘要
        2. 退出Skill
        3. 如果有下一个Skill提示，预加载
        """
        result = await self._skill_manager.exit_skill(
            skill_name=skill_name,
            trigger=ExitTrigger.TASK_COMPLETE,
            summary=task_summary,
            key_outputs=key_outputs,
        )
        
        # 预加载下一个Skill
        if next_skill_hint:
            # 可以在这里预加载下一个Skill的元数据
            pass
        
        return result
    
    async def handle_context_pressure(self) -> Dict[str, Any]:
        """
        处理上下文压力
        
        当检测到上下文即将超出限制时调用
        """
        stats = self._slot_manager.get_statistics()
        pressure_level = stats["total_tokens"] / stats["token_budget"]
        
        actions = []
        
        if pressure_level > 0.9:
            # 紧急：驱逐所有非活跃Skill
            for skill_name in self._skill_manager.get_active_skills():
                result = await self._skill_manager.exit_skill(
                    skill_name=skill_name,
                    trigger=ExitTrigger.CONTEXT_PRESSURE,
                )
                actions.append(f"evicted skill: {skill_name}")
        
        elif pressure_level > 0.75:
            # 警告：驱逐LRU Skill
            result = await self._skill_manager._evict_lru_skill()
            if result:
                actions.append(f"evicted LRU skill: {result.skill_name}")
        
        return {
            "pressure_level": pressure_level,
            "actions_taken": actions,
            "new_stats": self._slot_manager.get_statistics(),
        }
    
    def get_context_report(self) -> Dict[str, Any]:
        """获取上下文报告"""
        return {
            "session_id": self._session_id,
            "slot_stats": self._slot_manager.get_statistics(),
            "active_skills": self._skill_manager.get_active_skills(),
            "loaded_tools": list(self._tool_manager.get_loaded_tools()),
            "skill_history": [
                {
                    "skill": r.skill_name,
                    "trigger": r.exit_trigger.value,
                    "summary": r.summary,
                    "tokens_freed": r.tokens_freed,
                }
                for r in self._skill_manager.get_skill_history()
            ],
        }
```

---

## Core架构集成方案

### 核心修改

为 `core` 架构添加上下文生命周期管理：

```python
# derisk/agent/core/context_lifecycle/__init__.py

from .slot_manager import ContextSlotManager, ContextSlot, SlotType, SlotState
from .skill_lifecycle import SkillLifecycleManager, ExitTrigger, SkillExitResult
from .tool_lifecycle import ToolLifecycleManager, ToolCategory
from .orchestrator import ContextLifecycleOrchestrator

__all__ = [
    "ContextSlotManager", "ContextSlot", "SlotType", "SlotState",
    "SkillLifecycleManager", "ExitTrigger", "SkillExitResult",
    "ToolLifecycleManager", "ToolCategory",
    "ContextLifecycleOrchestrator",
]
```

### 集成到ExecutionEngine

```python
# derisk/agent/core/execution_engine.py 的修改

class ExecutionEngine(Generic[T]):
    def __init__(
        self,
        max_steps: int = 10,
        timeout_seconds: Optional[float] = None,
        hooks: Optional[ExecutionHooks] = None,
        context_lifecycle: Optional[ContextLifecycleOrchestrator] = None,
    ):
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.hooks = hooks or ExecutionHooks()
        self.context_lifecycle = context_lifecycle
        
        # 添加新的Hook点
        self.hooks.on("before_skill_load", self._handle_skill_load)
        self.hooks.on("after_skill_complete", self._handle_skill_exit)
    
    async def _handle_skill_load(self, skill_name: str, **kwargs):
        """Skill加载前处理"""
        if self.context_lifecycle:
            # 准备上下文
            pass
    
    async def _handle_skill_exit(self, skill_name: str, result: Any, **kwargs):
        """Skill完成后处理"""
        if self.context_lifecycle:
            await self.context_lifecycle.complete_skill(
                skill_name=skill_name,
                task_summary=str(result),
            )
```

---

## CoreV2架构集成方案

### 核心修改

为 `corev2` 架构添加上下文生命周期管理：

```python
# derisk/agent/core_v2/context_lifecycle/__init__.py
```

### 集成到AgentHarness

```python
# derisk/agent/core_v2/agent_harness.py 的修改

class AgentHarness:
    """
    Agent执行框架，集成上下文生命周期管理
    """
    
    def __init__(
        self,
        ...,
        context_lifecycle: Optional[ContextLifecycleOrchestrator] = None,
    ):
        # ... 现有初始化
        self._context_lifecycle = context_lifecycle or ContextLifecycleOrchestrator()
    
    async def execute_step(self, step: ExecutionStep) -> Any:
        """执行步骤，集成上下文管理"""
        # 检查上下文压力
        stats = self._context_lifecycle.get_context_report()["slot_stats"]
        if stats["total_tokens"] / stats["token_budget"] > 0.8:
            await self._context_lifecycle.handle_context_pressure()
        
        # 执行步骤
        result = await self._do_execute_step(step)
        
        return result
```

### 集成到SceneStrategy

```python
# derisk/agent/core_v2/scene_strategy.py 的修改

class SceneStrategy:
    """
    场景策略，支持Skill退出配置
    """
    
    def __init__(
        self,
        ...,
        skill_exit_policy: Optional[Dict[str, Any]] = None,
    ):
        self._exit_policy = skill_exit_policy or {
            "auto_exit_on_complete": True,
            "keep_summary": True,
            "max_key_outputs": 5,
        }
```

---

## 使用示例

### 基本使用

```python
from derisk.agent.core.context_lifecycle import (
    ContextLifecycleOrchestrator,
    ExitTrigger,
)

# 创建编排器
orchestrator = ContextLifecycleOrchestrator(
    token_budget=50000,  # 50k token
    max_active_skills=2,
    max_tool_definitions=15,
)

# 初始化
await orchestrator.initialize(
    session_id="session_001",
    initial_tools=["read", "write", "bash"],
)

# 准备Skill上下文
context = await orchestrator.prepare_skill_context(
    skill_name="code_review",
    skill_content=skill_content,
    required_tools=["read", "grep", "bash"],
)

# 执行Skill...
# ...

# 完成并退出Skill
result = await orchestrator.complete_skill(
    skill_name="code_review",
    task_summary="Reviewed 3 files, found 5 issues",
    key_outputs=[
        "Issue 1: SQL injection risk in auth.py",
        "Issue 2: Missing error handling in api.py",
    ],
    next_skill_hint="fix_code_issues",
)

print(f"Tokens freed: {result.tokens_freed}")
```

### 与现有Agent集成

```python
# 在Agent创建时注入

from derisk.agent.core import create_agent_info
from derisk.agent.core.context_lifecycle import ContextLifecycleOrchestrator

# 创建上下文生命周期管理器
context_lifecycle = ContextLifecycleOrchestrator()

# 创建Agent时注入
agent_info = create_agent_info(
    name="primary",
    mode="primary",
    context_lifecycle=context_lifecycle,  # 注入
)
```

---

## 配置说明

### YAML配置示例

```yaml
# configs/context_lifecycle.yaml

context_lifecycle:
  token_budget: 100000
  max_active_skills: 3
  max_tool_definitions: 20
  
  skill:
    auto_exit: true
    summary_generation: llm  # llm | template | custom
    max_active: 3
    eviction_policy: lru
    
  tool:
    auto_load_core: true
    load_on_demand: true
    unload_after_use: false
    keep_system_tools: true
    
  eviction:
    policy: lru  # lru | lfu | priority
    pressure_threshold: 0.8
    critical_threshold: 0.95
```

---

## 性能考虑

### Token节省估算

| 场景 | 传统方式 | 优化后 | 节省 |
|-----|---------|--------|-----|
| 多Skill任务(5个) | ~50k tokens | ~15k tokens | 70% |
| MCP工具(20个) | ~10k tokens | ~3k tokens | 70% |
| 长对话(50轮) | ~80k tokens | ~40k tokens | 50% |

### 最佳实践

1. **Skill优先级设置**：为核心Skill设置高优先级和sticky=True
2. **工具按需加载**：只在需要时加载工具定义
3. **摘要质量**：使用LLM生成高质量摘要
4. **关键输出限制**：限制保留的关键输出数量
5. **监控与调优**：定期检查上下文报告并调整配置

---

## 总结

本方案设计了完整的Skill和工具生命周期管理机制：

1. **上下文槽位管理**：统一管理所有上下文内容
2. **主动退出机制**：Skill完成后自动释放空间
3. **按需加载**：工具定义按需加载和卸载
4. **智能驱逐**：基于策略的上下文驱逐
5. **摘要保留**：退出时保留关键信息摘要
6. **无缝集成**：与现有core和corev2架构集成

这套机制可以显著减少上下文空间占用，提升长任务执行的稳定性和效率。