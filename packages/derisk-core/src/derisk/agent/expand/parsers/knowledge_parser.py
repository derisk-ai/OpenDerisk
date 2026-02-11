import json
import logging
from typing import Optional, Type, Literal, List, get_args, get_origin, cast, Union

import xmltodict

from derisk._private.pydantic import BaseModel, Field
from derisk.agent.core.base_parser import AgentParser, SchemaType, T
from derisk.agent.core.reasoning.reasoning_engine import \
    ReasoningPlan, ReasoningModelOutput
from derisk.agent.util.llm.llm_client import AgentLLMOut
from derisk.agent.util.xml_utils import extract_valid_xmls
from derisk.util.json_utils import find_json_objects
from derisk.util.string_utils import is_str_list

logger = logging.getLogger(__name__)
FILE_TOOLS = ["create_file", "edit_file"]
FILE_DESCRIPTION = "Write File"
SANDBOX_TOOLS = ["browser", "create_file", "edit_file", "shell", "view", "download_file"]

class KnowledgePlan(ReasoningPlan):
    reason: Optional[str] = Field(
        None, description="必须执行的具体依据（需关联前置分析或执行结果）"
    )

    intention: Optional[str] = Field("", description="新动作目标")
    id: Optional[str] = Field(None, description="可用能力ID")
    parameters: Optional[dict] = Field(None, description="""执行参数, 
        {
          "operation": "xx",
          "args": {"parameter1": "xx", "parameter2": "xx"}
        }
        """)


class PlanItem(BaseModel):
    plan: Optional[KnowledgePlan] = Field(..., description="新动作目标")


class KnowledgePlannerInfo(BaseModel):
    """知识规划器信息模型"""

    status: Literal["planing", "done", "abort", "chat"] = Field(
        ...,
        description="planing (仅当需要执行下一步动作时) | done (仅当任务可终结时) | abort (仅当任务异常或无法推进或需要用户提供更多信息时)| chat (仅当用户问题为日常闲聊，无需调用工具或生成知识内容时"
    )
    reason: Optional[str] = Field(None, description="详细解释状态判定和plan拆解依据")

    plans: Optional[List[KnowledgePlan]] = Field(
        None,
        description="新动作目标（需对比历史动作确保不重复）<plans><plan>xxx</plan><plan>yyy</plan></plans>"
    )

    plans_brief_description: Optional[str] = Field(
        None, description="简短介绍要执行的动作，不超过10个字"
    )

    summary: Optional[str] = Field(
        None,
        description="当done/abort状态时出现，根据上下文信息给出任务结论。<注意>需要调用**文档框架助手**生成文档大纲框架后才能撰写报告内容才能完成结束</注意>",
    )

    answer: Optional[str] = Field(
        None,
        description="""当done/abort状态时出现，根据上下文信息给出任务结论,<注意>需要调用**文档框架助手**生成文档大纲框架后才能撰写报告内容才能完成结束</注意>"""
    )

    ask_user: Optional[str] = Field(
        None, description="需要向用户咨询的内容"
    )


class KnowledgePlannerParser(AgentParser[KnowledgePlannerInfo]):
    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.JSON

    @property
    def model_type(self) -> Optional[Type[KnowledgePlannerInfo]]:
        return KnowledgePlannerInfo

    from typing import Type
    from pydantic import BaseModel

    def xml_to_reason_output(self, llm_out: str) -> ReasoningModelOutput:
        model = self._xml_to_model(llm_out)
        return self.convert_to_reason_output(model)

    def parse(self, llm_out: Union[str, AgentLLMOut]) -> Optional[T]:
        match self._scheme_type:
            case SchemaType.XML:
                return self.xml_to_reason_output(llm_out)
            case SchemaType.JSON:
                json_parsed = find_json_objects(llm_out)
                if isinstance(json_parsed, list) and len(json_parsed) >= 1:
                    json_parsed = json_parsed[0]
                elif isinstance(json_parsed, list) and len(json_parsed) == 0:
                    # find_json_objects 没找到 JSON，尝试直接用 json_repair 解析
                    try:
                        import json_repair
                        json_parsed = json_repair.loads(llm_out)
                    except Exception:
                        # 如果解析失败，保持空列表，让后续验证抛出更清晰的错误
                        pass

                if "summary" in json_parsed and json_parsed["summary"]:
                    if is_str_list(json_parsed["summary"]):
                        json_parsed["summary"] = "\n".join(json_parsed["summary"])
                    elif not isinstance(json_parsed["summary"], str):
                        json_parsed["summary"] = json.dumps(
                            json_parsed["summary"], ensure_ascii=False
                        )

                if "answer" in json_parsed and json_parsed["answer"]:
                    if is_str_list(json_parsed["answer"]):
                        json_parsed["answer"] = "\n".join(json_parsed["answer"])
                    elif not isinstance(json_parsed["answer"], str):
                        json_parsed["answer"] = json.dumps(
                            json_parsed["answer"], ensure_ascii=False
                        )

                if "plan" in json_parsed:
                    if not isinstance(json_parsed["plan"], list):
                        json_parsed["plans"] = [json_parsed["plan"]]

                try:
                    result = ReasoningModelOutput.model_validate(json_parsed)
                    new_plans = []
                    for plan in result.plans or []:
                        params = plan.parameters
                        args = params.get("args")
                        operation = params.get("operation")
                        if (args is not None and
                                operation is not None and
                                isinstance(operation, str) and
                                any(keyword in operation for keyword in SANDBOX_TOOLS)):
                            new_plan = plan.copy() if hasattr(plan,
                                                              'copy') else plan.model_copy()
                            new_plan.parameters = args
                            new_plan.id = operation
                            if operation in FILE_TOOLS and not args.get("description"):
                                logger.info(
                                    f"文件工具缺少description参数，默认设置为{FILE_DESCRIPTION}"
                                )
                                new_plan.parameters["description"] = FILE_DESCRIPTION
                                if "edit_file" in operation:
                                    logger.info(
                                        f"文件工具append参数，默认设置为False"
                                    )
                                    new_plan.parameters["append"] = False
                            new_plans.append(new_plan)
                        else:
                            new_plans.append(plan)
                    result.plans = new_plans
                    return result
                except Exception as e:
                    logger.error(f"知识推理引擎模型输出解析失败！{json_parsed}, {e}")
                    raise ValueError(f"知识推理引擎模型输出解析失败！{json_parsed}, {e}")
            case _:
                return llm_out

    def convert_to_reason_output(
            self, knowledge_planner_info: KnowledgePlannerInfo
    ) -> ReasoningModelOutput:
        """
        将 KnowledgePlannerInfo 实例转换为 ReasoningModelOutput 实例

        Args:
            knowledge_planner_info: KnowledgePlannerInfo 实例

        Returns:
            ReasoningModelOutput 实例
        """
        reasoning_output = ReasoningModelOutput(
            reason=knowledge_planner_info.reason,
            status=knowledge_planner_info.status,
            plans=knowledge_planner_info.plans,
            plans_brief_description=knowledge_planner_info.plans_brief_description,
            summary=knowledge_planner_info.summary,
            answer=knowledge_planner_info.answer,
            ask_user=knowledge_planner_info.ask_user
        )

        return reasoning_output

    def _xml_to_model(self, llm_out: str) -> T:
        xml_strs = extract_valid_xmls(llm_out)
        if len(xml_strs) < 1:
            raise ValueError("Unable to obtain valid xml output.")

        xml_str = xml_strs[0]
        xml_dict = xmltodict.parse(xml_str)
        data_dict = xml_dict['root']

        # 预处理数据，确保嵌套的 BaseModel 列表被正确解析
        data_dict = self._preprocess_xml_dict(data_dict, self.model_type)

        if get_origin(self.model_type) is list:
            inner_type = get_args(self.model_type)[0]
            typed_cls = cast(Type[BaseModel], inner_type)
            return [typed_cls.model_validate(item) for item in
                    data_dict]  # type: ignore
        else:
            typed_cls = cast(Type[BaseModel], self.model_type)
            return typed_cls.model_validate(data_dict)

    def _preprocess_xml_dict(self, data_dict: dict,
                             model_type: Type[BaseModel]) -> dict:
        """
        预处理 XML 解析后的字典，确保列表字段被正确解析
        """
        if not isinstance(data_dict, dict):
            return data_dict

        if not (isinstance(model_type, type) and issubclass(model_type, BaseModel)):
            return data_dict

        processed_dict = {}

        for field_name, field_info in model_type.model_fields.items():
            if field_name not in data_dict:
                continue

            field_value = data_dict[field_name]
            field_annotation = field_info.annotation

            # 处理 None 或空值
            if field_value is None or field_value == '':
                processed_dict[field_name] = None
                continue

            # 获取字段的实际类型（处理 Optional/Union）
            origin = get_origin(field_annotation)
            args = get_args(field_annotation)

            if origin is Union:
                non_none_types = [arg for arg in args if arg is not type(None)]
                if non_none_types:
                    field_annotation = non_none_types[0]
                    origin = get_origin(field_annotation)
                    args = get_args(field_annotation)

            # 处理 List 类型
            if origin is list or origin is List:
                if args:
                    element_type = args[0]

                    # 检查元素类型是否为 BaseModel
                    if isinstance(element_type, type) and issubclass(element_type,
                                                                     BaseModel):
                        # 处理 xmltodict 的特殊结构：{'plan': [...]} 或 {'plan': {...}}
                        if isinstance(field_value, dict):
                            # 检查是否有单一的子键（如 'plan'）
                            if len(field_value) == 1:
                                sub_key = list(field_value.keys())[0]
                                field_value = field_value[sub_key]

                        # 确保是列表
                        if isinstance(field_value, dict):
                            field_value = [field_value]
                        elif not isinstance(field_value, list):
                            field_value = [field_value]

                        # 递归处理列表中的每个元素
                        processed_list = []
                        for item in field_value:
                            if isinstance(item, dict):
                                processed_item = self._preprocess_xml_dict(item,
                                                                           element_type)
                                processed_list.append(processed_item)
                            else:
                                processed_list.append(item)

                        processed_dict[field_name] = processed_list
                    else:
                        if not isinstance(field_value, list):
                            field_value = [field_value]
                        processed_dict[field_name] = field_value

            # 处理嵌套的 BaseModel
            elif isinstance(field_annotation, type) and issubclass(field_annotation,
                                                                   BaseModel):
                if isinstance(field_value, dict):
                    processed_dict[field_name] = self._preprocess_xml_dict(field_value,
                                                                           field_annotation)
                else:
                    processed_dict[field_name] = field_value

            # 处理 dict 类型（如 parameters）
            elif origin is dict or field_annotation is dict:
                processed_dict[field_name] = self._convert_to_dict(field_value)

            # 其他基本类型
            else:
                processed_dict[field_name] = field_value

        # 保留未在模型中定义的字段
        for key, value in data_dict.items():
            if key not in processed_dict:
                processed_dict[key] = value

        return processed_dict

    def _convert_to_dict(self, value):
        """将值转换为字典"""
        if value is None:
            return None

        if isinstance(value, dict):
            return dict(value)

        if isinstance(value, str):
            # 去除多余的空白字符
            value = value.strip()
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass

        return value
