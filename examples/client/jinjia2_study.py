from datetime import datetime

from jinja2 import Environment, meta
import re


def preserve_control_blocks(template_str, context, preserve_vars):
    """
    保留控制逻辑的分阶段渲染
    :param template_str: 模板字符串
    :param context: 渲染上下文
    :param preserve_vars: 需要保留的变量名集合
    :return: 渲染结果
    """
    # 提取所有控制块（if, for, etc.）
    control_blocks = []

    # 匹配所有控制块
    pattern = r'(\{%\s*(if|for|else|elif|endif|endfor)\b.*?%\})'
    matches = re.findall(pattern, template_str, re.DOTALL)

    # 为每个控制块创建唯一标识符
    for i, (full_match, block_type) in enumerate(matches):
        unique_id = f"__CONTROL_BLOCK_{i}__"
        control_blocks.append((unique_id, full_match))
        template_str = template_str.replace(full_match, unique_id, 1)

    # 创建环境并渲染变量部分
    env = Environment()

    # 使用自定义未定义处理只保留指定变量
    class SelectiveUndefined:
        def __init__(self, name):
            self.name = name

        def __str__(self):
            if self.name in preserve_vars:
                return "{{ " + self.name + " }}"
            return ""

        def __getattr__(self, name):
            return SelectiveUndefined(f"{self.name}.{name}")

        def __getitem__(self, key):
            if isinstance(key, str):
                return SelectiveUndefined(f"{self.name}['{key}']")
            return SelectiveUndefined(f"{self.name}[{key}]")

    env.undefined = lambda name: SelectiveUndefined(name)
    result = env.from_string(template_str).render(context)

    # 恢复控制块
    for unique_id, original_block in control_blocks:
        result = result.replace(unique_id, original_block)

    return result


def two_stage_render(template_str, context1, preserve_vars, context2=None):
    """
    分阶段渲染函数
    :param template_str: 模板字符串
    :param context1: 第一阶段渲染的上下文
    :param preserve_vars: 需要保留的变量名集合
    :param context2: 第二阶段渲染的上下文（可选）
    :return: 渲染结果
    """
    # 第一阶段：保留控制块和指定变量
    stage1 = preserve_control_blocks(template_str, context1, preserve_vars)

    # 如果没有第二阶段，直接返回
    if context2 is None:
        return stage1

    # 第二阶段：完整渲染
    env = Environment()
    return env.from_string(stage1).render({**context1, **context2})

if __name__ == "__main__":
    print(datetime.now())
    # 使用示例
    template = """
    User: {{ name }}
    Email: {{ email }}
    Test: {% if expand_prompt %} 
      Expand Prompt: {{ expand_prompt }} 
    {% endif %}
    Loop: {% for item in items %}
      - {{ item }}
    {% endfor %}
    """

    # 第一阶段上下文
    context1 = {"name": "Alice"}

    # 需要保留的变量
    preserve_vars = {"email", "expand_prompt", "items"}

    # 第一阶段渲染
    stage1_result = two_stage_render(template, context1, preserve_vars)
    print("第一阶段结果:")
    print(stage1_result)

    # 第二阶段上下文
    context2 = {
        "email": "alice@example.com",
        "expand_prompt": "Important message!",
        "items": ["Apple", "Banana", "Cherry"]
    }
    stage1_result = two_stage_render(template, context1, preserve_vars)
    print("第x阶段结果:")
    print(stage1_result)

    # 第二阶段渲染
    stage2_result = two_stage_render(template, context1, preserve_vars, context2)
    print("\n第二阶段结果:")
    print(stage2_result)
    print(datetime.now())