"""
Action 体系迁移适配器

将原有的 Action 体系适配为 Core_v2 Tool 体系：
- ActionToolAdapter: Action 到 Tool 的适配器
- ActionToolRegistry: Action 工具注册管理
- action_to_tool: Action 转换工厂函数
"""

from typing import Any, Dict, List, Optional, Type, Union
import logging
import asyncio
import uuid

from .tool_base import ToolBase, ToolMetadata, ToolResult, ToolRegistry

logger = logging.getLogger(__name__)


class ActionToolAdapter(ToolBase):
    """
    Action 到 Tool 的适配器
    
    将原有 Action 体系适配为 Core_v2 ToolBase 接口
    """
    
    def __init__(
        self,
        action: Any,
        action_name: Optional[str] = None,
        action_description: Optional[str] = None,
        resource: Optional[Any] = None
    ):
        self._action = action
        self._action_name = action_name or getattr(action, "name", action.__class__.__name__)
        self._action_description = action_description or getattr(action, "__doc__", "")
        self._resource = resource
        self._render_protocol = getattr(action, "_render", None)
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        description = self._action_description
        if not description:
            description = f"Action: {self._action_name}"
        
        parameters = self._extract_action_parameters()
        
        return ToolMetadata(
            name=f"action_{self._action_name.lower()}",
            description=description,
            parameters=parameters,
            requires_permission=False,
            dangerous=False,
            category="action",
            version="1.0.0"
        )
    
    def _extract_action_parameters(self) -> Dict[str, Any]:
        """从 Action 提取参数定义"""
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        ai_out_schema = getattr(self._action, "ai_out_schema_json", None)
        if ai_out_schema:
            try:
                import json
                schema = json.loads(ai_out_schema)
                if isinstance(schema, dict):
                    parameters["properties"] = schema
                elif isinstance(schema, list) and schema:
                    parameters["properties"]["items"] = {
                        "type": "array",
                        "items": schema[0] if isinstance(schema[0], dict) else {}
                    }
            except Exception:
                pass
        
        out_model_type = getattr(self._action, "out_model_type", None)
        if out_model_type:
            try:
                from ...._private.pydantic import model_fields, field_description
                fields = model_fields(out_model_type)
                for field_name, field in fields.items():
                    desc = field_description(field) or field_name
                    parameters["properties"][field_name] = {
                        "type": "string",
                        "description": desc
                    }
                    parameters["required"].append(field_name)
            except Exception:
                pass
        
        return parameters
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        try:
            if hasattr(self._action, "init_action"):
                await self._action.init_action()
            
            if self._resource and hasattr(self._action, "init_resource"):
                self._action.init_resource(self._resource)
            
            if hasattr(self._action, "before_run"):
                await self._action.before_run(action_uid=str(uuid.uuid4().hex))
            
            ai_message = args.get("ai_message", args.get("message", ""))
            resource = args.get("resource", self._resource)
            rely_action_out = args.get("rely_action_out")
            need_vis_render = args.get("need_vis_render", True)
            received_message = args.get("received_message")
            
            run_kwargs = {
                "ai_message": ai_message,
                "resource": resource,
                "rely_action_out": rely_action_out,
                "need_vis_render": need_vis_render,
            }
            if received_message:
                run_kwargs["received_message"] = received_message
            run_kwargs.update({k: v for k, v in args.items() if k not in run_kwargs})
            
            result = self._action.run(**run_kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            
            output = self._format_action_output(result)
            
            metadata = {
                "action_name": self._action_name,
                "is_exe_success": getattr(result, "is_exe_success", True),
                "action_id": getattr(result, "action_id", None),
            }
            
            if hasattr(result, "to_dict"):
                metadata["raw_output"] = result.to_dict()
            
            return ToolResult(
                success=getattr(result, "is_exe_success", True),
                output=output,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"[ActionToolAdapter] 执行失败 {self._action_name}: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    def _format_action_output(self, result: Any) -> str:
        if result is None:
            return "Action 执行完成"
        
        if hasattr(result, "view") and result.view:
            return result.view
        
        if hasattr(result, "content") and result.content:
            return result.content
        
        if hasattr(result, "to_dict"):
            import json
            return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        
        return str(result)
    
    def get_original_action(self) -> Any:
        return self._action
    
    def get_action_name(self) -> str:
        return self._action_name


class ActionToolRegistry:
    """
    Action 工具注册管理器
    
    管理从 Action 到 Tool 的转换和注册
    """
    
    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self._tool_registry = tool_registry or ToolRegistry()
        self._action_adapters: Dict[str, ActionToolAdapter] = {}
        self._action_classes: Dict[str, Type] = {}
    
    def register_action_class(
        self, 
        action_class: Type,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> ActionToolAdapter:
        """注册 Action 类"""
        action_name = name or getattr(action_class, "name", action_class.__name__)
        
        self._action_classes[action_name] = action_class
        
        try:
            action_instance = action_class()
            adapter = ActionToolAdapter(
                action=action_instance,
                action_name=action_name,
                action_description=description
            )
            self._tool_registry.register(adapter)
            self._action_adapters[action_name] = adapter
            
            logger.info(f"[ActionRegistry] 注册 Action 类: {action_name}")
            return adapter
        except Exception as e:
            logger.error(f"[ActionRegistry] 注册 Action 类失败 {action_name}: {e}")
            raise
    
    def register_action_instance(
        self,
        action: Any,
        name: Optional[str] = None,
        description: Optional[str] = None,
        resource: Optional[Any] = None
    ) -> ActionToolAdapter:
        """注册 Action 实例"""
        action_name = name or getattr(action, "name", action.__class__.__name__)
        
        adapter = ActionToolAdapter(
            action=action,
            action_name=action_name,
            action_description=description,
            resource=resource
        )
        
        self._tool_registry.register(adapter)
        self._action_adapters[action_name] = adapter
        
        logger.info(f"[ActionRegistry] 注册 Action 实例: {action_name}")
        return adapter
    
    def unregister_action(self, action_name: str) -> bool:
        """注销 Action"""
        if action_name in self._action_adapters:
            adapter = self._action_adapters[action_name]
            self._tool_registry.unregister(adapter.metadata.name)
            del self._action_adapters[action_name]
            return True
        return False
    
    def get_action_adapter(self, action_name: str) -> Optional[ActionToolAdapter]:
        """获取 Action 适配器"""
        return self._action_adapters.get(action_name)
    
    def list_actions(self) -> List[str]:
        """列出所有已注册的 Action"""
        return list(self._action_adapters.keys())
    
    def get_tool_registry(self) -> ToolRegistry:
        """获取底层工具注册表"""
        return self._tool_registry


def action_to_tool(
    action: Union[Any, Type],
    name: Optional[str] = None,
    description: Optional[str] = None,
    resource: Optional[Any] = None
) -> ActionToolAdapter:
    """
    将 Action 转换为 Tool
    
    Args:
        action: Action 实例或类
        name: 工具名称（可选）
        description: 工具描述（可选）
        resource: 关联资源（可选）
    
    Returns:
        ActionToolAdapter 实例
    """
    if isinstance(action, type):
        try:
            action_instance = action()
        except Exception:
            raise ValueError(f"无法实例化 Action 类: {action}")
    else:
        action_instance = action
    
    return ActionToolAdapter(
        action=action_instance,
        action_name=name,
        action_description=description,
        resource=resource
    )


def register_actions_from_module(
    registry: ToolRegistry,
    module_path: str,
    action_classes: Optional[List[str]] = None
) -> List[ActionToolAdapter]:
    """
    从模块批量注册 Actions
    
    Args:
        registry: 工具注册表
        module_path: 模块路径
        action_classes: 要注册的 Action 类名列表（可选，默认注册所有）
    
    Returns:
        注册的 ActionToolAdapter 列表
    """
    import importlib
    
    adapters = []
    
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        logger.error(f"[ActionRegistry] 无法导入模块 {module_path}: {e}")
        return adapters
    
    for attr_name in dir(module):
        if action_classes and attr_name not in action_classes:
            continue
        
        attr = getattr(module, attr_name)
        
        if isinstance(attr, type) and attr_name.endswith("Action"):
            try:
                from derisk.agent.core.action.base import Action
                if issubclass(attr, Action) and attr is not Action:
                    adapter = action_to_tool(attr)
                    registry.register(adapter)
                    adapters.append(adapter)
                    logger.info(f"[ActionRegistry] 从模块注册: {attr_name}")
            except ImportError:
                pass
    
    return adapters


def create_action_tools_from_resources(
    resources: List[Any],
    action_classes: Optional[Dict[str, Type]] = None
) -> Dict[str, ToolBase]:
    """
    根据资源创建对应的 Action 工具
    
    Args:
        resources: 资源列表
        action_classes: 资源类型到 Action 类的映射
    
    Returns:
        工具名称到工具实例的映射
    """
    tools = {}
    
    default_action_map = action_classes or {}
    
    for resource in resources:
        resource_type = getattr(resource, "type", None)
        if resource_type:
            resource_type = resource_type.value if hasattr(resource_type, "value") else str(resource_type)
        
        action_class = default_action_map.get(resource_type)
        
        if action_class:
            try:
                tool_name = getattr(resource, "name", f"tool_{len(tools)}")
                adapter = action_to_tool(
                    action=action_class,
                    name=tool_name,
                    resource=resource
                )
                tools[tool_name] = adapter
            except Exception as e:
                logger.error(f"[ActionRegistry] 创建工具失败 {resource_type}: {e}")
    
    return tools


class ActionTypeMapper:
    """
    Action 类型映射器
    
    将资源类型映射到对应的 Action 类
    """
    
    def __init__(self):
        self._mappings: Dict[str, Type] = {}
        self._default_action: Optional[Type] = None
    
    def register(self, resource_type: str, action_class: Type):
        """注册资源类型到 Action 的映射"""
        self._mappings[resource_type] = action_class
        logger.debug(f"[ActionMapper] 注册映射: {resource_type} -> {action_class.__name__}")
    
    def set_default(self, action_class: Type):
        """设置默认 Action"""
        self._default_action = action_class
    
    def get_action_class(self, resource_type: str) -> Optional[Type]:
        """获取资源类型对应的 Action 类"""
        return self._mappings.get(resource_type, self._default_action)
    
    def create_tool(
        self, 
        resource_type: str, 
        resource: Optional[Any] = None
    ) -> Optional[ActionToolAdapter]:
        """根据资源类型创建工具"""
        action_class = self.get_action_class(resource_type)
        if action_class:
            return action_to_tool(action_class, resource=resource)
        return None
    
    @classmethod
    def create_default_mapper(cls) -> "ActionTypeMapper":
        """创建默认的映射器"""
        mapper = cls()
        
        try:
            from derisk.agent.expand.actions.tool_action import ToolAction
            mapper.register("tool", ToolAction)
            mapper.set_default(ToolAction)
        except ImportError:
            pass
        
        try:
            from derisk.agent.expand.actions.sandbox_action import SandboxAction
            mapper.register("sandbox", SandboxAction)
        except ImportError:
            pass
        
        try:
            from derisk.agent.expand.actions.knowledge_action import KnowledgeAction
            mapper.register("knowledge", KnowledgeAction)
        except ImportError:
            pass
        
        try:
            from derisk.agent.expand.actions.code_action import CodeAction
            mapper.register("code", CodeAction)
        except ImportError:
            pass
        
        try:
            from derisk.agent.expand.actions.rag_action import RagAction
            mapper.register("rag", RagAction)
        except ImportError:
            pass
        
        try:
            from derisk.agent.expand.actions.chart_action import ChartAction
            mapper.register("chart", ChartAction)
        except ImportError:
            pass
        
        return mapper


default_action_mapper = ActionTypeMapper.create_default_mapper()