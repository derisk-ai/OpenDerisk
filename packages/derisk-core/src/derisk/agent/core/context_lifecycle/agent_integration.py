"""
Agent Context Integration - Agent上下文集成

展示如何在core和corev2架构中集成ContextLifecycle组件。

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
# CoreV2架构集成
# ============================================================

class CoreV2AgentContextIntegration:
    """
    CoreV2架构上下文集成
    
    集成到 AgentHarness 和 AgentBase
    """
    
    def __init__(
        self,
        token_budget: int = 100000,
        max_active_skills: int = 3,
        skill_timeout: int = 600,
    ):
        self._orchestrator = create_context_lifecycle(
            token_budget=token_budget,
            max_active_skills=max_active_skills,
        )
        
        self._assembler: Optional[ContextAssembler] = None
        self._monitor = SkillTaskMonitor(
            orchestrator=self._orchestrator,
            timeout_seconds=skill_timeout,
        )
        self._transition = SkillTransitionManager(
            orchestrator=self._orchestrator,
            monitor=self._monitor,
        )
        
        self._session_id: Optional[str] = None
        self._current_skill: Optional[str] = None
        self._execution_context: Dict[str, Any] = {}
    
    async def attach_to_harness(self, harness: Any) -> None:
        """
        附加到AgentHarness
        
        注入上下文管理能力
        """
        harness.set_context_lifecycle(self._orchestrator)
        
        if hasattr(harness, '_context_integration'):
            harness._context_integration = self
        
        logger.info("[CoreV2Integration] Attached to harness")
    
    async def initialize(
        self,
        session_id: str,
        system_prompt: str = "",
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化"""
        self._session_id = session_id
        self._execution_context = execution_context or {}
        
        await self._orchestrator.initialize(session_id=session_id)
        
        self._assembler = create_context_assembler(
            orchestrator=self._orchestrator,
            system_prompt=system_prompt,
        )
        
        logger.info(f"[CoreV2Integration] Initialized: {session_id}")
    
    async def prepare_execution(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
        skill_goals: Optional[List[str]] = None,
        skill_sequence: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        准备执行环境
        
        返回组装好的上下文信息
        """
        # 加载Skill
        await self._orchestrator.prepare_skill_context(
            skill_name=skill_name,
            skill_content=skill_content,
            required_tools=required_tools,
        )
        
        # 设置监控
        self._monitor.start_skill_monitoring(
            skill_name=skill_name,
            goals=skill_goals,
        )
        
        # 设置Skill序列（如果提供）
        if skill_sequence:
            self._transition.set_skill_sequence(skill_sequence)
        
        self._current_skill = skill_name
        
        # 组装上下文
        context = self._assemble_execution_context()
        
        return context
    
    def _assemble_execution_context(self) -> Dict[str, Any]:
        """组装执行上下文"""
        if not self._assembler:
            return {}
        
        return {
            "skill_context": self._assembler.get_skill_context_for_prompt(),
            "tool_context": self._assembler.get_tools_context_for_prompt(),
            "messages": self._assembler.get_injection_messages(""),
            "context_pressure": self._orchestrator.check_context_pressure(),
        }
    
    def inject_to_prompt_builder(self, prompt_builder: Any) -> None:
        """
        注入到Prompt构建器
        
        将上下文内容注入到Agent的Prompt构建过程
        """
        if not self._assembler:
            return
        
        # 获取Skill上下文
        skill_context = self._assembler.get_skill_context_for_prompt()
        
        # 获取工具上下文
        tool_context = self._assembler.get_tools_context_for_prompt()
        
        # 注入到prompt builder
        if hasattr(prompt_builder, 'add_context'):
            prompt_builder.add_context("skills", skill_context)
            prompt_builder.add_context("tools", tool_context)
        elif hasattr(prompt_builder, 'context'):
            prompt_builder.context["skills"] = skill_context
            prompt_builder.context["tools"] = tool_context
        
        logger.debug("[CoreV2Integration] Injected context to prompt builder")
    
    def build_messages_for_llm(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        构建LLM消息列表
        
        整合上下文、历史和用户输入
        """
        if not self._assembler:
            messages = [{"role": "user", "content": user_input}]
            if conversation_history:
                messages = conversation_history + messages
            return messages
        
        # 获取基础消息（包含Skills和Tools）
        base_messages = self._assembler.get_injection_messages("")
        
        # 移除最后的空user消息
        if base_messages and base_messages[-1]["content"] == "":
            base_messages = base_messages[:-1]
        
        # 添加历史
        if conversation_history:
            # 找到user消息的位置
            for i, msg in enumerate(base_messages):
                if msg["role"] == "user":
                    base_messages[i:i] = conversation_history
                    break
            else:
                base_messages.extend(conversation_history)
        
        # 添加当前用户输入
        base_messages.append({"role": "user", "content": user_input})
        
        return base_messages
    
    async def process_step_output(
        self,
        step_output: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        处理步骤输出
        
        返回处理结果，包含是否需要Skill转换
        """
        result = {
            "should_continue": True,
            "skill_exited": False,
            "next_skill": None,
            "context_pressure": self._orchestrator.check_context_pressure(),
        }
        
        # 记录工具调用
        if tool_calls:
            for call in tool_calls:
                tool_name = call.get("name", call.get("tool_name", ""))
                if tool_name:
                    await self.record_tool_call(tool_name)
        
        # 处理输出
        if self._current_skill:
            exit_info = await self._process_skill_output(step_output)
            
            if exit_info:
                result["skill_exited"] = True
                result["exit_info"] = exit_info
                result["next_skill"] = exit_info.get("next_skill")
                result["should_continue"] = exit_info.get("next_skill") is not None
        
        # 检查上下文压力
        if result["context_pressure"] > 0.9:
            await self._orchestrator.handle_context_pressure()
            result["pressure_handled"] = True
        
        return result
    
    async def _process_skill_output(self, output: str) -> Optional[Dict[str, Any]]:
        """处理Skill输出"""
        check_results = self._monitor.record_output(
            skill_name=self._current_skill,
            output=output,
        )
        
        for check_result in check_results:
            if check_result.should_exit:
                exit_result = await self._orchestrator.complete_skill(
                    skill_name=self._current_skill,
                    task_summary=check_result.summary or "Completed",
                    key_outputs=check_result.key_outputs,
                )
                
                self._monitor.stop_skill_monitoring(self._current_skill)
                
                next_skill = await self._transition.handle_skill_transition(
                    self._current_skill,
                    exit_result,
                )
                
                old_skill = self._current_skill
                self._current_skill = None
                
                return {
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
    
    async def transition_to_skill(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
    ) -> None:
        """转换到新Skill"""
        await self._orchestrator.prepare_skill_context(
            skill_name=skill_name,
            skill_content=skill_content,
            required_tools=required_tools,
        )
        
        self._monitor.start_skill_monitoring(skill_name)
        self._current_skill = skill_name
        
        logger.info(f"[CoreV2Integration] Transitioned to: {skill_name}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "orchestrator": self._orchestrator.get_context_report(),
            "monitor": self._monitor.get_statistics(),
            "current_skill": self._current_skill,
        }


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


async def example_corev2_integration():
    """
    CoreV2架构集成示例
    """
    # 创建集成实例
    integration = CoreV2AgentContextIntegration(
        token_budget=50000,
        max_active_skills=2,
    )
    
    # 初始化
    await integration.initialize(
        session_id="corev2_example",
        system_prompt="You are a development assistant.",
    )
    
    # 准备执行环境（设置Skill序列）
    skill_sequence = [
        "requirement_analysis",
        "design",
        "implementation",
        "testing",
    ]
    
    context = await integration.prepare_execution(
        skill_name="requirement_analysis",
        skill_content="# Requirement Analysis Skill\n\n...",
        skill_goals=["Understand requirements"],
        skill_sequence=skill_sequence,
    )
    
    # 构建消息
    messages = integration.build_messages_for_llm(
        user_input="Build a user authentication system",
        conversation_history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi! How can I help?"},
        ],
    )
    
    # 模拟执行步骤
    for i, skill_name in enumerate(skill_sequence):
        context = await integration.prepare_execution(
            skill_name=skill_name,
            skill_content=f"# {skill_name} Skill\n\n...",
        )
        
        # 模拟LLM输出
        output = f"Working on {skill_name}... <task-complete>Done</task-complete>"
        
        result = await integration.process_step_output(output)
        
        print(f"Step {i+1}: {skill_name}")
        print(f"  Exited: {result['skill_exited']}")
        print(f"  Next: {result.get('next_skill')}")


if __name__ == "__main__":
    import asyncio
    
    print("=== Core Integration Example ===")
    asyncio.run(example_core_integration())
    
    print("\n=== CoreV2 Integration Example ===")
    asyncio.run(example_corev2_integration())