"""
SharedSessionContext - 统一会话上下文容器

作为 Core V1 和 Core V2 的共享基础设施，提供：
1. AgentFileSystem - 统一文件管理
2. TaskBoardManager - Todo/Kanban 任务管理
3. ContextArchiver - 上下文自动归档

设计原则：
- 统一资源平面：所有基础数据存储管理使用同一套组件
- 架构无关：不依赖特定 Agent 架构实现
- 会话隔离：每个会话独立管理资源
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem
    from derisk.agent.core.memory.gpts import GptsMemory
    from derisk.agent.core.memory.gpts.file_base import KanbanStorage

from derisk.agent.shared.context_archiver import ContextArchiver, create_context_archiver
from derisk.agent.shared.task_board import TaskBoardManager, create_task_board_manager

logger = logging.getLogger(__name__)


@dataclass
class SharedContextConfig:
    """共享上下文配置"""
    archive_threshold_tokens: int = 2000
    auto_archive: bool = True
    exploration_limit: int = 3
    
    enable_task_board: bool = True
    enable_archiver: bool = True
    
    file_system_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedSessionContext:
    """
    统一会话上下文容器 - Core V1 和 V2 共享
    
    核心组件：
    - file_system: AgentFileSystem 实例
    - task_board: TaskBoardManager 实例
    - archiver: ContextArchiver 实例
    
    使用示例：
        # 创建共享上下文
        ctx = await SharedSessionContext.create(
            session_id="session_001",
            conv_id="conv_001",
            gpts_memory=gpts_memory,
        )
        
        # 访问组件
        await ctx.file_system.save_file(...)
        await ctx.task_board.create_todo(...)
        result = await ctx.archiver.process_tool_output(...)
        
        # 清理
        await ctx.close()
    
    设计原则：
    - 组件懒加载：按需初始化各组件
    - 资源统一管理：所有文件/任务/归档统一管理
    - 会话生命周期：与 Agent 会话绑定
    """
    
    session_id: str
    conv_id: str
    
    file_system: Optional["AgentFileSystem"] = None
    task_board: Optional["TaskBoardManager"] = None
    archiver: Optional["ContextArchiver"] = None
    
    gpts_memory: Optional["GptsMemory"] = None
    kanban_storage: Optional["KanbanStorage"] = None
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    config: SharedContextConfig = field(default_factory=SharedContextConfig)
    
    _initialized: bool = field(default=False, repr=False)
    
    @classmethod
    async def create(
        cls,
        session_id: str,
        conv_id: str,
        gpts_memory: Optional["GptsMemory"] = None,
        file_storage_client: Optional[Any] = None,
        kanban_storage: Optional["KanbanStorage"] = None,
        config: Optional[SharedContextConfig] = None,
        sandbox: Optional[Any] = None,
    ) -> "SharedSessionContext":
        from derisk.agent.core.file_system.agent_file_system import AgentFileSystem
        
        config = config or SharedContextConfig()
        
        file_system = AgentFileSystem(
            conv_id=conv_id,
            session_id=session_id,
            file_storage_client=file_storage_client,
            metadata_storage=gpts_memory,
            sandbox=sandbox,
            **config.file_system_config,
        )
        
        task_board = None
        if config.enable_task_board:
            task_board = await create_task_board_manager(
                session_id=session_id,
                agent_id=conv_id,
                file_system=file_system,
                kanban_storage=kanban_storage or gpts_memory,
                exploration_limit=config.exploration_limit,
            )
        
        archiver = None
        if config.enable_archiver:
            archiver = await create_context_archiver(
                file_system=file_system,
                config={
                    "threshold_tokens": config.archive_threshold_tokens,
                    "auto_archive": config.auto_archive,
                },
            )
        
        ctx = cls(
            session_id=session_id,
            conv_id=conv_id,
            file_system=file_system,
            task_board=task_board,
            archiver=archiver,
            gpts_memory=gpts_memory,
            kanban_storage=kanban_storage,
            config=config,
        )
        ctx._initialized = True
        
        logger.info(
            f"[SharedContext] Created for session={session_id}, "
            f"file_system=✓, task_board={'✓' if task_board else '✗'}, "
            f"archiver={'✓' if archiver else '✗'}"
        )
        
        return ctx
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    async def get_file_system(self) -> "AgentFileSystem":
        if self.file_system is None:
            raise RuntimeError("File system not initialized")
        return self.file_system
    
    async def get_task_board(self) -> "TaskBoardManager":
        if self.task_board is None:
            if self.config.enable_task_board:
                self.task_board = await create_task_board_manager(
                    session_id=self.session_id,
                    agent_id=self.conv_id,
                    file_system=self.file_system,
                    kanban_storage=self.kanban_storage or self.gpts_memory,
                )
            else:
                raise RuntimeError("Task board is disabled in config")
        return self.task_board
    
    async def get_archiver(self) -> "ContextArchiver":
        if self.archiver is None:
            if self.config.enable_archiver:
                self.archiver = await create_context_archiver(
                    file_system=self.file_system,
                    config={
                        "threshold_tokens": self.config.archive_threshold_tokens,
                        "auto_archive": self.config.auto_archive,
                    },
                )
            else:
                raise RuntimeError("Archiver is disabled in config")
        return self.archiver
    
    async def process_tool_output(
        self,
        tool_name: str,
        output: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.archiver:
            return await self.archiver.process_tool_output(
                tool_name=tool_name,
                output=output,
                metadata=metadata,
            )
        return {"content": str(output), "archived": False}
    
    async def create_todo(
        self,
        title: str,
        description: str = "",
        **kwargs,
    ):
        task_board = await self.get_task_board()
        from derisk.agent.shared.task_board import TaskPriority
        return await task_board.create_todo(
            title=title,
            description=description,
            priority=kwargs.pop("priority", TaskPriority.MEDIUM),
            **kwargs,
        )
    
    async def get_task_status_report(self) -> str:
        if self.task_board:
            return await self.task_board.get_status_report()
        return "Task board not enabled"
    
    async def save_file(
        self,
        file_key: str,
        data: Any,
        file_type: str = "tool_output",
        **kwargs,
    ):
        from derisk.agent.core.memory.gpts import FileType
        
        file_type_enum = FileType.TOOL_OUTPUT
        if isinstance(file_type, str):
            type_map = {
                "tool_output": FileType.TOOL_OUTPUT,
                "conclusion": FileType.CONCLUSION,
                "deliverable": FileType.DELIVERABLE,
                "kanban": FileType.KANBAN,
                "truncated": FileType.TRUNCATED_OUTPUT,
            }
            file_type_enum = type_map.get(file_type, FileType.TOOL_OUTPUT)
        
        return await self.file_system.save_file(
            file_key=file_key,
            data=data,
            file_type=file_type_enum,
            **kwargs,
        )
    
    async def read_file(self, file_key: str) -> Optional[str]:
        return await self.file_system.read_file(file_key)
    
    def get_statistics(self) -> Dict[str, Any]:
        stats = {
            "session_id": self.session_id,
            "conv_id": self.conv_id,
            "created_at": self.created_at,
            "initialized": self._initialized,
            "components": {
                "file_system": self.file_system is not None,
                "task_board": self.task_board is not None,
                "archiver": self.archiver is not None,
            },
        }
        
        if self.task_board:
            stats["task_board"] = {
                "todos": len(self.task_board._todos),
                "has_kanban": self.task_board._kanban is not None,
            }
        
        if self.archiver:
            stats["archiver"] = self.archiver.get_statistics()
        
        return stats
    
    async def export_context(self) -> Dict[str, Any]:
        manifest = {
            "session_id": self.session_id,
            "conv_id": self.conv_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        
        if self.archiver:
            manifest["archives"] = await self.archiver.export_archives_manifest()
        
        if self.task_board:
            manifest["task_board"] = {
                "todos": {
                    tid: t.to_dict() for tid, t in self.task_board._todos.items()
                },
                "kanban": self.task_board._kanban.to_dict() if self.task_board._kanban else None,
            }
        
        return manifest
    
    async def close(self):
        if self.task_board:
            await self.task_board.close()
        
        logger.info(f"[SharedContext] Closed session={self.session_id}")
    
    async def __aenter__(self) -> "SharedSessionContext":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


async def create_shared_context(
    session_id: str,
    conv_id: str,
    gpts_memory: Optional["GptsMemory"] = None,
    config: Optional[SharedContextConfig] = None,
    **kwargs,
) -> SharedSessionContext:
    return await SharedSessionContext.create(
        session_id=session_id,
        conv_id=conv_id,
        gpts_memory=gpts_memory,
        config=config,
        **kwargs,
    )


__all__ = [
    "SharedSessionContext",
    "SharedContextConfig",
    "create_shared_context",
]