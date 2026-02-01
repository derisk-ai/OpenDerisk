from typing import Type, Optional

from derisk.context.operator import GroupedConfigItem, Operator, ConfigItem, ValuedConfigItem


def compute_config(config: ConfigItem, reference: ConfigItem):
    if not reference:
        return

    if isinstance(config, ValuedConfigItem):
        value = reference.get(config.name)
        config.value = value if value is not None else config.value
    elif isinstance(config, GroupedConfigItem):
        if config.title_field:
            compute_config(config.title_field, reference)

        if config.fields:
            for field in config.fields:
                compute_config(field, reference)

        if config.dynamic:
            for dynamic in config.dynamic:
                for field in dynamic.fields:
                    compute_config(field, reference)
    pass


def build_operator_config(operator_cls: Type[Operator], old_config: GroupedConfigItem = None) -> Optional[ConfigItem]:
    config: ConfigItem = operator_cls().config
    if config is None:
        return None
    config = config.model_copy()
    compute_config(config, old_config)
    return config


def build_by_agent_config(agent_config: GroupedConfigItem = None) -> GroupedConfigItem:
    from derisk.context.operator import OperatorManager
    operator_clss: list[Type[Operator]] = list(set([operator_cls for event_type, operator_clss in OperatorManager.operator_clss().items() for operator_cls in operator_clss]))
    operator_clss.sort(key=lambda op: op.name)  # 排个序 避免每次返回顺序不一致
    operators_fields = [field for operator_cls in operator_clss
                        if (field := build_operator_config(operator_cls, old_config=agent_config))]
    return GroupedConfigItem(
        name="context_config",
        label="上下文配置",
        description="上下文处理相关配置",
        fields=operators_fields
    )
