"""
Tool Lifecycle Manager - 工具生命周期管理器

管理工具定义的按需加载和卸载。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .slot_manager import (
    ContextSlot,
    ContextSlotManager,
    EvictionPolicy,
    SlotType,
)

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """工具类别"""
    SYSTEM = "system"
    BUILTIN = "builtin"
    MCP = "mcp"
    CUSTOM = "custom"
    INTERACTION = "interaction"


@dataclass
class ToolManifest:
    """工具清单"""
    name: str
    category: ToolCategory
    description: str = ""
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    auto_load: bool = False
    load_priority: int = 5
    dependencies: List[str] = field(default_factory=list)
    dangerous: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "auto_load": self.auto_load,
            "load_priority": self.load_priority,
        }


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
        context_slot_manager: ContextSlotManager,
        max_tool_definitions: int = 20,
    ):
        self._slot_manager = context_slot_manager
        self._max_tool_definitions = max_tool_definitions
        
        self._tool_manifests: Dict[str, ToolManifest] = {}
        self._loaded_tools: Set[str] = set(self.DEFAULT_ALWAYS_LOADED)
        self._tool_usage: Dict[str, int] = {}
        self._tool_results: Dict[str, Dict[str, Any]] = {}
    
    def register_manifest(self, manifest: ToolManifest) -> None:
        """注册工具清单"""
        self._tool_manifests[manifest.name] = manifest
        logger.debug(f"[ToolLifecycle] Registered manifest: {manifest.name}")
    
    def register_manifests(self, manifests: List[ToolManifest]) -> None:
        """批量注册工具清单"""
        for manifest in manifests:
            self.register_manifest(manifest)
    
    async def ensure_tools_loaded(
        self,
        tool_names: List[str],
    ) -> Dict[str, bool]:
        """确保指定工具已加载"""
        results = {}
        tools_to_load = []
        
        for name in tool_names:
            if name in self._loaded_tools:
                results[name] = True
            else:
                tools_to_load.append(name)
        
        if not tools_to_load:
            return results
        
        projected_count = len(self._loaded_tools) + len(tools_to_load)
        if projected_count > self._max_tool_definitions:
            await self._evict_unused_tools(
                count=projected_count - self._max_tool_definitions
            )
        
        for name in tools_to_load:
            loaded = await self._load_tool_definition(name)
            results[name] = loaded
        
        return results
    
    async def _load_tool_definition(self, tool_name: str) -> bool:
        """加载工具定义到上下文"""
        manifest = self._tool_manifests.get(tool_name)
        
        if not manifest:
            slot = self._slot_manager.get_slot_by_name(tool_name, SlotType.TOOL)
            if slot:
                self._loaded_tools.add(tool_name)
                return True
            logger.warning(f"[ToolLifecycle] Tool '{tool_name}' manifest not found")
            return False
        
        content = self._format_tool_definition(manifest)
        
        is_system = manifest.category == ToolCategory.SYSTEM
        
        slot = await self._slot_manager.allocate(
            slot_type=SlotType.TOOL,
            content=content,
            source_name=tool_name,
            metadata={"category": manifest.category.value},
            eviction_policy=EvictionPolicy.LFU,
            priority=manifest.load_priority,
            sticky=is_system,
        )
        
        self._loaded_tools.add(tool_name)
        logger.debug(f"[ToolLifecycle] Loaded tool: {tool_name}")
        
        return True
    
    def _format_tool_definition(self, manifest: ToolManifest) -> str:
        """格式化工具定义为紧凑形式"""
        desc = manifest.description[:200] if manifest.description else ""
        
        return json.dumps({
            "name": manifest.name,
            "description": desc,
            "parameters": manifest.parameters_schema,
            "dangerous": manifest.dangerous,
        }, ensure_ascii=False)
    
    async def unload_tools(
        self,
        tool_names: List[str],
        keep_system: bool = True,
    ) -> List[str]:
        """卸载工具"""
        unloaded = []
        
        for name in tool_names:
            if keep_system and name in self.DEFAULT_ALWAYS_LOADED:
                continue
            
            manifest = self._tool_manifests.get(name)
            if keep_system and manifest and manifest.category == ToolCategory.SYSTEM:
                continue
            
            if name in self._loaded_tools:
                await self._slot_manager.evict(
                    slot_type=SlotType.TOOL,
                    source_name=name,
                )
                self._loaded_tools.discard(name)
                unloaded.append(name)
        
        if unloaded:
            logger.info(f"[ToolLifecycle] Unloaded tools: {unloaded}")
        
        return unloaded
    
    async def unload_unused_tools(
        self,
        keep_used: bool = True,
        usage_threshold: int = 1,
    ) -> List[str]:
        """卸载不常用的工具"""
        candidates = []
        
        for name in self._loaded_tools:
            if name in self.DEFAULT_ALWAYS_LOADED:
                continue
            
            manifest = self._tool_manifests.get(name)
            if manifest and manifest.category == ToolCategory.SYSTEM:
                continue
            
            usage = self._tool_usage.get(name, 0)
            if keep_used and usage >= usage_threshold:
                continue
            
            candidates.append((name, usage))
        
        candidates.sort(key=lambda x: x[1])
        to_unload = [c[0] for c in candidates]
        
        return await self.unload_tools(to_unload, keep_system=True)
    
    async def _evict_unused_tools(self, count: int):
        """驱逐不常用的工具"""
        candidates = [
            name for name in self._loaded_tools
            if name not in self.DEFAULT_ALWAYS_LOADED
        ]
        
        manifests = self._tool_manifests
        candidates = [
            n for n in candidates
            if manifests.get(n, ToolCategory.CUSTOM) != ToolCategory.SYSTEM
        ]
        
        candidates.sort(key=lambda x: self._tool_usage.get(x, 0))
        
        to_evict = candidates[:count]
        await self.unload_tools(to_evict, keep_system=False)
    
    def record_tool_usage(self, tool_name: str) -> None:
        """记录工具使用"""
        self._tool_usage[tool_name] = self._tool_usage.get(tool_name, 0) + 1
    
    def record_tool_result(
        self,
        tool_name: str,
        result: Dict[str, Any],
    ) -> None:
        """记录工具执行结果"""
        self._tool_results[tool_name] = result
        self.record_tool_usage(tool_name)
    
    def get_loaded_tools(self) -> Set[str]:
        """获取已加载的工具列表"""
        return self._loaded_tools.copy()
    
    def get_tool_usage_stats(self) -> Dict[str, int]:
        """获取工具使用统计"""
        return self._tool_usage.copy()
    
    def get_tool_result(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取工具执行结果"""
        return self._tool_results.get(tool_name)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "loaded_count": len(self._loaded_tools),
            "max_tools": self._max_tool_definitions,
            "total_manifests": len(self._tool_manifests),
            "usage_stats": dict(sorted(
                self._tool_usage.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
        }
    
    def set_max_tools(self, max_tools: int) -> None:
        """设置最大工具数量"""
        self._max_tool_definitions = max_tools
    
    def get_always_loaded_tools(self) -> Set[str]:
        """获取常驻工具列表"""
        return self.DEFAULT_ALWAYS_LOADED.copy()
    
    def add_always_loaded_tool(self, tool_name: str) -> None:
        """添加常驻工具"""
        self.DEFAULT_ALWAYS_LOADED.add(tool_name)
    
    def remove_always_loaded_tool(self, tool_name: str) -> None:
        """移除常驻工具"""
        self.DEFAULT_ALWAYS_LOADED.discard(tool_name)