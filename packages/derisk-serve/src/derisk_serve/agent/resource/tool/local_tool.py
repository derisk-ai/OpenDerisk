import dataclasses
import json
import logging
from functools import partial
from typing import Type, Optional, Any, List, cast

from derisk.agent.resource import PackResourceParameters
from derisk.agent.resource.tool.base import ToolFunc
from derisk.agent.resource.tool.pack import ToolPack, json_parse_execute_args_func
from derisk.util import ParameterDescription
from derisk.util.global_helper import truncate_text
from derisk.util.i18n_utils import _
from derisk.util.tracer import root_tracer
from derisk_serve.agent.app.controller import gpts_tool_dao
from derisk_serve.agent.db.gpts_tool_messages import GptsToolMessagesDao, GptsToolMessages
from derisk_serve.agent.resource.func_registry import central_registry
from derisk_serve.agent.resource.tool.mcp_utils import switch_mcp_input_schema

logger = logging.getLogger(__name__)
gpts_tool_messages_dao = GptsToolMessagesDao()


@dataclasses.dataclass
class LocalToolPackResourceParameters(PackResourceParameters):
    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
            cls,
            parameters: Type["LocalToolPackResourceParameters"],
            version: Optional[str] = None,
            **kwargs,
    ) -> Any:
        """Convert the parameters to configurations."""
        conf: List[ParameterDescription] = cast(
            List[ParameterDescription], super().to_configurations(parameters)
        )
        version = version or cls._resource_version()
        if version != "v1":
            for param in conf:
                if param.param_name == "tool_name":
                    try:
                        tools = gpts_tool_dao.get_tool_by_type('LOCAL')
                        filter_tools = []
                        user_code = kwargs.get("user_code")
                        sys_code = kwargs.get("sys_code")
                        if user_code and sys_code:
                            for tool in tools:
                                if tool.owner == user_code or tool.owner == sys_code:
                                    filter_tools.append(tool)
                        else:
                            filter_tools = tools
                        param.valid_values = [
                            {
                                "label": tool.label,
                                "key": tool.tool_name,
                                "description": tool.description,
                                "name": tool.tool_name,
                            }
                            for tool in filter_tools
                        ]
                    except Exception as e:
                        logger.error(f"get local tool error: {e}")
        return conf
        # Compatible with old version
        for param in conf:
            if param.param_name == "tool_name":
                try:
                    tools = gpts_tool_dao.get_tool_by_type('LOCAL')
                    filter_tools = []
                    user_code = kwargs.get("user_code")
                    sys_code = kwargs.get("sys_code")
                    if user_code and sys_code:
                        for tool in tools:
                            if tool.owner == user_code or tool.owner == sys_code:
                                filter_tools.append(tool)
                    else:
                        filter_tools = tools
                    param.valid_values = [tool.tool_name for tool in filter_tools]
                except Exception as e:
                    logger.error(f"get local tool error: {e}")
                return param.valid_values or []
        return []

    @classmethod
    def from_dict(
            cls, data: dict, ignore_extra_fields: bool = True
    ) -> "LocalToolPackResourceParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        if "tool_id" not in copied_data and "value" in copied_data:
            copied_data["tool_id"] = copied_data.pop("value")
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


class LocalToolPack(ToolPack):
    def __init__(self, tool_func: List[ToolFunc] = None, tool_id: str = None, tool_name: str = None, nex_tool_id: str = None, **kwargs):
        super().__init__([], **kwargs)
        self.tool_configs = []
        for func in tool_func or ():
            if not hasattr(func, '_to_register'):
                continue
            central_registry.register(func)
            self.tool_configs.append({
                'method_name': func._to_register['name'],
                'description': func._to_register['description'],
                'input_schema': func._to_register['input_schema'],
                'ask_user': func._to_register['ask_user']
            })
        if tool_id or tool_name:
            self.tool_configs = [{
                'tool_id': tool_id,
                'tool_name': tool_name,
                'nex_tool_id': nex_tool_id,
            }]

    @classmethod
    def type_alias(cls) -> str:
        return "tool(local)"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[LocalToolPackResourceParameters]:
        logger.info(f"resource_parameters_class:{kwargs}")

        @dataclasses.dataclass
        class _DynLocalToolPackResourceParameters(LocalToolPackResourceParameters):
            tool_id: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Local tool id"),
                },
            )
            tool_name: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _(
                        'tool name, use method_name if not set'
                    ),
                },
            )
            nex_tool_id: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Next tool id"),
                },
            )

        return _DynLocalToolPackResourceParameters

    async def preload_resource(self):
        """Preload the resource."""
        trace_id = getattr(root_tracer.get_current_span(), 'trace_id', None)
        cookie = root_tracer.get_context_cookie()
        central_registry.set_context_entry('Cookie', cookie)

        for tool_config in self.tool_configs:
            try:
                tool_id, method_name, class_name = tool_config.get('tool_id', None), tool_config.get('method_name', None), None
                tool_name, description, input_schema = tool_config.get('tool_name', None), tool_config.get('description', None), tool_config.get('input_schema', None)
                nex_tool_id = tool_config.get('nex_tool_id', None)
                ask_user = False

                if tool_id or tool_name:
                    if tool_id:
                        tool = gpts_tool_dao.get_tool_by_tool_id(tool_id)
                    else:
                        tool = gpts_tool_dao.get_tool_by_name(tool_name)
                    if not tool:
                        logger.warning(f"tool {tool_id} not found, skipping")
                        continue
                    config = json.loads(tool.config)
                    class_name, method_name = config.get('class_name', None), config.get('method_name', method_name)
                    description, input_schema = config.get('description', description), config.get('input_schema', input_schema)
                    ask_user = config.get('ask_user', False)
                    nexa_relation_config_map = config.get('nexa_relation_config', None)
                    if nexa_relation_config_map and nex_tool_id:
                        nexa_relation_config_str = nexa_relation_config_map.get(nex_tool_id, None)
                        if nexa_relation_config_str:
                            nexa_relation_config = json.loads(nexa_relation_config_str)
                            input_schema = nexa_relation_config.get('inputSchema', input_schema)
                            description = nexa_relation_config.get('description', description)
                            ask_user = nexa_relation_config.get('askUser', False) if 'askUser' in nexa_relation_config else ask_user

                logger.info(
                    f"call_local_tool:{trace_id}, {method_name}, {nex_tool_id}")

                async def call_local_tool(tool_id: str, class_name: Optional[str], method_name: str, **kwargs):
                    gpts_tool_messages = GptsToolMessages(
                        tool_id=tool_id,
                        name=method_name,
                        type='LOCAL',
                        success=1,
                        input=json.dumps(kwargs, ensure_ascii=False),
                        trace_id=trace_id
                    )
                    try:
                        result = await central_registry.call_registered_function(class_name, method_name, **kwargs)
                        gpts_tool_messages.output = truncate_text(f'{result}', 65535)
                        return result
                    except Exception as e:
                        gpts_tool_messages.success = 0
                        gpts_tool_messages.error = str(e)
                        raise e
                    finally:
                        try:
                            if trace_id:
                                gpts_tool_messages_dao.create(gpts_tool_messages)
                        except Exception as m:
                            logger.error(f"call_local_tool: save message error:{m}, trace_id:{trace_id}")

                if isinstance(input_schema, str):
                    input_schema = json.loads(input_schema)
                args = switch_mcp_input_schema(input_schema)

                # 使用偏函数绑定固定参数
                bound_call = partial(
                    call_local_tool,
                    tool_id=tool_id,
                    class_name=class_name,
                    method_name=method_name
                )
                self.add_command(
                    description,
                    method_name,
                    args,
                    bound_call,
                    parse_execute_args_func=json_parse_execute_args_func,
                    overwrite=True,
                    ask_user = ask_user,
                )
            except Exception as e:
                logger.error(f"call_local_tool:{trace_id}, {tool_config}, error:{e}")
                raise e
