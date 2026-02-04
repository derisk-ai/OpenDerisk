import dataclasses
import logging

from typing import Any, List, Optional, Type, Union, cast, Dict, Tuple

import cachetools

from derisk._private.config import Config
from derisk.agent import ResourceType
from derisk.util.cache_utils import cached
from derisk.util.template_utils import render
from derisk.agent.resource import PackResourceParameters, Resource
from derisk.util import ParameterDescription
from derisk.util.i18n_utils import _

logger = logging.getLogger(__name__)
CFG = Config()

agent_skill_prompt_template = """<agent-skills>
这里是你可使用的agent-skill的元数据信息，skill的完整文件存在沙箱环境计算机的技能仓库目录中。下面是skill的基础信息包含skill名称'name'，能力介绍'description', 相对路径:'path', 仓库分支:'branch'.
{% for item in skills %}\
<{{loop.index }}>\
<name>{{item.name }}</name>
<description>{{item.description}}</description>
{% if item.path %}\
<path>{{item.path}}</path>
{% endif %}\
{% if item.owner %}\
<owner>{{item.owner}}</owner>
{% endif %}\
{% if item.branch %}\
<branch>{{item.branch}}</branch>
{% endif %}\
</{{loop.index}}>
{% endfor %}\
</agent-skills>"""


@dataclasses.dataclass
class SkillMeta:
    name: str
    description: str
    allowed_tools: Optional[List[str]] = None
    owner: Optional[str] = None
    domain: Optional[str] = None
    path: Optional[str] = None

    def to_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass
class SkillInfo:
    name: Optional[str] = None
    meta_map: dict[str, SkillMeta] = dataclasses.field(default_factory=dict)
    parent_folder: Optional[str] = None
    # key 'debug'、'release'

    # debug: Optional[SkillBranch] = None
    # release: Optional[SkillBranch] = None


@dataclasses.dataclass
class AgentSkillResourceParameters(PackResourceParameters):
    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
        cls,
        parameters: Type["AgentSkillResourceParameters"],
        version: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Convert the parameters to configurations."""
        conf: List[ParameterDescription] = cast(
            List[ParameterDescription], super().to_configurations(parameters)
        )
        version = version or cls._resource_version()
        return conf

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "AgentSkillResourceParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


class AgentSkillResource(Resource):
    def __init__(self, name: str = "SKILL Resource", **kwargs):
        """Initialize the skill resource ."""
        if 'description' in kwargs and 'path' in kwargs:
            self._skill: SkillInfo = SkillInfo(
                name=name,
                meta_map={
                    'release': SkillMeta(
                        name=name,
                        description=kwargs['description'],
                        path=kwargs['path'],
                    )
                },
            )
        self._name = name
        self.debug_info = kwargs.get('debug_info', None)

    @property
    def name(self) -> str:
        """Return the resource name."""
        return self._name

    def skill_meta(self, mode: Optional[str] = "release") -> Optional[SkillMeta]:
        return self._skill.meta_map.get(mode)

    @classmethod
    def type(cls) -> Union[ResourceType, str]:
        """Return the resource type."""
        return "skill"

    @classmethod
    def type_alias(cls) -> str:
        return "skill"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[AgentSkillResourceParameters]:
        logger.info(f"resource_parameters_class:{kwargs}")

        @dataclasses.dataclass
        class _DynAgentSkillResourceParameters(AgentSkillResourceParameters):
            name: str = dataclasses.field(
                default="skill name",
                metadata={
                    "help": _("skill name"),
                },
            )
            description: str = dataclasses.field(
                default="skill description",
                metadata={
                    "help": _("skill description"),
                },
            )
            path: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("skill path"),
                },
            )

        return _DynAgentSkillResourceParameters

    @cached(cachetools.TTLCache(maxsize=100, ttl=10))
    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, Optional[List[Dict]]]:
        """Get the prompt."""
        if not self._skill:
            return "No Skills provided.", None

        mode, branch = "release", "master"
        if self.debug_info and self.debug_info.get('is_debug'):
            mode, branch = "debug", self.debug_info.get('branch')
        params = {
            "skills": [
                {
                    "name": self.skill_meta(mode).name,
                    "description": self.skill_meta(mode).description,
                    "path": self._skill.parent_folder,
                    "owner": self.skill_meta(mode).owner,
                    "branch": branch
                }
            ]
        }

        agent_skill_meta_prompt = render(agent_skill_prompt_template, params)
        agent_skill_meta: List[Dict] = [self.skill_meta(mode).to_dict()]
        return agent_skill_meta_prompt, agent_skill_meta
