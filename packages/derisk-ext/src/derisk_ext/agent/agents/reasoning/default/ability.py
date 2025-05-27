import json
from typing import cast, Union, get_args, Any, Optional, Type

from derisk.agent import ConversableAgent
from derisk.agent.resource import FunctionTool
from derisk_serve.agent.resource.knowledge_pack import KnowledgePackSearchResource

_AbilityType = Union[FunctionTool, ConversableAgent, KnowledgePackSearchResource]


class Ability:
    _ability: _AbilityType = None

    @classmethod
    def by(cls, source: Any) -> Optional["Ability"]:
        if not cls._actual_type(source):
            return None

        # Nex Agent默认有一个KnowledgePackSearchResource配置，但可能实际没有知识，需要踢掉
        if isinstance(source, KnowledgePackSearchResource) and source.is_empty:
            return None

        return Ability().bind(source)

    def bind(self, ability: _AbilityType):
        self._ability = ability
        return self

    @property
    def name(self) -> str:
        if isinstance(self._ability, KnowledgePackSearchResource):
            return "knowledge_retrieve"
        return self._ability.name

    @property
    def description(self) -> str:
        if isinstance(self._ability, FunctionTool):
            return self._ability.name
        elif isinstance(self._ability, ConversableAgent):
            return self._ability.desc
        elif isinstance(self._ability, KnowledgePackSearchResource):
            return self._ability.description
        raise NotImplementedError

    @property
    def actual_type(self) -> Type:
        return self._actual_type(self._ability)

    @classmethod
    def _actual_type(cls, _ability) -> Optional[Type]:
        for _type in get_args(_AbilityType):
            if _ability == _type or isinstance(_ability, _type):
                return _type
        return None
        # return next((_type for _type in get_args(_AbilityType) if isinstance(_ability, _type)), None)

    async def get_prompt(self) -> str:
        if isinstance(self._ability, FunctionTool):
            prompt, _ = await self._ability.get_prompt(lang="zh")
            return prompt

        elif isinstance(self._ability, ConversableAgent):
            agent = cast(ConversableAgent, self._ability)
            return "**id**: " + agent.name + "\n\n**描述**: " + agent.desc

        elif isinstance(self._ability, KnowledgePackSearchResource):
            parameters: list[dict] = [
                {
                    "name": "query",
                    "type": "string",
                    "description": "检索内容",
                    "required": True,
                },
                {
                    "name": "knowledge_ids",
                    "type": "Array",
                    "description": "需要检索相关知识库id列表,['id1','id2'], 如果都不涉及返回[]",
                    "required": True,
                }
            ]
            return f"**id**: {self.name}\n\n**描述**: {self.description} \n\n**参数**:\n\n{json.dumps(parameters, ensure_ascii=False)}"

        raise NotImplementedError
