from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
)

from pydantic_core import PydanticUndefined

from ..._private.pydantic import (
    BaseModel,
    field_default,
    field_description,
    model_fields,
    model_to_dict,
    model_validator,
)

# def create_model_example(
#     model_type,
# ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
#     if model_type is None:
#         return None
#     origin = get_origin(model_type)
#     args = get_args(model_type)
#     if origin is None:
#         example = {}
#         single_model_type = cast(Type[BaseModel], model_type)
#         for field_name, field in model_fields(single_model_type).items():
#             description = field_description(field)
#             default_value = field_default(field)
#             if description:
#                 example[field_name] = description
#             elif default_value:
#                 example[field_name] = default_value
#             else:
#                 example[field_name] = ""
#         return example
#     elif origin is list or origin is List:
#         element_type = cast(Type[BaseModel], args[0])
#         if issubclass(element_type, BaseModel):
#             list_example = create_model_example(element_type)
#             typed_list_example = cast(Dict[str, Any], list_example)
#             return [typed_list_example]
#         else:
#             raise TypeError("List elements must be BaseModel subclasses")
#     else:
#         raise ValueError(
#             f"Model type {model_type} is not an instance of BaseModel."
#         )
def create_model_example(
        model_type,
) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    if model_type is None:
        return None

    origin = get_origin(model_type)
    args = get_args(model_type)

    # 处理 Optional/Union 类型
    if origin is Union:
        # 过滤掉 NoneType，获取实际类型
        non_none_args = [arg for arg in args if arg is not type(None)]
        if non_none_args:
            # 递归处理 Union 中的实际类型
            return create_model_example(non_none_args[0])
        return None

    # 处理 List 类型
    if origin is list or origin is List:
        if args:
            element_type = args[0]
            # 递归处理列表元素类型
            list_example = create_model_example(element_type)
            if list_example is not None:
                return [list_example]
        return []

    # 处理 BaseModel 类型
    if origin is None:
        # 检查是否为 BaseModel 子类
        try:
            if isinstance(model_type, type) and issubclass(model_type, BaseModel):
                example = {}
                single_model_type = cast(Type[BaseModel], model_type)

                for field_name, field in model_fields(single_model_type).items():
                    # 获取字段信息
                    description = field_description(field)
                    default_value = field_default(field)
                    field_annotation = field.annotation

                    # 检查字段类型是否为嵌套的 BaseModel 或 List
                    field_origin = get_origin(field_annotation)
                    field_args = get_args(field_annotation)

                    # 处理 Union[BaseModel, None] 或 Optional[BaseModel]
                    if field_origin is Union:
                        non_none_types = [arg for arg in field_args if
                                          arg is not type(None)]
                        if non_none_types:
                            actual_type = non_none_types[0]
                            actual_origin = get_origin(actual_type)

                            # 检查是否为 List[BaseModel] 或 BaseModel
                            if actual_origin is list or actual_origin is List:
                                nested_result = create_model_example(actual_type)
                                example[
                                    field_name] = nested_result if nested_result is not None else (
                                            description or "")
                            elif isinstance(actual_type, type) and issubclass(
                                    actual_type, BaseModel):
                                nested_result = create_model_example(actual_type)
                                example[
                                    field_name] = nested_result if nested_result is not None else (
                                            description or "")
                            else:
                                # 基本类型，使用 description 或 default
                                example[field_name] = description or (
                                    default_value if default_value is not None else "")
                        else:
                            example[field_name] = description or ""
                    # 处理 List[BaseModel]
                    elif field_origin is list or field_origin is List:
                        nested_result = create_model_example(field_annotation)
                        example[
                            field_name] = nested_result if nested_result is not None else (
                                    description or "")
                    # 处理直接的 BaseModel
                    elif isinstance(field_annotation, type) and issubclass(
                            field_annotation, BaseModel):
                        nested_result = create_model_example(field_annotation)
                        example[
                            field_name] = nested_result if nested_result is not None else (
                                    description or "")
                    # 处理基本类型
                    else:
                        if description:
                            example[field_name] = description
                        elif default_value is not None and default_value != PydanticUndefined:
                            example[field_name] = default_value
                        else:
                            example[field_name] = ""

                return example
        except (TypeError, AttributeError):
            pass

        # 如果不是 BaseModel，返回空字符串
        return ""

    # 其他情况
    return None

