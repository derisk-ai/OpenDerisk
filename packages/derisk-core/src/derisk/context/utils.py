import json
from typing import Type, Optional

from derisk.context.manager import Manager, ChatContextKey
from derisk.context.operator import GroupedConfigItem, Operator, ConfigItem, ValuedConfigItem


def compute_config(config: ConfigItem, reference: ConfigItem):
    if not reference:
        return

    if isinstance(config, ValuedConfigItem):
        config.value = reference.get(config.name) or config.value
    elif isinstance(config, GroupedConfigItem):
        if config.fields:
            for field in config.fields:
                compute_config(field, reference)

        if config.dynamic:
            for dynamic in config.dynamic:
                for field in dynamic.fields:
                    compute_config(field, reference)


def build_by_operator(operator_cls: Type[Operator], old_config: GroupedConfigItem = None) -> Optional[ConfigItem]:
    config: ConfigItem = operator_cls().config
    if config is None:
        return None
    compute_config(config, old_config)
    return config


def build_by_agent_config(agent_config: GroupedConfigItem = None) -> GroupedConfigItem:
    from derisk.context.manager import Manager
    manager: Manager = Manager.get_instance()
    operator_clss = set([operator_cls for event_type, operator_clss in manager.operator_clss().items() for operator_cls in operator_clss])
    operators_fields = [field for operator_cls in operator_clss
                        if (field := build_by_operator(operator_cls, old_config=agent_config))]
    return GroupedConfigItem(
        name="context_config",
        label="上下文配置",
        description="上下文处理相关配置",
        fields=operators_fields
    )


def format_ability_by_context() -> str:
    context = Manager.current_window()
    prompts: list[str] = []
    if ChatContextKey.SUB_AGENTS in context:
        for agent in context[ChatContextKey.SUB_AGENTS]:
            prompts.append("**id**: " + agent["name"] + "\n\n**描述**: " + agent["description"])

    if ChatContextKey.MCPS in context:
        for mcp in context[ChatContextKey.MCPS]:
            for tool in mcp.get("tools", []):
                prompts.append(tool.get("prompt"))

    if ChatContextKey.TOOLS in context:
        for tool in context[ChatContextKey.TOOLS]:
            prompts.append(tool.get("prompt"))

    if ChatContextKey.KNOWLEDGE in context:
        # name = context[ChatContextKey.KNOWLEDGE].get("name")
        name = "knowledge_retrieve"
        description = context[ChatContextKey.KNOWLEDGE].get("description")
        parameters = context[ChatContextKey.KNOWLEDGE].get("parameters")
        prompts.append(f"**id**: {name}\n\n**描述**: {description} \n\n**参数**:\n\n{json.dumps(parameters, ensure_ascii=False)}")

    return ("\n\n".join(["### 可用能力\n" + prompt for prompt in prompts if prompt])).strip()
