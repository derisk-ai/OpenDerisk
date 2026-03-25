"""Prompt 模板注册表 - 支持 Agent 级别模板目录

设计理念：
1. 每个 Agent 可以有自己的 prompts 目录
2. 共享模板在 shared/prompt_assembly/prompts/
3. Agent 模板优先级高于共享模板
4. 支持模板覆盖和扩展

模板加载优先级：
1. Agent 级别模板 (agent_prompts_dir)
2. 共享模板 (shared_prompts_dir)
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """Prompt 模板定义"""

    category: str
    name: str
    content: str = ""
    version: str = "latest"
    file_path: Optional[Path] = None
    description: str = ""
    is_jinja2: bool = False
    source: str = "shared"

    def render(self, **kwargs) -> str:
        """渲染模板"""
        if not self.content:
            return ""

        if self.is_jinja2:
            try:
                from jinja2 import Template

                return Template(self.content).render(**kwargs)
            except ImportError:
                logger.warning(
                    "Jinja2 not installed, falling back to simple replacement"
                )
            except Exception as e:
                logger.error(f"Failed to render Jinja2 template: {e}")

        result = self.content
        for key, value in kwargs.items():
            if value is None:
                continue
            result = result.replace(f"{{{{{key}}}}}", str(value))
            result = result.replace(f"{{{key}}}", str(value))
        return result


class PromptRegistry:
    """
    Prompt 模板注册表 - 支持多级模板目录

    模板加载顺序（优先级从高到低）：
    1. Agent 级别模板 (agent_prompts_dir)
    2. 共享模板 (shared_prompts_dir)
    """

    _instance: Optional["PromptRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._templates = {}
            cls._instance._initialized = False
            cls._instance._agent_prompts_dir = None
        return cls._instance

    @classmethod
    def get_instance(cls) -> "PromptRegistry":
        """获取单例实例"""
        return cls()

    def set_agent_prompts_dir(self, prompts_dir: Optional[Path]) -> None:
        """设置 Agent 级别的模板目录"""
        self._agent_prompts_dir = prompts_dir
        self._templates.clear()
        self._initialized = False

    def initialize(self, agent_prompts_dir: Optional[Path] = None) -> None:
        """初始化 - 加载所有模板文件"""
        if self._initialized:
            return

        if agent_prompts_dir:
            self._agent_prompts_dir = agent_prompts_dir

        self._load_shared_templates()
        self._load_agent_templates()

        self._initialized = True
        logger.info(f"PromptRegistry initialized with {len(self._templates)} templates")

    def _get_shared_prompts_dir(self) -> Path:
        """获取共享模板目录"""
        return Path(__file__).parent / "prompts"

    def _load_shared_templates(self) -> None:
        """加载共享模板"""
        shared_dir = self._get_shared_prompts_dir()
        if shared_dir.exists():
            self._load_templates_from_dir(shared_dir, source="shared")

    def _load_agent_templates(self) -> None:
        """加载 Agent 级别模板"""
        if not self._agent_prompts_dir or not self._agent_prompts_dir.exists():
            return

        self._load_templates_from_dir(self._agent_prompts_dir, source="agent")

    def _load_templates_from_dir(self, prompts_dir: Path, source: str) -> None:
        """从目录加载模板"""
        categories = [
            "identity",
            "workflow",
            "exceptions",
            "delivery",
            "resources",
            "user",
        ]

        for category in categories:
            category_path = prompts_dir / category
            if not category_path.exists():
                continue

            for file_path in category_path.glob("*.md*"):
                if file_path.name.startswith("README"):
                    continue

                self._register_template(category, file_path, source)

    def _register_template(self, category: str, file_path: Path, source: str) -> None:
        """注册单个模板"""
        try:
            content = file_path.read_text(encoding="utf-8")
            # 处理双后缀文件如 .md.j2：stem 返回 "sandbox.md"，需要得到 "sandbox"
            name = file_path.stem
            if name.endswith(".md"):
                name = name[:-3]  # 去掉 ".md" 后缀
            is_jinja2 = file_path.suffix == ".j2" or "{{" in content

            template = PromptTemplate(
                category=category,
                name=name,
                version="latest",
                content=content,
                file_path=file_path,
                is_jinja2=is_jinja2,
                source=source,
            )

            key = f"{category}/{name}"

            if (
                key in self._templates
                and self._templates[key].source == "shared"
                and source == "agent"
            ):
                logger.info(f"Template {key} overridden by agent template")

            self._templates[key] = template
            logger.debug(f"Registered template: {key} (source={source})")

        except Exception as e:
            logger.error(f"Failed to load template {file_path}: {e}")

    def get(
        self, category: str, name: str, version: str = "latest"
    ) -> Optional[PromptTemplate]:
        """获取模板"""
        if not self._initialized:
            self.initialize()

        key = f"{category}/{name}"
        return self._templates.get(key)

    def get_content(self, category: str, name: str, version: str = "latest") -> str:
        """获取模板内容"""
        template = self.get(category, name, version)
        return template.content if template else ""

    def render(
        self, category: str, name: str, version: str = "latest", **kwargs
    ) -> str:
        """渲染模板"""
        template = self.get(category, name, version)
        if template:
            return template.render(**kwargs)
        return ""

    def has(self, category: str, name: str) -> bool:
        """检查模板是否存在"""
        if not self._initialized:
            self.initialize()
        return f"{category}/{name}" in self._templates

    def list_templates(
        self, category: Optional[str] = None, source: Optional[str] = None
    ) -> List[str]:
        """列出所有模板"""
        if not self._initialized:
            self.initialize()

        templates = list(self._templates.keys())

        if category:
            templates = [k for k in templates if k.startswith(f"{category}/")]

        if source:
            templates = [k for k, v in self._templates.items() if v.source == source]

        return templates

    def get_templates_by_category(self, category: str) -> Dict[str, PromptTemplate]:
        """获取指定分类的所有模板"""
        if not self._initialized:
            self.initialize()

        return {
            k: v for k, v in self._templates.items() if k.startswith(f"{category}/")
        }

    def reload(self) -> None:
        """重新加载所有模板"""
        self._templates.clear()
        self._initialized = False
        self.initialize()

    def register(self, template: PromptTemplate) -> None:
        """手动注册模板"""
        key = f"{template.category}/{template.name}"
        self._templates[key] = template
        logger.debug(f"Manually registered template: {key}")

    def register_content(
        self, category: str, name: str, content: str, is_jinja2: bool = False, **kwargs
    ) -> None:
        """便捷方法：直接注册内容"""
        template = PromptTemplate(
            category=category,
            name=name,
            content=content,
            is_jinja2=is_jinja2,
            source="manual",
            **kwargs,
        )
        self.register(template)


def get_registry() -> PromptRegistry:
    """获取 Prompt 注册表实例"""
    return PromptRegistry.get_instance()


def register_template(category: str, name: str, content: str, **kwargs) -> None:
    """便捷函数：注册模板"""
    get_registry().register_content(category, name, content, **kwargs)
