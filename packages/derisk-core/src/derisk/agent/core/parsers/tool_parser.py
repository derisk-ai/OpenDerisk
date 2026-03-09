import json
import uuid
from typing import Type, List, Any, Optional

from derisk.agent import Action, Resource
from derisk.agent.core.action_parser import ActionParser
from derisk.agent.expand.actions.tool_action import ToolInput
from derisk.agent.resource import BaseTool, ToolPack
from derisk_ext.agent.actions.ant_tool_action import AntToolAction


class ToolParser(ActionParser):
    @property
    def action_typ(self) -> Type[Action]:
        return AntToolAction

    @property
    def resource_types(self) -> List[Type[Resource]]:
        return [BaseTool, ToolPack]

    async def _resources_to_functions(
        self, all_resources: Resource
    ) -> Optional[List[dict]]:
        resource_map = await self._tidy_resource(all_resources)
        used_resources = []
        for item in self.resource_types:
            type_resources = resource_map.get(item.type())
            if type_resources:
                used_resources.extend(type_resources)
        functions = []
        for item in used_resources:
            tool = item  # type: ignore

            # 新框架 ToolBase: 使用 to_openai_tool() 方法
            if hasattr(tool, "to_openai_tool"):
                openai_tool = tool.to_openai_tool()
                self.functions.append(tool.name)
                functions.append(openai_tool)
                continue

            # 旧框架 BaseTool: 使用 args 属性
            properties = {}
            required_list = []
            for key, value in tool.args.items():
                properties[key] = {
                    "type": value.type,
                    "description": value.description,
                }
                if value.required:
                    required_list.append(key)
            parameters_dict = {
                "type": "object",
                "properties": properties,
                "required": required_list,
            }

            function: dict = {
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters_dict,
            }
            self.functions.append(tool.name)
            functions.append({"type": "function", "function": function})
        return functions

    async def _resources_to_prompt(
        self, all_resources: Resource
    ) -> Optional[List[dict]]:
        pass

    async def _functions_to_action(
        self, function_call_param: dict, thought: Optional[str] = None
    ) -> Action:
        function_name: str = function_call_param["function"].get("name")

        tool_call_id = function_call_param["id"]
        # 参数解析
        func_args = function_call_param["function"].get("arguments")
        args = {}
        if func_args:
            args = json.loads(func_args) if isinstance(func_args, str) else func_args
        action_cls = self.action_typ

        action_input = self.build_action_input(
            func_name=function_name,
            thought=thought,
            args=args,
        )
        action = action_cls(action_uid=tool_call_id)
        action.action_input = action_input

        return action

    async def _out_to_action(self, plan: dict, thought: Optional[str] = None) -> Action:
        action_cls = self.action_typ

        action_input = self.build_action_input(
            func_name=plan.get("action"),
            thought=thought,
            args=plan.get("action_input"),
        )

        action = action_cls(action_uid=uuid.uuid4().hex)
        action.action_input = action_input
        return action

    def build_action_input(
        self, func_name: str, args: Optional[dict], thought: Optional[str] = None
    ) -> Any:
        return ToolInput(
            tool_name=func_name,
            args=args,
            thought=thought,
        )
