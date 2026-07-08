"""PR 5 Level 5: 权限决策检查点存储 + replay。

V1 已有 RecoveryCoordinator.create_interaction_checkpoint（保存 InteractionRequest），
但没有"权限决策 replay"——即"上次用户对相同 (conv_id, tool_name, input_hash) 的决策是 allow，
本次直接复用，不再问"。

本模块补这个能力：
- save_checkpoint: ASK 决策后落 StateStore
- load_checkpoint: 下次相同输入时先查 store，命中则复用决策

存储抽象复用 V1 的 StateStore（MemoryStateStore / 未来 RedisStateStore），
不引入新依赖。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from derisk.agent.interaction.interaction_gateway import (
    MemoryStateStore,
    StateStore,
)

logger = logging.getLogger(__name__)


@dataclass
class PermissionCheckpoint:
    """单条权限决策检查点。"""
    conv_id: str
    tool_name: str
    input_hash: str
    decision: str  # "allow" | "deny"
    reason: Optional[str] = None
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionCheckpoint":
        return cls(
            conv_id=data["conv_id"],
            tool_name=data["tool_name"],
            input_hash=data["input_hash"],
            decision=data["decision"],
            reason=data.get("reason"),
            timestamp=data.get("timestamp", 0.0),
        )


def hash_tool_input(tool_input: Dict[str, Any]) -> str:
    """对 tool_input 计算稳定 hash（sorted keys + JSON serialize）。

    相同 input → 相同 hash；不同 key 顺序 → 相同 hash（sort_keys=True）。
    """
    if not tool_input:
        return "empty"
    try:
        serialized = json.dumps(tool_input, sort_keys=True, default=str)
    except (TypeError, ValueError):
        # 兜底：fallback 到 str
        serialized = str(tool_input)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


class PermissionCheckpointStore:
    """权限决策检查点存储：落 StateStore，会话 resume 时 replay。

    Usage:
        store = PermissionCheckpointStore(state_store=MemoryStateStore())
        # ASK 后保存
        await store.save_checkpoint("conv1", "execute_sql", hash_tool_input({"sql": "..."}), "allow")
        # 下次相同输入查 store
        cp = await store.load_checkpoint("conv1", "execute_sql", hash_tool_input({"sql": "..."}))
        if cp:
            return cp.decision == "allow"
    """

    KEY_PREFIX = "perm_cp"

    def __init__(self, state_store: Optional[StateStore] = None):
        self._store = state_store or MemoryStateStore()

    def _key(self, conv_id: str, tool_name: str, input_hash: str) -> str:
        return f"{self.KEY_PREFIX}:{conv_id}:{tool_name}:{input_hash}"

    def _index_key(self, conv_id: str) -> str:
        return f"{self.KEY_PREFIX}:index:{conv_id}"

    async def save_checkpoint(
        self,
        conv_id: str,
        tool_name: str,
        input_hash: str,
        decision: str,
        reason: Optional[str] = None,
    ) -> None:
        """保存一条权限决策。同 (conv_id, tool_name, input_hash) 覆盖。"""
        if not conv_id or not tool_name:
            return
        checkpoint = PermissionCheckpoint(
            conv_id=conv_id,
            tool_name=tool_name,
            input_hash=input_hash,
            decision=decision,
            reason=reason,
            timestamp=time.time(),
        )
        key = self._key(conv_id, tool_name, input_hash)
        try:
            await self._store.set(key, checkpoint.to_dict())
            # 维护 conv_id 索引（便于 list_checkpoints / clear）
            index = await self._get_index(conv_id)
            entry = f"{tool_name}:{input_hash}"
            if entry not in index:
                index.append(entry)
                await self._store.set(self._index_key(conv_id), {"entries": index})
        except Exception as e:
            logger.warning(
                f"[perm-cp] failed to save checkpoint conv={conv_id} "
                f"tool={tool_name}: {e}"
            )

    async def load_checkpoint(
        self,
        conv_id: str,
        tool_name: str,
        input_hash: str,
    ) -> Optional[PermissionCheckpoint]:
        """查 checkpoint。命中返回对象，未命中返回 None。"""
        if not conv_id or not tool_name:
            return None
        key = self._key(conv_id, tool_name, input_hash)
        try:
            data = await self._store.get(key)
        except Exception as e:
            logger.warning(
                f"[perm-cp] failed to load checkpoint conv={conv_id} "
                f"tool={tool_name}: {e}"
            )
            return None
        if data is None:
            return None
        try:
            return PermissionCheckpoint.from_dict(data)
        except Exception as e:
            logger.warning(
                f"[perm-cp] corrupted checkpoint at {key}: {e}"
            )
            return None

    async def list_checkpoints(self, conv_id: str) -> List[PermissionCheckpoint]:
        """列出 conv_id 下所有 checkpoint（用于调试 / 审计）。"""
        if not conv_id:
            return []
        index = await self._get_index(conv_id)
        result: List[PermissionCheckpoint] = []
        for entry in index:
            parts = entry.split(":", 1)
            if len(parts) != 2:
                continue
            tool_name, input_hash = parts
            cp = await self.load_checkpoint(conv_id, tool_name, input_hash)
            if cp is not None:
                result.append(cp)
        return result

    async def clear(self, conv_id: str) -> None:
        """清空 conv_id 下所有 checkpoint。"""
        if not conv_id:
            return
        index = await self._get_index(conv_id)
        for entry in index:
            parts = entry.split(":", 1)
            if len(parts) != 2:
                continue
            tool_name, input_hash = parts
            key = self._key(conv_id, tool_name, input_hash)
            try:
                await self._store.delete(key)
            except Exception as e:
                logger.warning(
                    f"[perm-cp] failed to delete {key}: {e}"
                )
        try:
            await self._store.delete(self._index_key(conv_id))
        except Exception:
            pass

    async def _get_index(self, conv_id: str) -> List[str]:
        try:
            data = await self._store.get(self._index_key(conv_id))
        except Exception:
            return []
        if data is None:
            return []
        return list(data.get("entries", []))
