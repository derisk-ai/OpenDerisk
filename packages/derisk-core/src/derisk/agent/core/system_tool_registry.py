import asyncio
import functools
import inspect
import logging
from typing import get_origin, get_args, Any, Annotated, Callable

from derisk.agent.resource.tool.base import ToolFunc, FunctionTool

logger = logging.getLogger(__name__)
DERISK_TOOL_IDENTIFIER = 'system_tool'

# 工具函数映射
system_tool_dict:[str, FunctionTool] = {}



def system_tool(
        name=None,
        description=None,
        owner=None,
        input_schema=None,
        ask_user=False,
        stream=False,
        concurrency="parallel",
) -> Callable[..., Any]:
    """
    Decorator to register a function with a name and description.
    """

    def decorator(func: ToolFunc):
        tool_name = name if name is not None else func.__name__
        ft = FunctionTool(tool_name, func, description, None, None, input_schema=input_schema, ask_user=ask_user, concurrency=concurrency)

        func._to_register = {
            'name': tool_name,
            'description': description,
            'owner': owner if owner is not None else 'derisk',
            'input_schema': input_schema if input_schema is not None else generate_function_schema(func),
            'ask_user': ask_user,
            'stream': stream,
            'concurrency': concurrency,
        }  # Attribute indicates it should be registered
        func.__ant_tool__ = True
        # 更新全局映射 poc_function_map
        if name not in system_tool_dict:
            system_tool_dict[name] = ft
            logger.info(f"工具{name}已成功注册")
        else:
            logger.warning(f"工具{name}已存在，跳过重复注册")

        @functools.wraps(func)
        def sync_wrapper(*f_args, **kwargs):
            if stream:
                return ft.execute_stream(*f_args, **kwargs)
            else:
                return ft.execute(*f_args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*f_args, **kwargs):
            if stream:
                return ft.async_execute_stream(*f_args, **kwargs)
            else:
                return await ft.async_execute(*f_args, **kwargs)

        # 检查函数类型
        import inspect
        if inspect.isasyncgenfunction(func) or asyncio.iscoroutinefunction(func):
            wrapper = async_wrapper
        else:
            wrapper = sync_wrapper

        wrapper._tool = ft  # type: ignore
        setattr(wrapper, DERISK_TOOL_IDENTIFIER, True)
        return wrapper

    return decorator


def generate_function_schema(func):
    """
    从函数中提取参数类型注解，生成符合 JSON schema 格式的字典。
    """
    sig = inspect.signature(func)
    schema = {
        "type": "object",
        "properties": {}
    }

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            raise TypeError(f"Missing type annotation for parameter '{name}' in function {func.__name__}.")

        schema["properties"][name] = {
            "type": _convert_type(annotation)
        }

    return schema


def _convert_type(t: Any) -> str:
    """
    将 Python 类型注解转换为 JSON schema 中的类型字符串。
    支持基本类型和部分组合类型（如 List, Dict）。
    """
    if get_origin(t) is Annotated:
        t = get_args(t)[0]
    if t is str:
        return "string"
    elif t is int:
        return "integer"
    elif t is float:
        return "number"
    elif t is bool:
        return "boolean"
    elif t is bytes:
        return "string"  # JSON 中用 string 表示二进制数据
    elif get_origin(t) is list:
        return "array"
    else:
        return "object"

