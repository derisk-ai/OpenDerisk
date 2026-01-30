import json
import xmltodict

from abc import ABC
from enum import Enum
from typing import TypeVar, Union, List, Generic, Optional, get_origin, get_args, cast, Type

from derisk.agent import Action
from derisk.agent.util.llm.llm_client import AgentLLMOut
from derisk.agent.util.model_utils import create_model_example
from derisk._private.pydantic import BaseModel
from derisk.agent.util.xml_utils import extract_valid_xmls

T = TypeVar("T", bound=Union[BaseModel, List[BaseModel], str, None])


class SchemaType(Enum):
    XML = "xml"
    JSON = "json"
    TEXT = "text"


class AgentParser(ABC, Generic[T]):
    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.TEXT  # 基类默认的Agent输出结构类型

    def __init__(self, type: Optional[SchemaType] = None, **kwargs):
        self._scheme_type = type if type is not None else self.__class__.DEFAULT_SCHEMA_TYPE

    @property
    def schema_type(self):
        return self._scheme_type.value

    @property
    def model_type(self) -> Optional[Type[T]]:
        return None

    def json_schema(self) -> Optional[str]:
        if self.model_type is None:
            return None

        return json.dumps(
            create_model_example(self.model_type), indent=2, ensure_ascii=False
        )

    def xml_schema(self) -> Optional[str]:
        if self.model_type is None:
            return None

        model_dict = create_model_example(self.model_type)
        data_dict = {
            'root': model_dict  # 将原始数据作为根元素的值
        }
        return xmltodict.unparse(data_dict, pretty=True)

    def schema(self) -> Optional[str]:
        match self._scheme_type:
            case SchemaType.XML:
                return self.xml_schema()
            case SchemaType.JSON:
                return self.json_schema()
            case _:
                return None

    def _xml_to_model(self, llm_out: str) -> T:

        xml_strs = extract_valid_xmls(llm_out)
        if len(xml_strs) < 1:
            raise ValueError("Unable to obtain valid xml output.")
        xml_str = xml_strs[0]
        xml_dict = xmltodict.parse(xml_str)
        data_dict = xml_dict['root']

        if get_origin(T) is list:
            inner_type = get_args(T)[0]
            typed_cls = cast(Type[BaseModel], inner_type)
            return [typed_cls.model_validate(item) for item in data_dict]  # type: ignore
        else:
            typed_cls = cast(Type[BaseModel], self.model_type)
            return typed_cls.model_validate(data_dict)

    def _json_to_model(self, llm_out: str) -> T:
        from derisk.util.json_utils import find_json_objects
        json_objects = find_json_objects(llm_out)
        json_count = len(json_objects)
        if json_count < 1:
            raise ValueError("Unable to obtain valid json output.")
        json_object = json_objects[0]

        if get_origin(T) is list:
            inner_type = get_args(T)[0]
            typed_cls = cast(Type[BaseModel], inner_type)
            return [typed_cls.model_validate(item) for item in json_result]  # type: ignore
        else:
            typed_cls = cast(Type[BaseModel], self.model_type)
            return typed_cls.model_validate(json_object)

    def parse(self, llm_out: Union[str, AgentLLMOut]) -> Optional[T]:
        match self._scheme_type:
            case SchemaType.XML:
                return self.xml_schema()
            case SchemaType.JSON:
                return self._json_to_model(llm_out.content)
            case _:
                raise ValueError("无法支持的解析模式!")

    def parse_actions(self, llm_out:  AgentLLMOut, action_cls_list: List[Type[Action]], **kwargs) -> Optional[list[Action]]:
        pass

    async def parse_streaming(self, llm_out: Union[str, AgentLLMOut], field_name: str) -> Optional[T]:
        match self._scheme_type:
            case SchemaType.XML:
                return self.parse_streaming_xml(llm_out, field_name)
            case SchemaType.JSON:
                return self.parse_streaming_json(llm_out, field_name)
            case _:
                raise ValueError("无法支持的解析模式!")

    def xml_to_reason_output(self, llm_out: Union[str, AgentLLMOut]) -> Optional[T]:
        pass

    def parse_streaming_json(self, json_string, field_name):
        """流式提取JSON字段内容，不需要等待结束符"""
        import re

        # 匹配 "field": "内容（可能不完整）
        pattern = f'"{field_name}"\\s*:\\s*"([^"]*)'
        match = re.search(pattern, json_string, re.DOTALL)

        if match:
            return match.group(1)
        else:
            return None

    def parse_streaming_xml(self, xml_string, field_name):
        """
        流式提取XML字段内容，不需要等待结束标签

        参数:
            xml_string: XML格式的字符串（可能不完整）
            field_name: 要提取的字段名

        返回:
            字段的内容，即使标签未闭合也能提取
        """
        import re

        # 匹配开始标签后的内容（不要求结束标签）
        pattern = f'<{field_name}>(.*?)(?:</{field_name}>|$)'

        match = re.search(pattern, xml_string, re.DOTALL)

        if match:
            return match.group(1).strip()
        else:
            return None


class DefaultAgentParser(AgentParser[None]):
    def parse(self, llm_out: AgentLLMOut, type: SchemaType = SchemaType.TEXT) -> Optional[T]:
        return llm_out

    def schema(self) -> Optional[str]:
        return None
