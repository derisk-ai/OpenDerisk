"""Role class for role-based conversation."""

import json
import logging
from abc import ABC
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union, Tuple

from jinja2.sandbox import SandboxedEnvironment

from derisk._private.pydantic import BaseModel, ConfigDict, Field
from derisk.core.interface.scheduler import Scheduler
from .action.base import ActionOutput
from .memory.agent_memory import (
    AgentMemory,
    AgentMemoryFragment,
    StructuredAgentMemoryFragment,
)
from .memory.llm import LLMImportanceScorer, LLMInsightExtractor
from .profile import Profile, ProfileConfig
from .. import AgentMessage
from ...context.event import EventType, MemoryWritePayload
from ...util import BaseParameters
from ...util.date_utils import convert_datetime
from ...util.json_utils import serialize
from ...util.tracer import root_tracer

logger = logging.getLogger(__name__)


class PromptType(Enum):
    JINJIA2 = "jinja2"
    FSTRING = "f-string"


class AgentRunMode(str, Enum):
    """Agent run mode."""

    DEFAULT = "default"
    # Run the agent in loop mode, until the conversation is over(Maximum retries or
    # encounter a stop signal)
    LOOP = "loop"
    # Run the agent in trace mode (return directly, continuously update memory in the background) until the conversation ends (reach maximum retry count or Encountering a stop signal)
    TRACKING = "tracking"


class Role(ABC, BaseModel):
    """Role class for role-based conversation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ProfileConfig = Field(
        ...,
        description="The profile of the role.",
    )
    _inited_profile: Profile = None
    memory: AgentMemory = Field(default_factory=AgentMemory)
    scheduler: Optional[Scheduler] = Field(default=None)

    fixed_subgoal: Optional[str] = Field(None, description="Fixed subgoal")

    language: str = "zh"
    is_human: bool = False
    is_team: bool = False

    template_env: SandboxedEnvironment = Field(default_factory=SandboxedEnvironment)

    async def build_prompt(
        self,
        is_system: bool = True,
        resource_vars: Optional[Dict] = None,
        is_retry_chat: bool = False,
        **kwargs,
    ) -> str:
        """Return the prompt template for the role.

        Returns:
            str: The prompt template.
        """
        if is_system:
            return self.current_profile.format_system_prompt(
                template_env=self.template_env,
                language=self.language,
                resource_vars=resource_vars,
                is_retry_chat=is_retry_chat,
                **kwargs,
            )
        else:
            return self.current_profile.format_user_prompt(
                template_env=self.template_env,
                language=self.language,
                resource_vars=resource_vars,
                **kwargs,
            )

    def identity_check(self) -> None:
        """Check the identity of the role."""
        pass

    def get_name(self) -> str:
        """Get the name of the role."""
        return self.current_profile.get_name()

    @property
    def current_profile(self) -> Profile:
        """Return the current profile."""
        if not self._inited_profile:
            self._inited_profile = self.profile.create_profile(
                prefer_prompt_language=self.language
            )
        return self._inited_profile

    def prompt_template(
        self,
        prompt_type: str = "system",
        language: str = "en",
        is_retry_chat: bool = False,
    ) -> Tuple[str, str]:
        """Get agent prompt template."""
        self.language = language
        prompt = (
            self.current_profile.get_user_prompt_template()
            if prompt_type == "user"
            else self.current_profile.get_write_memory_template()
            if prompt_type == "write"
            else self.current_profile.get_system_prompt_template()
        )

        # env = Environment()
        # parsed_content = env.parse(prompt)
        # variables = meta.find_undeclared_variables(parsed_content)
        #
        # role_params = {
        #     "role": self.role,
        #     "name": self.name,
        #     "goal": self.goal,
        #     "retry_goal": self.retry_goal,
        #     "expand_prompt": self.expand_prompt,
        #     "language": language,
        #     "constraints": self.constraints,
        #     "retry_constraints": self.retry_constraints,
        #     "examples": self.examples,
        #     "is_retry_chat": is_retry_chat,
        # }
        # param = role_params.copy()
        # runtime_param_names = []
        # for variable in variables:
        #     if variable not in role_params:
        #         runtime_param_names.append(variable)
        #
        # if template_format == "f-string":
        #     input_params = {}
        #     for variable in runtime_param_names:
        #         input_params[variable] = "{" + variable + "}"
        #     param.update(input_params)
        # else:
        #     input_params = {}
        #     for variable in runtime_param_names:
        #         input_params[variable] = "{{" + variable + "}}"
        #     param.update(input_params)
        #

        # prompt_template = render(prompt, param)
        prompt_template = prompt
        return prompt_template, PromptType.JINJIA2.value

    @property
    def name(self) -> str:
        """Return the name of the role."""
        return self.current_profile.get_name()

    @property
    def role(self) -> str:
        """Return the role of the role."""
        return self.current_profile.get_role()

    @property
    def goal(self) -> Optional[str]:
        """Return the goal of the role."""
        return self.current_profile.get_goal()

    @property
    def avatar(self) -> Optional[str]:
        """Return the goal of the role."""
        return self.current_profile.get_avatar()

    @property
    def retry_goal(self) -> Optional[str]:
        """Return the retry goal of the role."""
        return self.current_profile.get_retry_goal()

    @property
    def constraints(self) -> Optional[List[str]]:
        """Return the constraints of the role."""
        return self.current_profile.get_constraints()

    @property
    def retry_constraints(self) -> Optional[List[str]]:
        """Return the retry constraints of the role."""
        return self.current_profile.get_retry_constraints()

    @property
    def desc(self) -> Optional[str]:
        """Return the description of the role."""
        return self.current_profile.get_description()

    @property
    def expand_prompt(self) -> Optional[str]:
        """Return the expand prompt introduction of the role."""
        return self.current_profile.get_expand_prompt()

    @property
    def write_memory_template(self) -> str:
        """Return the current save memory template."""
        return self.current_profile.get_write_memory_template()

    @property
    def is_reporter(self):
        return False

    @property
    def examples(self) -> Optional[str]:
        """Return the current example template."""
        return self.current_profile.get_examples()

    def _render_template(self, template: str, **kwargs):
        r_template = self.template_env.from_string(template)
        return r_template.render(**kwargs)

    @property
    def memory_importance_scorer(self) -> Optional[LLMImportanceScorer]:
        """Create the memory importance scorer.

        The memory importance scorer is used to score the importance of a memory
        fragment.
        """
        return None

    @property
    def memory_insight_extractor(self) -> Optional[LLMInsightExtractor]:
        """Create the memory insight extractor.

        The memory insight extractor is used to extract a high-level insight from a
        memory fragment.
        """
        return None

    @property
    def memory_fragment_class(self) -> Type[AgentMemoryFragment]:
        """Return the memory fragment class."""
        return AgentMemoryFragment

    async def read_memories(
        self,
        question: str,
        conv_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        llm_token_limit: Optional[int] = None,
        sub_agent_ids: Optional[List[str]] = None,
    ) -> Union[str, List["AgentMessage"]]:
        """Read the memories from the memory."""
        with root_tracer.start_span("agent.read_memories"):
            from derisk.agent.resource.memory import MemoryParameters

            memory_params: MemoryParameters = self.get_memory_parameters()  # type: ignore
            memories = await self.memory.search(
                observation=question,
                session_id=conv_id,
                agent_id=agent_id,
                enable_global_session=memory_params.enable_global_session,
                retrieve_strategy=memory_params.retrieve_strategy,
                discard_strategy=memory_params.discard_strategy,
                condense_prompt=memory_params.message_condense_prompt,
                condense_model=memory_params.message_condense_model,
                score_threshold=memory_params.score_threshold,
                top_k=memory_params.top_k,
                llm_token_limit=llm_token_limit,
                sub_agent_ids=sub_agent_ids,
            )
            recent_messages = [m.raw_observation for m in memories]
            return "".join(recent_messages)

    async def write_memories(
        self,
        question: str,
        ai_message: str,
        action_output: Optional[List[ActionOutput]] = None,
        check_pass: bool = True,
        check_fail_reason: Optional[str] = None,
        current_retry_counter: Optional[int] = None,
        reply_message: Optional[AgentMessage] = None,
        agent_id: Optional[str] = None,
        condense: bool = False,
        terminate: bool = False,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Union[AgentMemoryFragment, List[AgentMemoryFragment]]]:
        """Write the memories to the memory.

        We suggest you to override this method to save the conversation to memory
        according to your needs.

        Args:
            question(str): The question received.
            ai_message(str): The AI message, LLM output.
            action_output(List[ActionOutput]): The action output.
            check_pass(bool): Whether the check pass.
            check_fail_reason(str): The check fail reason.
            current_retry_counter(int): The current retry counter.
            reply_message(AgentMessage): The reply message.
            agent_id(str): The agent id.
            condense(bool): 是否是压缩后的内容,
            terminate(bool): 是否是终止
            extra_context(Dict[str, Any]): 额外的上下文信息，会合并到 memory_map 中，
                可用于传入 action、observation 等模板变量

        Returns:
            AgentMemoryFragment: The memory fragment created.
        """
        if not action_output:
            logger.info("Action output is required to save to memory.")
            return None

        with root_tracer.start_span("agent.write_memories"):
            fragments: List[AgentMemoryFragment] = []

            from derisk.agent.resource.memory import MemoryParameters

            memory_parameter: MemoryParameters = self.get_memory_parameters()

            if action_output and action_output[0].thoughts:
                mem_thoughts = action_output[0].thoughts
            else:
                mem_thoughts = ai_message

            actions: List[dict] = []
            for item in action_output:
                mem_thoughts = item.thoughts or ai_message
                action = item.action
                action_input = item.action_input
                observation = item.content_summary or item.observations or item.content
                if terminate:
                    action = "answer"
                action_dict = {
                    "is_exe_success": item.is_exe_success,
                    "action": action,
                    "observation": observation,
                }
                if action_input:
                    action_dict["action_input"] = action_input
                actions.append(action_dict)

            memory_map = {
                "question": question,
                "thought": mem_thoughts,
                "actions": actions,
            }
            if current_retry_counter is not None and current_retry_counter == 0:
                memory_map["question"] = question

            # 合并调用方传入的额外上下文（如 action、observation 等）
            if extra_context:
                memory_map.update(extra_context)

            write_memory_template = self.write_memory_template
            memory_content = self._render_template(write_memory_template, **memory_map)

            fragment_cls: Type[AgentMemoryFragment] = self.memory_fragment_class
            if issubclass(fragment_cls, StructuredAgentMemoryFragment):
                fragment = fragment_cls(memory_map)
            else:
                fragment = fragment_cls(
                    observation=memory_content,
                    agent_id=agent_id,
                    memory_id=reply_message.message_id,
                    role=self.name,
                    rounds=current_retry_counter
                    if current_retry_counter
                    else reply_message.rounds,
                    task_goal=question,
                    thought=mem_thoughts,
                    action=None,
                    actions=actions,
                    action_result=None,
                    agent_type=self.role,
                    condense=condense,
                    user_input=question,
                    ai_message=ai_message,
                    raw_action_outputs=json.dumps(
                        convert_datetime(
                            [output.to_dict() for output in action_output]
                        ),
                        ensure_ascii=False,
                        default=serialize,
                    ),
                )

            await self.memory.write(
                memory_fragment=fragment,
                enable_message_condense=memory_parameter.enable_message_condense,
                message_condense_model=memory_parameter.message_condense_model,
                message_condense_prompt=memory_parameter.message_condense_prompt,
            )
            await self.push_context_event(
                EventType.AfterMemoryWrite,
                MemoryWritePayload(fragment=fragment),
                reply_message.goal_id,
            )

            return fragments

    def get_memory_parameters(self) -> BaseParameters | None:
        """Get memory parameters from the agent's resource if available."""
        from derisk.agent.resource.memory import MemoryResource

        resource = self.resource
        if resource and resource.is_pack and resource.sub_resources:
            for r in resource.sub_resources:
                if isinstance(r, MemoryResource):
                    return r.memory_params
        elif resource and isinstance(resource, MemoryResource):
            return resource.memory_params
        return MemoryResource.default_parameters()

    async def recovering_memory(self, action_outputs: List[ActionOutput]) -> None:
        """Recover the memory from the action outputs."""
        fragments = []
        fragment_cls: Type[AgentMemoryFragment] = self.memory_fragment_class
        for action_output in action_outputs:
            if action_output.memory_fragments:
                fragment = fragment_cls.build_from(
                    observation=action_output.memory_fragments["memory"],
                    importance=action_output.memory_fragments.get("importance"),
                    memory_id=action_output.memory_fragments.get("id"),
                )
                fragments.append(fragment)
        await self.memory.write_batch(fragments)
