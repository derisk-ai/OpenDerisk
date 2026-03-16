"""
工具组合模式 - 参考OpenCode的Batch和Task模式
支持并行执行多个工具、串行执行、条件执行等高级组合
"""
import asyncio
from typing import Dict, Any, Optional, List, Callable, Awaitable
from pydantic import BaseModel, Field
from derisk.agent.tools.base import ToolBase
from derisk.agent.tools.result import ToolResult
from derisk.agent.tools.registry import tool_registry


class BatchResult(BaseModel):
    """批处理结果"""
    results: Dict[str, ToolResult] = Field(default_factory=dict)
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0


class TaskResult(BaseModel):
    """任务结果"""
    task_id: str
    success: bool
    result: Optional[ToolResult] = None
    error: Optional[str] = None


class BatchExecutor:
    """批处理器 - 并行执行多个工具调用"""
    
    def __init__(self, registry=None):
        self.registry = registry or tool_registry
    
    async def execute(
        self, 
        calls: List[Dict[str, Any]], 
        fail_fast: bool = False
    ) -> BatchResult:
        """
        并行执行多个工具调用
        
        Args:
            calls: 工具调用列表，格式: [{"tool": "name", "args": {...}}, ...]
            fail_fast: 是否在第一个失败时停止
        
        Returns:
            BatchResult: 批处理结果
        """
        import time
        start_time = time.time()
        
        results: Dict[str, ToolResult] = {}
        success_count = 0
        failure_count = 0
        
        tasks = []
        for i, call in enumerate(calls):
            tool_name = call.get("tool")
            args = call.get("args", {})
            call_id = call.get("id", f"call_{i}")
            
            tool = self.registry.get(tool_name)
            if not tool:
                results[call_id] = ToolResult(
                    success=False,
                    error=f"工具不存在: {tool_name}"
                )
                failure_count += 1
                if fail_fast:
                    break
                continue
            
            tasks.append((call_id, tool, args))
        
        if tasks:
            coroutines = [
                self._execute_with_id(call_id, tool, args)
                for call_id, tool, args in tasks
            ]
            
            if fail_fast:
                for coro in asyncio.as_completed(coroutines):
                    call_id, result = await coro
                    results[call_id] = result
                    if not result.success:
                        break
            else:
                task_results = await asyncio.gather(*coroutines, return_exceptions=True)
                for i, (call_id, _, _) in enumerate(tasks):
                    result = task_results[i]
                    if isinstance(result, Exception):
                        results[call_id] = ToolResult(
                            success=False,
                            error=str(result)
                        )
                        failure_count += 1
                    else:
                        results[call_id] = result[1]
                        if result[1].success:
                            success_count += 1
                        else:
                            failure_count += 1
        
        total_duration = (time.time() - start_time) * 1000
        
        return BatchResult(
            results=results,
            success_count=success_count,
            failure_count=failure_count,
            total_duration_ms=total_duration
        )
    
    async def _execute_with_id(
        self, 
        call_id: str, 
        tool: ToolBase, 
        args: Dict[str, Any]
    ) -> tuple:
        """带ID的执行"""
        result = await tool.execute(args)
        return (call_id, result)


class TaskExecutor:
    """任务执行器 - 子任务委派"""
    
    def __init__(self, registry=None):
        self.registry = registry or tool_registry
        self._task_counter = 0
    
    async def spawn(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """
        生成子任务
        
        Args:
            task: 任务描述或工具调用
            context: 执行上下文
        
        Returns:
            TaskResult: 任务结果
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        
        if isinstance(task, dict):
            tool_name = task.get("tool")
            args = task.get("args", {})
        else:
            return TaskResult(
                task_id=task_id,
                success=False,
                error="任务格式错误，应为字典格式"
            )
        
        tool = self.registry.get(tool_name)
        if not tool:
            return TaskResult(
                task_id=task_id,
                success=False,
                error=f"工具不存在: {tool_name}"
            )
        
        try:
            result = await tool.execute(args, context)
            return TaskResult(
                task_id=task_id,
                success=result.success,
                result=result,
                error=result.error
            )
        except Exception as e:
            return TaskResult(
                task_id=task_id,
                success=False,
                error=str(e)
            )
    
    async def spawn_multiple(
        self,
        tasks: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[TaskResult]:
        """并行生成多个子任务"""
        coroutines = [self.spawn(task, context) for task in tasks]
        return await asyncio.gather(*coroutines)


class WorkflowBuilder:
    """工作流构建器 - 链式组合工具"""
    
    def __init__(self, registry=None):
        self.registry = registry or tool_registry
        self._steps: List[Dict[str, Any]] = []
        self._results: Dict[str, ToolResult] = {}
        self._context: Dict[str, Any] = {}
    
    def step(
        self, 
        tool_name: str, 
        args: Dict[str, Any], 
        name: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """添加步骤"""
        step_id = name or f"step_{len(self._steps)}"
        self._steps.append({
            "id": step_id,
            "tool": tool_name,
            "args": args
        })
        return self
    
    def condition(
        self, 
        condition: Callable[[Dict[str, Any]], bool],
        then_steps: List[Dict[str, Any]],
        else_steps: Optional[List[Dict[str, Any]]] = None
    ) -> 'WorkflowBuilder':
        """添加条件分支"""
        self._steps.append({
            "type": "condition",
            "condition": condition,
            "then": then_steps,
            "else": else_steps or []
        })
        return self
    
    def parallel(self, calls: List[Dict[str, Any]]) -> 'WorkflowBuilder':
        """添加并行步骤"""
        self._steps.append({
            "type": "parallel",
            "calls": calls
        })
        return self
    
    async def run(self) -> Dict[str, ToolResult]:
        """执行工作流"""
        for step in self._steps:
            if step.get("type") == "condition":
                if step["condition"](self._context):
                    for sub_step in step["then"]:
                        await self._execute_step(sub_step)
                elif step.get("else"):
                    for sub_step in step["else"]:
                        await self._execute_step(sub_step)
            
            elif step.get("type") == "parallel":
                batch = BatchExecutor(self.registry)
                result = await batch.execute(step["calls"])
                self._results.update(result.results)
            
            else:
                await self._execute_step(step)
        
        return self._results
    
    async def _execute_step(self, step: Dict[str, Any]) -> None:
        """执行单个步骤"""
        tool_name = step.get("tool")
        args = step.get("args", {})
        step_id = step.get("id", f"step_{len(self._results)}")
        
        # 替换参数中的引用
        resolved_args = self._resolve_args(args)
        
        tool = self.registry.get(tool_name)
        if tool:
            result = await tool.execute(resolved_args, self._context)
            self._results[step_id] = result
            
            # 更新上下文
            if result.success and result.output:
                self._context[step_id] = result.output
    
    def _resolve_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """解析参数中的引用 ${step_id}"""
        import re
        resolved = {}
        
        for key, value in args.items():
            if isinstance(value, str):
                pattern = r'\$\{([^}]+)\}'
                def replace(match):
                    ref = match.group(1)
                    if ref in self._results:
                        return str(self._results[ref].output)
                    return match.group(0)
                resolved[key] = re.sub(pattern, replace, value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_args(value)
            else:
                resolved[key] = value
        
        return resolved
    
    def reset(self) -> 'WorkflowBuilder':
        """重置工作流"""
        self._steps = []
        self._results = {}
        self._context = {}
        return self


def batch(calls: List[Dict[str, Any]], fail_fast: bool = False) -> BatchResult:
    """便捷函数：并行执行多个工具调用"""
    executor = BatchExecutor()
    return asyncio.run(executor.execute(calls, fail_fast))


def spawn(task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> TaskResult:
    """便捷函数：生成子任务"""
    executor = TaskExecutor()
    return asyncio.run(executor.spawn(task, context))


def workflow() -> WorkflowBuilder:
    """便捷函数：创建工作流构建器"""
    return WorkflowBuilder()