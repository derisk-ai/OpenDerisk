from typing import Type, List, Optional

from derisk.agent import Resource
from derisk.agent.core.parsers.tool_parser import ToolParser
from derisk.agent.resource import RetrieverResource


class KnowledgeParser(ToolParser):

    @property
    def resource_types(self) -> List[Type[Resource]]:
        return [RetrieverResource]

    async def _resources_to_functions(self, all_resources: Resource) -> Optional[List[dict]]:
        return await super()._resources_to_functions(all_resources)

    async def _resources_to_prompt(self, all_resources: Resource) -> Optional[List[dict]]:
        return await super()._resources_to_prompt(all_resources)

