import json
from abc import ABC
from typing import List, Type, Optional, Any

from derisk.agent import Action, Resource
from derisk.agent.resource import ResourcePack


class ActionParser(ABC):
    """
    对于需要执行消费的资源，进行资源解压和输入转换，并对输入反解析为action.(记录每个可执行最细粒度资源)
    """

    def __init__(self):
        self._functions: List[str] = []

    @property
    def action_type(self) -> Type[Action]:
        raise NotImplementedError

    @property
    def resource_types(self) -> List[Type[Resource]]:
        raise NotImplementedError

    @property
    def functions(self) -> List[str]:
        return self._functions



    def unpack_ability_resource(self, resource: Resource) -> list[Resource]:
        if not resource:
            return []
        temp_types = [item.type() for item in self.resource_types]
        if resource.is_pack and resource.sub_resources:
            result = []
            for r in resource.sub_resources:
                if r.type() in temp_types:
                    result.append(r)
                elif r.is_pack:
                    result.extend(self.unpack_ability_resource(r))
            return result
        elif resource.type() in temp_types:
            return [resource]
        return []

    async def _resources_to_functions(self, all_resources: Resource) -> Optional[List[dict]]:
        """将模型可消费资源"""
        raise NotImplementedError

    async def _resources_to_prompt(self, all_resources: Resource) -> Optional[List[dict]]:
        raise NotImplementedError

    async def resources_to_llm_in(self, all_resources: Resource, use_function_call: bool = False) -> Optional[ List[dict]]:
        """
        模型可消费资源转模型输入
        """

        if use_function_call:
            return await self._resources_to_functions(all_resources)
        else:
            return await self._resources_to_prompt(all_resources)

    async def _out_to_action(self, function_call_param: dict, thought: Optional[str] = None) -> Action:
        pass

    async def _functions_to_action(self, function_call_param: dict, thought: Optional[str] = None) -> Action:
        pass

    async def llm_out_to_actions(self, item: Any, use_function_call: bool = False) -> Action:
        """
        模型输出的当前资源使用转Action
        """
        if use_function_call:
            return await self._functions_to_action(item)
        else:
            return await self._out_to_action(item)
