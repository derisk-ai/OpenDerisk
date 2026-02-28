"""
扩展生命周期管理示例

展示如何为新的内容类型快速实现生命周期管理。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_lifecycle import (
    BaseLifecycleManager,
    ContentManifest,
    ExitResult,
    ExitTrigger,
)
from .slot_manager import (
    ContextSlot,
    ContextSlotManager,
    EvictionPolicy,
    SlotType,
)

logger = logging.getLogger(__name__)


# ============================================================
# 示例1: Resource 生命周期管理（绑定资源如数据库、文件等）
# ============================================================

@dataclass
class ResourceManifest(ContentManifest):
    """资源清单"""
    resource_type: str = "file"  # file, database, api, cache
    connection_info: Dict[str, Any] = field(default_factory=dict)
    auto_reconnect: bool = True


class ResourceLifecycleManager(BaseLifecycleManager[Dict[str, Any]]):
    """
    资源生命周期管理器
    
    管理绑定资源（数据库连接、文件句柄、API客户端等）
    """
    
    def __init__(
        self,
        slot_manager: ContextSlotManager,
        max_active: int = 10,
    ):
        super().__init__(
            slot_manager=slot_manager,
            slot_type=SlotType.RESOURCE,
            content_type_name="Resource",
            max_active=max_active,
            eviction_policy=EvictionPolicy.LFU,
        )
        self._connections: Dict[str, Any] = {}
    
    async def connect(
        self,
        name: str,
        resource_config: Dict[str, Any],
    ) -> ContextSlot:
        """连接资源"""
        content = self._format_resource_info(resource_config)
        
        slot = await self.load(name, content, metadata=resource_config)
        
        self._connections[name] = resource_config
        
        return slot
    
    async def disconnect(
        self,
        name: str,
    ) -> ExitResult:
        """断开资源连接"""
        result = await self.exit(
            name=name,
            trigger=ExitTrigger.MANUAL,
            summary=f"Disconnected from {name}",
        )
        
        self._connections.pop(name, None)
        
        return result
    
    def _format_resource_info(self, config: Dict[str, Any]) -> str:
        """格式化资源信息"""
        lines = [f"<resource name=\"{config.get('name', 'unknown')}\">"]
        
        if "type" in config:
            lines.append(f"  <type>{config['type']}</type>")
        if "host" in config:
            lines.append(f"  <host>{config['host']}</host>")
        if "description" in config:
            lines.append(f"  <description>{config['description']}</description>")
        
        lines.append("</resource>")
        return "\n".join(lines)
    
    def _create_compact_representation(
        self,
        name: str,
        summary: str,
        key_outputs: List[str],
    ) -> str:
        """创建压缩表示"""
        return f'<resource-result name="{name}">{summary}</resource-result>'
    
    def _generate_summary(self, slot: ContextSlot) -> str:
        """生成摘要"""
        return f"Resource {slot.source_name} released after {slot.access_count} accesses"


# ============================================================
# 示例2: Memory 生命周期管理（对话历史、用户偏好等）
# ============================================================

@dataclass
class MemoryManifest(ContentManifest):
    """记忆清单"""
    memory_scope: str = "session"  # session, user, global
    retention_policy: str = "auto"  # auto, manual, permanent
    max_age_seconds: int = 3600


class MemoryLifecycleManager(BaseLifecycleManager[List[str]]):
    """
    记忆生命周期管理器
    
    管理对话历史、用户偏好、上下文记忆等
    """
    
    def __init__(
        self,
        slot_manager: ContextSlotManager,
        max_active: int = 20,
    ):
        super().__init__(
            slot_manager=slot_manager,
            slot_type=SlotType.MEMORY,
            content_type_name="Memory",
            max_active=max_active,
            eviction_policy=EvictionPolicy.LRU,
        )
        self._memories: Dict[str, List[str]] = {}
    
    async def store_memory(
        self,
        name: str,
        items: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextSlot:
        """存储记忆"""
        content = self._format_memory_content(name, items)
        
        slot = await self.load(name, content, metadata)
        
        self._memories[name] = items
        
        return slot
    
    async def append_memory(
        self,
        name: str,
        item: str,
    ) -> bool:
        """追加记忆"""
        if name not in self._active:
            return False
        
        self._memories.setdefault(name, []).append(item)
        
        slot = self._active[name]
        items = self._memories[name]
        new_content = self._format_memory_content(name, items)
        
        self._slot_manager.update_slot_content(slot.slot_id, new_content)
        slot.touch()
        
        return True
    
    async def compact_memory(
        self,
        name: str,
        summary: str,
    ) -> ExitResult:
        """压缩记忆"""
        items = self._memories.get(name, [])
        
        result = await self.exit(
            name=name,
            trigger=ExitTrigger.COMPLETE,
            summary=summary,
            key_outputs=items[:5],
        )
        
        return result
    
    def _format_memory_content(self, name: str, items: List[str]) -> str:
        """格式化记忆内容"""
        lines = [f"<memory name=\"{name}\">"]
        for i, item in enumerate(items[-50:]):
            lines.append(f"  <item>{item[:200]}</item>")
        lines.append("</memory>")
        return "\n".join(lines)
    
    def _create_compact_representation(
        self,
        name: str,
        summary: str,
        key_outputs: List[str],
    ) -> str:
        """创建压缩表示"""
        lines = [f'<memory-result name="{name}">']
        lines.append(f"  <summary>{summary}</summary>")
        if key_outputs:
            lines.append("  <highlights>")
            for item in key_outputs[:5]:
                lines.append(f"    <item>{item[:100]}</item>")
            lines.append("  </highlights>")
        lines.append("</memory-result>")
        return "\n".join(lines)
    
    def _generate_summary(self, slot: ContextSlot) -> str:
        """生成摘要"""
        items = self._memories.get(slot.source_name, [])
        return f"Memory {slot.source_name}: {len(items)} items compressed"


# ============================================================
# 示例3: Plugin 生命周期管理（示例自定义类型）
# ============================================================

class PluginType:
    """插件类型"""
    ANALYZER = "analyzer"
    TRANSFORMER = "transformer"
    OUTPUTTER = "outputter"


@dataclass
class PluginManifest(ContentManifest):
    """插件清单"""
    plugin_type: str = PluginType.ANALYZER
    version: str = "1.0.0"
    dependencies: List[str] = field(default_factory=list)


class PluginLifecycleManager(BaseLifecycleManager[Dict[str, Any]]):
    """
    插件生命周期管理器
    
    展示如何为自定义类型快速实现
    """
    
    def __init__(
        self,
        slot_manager: ContextSlotManager,
        max_active: int = 15,
    ):
        super().__init__(
            slot_manager=slot_manager,
            slot_type=SlotType.TOOL,  # 复用TOOL类型或扩展新类型
            content_type_name="Plugin",
            max_active=max_active,
            eviction_policy=EvictionPolicy.PRIORITY,
        )
        self._plugins: Dict[str, Dict[str, Any]] = {}
    
    async def load_plugin(
        self,
        name: str,
        plugin_code: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> ContextSlot:
        """加载插件"""
        content = self._format_plugin_content(name, plugin_code)
        
        slot = await self.load(name, content, metadata=config)
        
        self._plugins[name] = {
            "code": plugin_code,
            "config": config or {},
        }
        
        return slot
    
    async def unload_plugin(
        self,
        name: str,
    ) -> ExitResult:
        """卸载插件"""
        result = await self.exit(
            name=name,
            trigger=ExitTrigger.MANUAL,
            summary=f"Plugin {name} unloaded",
        )
        
        self._plugins.pop(name, None)
        
        return result
    
    def _format_plugin_content(self, name: str, code: str) -> str:
        """格式化插件内容"""
        return f'<plugin name="{name}">\n{code}\n</plugin>'
    
    def _create_compact_representation(
        self,
        name: str,
        summary: str,
        key_outputs: List[str],
    ) -> str:
        """创建压缩表示"""
        return f'<plugin-result name="{name}">{summary}</plugin-result>'
    
    def _generate_summary(self, slot: ContextSlot) -> str:
        """生成摘要"""
        return f"Plugin {slot.source_name} used {slot.access_count} times"


# ============================================================
# 快速扩展示例：只需实现2个方法
# ============================================================

class CustomLifecycleManager(BaseLifecycleManager[Any]):
    """
    自定义生命周期管理器模板
    
    只需实现2个抽象方法即可快速扩展：
    1. _create_compact_representation() - 压缩内容
    2. _generate_summary() - 生成摘要
    """
    
    def __init__(
        self,
        slot_manager: ContextSlotManager,
        slot_type: SlotType,
        type_name: str,
        max_active: int = 10,
    ):
        super().__init__(
            slot_manager=slot_manager,
            slot_type=slot_type,
            content_type_name=type_name,
            max_active=max_active,
        )
    
    def _create_compact_representation(
        self,
        name: str,
        summary: str,
        key_outputs: List[str],
    ) -> str:
        """实现压缩逻辑"""
        return f'<result name="{name}">{summary}</result>'
    
    def _generate_summary(self, slot: ContextSlot) -> str:
        """实现摘要生成"""
        return f"{self._content_type_name} {slot.source_name} completed"


# ============================================================
# 使用示例
# ============================================================

async def example_usage():
    """使用示例"""
    from .slot_manager import ContextSlotManager
    from .orchestrator import ContextLifecycleOrchestrator
    
    # 创建编排器
    orchestrator = ContextLifecycleOrchestrator()
    await orchestrator.initialize(session_id="example_session")
    
    slot_manager = orchestrator.get_slot_manager()
    
    # 1. 资源管理
    resource_manager = ResourceLifecycleManager(slot_manager)
    
    await resource_manager.connect("db_main", {
        "name": "main_db",
        "type": "postgresql",
        "host": "localhost:5432",
    })
    
    stats = resource_manager.get_statistics()
    print(f"Active resources: {stats['active_items']}")
    
    # 使用完后退出
    result = await resource_manager.disconnect("db_main")
    print(f"Tokens freed: {result.tokens_freed}")
    
    # 2. 记忆管理
    memory_manager = MemoryLifecycleManager(slot_manager)
    
    await memory_manager.store_memory("user_preferences", [
        "prefers dark mode",
        "language: zh-CN",
        "timezone: UTC+8",
    ])
    
    await memory_manager.append_memory("user_preferences", "likes concise output")
    
    result = await memory_manager.compact_memory(
        "user_preferences",
        "User prefers dark mode, Chinese language"
    )
    
    # 3. 自定义类型扩展
    custom_manager = CustomLifecycleManager(
        slot_manager=slot_manager,
        slot_type=SlotType.RESOURCE,
        type_name="MyCustomType",
    )
    
    await custom_manager.load("custom_item_1", "content here")
    result = await custom_manager.exit("custom_item_1")


# ============================================================
# 扩展新类型的步骤总结
# ============================================================
"""
扩展新类型只需3步：

1. 创建清单类（可选）
   - 继承 ContentManifest
   - 添加类型特有的配置字段

2. 创建生命周期管理器
   - 继承 BaseLifecycleManager[T]
   - 实现 _create_compact_representation()
   - 实现 _generate_summary()
   - 可选：添加类型特有方法

3. 注册到编排器
   - orchestrator.register_custom_manager("type_name", manager)
   
示例（5分钟快速实现）：

class MyTypeManager(BaseLifecycleManager[Dict]):
    def _create_compact_representation(self, name, summary, key_outputs):
        return f'<my-type name="{name}">{summary}</my-type>'
    
    def _generate_summary(self, slot):
        return f"MyType {slot.source_name}: {slot.access_count} uses"

# 使用
manager = MyTypeManager(slot_manager, SlotType.RESOURCE, "MyType", max_active=5)
await manager.load("item1", "content")
result = await manager.exit("item1")
"""