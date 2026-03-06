"""
Part版本控制和回放系统

支持Part状态的版本历史记录和回放
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy

from derisk.vis.parts import PartContainer, PartStatus, PartType, VisPart

logger = logging.getLogger(__name__)


@dataclass
class PartVersion:
    """Part版本记录"""
    version_id: str
    part_uid: str
    timestamp: datetime
    part_snapshot: Dict[str, Any]
    changes: Dict[str, Any]
    author: Optional[str] = None
    message: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class Checkpoint:
    """检查点"""
    checkpoint_id: str
    timestamp: datetime
    label: str
    description: Optional[str] = None
    container_snapshot: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PartVersionControl:
    """
    Part版本控制系统
    
    功能:
    1. 版本记录 - 记录Part的每次变化
    2. 版本回退 - 回退到指定版本
    3. 版本对比 - 对比不同版本的差异
    4. 检查点 - 创建和恢复检查点
    5. 变更历史 - 查看完整变更历史
    """
    
    def __init__(self, max_versions: int = 1000):
        """
        初始化版本控制系统
        
        Args:
            max_versions: 最大版本记录数
        """
        self.max_versions = max_versions
        
        # 版本存储
        self._versions: Dict[str, List[PartVersion]] = defaultdict(list)
        
        # 检查点存储
        self._checkpoints: List[Checkpoint] = []
        
        # 全局版本计数
        self._version_counter = 0
    
    def record_version(
        self,
        part: VisPart,
        changes: Optional[Dict[str, Any]] = None,
        author: Optional[str] = None,
        message: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        记录Part版本
        
        Args:
            part: Part实例
            changes: 变更内容
            author: 作者
            message: 提交信息
            tags: 标签
            
        Returns:
            版本ID
        """
        self._version_counter += 1
        version_id = f"v{self._version_counter}"
        
        # 创建版本记录
        version = PartVersion(
            version_id=version_id,
            part_uid=part.uid,
            timestamp=datetime.now(),
            part_snapshot=part.model_dump(),
            changes=changes or {},
            author=author,
            message=message,
            tags=tags or [],
        )
        
        self._versions[part.uid].append(version)
        
        # 限制版本数量
        if len(self._versions[part.uid]) > self.max_versions:
            self._versions[part.uid] = self._versions[part.uid][-self.max_versions:]
        
        logger.debug(f"[Version] 记录版本: {version_id} for {part.uid}")
        return version_id
    
    def get_version(self, part_uid: str, version_id: str) -> Optional[PartVersion]:
        """
        获取指定版本
        
        Args:
            part_uid: Part UID
            version_id: 版本ID
            
        Returns:
            版本记录
        """
        for version in self._versions.get(part_uid, []):
            if version.version_id == version_id:
                return version
        return None
    
    def get_history(self, part_uid: str, limit: int = 100) -> List[PartVersion]:
        """
        获取版本历史
        
        Args:
            part_uid: Part UID
            limit: 限制数量
            
        Returns:
            版本列表
        """
        return self._versions.get(part_uid, [])[-limit:]
    
    def restore_version(
        self,
        container: PartContainer,
        part_uid: str,
        version_id: str
    ) -> Optional[VisPart]:
        """
        恢复到指定版本
        
        Args:
            container: Part容器
            part_uid: Part UID
            version_id: 版本ID
            
        Returns:
            恢复的Part实例
        """
        version = self.get_version(part_uid, version_id)
        if not version:
            logger.warning(f"[Version] 版本不存在: {version_id}")
            return None
        
        # 从快照恢复Part
        restored_part = VisPart(**version.part_snapshot)
        
        # 更新容器
        container.update_part(part_uid, lambda p: restored_part)
        
        logger.info(f"[Version] 恢复版本: {version_id}")
        return restored_part
    
    def diff_versions(
        self,
        part_uid: str,
        version_id1: str,
        version_id2: str
    ) -> Dict[str, Any]:
        """
        对比两个版本
        
        Args:
            part_uid: Part UID
            version_id1: 版本1
            version_id2: 版本2
            
        Returns:
            差异字典
        """
        v1 = self.get_version(part_uid, version_id1)
        v2 = self.get_version(part_uid, version_id2)
        
        if not v1 or not v2:
            return {"error": "版本不存在"}
        
        diff = {
            "version1": version_id1,
            "version2": version_id2,
            "timestamp1": v1.timestamp.isoformat(),
            "timestamp2": v2.timestamp.isoformat(),
            "changes": {},
        }
        
        # 对比所有字段
        all_keys = set(v1.part_snapshot.keys()) | set(v2.part_snapshot.keys())
        
        for key in all_keys:
            val1 = v1.part_snapshot.get(key)
            val2 = v2.part_snapshot.get(key)
            
            if val1 != val2:
                diff["changes"][key] = {
                    "from": val1,
                    "to": val2,
                }
        
        return diff
    
    def create_checkpoint(
        self,
        container: PartContainer,
        label: str,
        description: Optional[str] = None,
        **metadata
    ) -> str:
        """
        创建检查点
        
        Args:
            container: Part容器
            label: 标签
            description: 描述
            **metadata: 元数据
            
        Returns:
            检查点ID
        """
        checkpoint_id = f"checkpoint_{len(self._checkpoints)}"
        
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            label=label,
            description=description,
            container_snapshot=[p.model_dump() for p in container],
            metadata=metadata,
        )
        
        self._checkpoints.append(checkpoint)
        
        logger.info(f"[Version] 创建检查点: {checkpoint_id} - {label}")
        return checkpoint_id
    
    def restore_checkpoint(
        self,
        container: PartContainer,
        checkpoint_id: str
    ) -> bool:
        """
        恢复检查点
        
        Args:
            container: Part容器
            checkpoint_id: 检查点ID
            
        Returns:
            是否成功
        """
        checkpoint = None
        for cp in self._checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                checkpoint = cp
                break
        
        if not checkpoint:
            logger.warning(f"[Version] 检查点不存在: {checkpoint_id}")
            return False
        
        # 清空容器
        container.clear()
        
        # 恢复快照
        for part_data in checkpoint.container_snapshot:
            part = VisPart(**part_data)
            container.add_part(part)
        
        logger.info(f"[Version] 恢复检查点: {checkpoint_id}")
        return True
    
    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """列出所有检查点"""
        return [
            {
                "checkpoint_id": cp.checkpoint_id,
                "timestamp": cp.timestamp.isoformat(),
                "label": cp.label,
                "description": cp.description,
                "part_count": len(cp.container_snapshot),
            }
            for cp in self._checkpoints
        ]


class PartReplay:
    """
    Part回放系统
    
    支持时间线回放和动画演示
    """
    
    def __init__(self):
        self._timeline: List[Tuple[datetime, str, VisPart]] = []
        self._playing = False
        self._current_index = 0
        self._speed = 1.0
    
    def record_event(
        self,
        event_type: str,
        part: VisPart
    ):
        """
        记录事件到时间线
        
        Args:
            event_type: 事件类型 (create, update, delete)
            part: Part实例
        """
        self._timeline.append((datetime.now(), event_type, part))
    
    def get_timeline(self) -> List[Dict[str, Any]]:
        """获取时间线"""
        return [
            {
                "timestamp": ts.isoformat(),
                "event_type": event_type,
                "part_uid": part.uid,
                "part_type": part.type.value if hasattr(part.type, 'value') else str(part.type),
            }
            for ts, event_type, part in self._timeline
        ]
    
    async def replay(
        self,
        container: PartContainer,
        callback: Optional[callable] = None,
        speed: float = 1.0
    ):
        """
        回放时间线
        
        Args:
            container: Part容器
            callback: 回调函数
            speed: 回放速度 (1.0 = 正常, 2.0 = 2倍速)
        """
        import asyncio
        
        self._playing = True
        self._current_index = 0
        
        logger.info(f"[Replay] 开始回放, 共 {len(self._timeline)} 个事件")
        
        for i, (ts, event_type, part) in enumerate(self._timeline):
            if not self._playing:
                logger.info("[Replay] 回放已停止")
                break
            
            self._current_index = i
            
            # 执行事件
            if event_type == "create":
                container.add_part(part)
            elif event_type == "update":
                container.update_part(part.uid, lambda p: part)
            elif event_type == "delete":
                container.remove_part(part.uid)
            
            # 回调
            if callback:
                await callback(event_type, part)
            
            # 延迟 (模拟时间流逝)
            if i < len(self._timeline) - 1:
                next_ts = self._timeline[i + 1][0]
                delay = (next_ts - ts).total_seconds() / speed
                if delay > 0:
                    await asyncio.sleep(min(delay, 1.0))  # 最大延迟1秒
        
        self._playing = False
        logger.info("[Replay] 回放完成")
    
    def stop(self):
        """停止回放"""
        self._playing = False
    
    def pause(self):
        """暂停回放"""
        self._playing = False
    
    def resume(self):
        """继续回放"""
        self._playing = True
    
    def set_speed(self, speed: float):
        """设置回放速度"""
        self._speed = max(0.1, min(10.0, speed))


# 全局版本控制实例
_version_control: Optional[PartVersionControl] = None
_replay_system: Optional[PartReplay] = None


def get_version_control() -> PartVersionControl:
    """获取全局版本控制系统"""
    global _version_control
    if _version_control is None:
        _version_control = PartVersionControl()
    return _version_control


def get_replay_system() -> PartReplay:
    """获取全局回放系统"""
    global _replay_system
    if _replay_system is None:
        _replay_system = PartReplay()
    return _replay_system