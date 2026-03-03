"""
ReasoningStrategy - 推理策略系统

实现多种推理策略
支持ReAct、Plan-and-Execute、Tree-of-Thought等
"""

from typing import List, Optional, Dict, Any, AsyncIterator, Callable, Awaitable
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


class ReasoningStep(BaseModel):
    """推理步骤"""
    step_id: int
    step_type: str  # "thought", "action", "observation", "plan", "execute"
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class ReasoningResult(BaseModel):
    """推理结果"""
    success: bool
    final_answer: str
    steps: List[ReasoningStep] = Field(default_factory=list)
    
    total_steps: int = 0
    total_time: float = 0.0
    
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    reasoning_chain: List[str] = Field(default_factory=list)
    
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StrategyType(str, Enum):
    """策略类型"""
    REACT = "react"
    PLAN_AND_EXECUTE = "plan_and_execute"
    TREE_OF_THOUGHT = "tree_of_thought"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    REFLECTION = "reflection"


class ReasoningStrategy(ABC):
    """推理策略基类"""
    
    def __init__(self, llm_client: Any, max_steps: int = 10):
        self.llm_client = llm_client
        self.max_steps = max_steps
    
    @abstractmethod
    async def reason(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        execute_tool: Optional[Callable[[str, Dict], Awaitable[Any]]] = None
    ) -> ReasoningResult:
        """执行推理"""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass
    
    async def _generate(self, prompt: str) -> str:
        """生成响应"""
        from .llm_utils import call_llm
        
        result = await call_llm(self.llm_client, prompt)
        if result is None:
            raise NotImplementedError("LLM client call failed")
        return result


class ReActStrategy(ReasoningStrategy):
    """
    ReAct推理策略
    
    ReAct = Reasoning + Acting
    
    示例:
        strategy = ReActStrategy(llm_client)
        result = await strategy.reason(
            query="What is the weather in Beijing?",
            tools=tools,
            execute_tool=execute_fn
        )
    """
    
    def __init__(self, llm_client: Any, max_steps: int = 10):
        super().__init__(llm_client, max_steps)
        self._step_count = 0
    
    def get_strategy_name(self) -> str:
        return "ReAct"
    
    async def reason(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        execute_tool: Optional[Callable[[str, Dict], Awaitable[Any]]] = None
    ) -> ReasoningResult:
        start_time = datetime.now()
        self._step_count = 0
        
        steps: List[ReasoningStep] = []
        tool_calls: List[Dict[str, Any]] = []
        reasoning_chain: List[str] = []
        
        current_query = query
        
        try:
            while self._step_count < self.max_steps:
                self._step_count += 1
                
                thought = await self._generate_thought(current_query, context)
                steps.append(ReasoningStep(
                    step_id=self._step_count,
                    step_type="thought",
                    content=thought
                ))
                reasoning_chain.append(f"Thought: {thought}")
                
                action_info = await self._decide_action(thought, current_query, tools)
                
                if action_info["type"] == "finish":
                    answer = action_info.get("answer", "")
                    steps.append(ReasoningStep(
                        step_id=self._step_count,
                        step_type="action",
                        content=f"Finish: {answer}"
                    ))
                    
                    total_time = (datetime.now() - start_time).total_seconds()
                    return ReasoningResult(
                        success=True,
                        final_answer=answer,
                        steps=steps,
                        total_steps=self._step_count,
                        total_time=total_time,
                        tool_calls=tool_calls,
                        reasoning_chain=reasoning_chain
                    )
                
                if action_info["type"] == "tool_call" and execute_tool:
                    tool_name = action_info.get("tool_name", "")
                    tool_args = action_info.get("tool_args", {})
                    
                    steps.append(ReasoningStep(
                        step_id=self._step_count,
                        step_type="action",
                        content=f"Action: {tool_name}({json.dumps(tool_args)})"
                    ))
                    
                    try:
                        observation = await execute_tool(tool_name, tool_args)
                        tool_calls.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": str(observation)
                        })
                    except Exception as e:
                        observation = f"Error: {str(e)}"
                    
                    steps.append(ReasoningStep(
                        step_id=self._step_count,
                        step_type="observation",
                        content=f"Observation: {str(observation)}"
                    ))
                    reasoning_chain.append(f"Observation: {str(observation)[:200]}")
                    
                    current_query = f"{current_query}\n\nThought: {thought}\nAction: {tool_name}\nObservation: {str(observation)}"
                
                else:
                    current_query = f"{current_query}\n\nThought: {thought}"
            
            total_time = (datetime.now() - start_time).total_seconds()
            return ReasoningResult(
                success=False,
                final_answer="",
                steps=steps,
                total_steps=self._step_count,
                total_time=total_time,
                tool_calls=tool_calls,
                reasoning_chain=reasoning_chain,
                error=f"Reached max steps ({self.max_steps})"
            )
            
        except Exception as e:
            total_time = (datetime.now() - start_time).total_seconds()
            return ReasoningResult(
                success=False,
                final_answer="",
                steps=steps,
                total_steps=self._step_count,
                total_time=total_time,
                error=str(e)
            )
    
    async def _generate_thought(self, query: str, context: Optional[Dict] = None) -> str:
        """生成思考"""
        prompt = f"""Given the following query, generate a thought about what to do next.

Query: {query}

{f"Context: {json.dumps(context)}" if context else ""}

Generate a concise thought (one sentence) about what information or action is needed.
Thought:"""
        
        return await self._generate(prompt)
    
    async def _decide_action(
        self,
        thought: str,
        query: str,
        tools: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """决定下一步动作"""
        tools_desc = ""
        if tools:
            tools_desc = "\n".join([
                f"- {t.get('name', t.get('function', {}).get('name', 'unknown'))}: {t.get('description', t.get('function', {}).get('description', ''))}"
                for t in tools
            ])
        
        prompt = f"""Based on the thought, decide the next action.

Query: {query}
Thought: {thought}

Available tools:
{tools_desc if tools_desc else "No tools available"}

Decide one of:
1. Use a tool: {{"type": "tool_call", "tool_name": "...", "tool_args": {{...}}}}
2. Provide final answer: {{"type": "finish", "answer": "..."}}

Response in JSON:"""
        
        response = await self._generate(prompt)
        
        try:
            match = None
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                match = json_match.group()
            
            if match:
                return json.loads(match)
        except Exception:
            pass
        
        return {"type": "finish", "answer": response}


class PlanAndExecuteStrategy(ReasoningStrategy):
    """
    Plan-and-Execute推理策略
    
    示例:
        strategy = PlanAndExecuteStrategy(llm_client)
        result = await strategy.reason(query, tools, execute_tool)
    """
    
    def __init__(self, llm_client: Any, max_steps: int = 10):
        super().__init__(llm_client, max_steps)
    
    def get_strategy_name(self) -> str:
        return "PlanAndExecute"
    
    async def reason(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        execute_tool: Optional[Callable[[str, Dict], Awaitable[Any]]] = None
    ) -> ReasoningResult:
        start_time = datetime.now()
        steps: List[ReasoningStep] = []
        tool_calls: List[Dict[str, Any]] = []
        
        plan = await self._create_plan(query, context, tools)
        steps.append(ReasoningStep(
            step_id=1,
            step_type="plan",
            content=json.dumps(plan, indent=2)
        ))
        
        results = []
        step_id = 2
        
        for i, task in enumerate(plan["tasks"]):
            if step_id > self.max_steps:
                break
            
            steps.append(ReasoningStep(
                step_id=step_id,
                step_type="execute",
                content=f"Executing task {i+1}: {task['description']}"
            ))
            step_id += 1
            
            if task.get("tool") and execute_tool:
                try:
                    result = await execute_tool(task["tool"], task.get("args", {}))
                    tool_calls.append({
                        "tool": task["tool"],
                        "args": task.get("args", {}),
                        "result": str(result)
                    })
                    results.append(str(result))
                except Exception as e:
                    results.append(f"Error: {str(e)}")
            else:
                result = await self._execute_task(task, query, results)
                results.append(result)
            
            steps.append(ReasoningStep(
                step_id=step_id,
                step_type="observation",
                content=f"Result: {results[-1][:200]}"
            ))
            step_id += 1
        
        answer = await self._synthesize_answer(query, plan, results)
        
        total_time = (datetime.now() - start_time).total_seconds()
        return ReasoningResult(
            success=True,
            final_answer=answer,
            steps=steps,
            total_steps=step_id - 1,
            total_time=total_time,
            tool_calls=tool_calls
        )
    
    async def _create_plan(
        self,
        query: str,
        context: Optional[Dict],
        tools: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """创建执行计划"""
        tools_desc = ""
        if tools:
            tools_desc = "\n".join([
                f"- {t.get('name', t.get('function', {}).get('name', 'unknown'))}"
                for t in tools
            ])
        
        prompt = f"""Create an execution plan for the following query.

Query: {query}

{f"Context: {json.dumps(context)}" if context else ""}

Available tools:
{tools_desc if tools_desc else "No tools available"}

Create a plan in JSON format:
{{
    "tasks": [
        {{"description": "task description", "tool": "tool_name or null", "args": {{}}}}
    ]
}}

Plan:"""
        
        response = await self._generate(prompt)
        
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        
        return {"tasks": [{"description": query, "tool": None, "args": {}}]}
    
    async def _execute_task(
        self,
        task: Dict,
        query: str,
        previous_results: List[str]
    ) -> str:
        """执行任务"""
        prompt = f"""Execute the following task and provide the result.

Original Query: {query}
Task: {task['description']}

Previous Results:
{chr(10).join(previous_results[-3:]) if previous_results else 'None'}

Result:"""
        
        return await self._generate(prompt)
    
    async def _synthesize_answer(
        self,
        query: str,
        plan: Dict,
        results: List[str]
    ) -> str:
        """综合答案"""
        prompt = f"""Based on the execution results, provide a final answer to the query.

Query: {query}

Execution Results:
{chr(10).join(results)}

Final Answer:"""
        
        return await self._generate(prompt)


class ChainOfThoughtStrategy(ReasoningStrategy):
    """链式思考策略"""
    
    def __init__(self, llm_client: Any, max_steps: int = 10):
        super().__init__(llm_client, max_steps)
    
    def get_strategy_name(self) -> str:
        return "ChainOfThought"
    
    async def reason(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        execute_tool: Optional[Callable[[str, Dict], Awaitable[Any]]] = None
    ) -> ReasoningResult:
        start_time = datetime.now()
        steps: List[ReasoningStep] = []
        
        prompt = f"""Solve the following problem step by step.

Query: {query}

{f"Context: {json.dumps(context)}" if context else ""}

Let's think step by step:
1."""
        
        response = await self._generate(prompt)
        
        steps.append(ReasoningStep(
            step_id=1,
            step_type="thought",
            content=response
        ))
        
        import re
        answer_match = re.search(r'(Therefore|Thus|So|Answer|Result)[:：]\s*(.+)', response, re.IGNORECASE)
        
        final_answer = answer_match.group(2).strip() if answer_match else response
        
        total_time = (datetime.now() - start_time).total_seconds()
        return ReasoningResult(
            success=True,
            final_answer=final_answer,
            steps=steps,
            total_steps=1,
            total_time=total_time,
            reasoning_chain=[response]
        )


class ReflectionStrategy(ReasoningStrategy):
    """反思策略"""
    
    def __init__(self, llm_client: Any, max_steps: int = 10, max_reflections: int = 3):
        super().__init__(llm_client, max_steps)
        self.max_reflections = max_reflections
    
    def get_strategy_name(self) -> str:
        return "Reflection"
    
    async def reason(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        execute_tool: Optional[Callable[[str, Dict], Awaitable[Any]]] = None
    ) -> ReasoningResult:
        start_time = datetime.now()
        steps: List[ReasoningStep] = []
        
        initial_answer = await self._generate_initial_answer(query, context)
        steps.append(ReasoningStep(
            step_id=1,
            step_type="thought",
            content=f"Initial Answer: {initial_answer}"
        ))
        
        current_answer = initial_answer
        
        for i in range(self.max_reflections):
            reflection = await self._reflect(query, current_answer, context)
            steps.append(ReasoningStep(
                step_id=i + 2,
                step_type="thought",
                content=f"Reflection {i+1}: {reflection}"
            ))
            
            improved_answer = await self._improve(query, current_answer, reflection, context)
            current_answer = improved_answer
        
        total_time = (datetime.now() - start_time).total_seconds()
        return ReasoningResult(
            success=True,
            final_answer=current_answer,
            steps=steps,
            total_steps=len(steps),
            total_time=total_time
        )
    
    async def _generate_initial_answer(self, query: str, context: Optional[Dict]) -> str:
        """生成初始答案"""
        prompt = f"""Answer the following question.

Query: {query}

{f"Context: {json.dumps(context)}" if context else ""}

Answer:"""
        
        return await self._generate(prompt)
    
    async def _reflect(self, query: str, answer: str, context: Optional[Dict]) -> str:
        """反思"""
        prompt = f"""Critically evaluate the following answer.

Query: {query}
Current Answer: {answer}

{f"Context: {json.dumps(context)}" if context else ""}

What are the potential issues or improvements? Be critical.

Reflection:"""
        
        return await self._generate(prompt)
    
    async def _improve(self, query: str, answer: str, reflection: str, context: Optional[Dict]) -> str:
        """改进答案"""
        prompt = f"""Improve the answer based on the reflection.

Query: {query}
Current Answer: {answer}
Reflection: {reflection}

{f"Context: {json.dumps(context)}" if context else ""}

Improved Answer:"""
        
        return await self._generate(prompt)


class ReasoningStrategyFactory:
    """
    推理策略工厂
    
    示例:
        factory = ReasoningStrategyFactory(llm_client)
        
        strategy = factory.create(StrategyType.REACT)
        result = await strategy.reason(query)
    """
    
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client
    
    def create(
        self,
        strategy_type: StrategyType,
        max_steps: int = 10,
        **kwargs
    ) -> ReasoningStrategy:
        """创建推理策略"""
        strategies = {
            StrategyType.REACT: ReActStrategy,
            StrategyType.PLAN_AND_EXECUTE: PlanAndExecuteStrategy,
            StrategyType.CHAIN_OF_THOUGHT: ChainOfThoughtStrategy,
            StrategyType.REFLECTION: ReflectionStrategy,
        }
        
        strategy_class = strategies.get(strategy_type, ReActStrategy)
        return strategy_class(self.llm_client, max_steps, **kwargs)
    
    def list_strategies(self) -> List[str]:
        """列出所有策略"""
        return [s.value for s in StrategyType]


reasoning_strategy_factory = ReasoningStrategyFactory