"""
AgentChat 集成适配器

提供最小化改造的集成方案，将 UnifiedContextMiddleware 集成到 AgentChat
"""

from typing import Optional, Dict, Any, List
import logging

from derisk.context.unified_context_middleware import (
    UnifiedContextMiddleware,
    ContextLoadResult,
)
from derisk.agent.shared.hierarchical_context import (
    HierarchicalContextConfig,
    HierarchicalCompactionConfig,
    CompactionStrategy,
)

logger = logging.getLogger(__name__)


class AgentChatIntegration:
    """
    AgentChat 集成适配器
    
    提供统一的集成接口，最小化对原有代码的改动
    """
    
    def __init__(
        self,
        gpts_memory: Any,
        agent_file_system: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        enable_hierarchical_context: bool = True,
    ):
        self.enable_hierarchical_context = enable_hierarchical_context
        self.middleware: Optional[UnifiedContextMiddleware] = None
        
        if enable_hierarchical_context:
            self.middleware = UnifiedContextMiddleware(
                gpts_memory=gpts_memory,
                agent_file_system=agent_file_system,
                llm_client=llm_client,
                hc_config=HierarchicalContextConfig(
                    max_chapter_tokens=10000,
                    max_section_tokens=2000,
                    recent_chapters_full=2,
                    middle_chapters_index=3,
                    early_chapters_summary=5,
                ),
                compaction_config=HierarchicalCompactionConfig(
                    enabled=True,
                    strategy=CompactionStrategy.LLM_SUMMARY,
                    token_threshold=40000,
                    protect_recent_chapters=2,
                ),
            )
    
    async def initialize(self) -> None:
        """初始化集成器"""
        if self.middleware:
            await self.middleware.initialize()
            logger.info("[AgentChatIntegration] 已初始化分层上下文集成")
    
    async def load_historical_context(
        self,
        conv_id: str,
        task_description: str,
        include_worklog: bool = True,
    ) -> Optional[ContextLoadResult]:
        """
        加载历史上下文
        
        Args:
            conv_id: 会话ID
            task_description: 任务描述
            include_worklog: 是否包含 WorkLog
            
        Returns:
            上下文加载结果，如果未启用则返回 None
        """
        if not self.middleware:
            return None
        
        try:
            result = await self.middleware.load_context(
                conv_id=conv_id,
                task_description=task_description,
                include_worklog=include_worklog,
                token_budget=12000,
            )
            
            logger.info(
                f"[AgentChatIntegration] 已加载历史上下文: {conv_id[:8]}, "
                f"chapters={result.stats.get('chapter_count', 0)}, "
                f"sections={result.stats.get('section_count', 0)}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[AgentChatIntegration] 加载上下文失败: {e}", exc_info=True)
            return None
    
    async def inject_to_agent(
        self,
        agent: Any,
        context_result: ContextLoadResult,
    ) -> None:
        """
        注入上下文到 Agent
        
        Args:
            agent: Agent 实例
            context_result: 上下文加载结果
        """
        if not context_result:
            return
        
        # 注入回溯工具
        if context_result.recall_tools:
            self._inject_recall_tools(agent, context_result.recall_tools)
        
        # 注入分层上下文到系统提示
        if context_result.hierarchical_context_text:
            self._inject_hierarchical_context_to_prompt(
                agent,
                context_result.hierarchical_context_text,
            )
        
        # 设置历史消息
        if context_result.recent_messages:
            if hasattr(agent, 'history_messages'):
                agent.history_messages = context_result.recent_messages
    
    def _inject_recall_tools(
        self,
        agent: Any,
        recall_tools: List[Any],
    ) -> None:
        """注入回溯工具到 Agent"""
        
        if not recall_tools:
            return
        
        logger.info(f"[AgentChatIntegration] 注入 {len(recall_tools)} 个回溯工具")
        
        # Core V1: ConversableAgent
        if hasattr(agent, 'available_system_tools'):
            for tool in recall_tools:
                agent.available_system_tools[tool.name] = tool
                logger.debug(f"[AgentChatIntegration] 注入工具: {tool.name}")
        
        # Core V2: AgentBase
        elif hasattr(agent, 'tools') and hasattr(agent.tools, 'register'):
            for tool in recall_tools:
                try:
                    agent.tools.register(tool)
                    logger.debug(f"[AgentChatIntegration] 注册工具: {tool.name}")
                except Exception as e:
                    logger.warning(f"[AgentChatIntegration] 注册工具失败: {e}")
    
    def _inject_hierarchical_context_to_prompt(
        self,
        agent: Any,
        hierarchical_context: str,
    ) -> None:
        """注入分层上下文到系统提示"""
        
        if not hierarchical_context:
            return
        
        try:
            from derisk.agent.shared.hierarchical_context import (
                integrate_hierarchical_context_to_prompt,
            )
            
            # 方式1：直接修改系统提示
            if hasattr(agent, 'system_prompt'):
                original_prompt = agent.system_prompt or ""
                
                integrated_prompt = integrate_hierarchical_context_to_prompt(
                    original_system_prompt=original_prompt,
                    hierarchical_context=hierarchical_context,
                )
                
                agent.system_prompt = integrated_prompt
                logger.info("[AgentChatIntegration] 已注入分层上下文到系统提示")
            
            # 方式2：通过 register_variables（ReActMasterAgent）
            elif hasattr(agent, 'register_variables'):
                agent.register_variables(
                    hierarchical_context=hierarchical_context,
                )
                logger.info("[AgentChatIntegration] 已通过 register_variables 注入上下文")
                
        except Exception as e:
            logger.warning(f"[AgentChatIntegration] 注入上下文失败: {e}")
    
    async def record_step(
        self,
        conv_id: str,
        action_out: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """记录执行步骤"""
        if not self.middleware:
            return None
        
        return await self.middleware.record_step(
            conv_id=conv_id,
            action_out=action_out,
            metadata=metadata,
        )
    
    async def cleanup(self, conv_id: str) -> None:
        """清理上下文"""
        if self.middleware:
            await self.middleware.cleanup_context(conv_id)
    
    def get_statistics(self, conv_id: str) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.middleware:
            return {"error": "Hierarchical context not enabled"}
        
        return self.middleware.get_statistics(conv_id)
    
    def set_file_system(self, file_system: Any) -> None:
        """设置文件系统"""
        if self.middleware:
            self.middleware.file_system = file_system