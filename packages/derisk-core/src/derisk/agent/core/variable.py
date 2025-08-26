import asyncio
import inspect
from inspect import Parameter, signature
from typing import Any, Dict, Callable, Set


class VariableManager:
    """支持同步和异步函数的变量管理器，自动参数筛选"""

    def __init__(self):
        self._registry = {}  # 结构：{name: {func, method_type, is_async, desc}}

    def register(self, name: str, description: str = ""):
        """增强型注册装饰器，支持同步和异步函数"""

        def decorator(func):
            # 提取原始函数（处理装饰器链）
            original_func = func
            while hasattr(original_func, '__wrapped__'):
                original_func = original_func.__wrapped__

            # 检测方法类型和函数类型
            method_type = self._detect_method_type(original_func)
            is_async = inspect.iscoroutinefunction(original_func)

            self._registry[name] = {
                'func': original_func,
                'method_type': method_type,
                'is_async': is_async,
                'description': description,
                'required_params': self._get_required_params(original_func)
            }
            return func

        return decorator

    async def get_value(self, var_name: str, **kwargs) -> Any:
        """获取变量值，支持异步函数"""
        if var_name not in self._registry:
            raise KeyError(f"未注册的变量: {var_name}")

        var_info = self._registry[var_name]
        # 检查必需参数
        self._validate_arguments(var_info['func'], var_info['method_type'], kwargs)
        # 执行函数并返回结果
        return await self._execute_function(var_info, kwargs)

    def get_all_variables(self) -> Dict[str, Dict]:
        """获取所有变量元信息，包含参数要求"""
        return {
            name: {
                'description': info['description'],
                'method_type': info['method_type'],
                'is_async': info['is_async'],
                'signature': str(signature(info['func'])),
                'required_params': info['required_params']
            }
            for name, info in self._registry.items()
        }

    def _detect_method_type(self, func: Callable) -> str:
        """智能方法类型检测"""
        # 处理绑定方法（类方法/实例方法）
        if hasattr(func, '__self__'):
            if isinstance(func.__self__, type):
                return 'class'
            return 'instance'

        # 处理普通函数
        if isinstance(func, classmethod):
            return 'class'
        if isinstance(func, staticmethod):
            return 'static'

        sig = signature(func)
        params = list(sig.parameters.values())
        if params and params[0].name == 'self':
            return 'instance'
        if params and params[0].name == 'cls':
            return 'class'
        return 'static'

    def _get_required_params(self, func: Callable) -> Set[str]:
        """获取函数必需的参数名集合"""
        sig = signature(func)
        required = set()
        for name, param in sig.parameters.items():
            # 跳过上下文参数和可变参数
            if name in ['self', 'cls'] or param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                continue

            # 没有默认值的参数是必需的
            if param.default is Parameter.empty:
                required.add(name)
        return required

    def _validate_arguments(self, func: Callable, method_type: str, user_kwargs: Dict):
        """验证参数是否满足函数要求"""
        # 获取函数签名和必需参数
        sig = signature(func)
        required_params = self._get_required_params(func)

        # 根据方法类型添加上下文参数
        context = self._get_context(method_type, user_kwargs)
        if context:
            # 上下文参数会被自动提供，不作为用户必需参数
            required_params -= set(context.keys())

        # 检查必需参数是否提供
        missing = required_params - set(user_kwargs.keys())
        if missing:
            raise ValueError(f"缺少必需参数: {', '.join(sorted(missing))}")

        # 检查是否有多余参数
        allowed_params = set()
        for name, param in sig.parameters.items():
            if param.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD,
                              Parameter.KEYWORD_ONLY, Parameter.VAR_KEYWORD):
                allowed_params.add(name)

        # 上下文参数和可变参数允许额外参数
        if Parameter.VAR_KEYWORD not in [p.kind for p in sig.parameters.values()]:
            additional_params = set(user_kwargs.keys()) - allowed_params - set(context.keys())
            # if additional_params:
            #     raise ValueError(f"发现未知参数: {', '.join(sorted(additional_params))}")

    def _get_context(self, method_type: str, user_kwargs: Dict) -> Dict[str, Any]:
        """获取方法类型对应的上下文参数"""
        if method_type == 'instance':
            instance = user_kwargs.get('instance')
            if instance is None:
                raise ValueError("实例方法缺少 'instance' 参数")
            return {'self': instance}
        elif method_type == 'class':
            cls = user_kwargs.get('cls')
            if cls is None:
                raise ValueError("类方法缺少 'cls' 参数")
            return {'cls': cls}
        return {}

    def _bind_arguments(self, func: Callable, method_type: str, user_kwargs: Dict) -> Dict:
        """参数绑定：智能参数绑定（上下文感知）"""
        # 创建上下文参数
        context = self._get_context(method_type, user_kwargs)

        # 准备最终参数集合
        bound_args = {}

        # 获取函数签名
        sig = signature(func)

        # 绑定上下文参数
        for param in sig.parameters.values():
            if param.name in context:
                bound_args[param.name] = context[param.name]
                break  # 上下文参数通常是第一个参数

        # 绑定用户参数
        for name, param in sig.parameters.items():
            if name in bound_args:
                continue  # 已绑定上下文参数

            if name in user_kwargs:
                bound_args[name] = user_kwargs[name]
            elif param.default is not Parameter.empty:
                bound_args[name] = param.default
            elif param.kind == Parameter.VAR_KEYWORD:
                # 处理 **kwargs 参数
                bound_args.update({k: v for k, v in user_kwargs.items() if k not in bound_args})
            elif param.kind == Parameter.VAR_POSITIONAL:
                # 忽略 *args 参数（我们不支持位置参数）
                continue

        return bound_args

    async def _execute_function(self, var_info: Dict, kwargs: Dict) -> Any:
        """执行函数，支持同步和异步调用，自动处理参数绑定"""
        bound_args = self._bind_arguments(var_info['func'], var_info['method_type'], kwargs)

        # 根据函数类型选择合适的调用方式
        if var_info['is_async']:
            return await var_info['func'](**bound_args)
        else:
            # 同步函数包装为异步执行
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: var_info['func'](**bound_args)
            )
