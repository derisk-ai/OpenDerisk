"""
Agent Context Integration - Agent上下文集成

展示如何在 Agent 架构中集成 ContextLifecycle 组件。

关键问题解决：
1. Skill任务完成判断 -> SkillTaskMonitor
2. Prompt注入 -> ContextAssembler
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .orchestrator import ContextLifecycleOrchestrator, create_context_lifecycle
from .context_assembler import ContextAssembler, create_context_assembler
from .skill_monitor import (
    CompletionTrigger,
    SkillTaskMonitor,
    SkillTransitionManager,
    SkillExecutionState,
)
from .skill_lifecycle import ExitTrigger

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ============================================================
# Core架构集成
# ============================================================

class CoreAgentContextIntegration:
    """
    Core架构上下文集成
    
    集成到 ExecutionEngine 和 AgentExecutor
    """
    
    def __init__(
        self,
        token_budget: int = 100000,
        max_active_skills: int = 3,
        max_tool_definitions: int = 20,
        skill_timeout: int = 600,
    ):
        # 核心组件
        self._orchestrator = create_context_lifecycle(
            token_budget=token_budget,
            max_active_skills=max_active_skills,
            max_tool_definitions=max_tool_definitions,
        )
        
        # Prompt组装器
        self._assembler: Optional[ContextAssembler] = None
        
        # Skill监控器
        self._monitor = SkillTaskMonitor(
            orchestrator=self._orchestrator,
            timeout_seconds=skill_timeout,
            auto_exit_on_marker=True,
            auto_exit_on_goal_complete=True,
        )
        
        # Skill转换管理
        self._transition = SkillTransitionManager(
            orchestrator=self._orchestrator,
            monitor=self._monitor,
        )
        
        self._session_id: Optional[str] = None
        self._current_skill: Optional[str] = None
    
    async def initialize(
        self,
        session_id: str,
        system_prompt: str = "",
    ) -> None:
        """初始化"""
        self._session_id = session_id
        await self._orchestrator.initialize(session_id=session_id)
        
        self._assembler = create_context_assembler(
            orchestrator=self._orchestrator,
            system_prompt=system_prompt,
            max_tokens=50000,
        )
        
        logger.info(f"[CoreIntegration] Initialized: {session_id}")
    
    async def load_skill(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
        goals: Optional[List[str]] = None,
    ) -> bool:
        """加载Skill"""
        try:
            await self._orchestrator.prepare_skill_context(
                skill_name=skill_name,
                skill_content=skill_content,
                required_tools=required_tools,
            )
            
            self._monitor.start_skill_monitoring(
                skill_name=skill_name,
                goals=goals,
            )
            
            self._current_skill = skill_name
            
            return True
        except Exception as e:
            logger.error(f"[CoreIntegration] Load skill failed: {e}")
            return False
    
    def assemble_prompt_context(self) -> str:
        """
        组装Prompt上下文
        
        这是注入到Prompt的关键方法
        """
        if not self._assembler:
            return ""
        
        return self._assembler.get_skill_context_for_prompt()
    
    def assemble_messages(
        self,
        user_message: str,
    ) -> List[Dict[str, str]]:
        """
        组装消息列表
        
        返回可直接传给LLM的消息格式
        """
        if not self._assembler:
            return [{"role": "user", "content": user_message}]
        
        return self._assembler.get_injection_messages(user_message)
    
    def get_tool_definitions_for_prompt(self) -> str:
        """获取工具定义（用于Prompt）"""
        if not self._assembler:
            return ""
        return self._assembler.get_tools_context_for_prompt()
    
    async def process_model_output(
        self,
        output: str,
    ) -> Optional[Dict[str, Any]]:
        """
        处理模型输出
        
        检查是否需要退出Skill，返回退出信息
        """
        if not self._current_skill:
            return None
        
        # 记录输出并检测完成信号
        check_results = self._monitor.record_output(
            skill_name=self._current_skill,
            output=output,
        )
        
        for result in check_results:
            if result.should_exit:
                exit_result = await self._orchestrator.complete_skill(
                    skill_name=self._current_skill,
                    task_summary=result.summary or "Task completed",
                    key_outputs=result.key_outputs,
                )
                
                # 停止监控
                self._monitor.stop_skill_monitoring(self._current_skill)
                
                # 检查是否需要转换到下一个Skill
                next_skill = await self._transition.handle_skill_transition(
                    self._current_skill,
                    exit_result,
                )
                
                old_skill = self._current_skill
                self._current_skill = None
                
                return {
                    "exited": True,
                    "skill_name": old_skill,
                    "exit_result": exit_result,
                    "next_skill": next_skill,
                }
        
        return None
    
    async def record_tool_call(self, tool_name: str) -> None:
        """记录工具调用"""
        if self._current_skill:
            self._monitor.record_tool_usage(
                skill_name=self._current_skill,
                tool_name=tool_name,
            )
            self._orchestrator.record_tool_usage(tool_name)
    
    async def check_auto_exit(self) -> Optional[Dict[str, Any]]:
        """
        检查是否需要自动退出
        
        用于超时等场景
        """
        if not self._current_skill:
            return None
        
        exit_result = await self._monitor.auto_exit_if_needed(self._current_skill)
        
        if exit_result:
            self._monitor.stop_skill_monitoring(self._current_skill)
            self._current_skill = None
            
            return {
                "exited": True,
                "skill_name": exit_result.skill_name,
                "exit_result": exit_result,
            }
        
        return None
    
    async def complete_skill(
        self,
        summary: str,
        key_outputs: Optional[List[str]] = None,
    ) -> bool:
        """手动完成当前Skill"""
        if not self._current_skill:
            return False
        
        await self._orchestrator.complete_skill(
            skill_name=self._current_skill,
            task_summary=summary,
            key_outputs=key_outputs,
        )
        
        self._monitor.stop_skill_monitoring(self._current_skill)
        self._current_skill = None
        
        return True
    
    def get_context_pressure(self) -> float:
        """获取上下文压力"""
        return self._orchestrator.check_context_pressure()
    
    def get_report(self) -> Dict[str, Any]:
        """获取上下文报告"""
        return self._orchestrator.get_context_report()




# ============================================================
# 使用示例
# ============================================================

async def example_core_integration():
    """
    Core架构集成示例
    """
    # 创建集成实例
    integration = CoreAgentContextIntegration(
        token_budget=50000,
        max_active_skills=2,
    )
    
    # 初始化
    await integration.initialize(
        session_id="core_example",
        system_prompt="You are a helpful coding assistant.",
    )
    
    # 加载Skill
    skill_content = """
# Code Review Skill

## Instructions
Review the code and identify issues.

## Completion
When done analyzing, output:
<task-complete>Review completed</task-complete>
"""
    
    await integration.load_skill(
        skill_name="code_review",
        skill_content=skill_content,
        required_tools=["read", "grep"],
        goals=["Analyze code structure", "Find issues"],
    )
    
    # 组装消息（注入到Prompt）
    messages = integration.assemble_messages(
        user_message="Please review the authentication module"
    )
    
    # messages 结构:
    # [
    #   {"role": "system", "content": "You are a helpful coding assistant..."},
    #   {"role": "system", "content": "# Current Skill Instructions\n\n## code_review\n\n..."},
    #   {"role": "system", "content": "# Available Tools\n\n..."},
    #   {"role": "user", "content": "Please review the authentication module"}
    # ]
    
    print("Messages for LLM:")
    for msg in messages:
        print(f"  [{msg['role']}]: {msg['content'][:50]}...")
    
    # 模拟LLM输出
    llm_outputs = [
        "Let me read the authentication file...",
        "Analyzing auth.py...",
        "Found potential SQL injection at line 45.",
        "<task-complete>Code review completed. Found 3 issues.</task-complete>",
    ]
    
    for output in llm_outputs:
        # 处理输出
        result = await integration.process_model_output(output)
        
        if result and result.get("exited"):
            print(f"\nSkill '{result['skill_name']}' exited")
            print(f"Next skill: {result.get('next_skill')}")
            break



if __name__ == "__main__":
    import asyncio
    asyncio.run(example_core_integration())
    
