import dataclasses
from typing import Optional, get_origin, Union, get_args


def parse_model(model):
    result = []
    for field in dataclasses.fields(model):
        if field.name == "name":
            continue
        field_info = {
            "name": field.name,
            "value": field.default if field.default is not dataclasses.MISSING else None,
            "type": get_simple_type_name(field.type),
            "description": field.metadata.get("help", ""),
            "label": field.metadata.get("label", ""),
            "options": field.metadata.get("options", [])
        }
        if field_info.get("options"):
            field_info["type"] = "array"
        result.append(field_info)
    return result


def get_simple_type_name(type_hint):
    if get_origin(type_hint) is Union:
        args = get_args(type_hint)
        if len(args) == 2 and type(None) in args:
            # This is an Optional type
            inner_type = next(arg for arg in args if arg is not type(None))
            return f"{get_simple_type_name(inner_type)}"
    if isinstance(type_hint, type):
        return type_hint.__name__
    return str(type_hint).replace("typing.", "")


def extract_inner_type(type_hint):
    """"""
    if hasattr(type_hint, '__origin__') and type_hint.__origin__ is Optional:
        inner_types = [t for t in type_hint.__args__ if t is not type(None)]
        return extract_inner_type(inner_types[0]) if inner_types else None

    if isinstance(type_hint, type):
        return type_hint.__name__

    if hasattr(type_hint, '__name__'):
        return type_hint.__name__

    return str(type_hint)