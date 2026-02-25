"""DeriskSkill Resource - Manage AgentSkills from the database.

This resource queries skill data from the skill module and serves it as a resource
that Agents can select, bind, and use.

This is similar to APPResource or MCPResource in structure.
"""

import dataclasses
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Type, cast

from derisk._private.config import Config
from derisk.agent import ResourceType
from derisk.agent.resource import PackResourceParameters, Resource, ResourceParameters
from derisk.agent.resource.agent_skills import AgentSkillResource
from derisk.util import ParameterDescription
from derisk.util.template_utils import render
from derisk.util.i18n_utils import _

# Skill prompt template
agent_skill_prompt_template = """<agent-skills>
这里是你可使用的agent-skill的元数据信息，skill的完整文件存在沙箱环境计算机的技能仓库目录中。下面是skill的基础信息包含skill名称'name'，能力介绍'description', 相对路径:'path', 仓库分支:'branch'.
{% for item in skills %}\
<{{loop.index }}>\
<name>{{item.name}}</name>
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
</{{loop.index }}>
{% endfor %}\
</agent-skills>"""


def _load_skills_from_db() -> List[Dict[str, Any]]:
    """Load available skills from the database."""
    skills = []

    try:
        from derisk.agent.resource.manage import _SYSTEM_APP

        if _SYSTEM_APP:
            try:
                from derisk_serve.skill.service.service import (
                    Service,
                    SKILL_SERVICE_COMPONENT_NAME,
                )
                from derisk_serve.skill.api.schemas import SkillQueryFilter

                service: Optional[Service] = _SYSTEM_APP.get_component(
                    SKILL_SERVICE_COMPONENT_NAME, Service, default=None
                )

                if service:
                    filter_request = SkillQueryFilter(filter="")
                    query_result = service.filter_list_page(
                        filter_request, page=1, page_size=1000
                    )

                    for skill in query_result.items:
                        if skill.available is not False:
                            skills.append(
                                {
                                    "name": skill.name,
                                    "skill_code": skill.skill_code,
                                    "description": skill.description,
                                    "path": skill.path or skill.skill_code,
                                    "owner": skill.author or "database",
                                    "branch": skill.branch or "main",
                                }
                            )

                    logger.info(f"Loaded {len(skills)} skills from database")
                else:
                    logger.warning("Skill service not available")
            except Exception as e:
                logger.warning(f"Error loading skills from database: {e}")
        else:
            logger.warning("System app not initialized")
    except Exception as e:
        logger.warning(f"Failed to import _SYSTEM_APP: {e}")

    return skills


logger = logging.getLogger(__name__)
CFG = Config()


@dataclasses.dataclass
class DeriskSkillResourceParameters(PackResourceParameters):
    """Parameters for DeriskSkill resource."""

    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v2"

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
        return conf

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "DeriskSkillResourceParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


class DeriskSkillResource(AgentSkillResource):
    """DeriskSkill resource class.

    This resource manages AgentSkills loaded from the skill module database.
    It provides skill metadata as resources that Agents can bind and use.

    The resource inherits the behavior of AgentSkillResource but is specifically
    designed for database-backed skills managed through the Skill REST API.
    """

    def __init__(self, name: str = "DeriskSkill Resource", **kwargs):
        """Initialize the DeriskSkill resource."""
        self._resource_name = name
        self._skill_name = kwargs.get("skill_name", name)
        self._skill_code = kwargs.get(
            "skill_code", kwargs.get("skillCode", self._skill_name)
        )
        self._skill_description = kwargs.get(
            "skill_description", kwargs.get("description")
        )
        self._skill_path = kwargs.get("skill_path", kwargs.get("path"))
        self._skill_branch = kwargs.get("skill_branch", kwargs.get("branch", "main"))
        self._skill_author = kwargs.get("skill_author", kwargs.get("owner"))

        sandbox_path = self._get_sandbox_path()

        parent_kwargs = {
            "description": self._skill_description,
            "path": self._skill_path,
            "owner": self._skill_author,
            "parent_folder": sandbox_path,
            **kwargs,
        }
        super().__init__(name, **parent_kwargs)

    def _get_sandbox_path(self) -> Optional[str]:
        """Get sandbox path for the skill using skill_code."""
        try:
            from derisk_serve.skill.service.service import (
                Service,
                SKILL_SERVICE_COMPONENT_NAME,
            )
            from derisk.agent.resource.manage import _SYSTEM_APP

            if _SYSTEM_APP and self._skill_code:
                service = _SYSTEM_APP.get_component(
                    SKILL_SERVICE_COMPONENT_NAME, Service, default=None
                )
                if service:
                    skill_dir = service.get_skill_directory(self._skill_code)
                    if skill_dir and os.path.exists(skill_dir):
                        return skill_dir
        except Exception as e:
            logger.warning(f"Error getting sandbox path: {e}")
        return None

    @property
    def name(self) -> str:
        """Return the resource name."""
        return self._resource_name

    @property
    def skill_name(self) -> Optional[str]:
        """Return the skill name."""
        return self._skill_name

    @property
    def skill_code(self) -> Optional[str]:
        """Return the skill code."""
        return self._skill_code

    @property
    def description(self) -> Optional[str]:
        """Return the skill description."""
        return self._skill_description

    @property
    def path(self) -> Optional[str]:
        """Return the skill path (sandbox path)."""
        return self._skill_path

    @property
    def branch(self) -> Optional[str]:
        """Return the skill branch."""
        return self._skill_branch

    @property
    def owner(self) -> Optional[str]:
        """Return the skill owner."""
        return self._skill_author

    @classmethod
    def type(cls) -> str:
        """Return the resource type.

        Returns 'skill(derisk)' which is the same type as AgentSkillResource.
        """
        return "skill(derisk)"

    @classmethod
    def type_alias(cls) -> str:
        """Return the resource type alias."""
        return "skill(derisk)"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[DeriskSkillResourceParameters]:
        """Return the resource parameters class.

        This method generates a dynamic parameters class that includes:
        - skill_name: The name of the selected skill
        - skill_description: The description of the selected skill
        - skill_path: The path to the skill files

        Valid values are populated by querying the skill database.
        """
        logger.info(f"resource_parameters_class: {kwargs}")

        @dataclasses.dataclass
        class _DynDeriskSkillResourceParameters(DeriskSkillResourceParameters):
            skills_list = _load_skills_from_db()
            valid_values = [
                {
                    "label": f"[{skill['name']}]{skill.get('description', '')}",
                    "key": skill["name"],
                    "skill_code": skill.get("skill_code", skill["name"]),
                    "skill_name": skill["name"],
                    "description": skill.get("description", ""),
                    "skill_path": skill.get("path", skill["name"]),
                    "skill_branch": skill.get("branch", "main"),
                    "skill_author": skill.get("owner", "database"),
                }
                for skill in skills_list
            ]

            name: str = dataclasses.field(
                default="DeriskSkill",
                metadata={
                    "help": _("Resource name"),
                },
            )
            skill_name: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Skill name"),
                    "valid_values": valid_values,
                },
            )
            skill_description: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Skill description"),
                    "valid_values": valid_values,
                },
            )
            skill_path: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Skill path"),
                    "valid_values": valid_values,
                },
            )
            skill_branch: Optional[str] = dataclasses.field(
                default="main",
                metadata={
                    "help": _("Skill branch"),
                    "valid_values": valid_values,
                },
            )
            skill_author: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Skill author"),
                    "valid_values": valid_values,
                },
            )

            @classmethod
            def to_configurations(
                cls,
                parameters: Type["ResourceParameters"],
                version: Optional[str] = None,
                **kwargs,
            ) -> Any:
                """Convert the parameters to configurations."""
                conf: List[ParameterDescription] = cast(
                    List[ParameterDescription], super().to_configurations(parameters)
                )
                version = version or cls._resource_version()
                if version != "v1":
                    return conf
                for param in conf:
                    if param.param_name == "skill_name":
                        return param.valid_values or []
                return []

            @classmethod
            def from_dict(
                cls, data: dict, ignore_extra_fields: bool = True
            ) -> "DeriskSkillResourceParameters":
                """Create a new instance from a dictionary."""
                copied_data = data.copy()
                return super().from_dict(
                    copied_data, ignore_extra_fields=ignore_extra_fields
                )

        return _DynDeriskSkillResourceParameters

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, Optional[Dict]]:
        """Get the prompt.

        This method returns the skill information for the current resource instance.

        Returns:
            Tuple[str, Optional[Dict]]: A tuple containing the rendered prompt
                and metadata about the loaded skills.
        """
        # Get sandbox path for the skill if available
        sandbox_path = None
        skill_code = self._skill_code if self._skill_code else self._skill_name

        try:
            from derisk_serve.skill.service.service import (
                Service,
                SKILL_SERVICE_COMPONENT_NAME,
            )
            from derisk_serve.skill.api.schemas import SkillRequest
            from derisk.agent.resource.manage import _SYSTEM_APP

            if _SYSTEM_APP:
                service = _SYSTEM_APP.get_component(
                    SKILL_SERVICE_COMPONENT_NAME, Service, default=None
                )
                if service and skill_code:
                    skill_dir = service.get_skill_directory(skill_code)
                    if skill_dir:
                        sandbox_path = skill_dir
        except Exception as e:
            logger.warning(f"Error loading skill sandbox path: {e}")

        # Use sandbox path if available, otherwise use stored path
        skill_path = sandbox_path or self._skill_path

        params = {
            "skills": [
                {
                    "name": self._skill_name,
                    "description": self._skill_description,
                    "path": skill_path,
                    "owner": self._skill_author,
                    "branch": self._skill_branch,
                }
            ]
        }

        agent_skill_meta_prompt = render(agent_skill_prompt_template, params)

        # Return both the prompt and the skills metadata
        skill_meta = {
            "name": self._skill_name,
            "description": self._skill_description,
            "path": skill_path,
            "owner": self._skill_author,
            "branch": self._skill_branch,
        }
        return agent_skill_meta_prompt, skill_meta

    @property
    def is_async(self) -> bool:
        """Return whether the resource is asynchronous."""
        return True

    def execute(self, *args, resource_name: Optional[str] = None, **kwargs) -> Any:
        """Execute the resource synchronously (not supported)."""
        if self.is_async:
            raise RuntimeError("Sync execution is not supported")

    async def async_execute(
        self,
        *args,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Execute the tool asynchronously.

        For DeriskSkill, this returns the skill prompt and metadata.
        """
        return await self.get_prompt(
            lang=kwargs.get("lang", "en"),
            prompt_type=kwargs.get("prompt_type", "default"),
            resource_name=resource_name,
            **kwargs,
        )


def register_derisk_skill_resource(system_app):
    """Register the DeriskSkill resource with the resource manager.

    This function should be called during system initialization to ensure
    the DeriskSkill resource is available for Agents to bind and use.

    Args:
        system_app: The SystemApp instance
    """
    from derisk.agent.resource import get_resource_manager

    rm = get_resource_manager(system_app)
    rm.register_resource(
        resource_cls=DeriskSkillResource,
        resource_type=ResourceType.Tool,
        resource_type_alias="skill(derisk)",
        ignore_duplicate=True,
    )

    logger.info("DeriskSkill resource registered successfully")
