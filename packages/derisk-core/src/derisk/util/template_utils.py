from typing import Any, Set

from jinja2 import meta
from jinja2.sandbox import SandboxedEnvironment

TMPL_ENV = SandboxedEnvironment()


def render(template: str, params: dict[str, Any]) -> str:
    return TMPL_ENV.from_string(template).render(params)


def extract_variables(template: str) -> Set[str]:
    """解析所有参数占位符"""
    ast = TMPL_ENV.parse(template)
    return meta.find_undeclared_variables(ast)


def two_stage_render(template_str, context1, context2=None):
    # 第一阶段渲染
    stage1 = TMPL_ENV.from_string(template_str).render(context1)

    # 提取未渲染的变量
    ast = TMPL_ENV.parse(stage1)
    remaining_vars = meta.find_undeclared_variables(ast)

    # 如果有未渲染变量且提供了第二阶段上下文
    if remaining_vars and context2:
        # 合并上下文
        full_context = {**context1, **context2}
        return TMPL_ENV.from_string(stage1).render(full_context)

    return stage1
