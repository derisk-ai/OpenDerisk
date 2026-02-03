import dataclasses
import logging
import os
import re
from typing import Any, List, Optional, Type, Union, cast, Dict, Tuple

import cachetools

from derisk._private.config import Config
from derisk.agent import ResourceType
from derisk.util.cache_utils import cached
from derisk.util.template_utils import render
from derisk.agent.resource import PackResourceParameters, Resource, ResourceParameters
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
        parameters: Type[ResourceParameters],
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


def _parse_skill_md(file_path: str) -> Optional[Dict[str, str]]:
    try:
        if not os.path.exists(file_path):
            return None
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract frontmatter
        match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not match:
            return None
            
        frontmatter = match.group(1)
        data = {}
        
        # Simple YAML-like parsing for name and description
        name_match = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
        if name_match:
            data['name'] = name_match.group(1).strip()
            
        desc_match = re.search(r'^description:\s*(.+)$', frontmatter, re.MULTILINE | re.DOTALL)
        if desc_match:
            # Handle multi-line description if needed, but for now assuming single line or simple wrap
            # This regex might need to be more robust for complex yaml, but sufficient for the example
            desc = desc_match.group(1).strip()
            # If description continues on next lines (indented), we might miss it with simple regex
            # But let's assume simple format for now based on SKILL.md example
            data['description'] = desc
            
        return data
    except Exception as e:
        logger.warning(f"Failed to parse skill metadata from {file_path}: {e}")
        return None

def _load_local_skills(root_path: str) -> List[Dict[str, Any]]:
    skills = []
    if not os.path.exists(root_path):
        return skills

    for entry in os.scandir(root_path):
        if entry.is_dir():
            skill_md_path = os.path.join(entry.path, "SKILL.md")
            if os.path.exists(skill_md_path):
                meta = _parse_skill_md(skill_md_path)
                if meta and 'name' in meta:
                    skills.append({
                        "name": meta['name'],
                        "description": meta.get('description', ''),
                        "path": entry.path,
                        "owner": "local",
                        "branch": "master"
                    })
    return skills


def _load_skills_from_db() -> List[Dict[str, Any]]:
    """Load available skills from the database.

    Returns:
        List[Dict[str, Any]]: List of skill metadata dictionaries
    """
    skills = []

    try:
        # Try to get the skill service from system app
        from derisk.component import SystemApp as TrekSystemApp

        # Get the system app instance
        system_app = TrekSystemApp.get_instance()
        if system_app:
            try:
                from derisk_serve.skill.service import Service, SKILL_SERVICE_COMPONENT_NAME
                from derisk_serve.skill.api.schemas import SkillQueryFilter

                service: Optional[Service] = system_app.get_component(
                    SKILL_SERVICE_COMPONENT_NAME, Service, default=None
                )

                if service:
                    # Get all available skills from database
                    filter_request = SkillQueryFilter()
                    query_result = service.filter_list_page(filter_request, page=1, page_size=1000)

                    for skill in query_result.items:
                        if skill.available:
                            skills.append({
                                "name": skill.name,
                                "description": skill.description,
                                "path": skill.path or skill.skill_code,
                                "owner": skill.author or "database",
                                "branch": skill.branch or "master"
                            })

                    logger.info(f"Loaded {len(skills)} skills from database")
            except Exception as e:
                logger.debug(f"Service not available or error loading from database: {e}")
    except Exception as e:
        logger.debug(f"System app not available: {e}")

    return skills


class AgentSkillResource(Resource):
    def __init__(self, name: str = "SKILL Resource", **kwargs):
        """Initialize the skill resource ."""
        self._skill: Optional[SkillInfo] = None
        if 'description' in kwargs and 'path' in kwargs:
            self._skill = SkillInfo(
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
        
        # Configure local skills path
        self._local_skills_path = "/Users/tuyang.yhj/Code/python/skills/skills"

    @property
    def name(self) -> str:
        """Return the resource name."""
        return self._name

    def skill_meta(self, mode: Optional[str] = "release") -> Optional[SkillMeta]:
        if not self._skill:
            return None
        return self._skill.meta_map.get(mode or "release")

    @classmethod
    def type(cls) -> Union[ResourceType, str]:
        """Return the resource type."""
        return "skill"

    @classmethod
    def type_alias(cls) -> str:
        return "tool(skill)"

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
    ) -> Tuple[str, Optional[Dict]]:
        """Get the prompt."""
        skills_list = []

        # Load skills from database first (highest priority)
        db_skills = _load_skills_from_db()
        skills_list.extend(db_skills)

        # Load local skills as fallback
        if self._local_skills_path:
            local_skills = _load_local_skills(self._local_skills_path)
            # Avoid duplicates by skill name
            existing_names = {skill["name"] for skill in skills_list}
            for skill in local_skills:
                if skill["name"] not in existing_names:
                    skills_list.append(skill)

        # Add single skill if configured
        if self._skill:
            mode, branch = "release", "master"
            if self.debug_info and self.debug_info.get('is_debug'):
                mode, branch = "debug", self.debug_info.get('branch')

            meta = self.skill_meta(mode)
            if meta:
                skill_name = meta.name
                # Check for duplicates
                existing_names = {skill["name"] for skill in skills_list}
                if skill_name not in existing_names:
                    skills_list.append({
                        "name": meta.name,
                        "description": meta.description,
                        "path": self._skill.parent_folder or meta.path,
                        "owner": meta.owner,
                        "branch": branch
                    })

        if not skills_list:
            return "No Skills provided.", None

        params = {
            "skills": skills_list
        }

        agent_skill_meta_prompt = render(agent_skill_prompt_template, params)
        # For metadata return, we might want to return the full list or just the main one
        # Depending on how the caller uses it. Returning the list of dicts.
        # But the type signature requires Optional[Dict], so let's wrap it
        return agent_skill_meta_prompt, {"skills": skills_list}


# Singleton instance for registration
_AgentSkillResource_Instance: Optional[AgentSkillResource] = None


def register_agent_skill_resource(system_app):
    """Register the AgentSkill resource with the resource manager.

    This function should be called during system initialization to ensure
    the AgentSkill resource is available for Agents to bind and use.

    Args:
        system_app: The SystemApp instance
    """
    global _AgentSkillResource_Instance

    if _AgentSkillResource_Instance is None:
        from derisk.agent.resource import get_resource_manager

        # Create the resource instance
        _AgentSkillResource_Instance = AgentSkillResource()

        # Register with the resource manager as an instance
        rm = get_resource_manager(system_app)
        rm.register_resource(
            resource_instance=_AgentSkillResource_Instance,
            resource_type=ResourceType.Tool,
            resource_type_alias="tool(skill)",
            ignore_duplicate=True,
        )

        logger.info("AgentSkill resource registered successfully as instance")

    return _AgentSkillResource_Instance


def get_agent_skill_resource() -> Optional[AgentSkillResource]:
    """Get the AgentSkill resource instance.

    Returns:
        The AgentSkill resource instance, or None if not yet registered.
    """
    return _AgentSkillResource_Instance
