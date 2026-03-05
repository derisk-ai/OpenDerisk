"""
Simplified Prompt System - Inspired by opencode/openclaw patterns.

Key improvements:
1. Declarative prompt configuration
2. Template inheritance
3. Variable injection
4. Support for markdown-based prompts
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union
from string import Template

from derisk._private.pydantic import BaseModel, Field


class PromptFormat(str, Enum):
    """Prompt format types."""

    JINJA2 = "jinja2"
    F_STRING = "f-string"
    MUSTACHE = "mustache"
    PLAIN = "plain"


@dataclass
class PromptVariable:
    """A variable in a prompt template."""

    name: str
    description: str = ""
    default: Any = None
    required: bool = True
    resolver: Optional[Callable] = None

    async def resolve(self, context: Dict[str, Any]) -> Any:
        """Resolve variable value from context or resolver."""
        if self.name in context:
            return context[self.name]
        if self.resolver:
            result = self.resolver(context)
            if hasattr(result, "__await__"):
                result = await result
            return result
        if self.default is not None:
            return self.default
        if self.required:
            raise ValueError(f"Required variable '{self.name}' not provided")
        return None


class PromptTemplate(BaseModel):
    """
    Simplified prompt template with variable support.
    """

    name: str = Field(default="default", description="Template name")
    template: str = Field(default="", description="Template content")
    format: PromptFormat = Field(
        default=PromptFormat.JINJA2, description="Template format"
    )
    variables: Dict[str, PromptVariable] = Field(
        default_factory=dict, description="Template variables"
    )

    _compiled_template: Optional[Any] = None

    def add_variable(
        self,
        name: str,
        description: str = "",
        default: Any = None,
        required: bool = True,
        resolver: Optional[Callable] = None,
    ) -> "PromptTemplate":
        """Add a variable to this template."""
        self.variables[name] = PromptVariable(
            name=name,
            description=description,
            default=default,
            required=required,
            resolver=resolver,
        )
        return self

    def render(self, **kwargs) -> str:
        """Render the template with provided values."""
        if self.format == PromptFormat.JINJA2:
            return self._render_jinja2(**kwargs)
        elif self.format == PromptFormat.F_STRING:
            return self._render_fstring(**kwargs)
        else:
            return self.template

    def _render_jinja2(self, **kwargs) -> str:
        """Render using Jinja2."""
        try:
            from jinja2 import Template

            template = Template(self.template)
            return template.render(**kwargs)
        except ImportError:
            return self._render_fstring(**kwargs)

    def _render_fstring(self, **kwargs) -> str:
        """Render using f-string style."""
        result = self.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{{{key}}}}}", str(value) if value else "")
        return result

    @classmethod
    def from_file(cls, path: str, name: Optional[str] = None) -> "PromptTemplate":
        """Load template from file."""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        format = PromptFormat.JINJA2
        if path.endswith(".txt"):
            format = PromptFormat.PLAIN

        return cls(name=name or Path(path).stem, template=content, format=format)


class SystemPromptBuilder:
    """
    Builder for constructing system prompts.

    Inspired by opencode's compose pattern.
    """

    def __init__(self):
        self._sections: List[str] = []
        self._variables: Dict[str, Any] = {}

    def role(self, role: str) -> "SystemPromptBuilder":
        """Set agent role."""
        self._sections.append(f"You are {role}.")
        return self

    def goal(self, goal: str) -> "SystemPromptBuilder":
        """Set agent goal."""
        self._sections.append(f"\nYour goal is: {goal}")
        return self

    def constraints(self, constraints: List[str]) -> "SystemPromptBuilder":
        """Add constraints."""
        if constraints:
            self._sections.append("\n\nConstraints:")
            for i, c in enumerate(constraints, 1):
                self._sections.append(f"{i}. {c}")
        return self

    def tools(self, tools: List[str]) -> "SystemPromptBuilder":
        """Add available tools."""
        if tools:
            self._sections.append("\n\nAvailable Tools:")
            for tool in tools:
                self._sections.append(f"- {tool}")
        return self

    def examples(self, examples: List[str]) -> "SystemPromptBuilder":
        """Add examples."""
        if examples:
            self._sections.append("\n\nExamples:")
            for example in examples:
                self._sections.append(example)
        return self

    def custom(self, content: str) -> "SystemPromptBuilder":
        """Add custom content."""
        self._sections.append(content)
        return self

    def context(self, key: str, value: Any) -> "SystemPromptBuilder":
        """Add context variable."""
        self._variables[key] = value
        return self

    def build(self) -> str:
        """Build the final prompt."""
        return "".join(self._sections)


DEFAULT_SYSTEM_PROMPT = (
    SystemPromptBuilder()
    .role("{{role}}")
    .goal("{{goal}}")
    .constraints(["{{constraints}}"])
    .tools(["{{tools}}"])
    .build()
)

DEFAULT_SYSTEM_PROMPT_ZH = """你是一个 {{role }}{{ name }}。

你的目标是：{{ goal }}。

{% if constraints %}
约束条件：
{% for constraint in constraints %}
{{ loop.index }}. {{ constraint }}
{% endfor %}
{% endif %}

{% if tools %}
可用工具：
{% for tool in tools %}
- {{ tool }}
{% endfor %}
{% endif %}

{% if examples %}
示例：
{{ examples }}
{% endif %}

请使用简体中文回答。
当前时间：{{ now_time }}
"""


class UserProfile(BaseModel):
    """
    User profile for personalized prompts.
    Inspired by openclaw user context.
    """

    name: Optional[str] = None
    preferred_language: str = "zh"
    context: Dict[str, Any] = Field(default_factory=dict)


class AgentProfile(BaseModel):
    """
    Simplified agent profile configuration.

    Supports:
    - Simple configuration
    - Markdown-style prompts
    - Template inheritance
    """

    name: str = Field(..., description="Agent name")
    role: str = Field(..., description="Agent role")
    goal: Optional[str] = Field(None, description="Agent goal")
    constraints: List[str] = Field(default_factory=list, description="Constraints")
    examples: Optional[str] = Field(None, description="Examples")
    system_prompt: Optional[str] = Field(None, description="Custom system prompt")
    user_prompt: Optional[str] = Field(None, description="Custom user prompt")

    temperature: float = Field(0.5, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1)

    language: str = Field("zh", description="Preferred language")

    @classmethod
    def from_markdown(cls, content: str) -> "AgentProfile":
        """
        Parse profile from markdown with frontmatter.

        Example:
        ---
        name: Code Reviewer
        role: A helpful code reviewer
        goal: Review code for quality and issues
        constraints:
          - Be constructive
          - Focus on important issues
        temperature: 0.3
        ---

        You are an expert code reviewer...
        """
        import yaml

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                system_prompt = parts[2].strip()

                if frontmatter:
                    return cls(
                        name=frontmatter.get("name", "Agent"),
                        role=frontmatter.get("role", ""),
                        goal=frontmatter.get("goal"),
                        constraints=frontmatter.get("constraints", []),
                        examples=frontmatter.get("examples"),
                        system_prompt=system_prompt,
                        temperature=frontmatter.get("temperature", 0.5),
                        max_tokens=frontmatter.get("max_tokens"),
                        language=frontmatter.get("language", "zh"),
                    )

        return cls(name="Agent", role=content[:100] if len(content) > 100 else content)

    def build_system_prompt(
        self,
        tools: Optional[List[str]] = None,
        resources: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Build system prompt from profile."""
        if self.system_prompt:
            template = PromptTemplate(template=self.system_prompt)
        elif self.language == "zh":
            template = PromptTemplate(template=DEFAULT_SYSTEM_PROMPT_ZH)
        else:
            template = PromptTemplate(template=DEFAULT_SYSTEM_PROMPT)

        render_vars = {
            "role": self.role,
            "name": self.name,
            "goal": self.goal or "",
            "constraints": self.constraints,
            "tools": tools or [],
            "examples": self.examples,
            "now_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **kwargs,
        }

        if resources:
            render_vars["resources"] = resources

        return template.render(**render_vars)

    def to_markdown(self) -> str:
        """Export profile as markdown with frontmatter."""
        import yaml

        frontmatter = {
            "name": self.name,
            "role": self.role,
            "goal": self.goal,
            "constraints": self.constraints,
            "temperature": self.temperature,
            "language": self.language,
        }

        yaml_str = yaml.dump(
            {k: v for k, v in frontmatter.items() if v}, default_flow_style=False
        )

        return f"---\n{yaml_str}---\n\n{self.system_prompt or ''}"


def load_prompt(path: str) -> str:
    """Load prompt from file path."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return path


def compose_prompts(*prompts: str) -> str:
    """Compose multiple prompts together."""
    return "\n\n".join(p for p in prompts if p)
