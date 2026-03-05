"""
V1ContextAdapter - Core V1 上下文适配器

将 SharedSessionContext 集成到 Core V1 (ConversableAgent) 架构中。

核心职责：
1. 共享组件注入到 ConversableAgent
2. 工具输出自动归档
3. 任务管理工具集成
4. 上下文生命周期联动
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from derisk.agent.shared.context import SharedSessionContext

if TYPE_CHECKING:
    from derisk.agent.core.base_agent import ConversableAgent
    from derisk.agent.expand.react_master_agent.truncation import Truncator

logger = logging.getLogger(__name__)


class V1ContextAdapter:
    """
    Core V1 上下文适配器
    
    将 SharedSessionContext 适配到 Core V1 的 ConversableAgent。
    
    使用示例：
        # 创建共享上下文
        shared_ctx = await SharedSessionContext.create(
            session_id="session_001",
            conv_id="conv_001",
        )
        
        # 创建适配器
        adapter = V1ContextAdapter(shared_ctx)
        
        # 集成到 Agent
        agent = ConversableAgent(agent_info=agent_info)
        await adapter.integrate_with_agent(agent)
    
    功能：
    - 注入 AgentFileSystem 到 Agent
    - 注入 Truncator 用于工具输出截断
    - 注入 KanbanManager 用于任务管理
    - 提供 Todo/Kanban 工具
    """
    
    def __init__(self, shared_context: SharedSessionContext):
        self.shared = shared_context
        
        self.agent_file_system = shared_context.file_system
        self.task_board = shared_context.task_board
        self.archiver = shared_context.archiver
    
    @property
    def session_id(self) -> str:
        return self.shared.session_id
    
    @property
    def conv_id(self) -> str:
        return self.shared.conv_id
    
    async def integrate_with_agent(
        self,
        agent: "ConversableAgent",
        enable_truncation: bool = True,
        max_output_chars: int = 8000,
    ) -> None:
        """
        集成到 ConversableAgent
        
        Args:
            agent: ConversableAgent 实例
            enable_truncation: 是否启用输出截断
            max_output_chars: 最大输出字符数
        """
        agent._agent_file_system = self.agent_file_system
        agent._shared_context = self.shared
        
        if self.task_board:
            agent._kanban_manager = self.task_board
            agent._task_board = self.task_board
        
        if enable_truncation and self.agent_file_system:
            try:
                from derisk.agent.expand.react_master_agent.truncation import Truncator
                
                truncator = Truncator(
                    max_output_chars=max_output_chars,
                    agent_file_system=self.agent_file_system,
                )
                agent._truncator = truncator
                logger.info(f"[V1Adapter] Truncator enabled with max={max_output_chars}")
            except ImportError:
                logger.warning("[V1Adapter] Truncator not available")
        
        logger.info(
            f"[V1Adapter] Integrated with agent: "
            f"file_system=✓, task_board={'✓' if self.task_board else '✗'}, "
            f"archiver={'✓' if self.archiver else '✗'}"
        )
    
    async def process_tool_output(
        self,
        tool_name: str,
        output: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """处理工具输出，按需归档"""
        if self.archiver:
            return await self.archiver.process_tool_output(
                tool_name=tool_name,
                output=output,
                metadata=metadata,
            )
        return {"content": str(output), "archived": False}
    
    async def truncate_output(
        self,
        output: str,
        tool_name: str,
        max_chars: int = 8000,
    ) -> str:
        """截断大输出"""
        if len(output) <= max_chars:
            return output
        
        if self.archiver:
            result = await self.archiver.process_tool_output(
                tool_name=tool_name,
                output=output,
                metadata={"original_size": len(output)},
            )
            return result.get("content", output[:max_chars])
        
        return output[:max_chars] + f"\n\n... [截断，共 {len(output)} 字符]"
    
    def get_context_for_llm(self) -> Dict[str, Any]:
        """获取供 LLM 使用的上下文信息"""
        context = {
            "session_id": self.session_id,
            "conv_id": self.conv_id,
        }
        
        return context
    
    async def get_task_status_for_prompt(self) -> str:
        """获取任务状态供 prompt 使用"""
        if self.task_board:
            return await self.task_board.get_status_report()
        return ""
    
    async def create_todo_tool_func(self) -> callable:
        """创建 Todo 工具函数"""
        async def create_todo(
            title: str,
            description: str = "",
            priority: str = "medium",
        ) -> str:
            from derisk.agent.shared.task_board import TaskPriority
            
            priority_map = {
                "critical": TaskPriority.CRITICAL,
                "high": TaskPriority.HIGH,
                "medium": TaskPriority.MEDIUM,
                "low": TaskPriority.LOW,
            }
            
            task = await self.task_board.create_todo(
                title=title,
                description=description,
                priority=priority_map.get(priority, TaskPriority.MEDIUM),
            )
            return f"Created todo: {task.id} - {task.title}"
        
        return create_todo
    
    async def update_todo_tool_func(self) -> callable:
        """创建更新 Todo 状态的工具函数"""
        async def update_todo(
            task_id: str,
            status: str,
            progress: Optional[float] = None,
        ) -> str:
            from derisk.agent.shared.task_board import TaskStatus
            
            status_map = {
                "pending": TaskStatus.PENDING,
                "working": TaskStatus.WORKING,
                "completed": TaskStatus.COMPLETED,
                "failed": TaskStatus.FAILED,
            }
            
            task = await self.task_board.update_todo_status(
                task_id=task_id,
                status=status_map.get(status, TaskStatus.PENDING),
                progress=progress,
            )
            
            if task:
                return f"Updated todo: {task.id} -> {task.status.value}"
            return f"Todo not found: {task_id}"
        
        return update_todo
    
    async def create_kanban_tool_func(self) -> callable:
        """创建 Kanban 工具函数"""
        async def create_kanban(
            mission: str,
            stages_json: str,
        ) -> str:
            import json
            
            try:
                stages = json.loads(stages_json)
            except json.JSONDecodeError:
                return "Error: Invalid JSON for stages"
            
            result = await self.task_board.create_kanban(
                mission=mission,
                stages=stages,
            )
            
            if result.get("status") == "success":
                return f"Kanban created: {result.get('kanban_id')}"
            return f"Error: {result.get('message')}"
        
        return create_kanban
    
    async def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取工具定义列表"""
        tools = []
        
        if self.task_board:
            tools.extend([
                {
                    "name": "create_todo",
                    "description": "创建一个新的 Todo 任务项",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "任务标题"},
                            "description": {"type": "string", "description": "任务描述"},
                            "priority": {
                                "type": "string",
                                "enum": ["critical", "high", "medium", "low"],
                                "description": "优先级",
                            },
                        },
                        "required": ["title"],
                    },
                    "func": await self.create_todo_tool_func(),
                },
                {
                    "name": "update_todo",
                    "description": "更新 Todo 任务状态",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string", "description": "任务ID"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "working", "completed", "failed"],
                                "description": "新状态",
                            },
                            "progress": {"type": "number", "description": "进度 (0-1)"},
                        },
                        "required": ["task_id", "status"],
                    },
                    "func": await self.update_todo_tool_func(),
                },
                {
                    "name": "create_kanban",
                    "description": "创建 Kanban 看板管理复杂任务",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mission": {"type": "string", "description": "任务使命"},
                            "stages_json": {
                                "type": "string",
                                "description": "阶段列表 JSON，如 [{\"stage_id\":\"s1\",\"description\":\"阶段1\"}]",
                            },
                        },
                        "required": ["mission", "stages_json"],
                    },
                    "func": await self.create_kanban_tool_func(),
                },
            ])
        
        return tools
    
    async def handle_context_pressure(
        self,
        current_tokens: int,
        budget_tokens: int,
    ) -> Dict[str, Any]:
        """处理上下文压力"""
        if not self.archiver:
            return {"action": "none", "reason": "Archiver not available"}
        
        archived = await self.archiver.auto_archive_for_pressure(
            current_tokens=current_tokens,
            budget_tokens=budget_tokens,
        )
        
        return {
            "action": "auto_archive",
            "archived_count": len(archived),
            "archives": archived,
        }
    
    async def close(self):
        """清理资源"""
        await self.shared.close()


async def create_v1_adapter(
    shared_context: SharedSessionContext,
) -> V1ContextAdapter:
    return V1ContextAdapter(shared_context)


__all__ = [
    "V1ContextAdapter",
    "create_v1_adapter",
]