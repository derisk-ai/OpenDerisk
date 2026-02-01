import asyncio
import functools
import importlib
import inspect
import json
import logging
import pkgutil
import uuid
from pathlib import Path
from typing import get_origin, get_args, Any, Union, Annotated, Callable

from derisk import SystemApp
from derisk.agent import ResourceType
from derisk.agent.resource import get_resource_manager
from derisk.agent.resource.tool.base import ToolFunc, FunctionTool
from derisk_serve.agent.db.gpts_tool import GptsToolDao, GptsTool

logger = logging.getLogger(__name__)
gpts_tool_dao = GptsToolDao()
DERISK_TOOL_IDENTIFIER = 'derisk_tool'


def derisk_tool(
        name=None,
        description=None,
        owner=None,
        input_schema=None
) -> Callable[..., Any]:
    """
    Decorator to register a function with a name and description.
    """

    def decorator(func: ToolFunc):
        tool_name = name if name is not None else func.__name__
        ft = FunctionTool(tool_name, func, description, None, None)

        func._to_register = {
            'name': tool_name,
            'description': description,
            'owner': owner if owner is not None else 'derisk',
            'input_schema': input_schema if input_schema is not None else generate_function_schema(func)
        }  # Attribute indicates it should be registered
        func.__derisk_tool__ = True

        @functools.wraps(func)
        def sync_wrapper(*f_args, **kwargs):
            return ft.execute(*f_args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*f_args, **kwargs):
            return await ft.async_execute(*f_args, **kwargs)

        if asyncio.iscoroutinefunction(func):
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


class CentralFunctionRegistry:
    """
    Central registry to manage registered functions from multiple classes.
    """

    def __init__(self):
        self.registry = {}
        self.instances = {}
        self.standalone_functions = {}
        self.context = {}

    def set_context_entry(self, key, value):
        self.context[key] = value

    def get_context_value(self, key):
        return self.context.get(key, None)

    def clear_context_key(self, key):
        self.context.pop(key)

    def get_registry(self):
        return self.registry, self.standalone_functions

    def get_registry_config(self, class_name=None, func_name=None):
        if class_name and func_name:
            if class_name in self.registry and func_name in self.registry[class_name]:
                func_info = self.registry[class_name][func_name]
                registration_data = func_info['function']._to_register
                return registration_data
        elif not class_name and func_name:
            if func_name in self.standalone_functions:
                func_info = self.standalone_functions[func_name]
                registration_data = func_info['function']._to_register
                return registration_data
        else:
            return None

    def register(self, *args):
        for item in args:
            if isinstance(item, type):
                self.register_class_functions(item)
            else:
                if hasattr(item, '_to_register'):
                    self.register_standalone_function(item)

    def register_class_functions(self, cls):
        """
        Registers functions from a given class that are decorated with @register_function.
        """
        class_name = cls.__name__
        self.registry[class_name] = {}
        # 为每个类创建一个实例
        self.instances[class_name] = cls()

        for name, func in cls.__dict__.items():
            if callable(func) and asyncio.iscoroutinefunction(func) and hasattr(func, '_to_register'):
                registration_info = func._to_register
                self.registry[class_name][registration_info['name']] = {
                    'function': func,
                }

    def register_standalone_function(self, func):
        """
        Registers standalone functions (not inside a class) that are decorated with @derisk_tool.
        """
        if asyncio.iscoroutinefunction(func):
            registration_info = func._to_register
            self.standalone_functions[registration_info['name']] = {
                'function': func,
            }

    def check_function_call(self, class_name, func_name, *args, **kwargs):
        if class_name in self.registry and func_name in self.registry[class_name]:
            return True
        else:
            return False

    async def call_registered_function(self, class_name=None, func_name=None, *args, **kwargs):
        """
        Calls a registered function from a specific class.
        """
        if class_name and func_name:
            if class_name in self.registry and func_name in self.registry[class_name]:
                func_info = self.registry[class_name][func_name]
                function = func_info['function']
                instance = self.instances[class_name]

                if asyncio.iscoroutinefunction(function):
                    return await function(instance, *args, **kwargs)
                else:
                    return function(instance, *args, **kwargs)
        elif not class_name and func_name:
            if func_name in self.standalone_functions:
                func_info = self.standalone_functions[func_name]
                function = func_info['function']

                if asyncio.iscoroutinefunction(function):
                    return await function(*args, **kwargs)
                else:
                    return function(*args, **kwargs)
        else:
            raise ValueError(f"Function '{func_name}' is not registered.")

    def create_class_with_functions(self, class_name):
        """
        Creates a new class with registered functions as methods.
        """
        if class_name not in self.registry:
            raise ValueError(f"Class '{class_name}' has no registered functions.")

        class DynamicClass:
            pass

        for func_name, func_info in self.registry[class_name].items():
            function = func_info['function']
            setattr(DynamicClass, func_name, function)

        return DynamicClass()

    def scan_register_and_save(self, system_app: SystemApp):
        """
        扫描，注册并并保存到数据库中。
        """
        from derisk.agent.resource.manage import get_resource_manager

        TOOL_MODULES_PACKAGE = 'derisk_ext.agent.agents'
        package = importlib.import_module(TOOL_MODULES_PACKAGE)
        package_path = Path(package.__file__).parent

        # 扫描 + 注册
        for _, module_name, _ in pkgutil.walk_packages([str(package_path)], prefix=TOOL_MODULES_PACKAGE + "."):
            try:
                module = importlib.import_module(module_name)
                for name in dir(module):
                    obj = getattr(module, name)
                    if inspect.isclass(obj):
                        has_derisk_tool = False
                        for method_name, method in inspect.getmembers(obj, inspect.isfunction):
                            if getattr(method, "__derisk_tool__", False):
                                has_derisk_tool = True
                                break
                        if has_derisk_tool:
                            self.register(obj)
                    elif inspect.isfunction(obj) and getattr(obj, "__derisk_tool__", False):
                        self.register(obj)
            except Exception as e:
                logger.warning(f"Failed to load module {module_name}: {e}")

        logger.info(f"Registered local tool functions: {self.get_registry()}")

        rm = get_resource_manager(system_app)
        gpts_tools, gpts_tools_name = [], []
        for class_name, methods in self.registry.items():
            for func_name, method_info in methods.items():
                func = method_info['function']
                rm.register_resource(resource_instance=func, resource_type=ResourceType.Tool, resource_type_alias='tool(local_v2)')
                registration_data = func._to_register
                config = json.dumps({
                    'class_name': class_name,
                    'method_name': func_name,
                    'description': registration_data['description'],
                    'input_schema': registration_data['input_schema']
                }, ensure_ascii=False)
                gpts_tools_name.append(registration_data['name'])
                gpts_tools.append(GptsTool(
                    tool_name=registration_data['name'],
                    tool_id=str(uuid.uuid4()),
                    type='LOCAL',
                    owner=registration_data['owner'],
                    config=config
                ))
        for func_name, func_info in self.standalone_functions.items():
            func = func_info['function']
            rm.register_resource(resource_instance=func, resource_type=ResourceType.Tool, resource_type_alias='tool(local_v2)')
            registration_data = func._to_register
            config = json.dumps({
                'method_name': func_name,
                'description': registration_data['description'],
                'input_schema': registration_data['input_schema']
            }, ensure_ascii=False)
            gpts_tools_name.append(registration_data['name'])
            gpts_tools.append(GptsTool(
                tool_name=registration_data['name'],
                tool_id=str(uuid.uuid4()),
                type='LOCAL',
                owner=registration_data['owner'],
                config=config
            ))
        cur_local_tools = gpts_tool_dao.get_tool_by_type('LOCAL')
        cur_local_tools_name = [tool.tool_name for tool in cur_local_tools]
        add_local_tools = [tool for tool in gpts_tools if tool.tool_name not in cur_local_tools_name]
        add_local_tools_name = [tool.tool_name for tool in add_local_tools]
        #exist_local_tools = [tool for tool in gpts_tools if tool.tool_name in cur_local_tools_name]
        delete_local_tools = [tool for tool in cur_local_tools if tool.tool_name not in gpts_tools_name]
        delete_local_tools_name = [tool.tool_name for tool in delete_local_tools]

        logger.info(f"exist_local_tools: {cur_local_tools_name}")
        logger.info(f"add_local_tools: {add_local_tools_name}")
        logger.info(f"delete_local_tools: {delete_local_tools_name}")
        # 增量创建
        for tool in add_local_tools:
            gpts_tool_dao.create(tool)
        # 存量更新
        # for tool in exist_local_tools:
        #     gpts_tool_dao.update_tool(tool)
        # 删除过滤
        # for tool in delete_local_tools:
        #     gpts_tool_dao.delete_by_tool_id(tool.tool_id)

        # Register AgentSkill resource (skills from database)
        try:
            from derisk.agent.resource.agent_skills import register_agent_skill_resource
            register_agent_skill_resource(system_app)
            logger.info("AgentSkill resource registered successfully")
        except Exception as e:
            logger.warning(f"Failed to register AgentSkill resource: {e}")


central_registry = CentralFunctionRegistry()
