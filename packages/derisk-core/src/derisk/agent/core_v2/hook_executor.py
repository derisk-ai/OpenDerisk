"""
HookExecutor - 场景钩子执行引擎

实现场景生命周期钩子的动态执行
支持自定义钩子函数的注册和调用

设计原则:
- 可扩展：支持注册自定义钩子函数
- 上下文传递：钩子可访问当前上下文
- 错误隔离：钩子执行失败不影响主流程
"""

from typing import Dict, Any, Callable, Optional, List
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


# 钩子函数类型
HookFunction = Callable[[Any, Dict[str, Any]], Any]


class HookExecutor:
    """
    钩子执行引擎

    管理和执行场景生命周期钩子：
    - on_enter: 场景进入时执行
    - on_exit: 场景退出时执行
    - before_think: 思考前执行
    - after_think: 思考后执行
    - before_act: 行动前执行
    - after_act: 行动后执行
    - before_tool: 工具调用前执行
    - after_tool: 工具调用后执行
    - on_error: 错误时执行
    - on_complete: 任务完成时执行
    """

    def __init__(self):
        """初始化钩子执行引擎"""
        # 钩子函数注册表
        self._hooks: Dict[str, HookFunction] = {}

        # 内置钩子
        self._builtin_hooks = {
            "diagnosis_session_init": self._diagnosis_session_init,
            "inject_diagnosis_context": self._inject_diagnosis_context,
            "record_diagnosis_step": self._record_diagnosis_step,
            "generate_diagnosis_report": self._generate_diagnosis_report,
            "performance_session_init": self._performance_session_init,
            "inject_performance_context": self._inject_performance_context,
            "record_performance_data": self._record_performance_data,
            "generate_performance_report": self._generate_performance_report,
        }

        # 注册内置钩子
        for name, func in self._builtin_hooks.items():
            self.register_hook(name, func)

        logger.info(
            f"[HookExecutor] Initialized with {len(self._hooks)} built-in hooks"
        )

    def register_hook(self, name: str, func: HookFunction) -> None:
        """
        注册钩子函数

        Args:
            name: 钩子名称
            func: 钩子函数
        """
        self._hooks[name] = func
        logger.info(f"[HookExecutor] Registered hook: {name}")

    def unregister_hook(self, name: str) -> bool:
        """
        注销钩子函数

        Args:
            name: 钩子名称

        Returns:
            是否注销成功
        """
        if name in self._hooks:
            del self._hooks[name]
            logger.info(f"[HookExecutor] Unregistered hook: {name}")
            return True
        return False

    async def execute_hook(
        self, hook_name: str, agent: Any, context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        执行钩子

        Args:
            hook_name: 钩子名称
            agent: Agent 实例
            context: 执行上下文

        Returns:
            钩子执行结果
        """
        # 查找钩子函数
        hook_func = self._hooks.get(hook_name)
        if not hook_func:
            logger.debug(f"[HookExecutor] Hook not found: {hook_name}")
            return None

        # 准备上下文
        if context is None:
            context = {}

        context["timestamp"] = datetime.now()
        context["hook_name"] = hook_name

        try:
            # 执行钩子
            logger.info(f"[HookExecutor] Executing hook: {hook_name}")

            if asyncio.iscoroutinefunction(hook_func):
                result = await hook_func(agent, context)
            else:
                result = hook_func(agent, context)

            logger.info(f"[HookExecutor] Hook executed successfully: {hook_name}")
            return result

        except Exception as e:
            logger.error(
                f"[HookExecutor] Hook execution failed: {hook_name}, error: {e}"
            )
            # 钩子执行失败不影响主流程
            return None

    # ==================== 内置钩子函数 ====================

    async def _diagnosis_session_init(
        self, agent: Any, context: Dict[str, Any]
    ) -> None:
        """诊断会话初始化钩子"""
        logger.info("[HookExecutor] Diagnosis session initialized")
        # 在实际实现中，这里可以加载历史诊断记录

    async def _inject_diagnosis_context(
        self, agent: Any, context: Dict[str, Any]
    ) -> None:
        """注入诊断上下文钩子"""
        logger.info("[HookExecutor] Injecting diagnosis context")
        # 在实际实现中，这里可以注入系统架构图、历史故障等

    async def _record_diagnosis_step(self, agent: Any, context: Dict[str, Any]) -> None:
        """记录诊断步骤钩子"""
        logger.info("[HookExecutor] Recording diagnosis step")

    async def _generate_diagnosis_report(
        self, agent: Any, context: Dict[str, Any]
    ) -> None:
        """生成诊断报告钩子"""
        logger.info("[HookExecutor] Generating diagnosis report")

    async def _performance_session_init(
        self, agent: Any, context: Dict[str, Any]
    ) -> None:
        """性能分析会话初始化钩子"""
        logger.info("[HookExecutor] Performance session initialized")

    async def _inject_performance_context(
        self, agent: Any, context: Dict[str, Any]
    ) -> None:
        """注入性能分析上下文钩子"""
        logger.info("[HookExecutor] Injecting performance context")

    async def _record_performance_data(
        self, agent: Any, context: Dict[str, Any]
    ) -> None:
        """记录性能数据钩子"""
        logger.info("[HookExecutor] Recording performance data")

    async def _generate_performance_report(
        self, agent: Any, context: Dict[str, Any]
    ) -> None:
        """生成性能报告钩子"""
        logger.info("[HookExecutor] Generating performance report")

    def list_hooks(self) -> List[str]:
        """列出所有已注册的钩子"""
        return list(self._hooks.keys())

    def has_hook(self, name: str) -> bool:
        """检查钩子是否存在"""
        return name in self._hooks


# ==================== 导出 ====================

__all__ = [
    "HookExecutor",
    "HookFunction",
]
