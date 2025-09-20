import datetime
import json
import logging
import random
import uuid
from abc import abstractmethod, ABCMeta
from copy import deepcopy
from enum import Enum
from typing import Any, Type, Dict, TypeVar, Generic, get_args

from pydantic import Field, BaseModel

from derisk.agent import Resource, AgentDummyTrigger
from derisk.core import ModelRequest, ModelMessage, ModelOutput, ModelMessageRoleType
from derisk.core.awel import DAG, BaseOperator
from derisk.core.awel.dag.base import DAGNode
from derisk.core.awel.flow import ViewMetadata
from derisk.core.awel.flow.flow_factory import FlowPanel, FlowCategory, State, FlowData, FlowPositionData, FlowNodeData, FlowEdgeData
from derisk.util.json_utils import find_json_objects
from derisk.util.module_utils import model_scan
from derisk.util.template_utils import render
from derisk_ext.agent.agents.awel.operators import ActionBranchConditionOperator, ActionBranchOperator, ActionOperator, _llm_client, ActionContextStrategy
from derisk_ext.agent.agents.reasoning.default.ability import valid_ability_types, Ability

logger: logging.Logger = logging.getLogger("awel")
OperatorType = TypeVar('OperatorType', bound=BaseOperator)
ModelType = TypeVar('ModelType', bound=BaseModel)


class ItemTypeEnum(str, Enum):
    ACTION_NODE = "action_node"
    BRANCH_NODE = "branch_node"
    NORMAL_EDGE = "normal_edge"
    BRANCH_EDGE = "branch_edge"


class _Meta(BaseModel):
    type: ItemTypeEnum = Field(..., description="节点类型")
    description: str = Field(..., description="节点功能描述")


class AwelJsonData(BaseModel):
    """"""
    # @abstractmethod
    # def to_dict(self):
    #     """
    #
    #     """


class AwelNodeData(AwelJsonData):
    node: Any = None

    def __init__(self, node: Any, **kwargs):
        super().__init__(**kwargs)
        self.node = node


class AwelEdgeData(AwelJsonData):
    source_node_id: str = None
    target_node_id: str = None

    def __init__(self, source_node_id: str, target_node_id: str, **kwargs):
        super().__init__(**kwargs)
        self.source_node_id: str = source_node_id
        self.target_node_id: str = target_node_id


class TransferMeta(ABCMeta):
    def __new__(cls, name, bases, namespace, **kwargs):
        new_class = super().__new__(cls, name, bases, namespace, **kwargs)
        new_class.after_define()
        return new_class


class Transfer(Generic[ModelType], metaclass=TransferMeta):
    meta: _Meta = None
    properties: ModelType = None

    _item_cls_register: Dict[ItemTypeEnum, Type["Transfer"]] = {}

    @classmethod
    def after_define(cls):
        if cls.meta and cls.meta.type:
            cls._item_cls_register[cls.meta.type.value] = cls

    @classmethod
    def property_cls(cls) -> Type[ModelType]:
        # 提取泛型参数ModelType
        for base in cls.__orig_bases__:
            if getattr(base, '__origin__', None) is Transfer:
                return get_args(base)[0]
        raise RuntimeError()

    def init_property(self, **kwargs):
        cls: Type[ModelType] = self.property_cls()
        self.properties = cls(**kwargs)

    @abstractmethod
    def to_awel(self, **kwargs) -> list[AwelJsonData]:
        """
        transfer to awel json data
        """

    @classmethod
    def to_prompt(cls) -> str:
        """
        description of the node
        """

        # 提取泛型参数ModelType
        model_type: Type[ModelType] = cls.property_cls()

        return json.dumps({
            "type": cls.meta.type.value,
            "description": cls.meta.description,
            "properties": model_type.model_json_schema()
        }, ensure_ascii=False) if model_type else None


class NodeProperty(BaseModel):
    node_id: str = Field(..., description="节点ID")


class ActionNodeProperty(NodeProperty):
    intention: str = Field(None, description="动作意图")

    ability_type: str = Field(
        ...,
        description="能力类型枚举",
        examples=[_type.__name__ for _type in valid_ability_types()],
    )

    ability_id: str = Field(
        ...,
        description="能力ID"
    )


class ActionNode(Transfer[ActionNodeProperty]):
    meta: _Meta = _Meta(
        type=ItemTypeEnum.ACTION_NODE,
        description="动作执行节点.",
    )

    def to_awel(self, **kwargs) -> list[AwelJsonData]:
        """
        transfer to awel json data
        """
        operator: ActionOperator = _build_operator(ActionOperator, {
            "app_code": kwargs.get("app_code"),
            "intention": self.properties.intention,
            "ability_type": self.properties.ability_type,
            "ability_id": self.properties.ability_id,
            "param_fill_strategy": ActionContextStrategy.CONTEXT_TO_LLM.value,
        })
        operator.set_node_id(self.properties.node_id)
        return [AwelNodeData(node=operator)]


class BranchNodeProperty(NodeProperty):
    criteria: str = Field(
        ...,
        description="用于定义分支决策逻辑的描述性陈述。"
    )


class BranchNode(Transfer[BranchNodeProperty]):
    meta: _Meta = _Meta(
        type=ItemTypeEnum.BRANCH_NODE,
        description="条件分支节点.",
    )

    def to_awel(self, **kwargs) -> list[AwelJsonData]:
        """
        transfer to awel json data
        """
        branch_operator: ActionBranchOperator = _build_operator(ActionBranchOperator, {
            "criteria": self.properties.criteria
        })
        branch_operator.set_node_id(self.properties.node_id)
        return [AwelNodeData(node=branch_operator)]


class EdgeProperty(BaseModel):
    source_node_id: str = Field(
        ...,
        description="源节点ID.表示本条边从哪个节点出发."
    )

    target_node_id: str = Field(
        ...,
        description="目的节点ID.表示本条边指向哪个节点."
    )


class Edge(Transfer[EdgeProperty]):
    meta: _Meta = _Meta(
        type=ItemTypeEnum.NORMAL_EDGE,
        description="常规边.",
    )

    def to_awel(self, **kwargs) -> list[AwelJsonData]:
        """
        transfer to awel json data
        """
        return [AwelEdgeData(source_node_id=self.properties.source_node_id, target_node_id=self.properties.target_node_id)]


class BranchEdgeProperty(EdgeProperty):
    branch: str = Field(
        ...,
        description="一个标签或键，用于表示该边所源自的BranchNode（分支节点）的特定分支结果。例如，可以是`是`、`否`、`大于0`或其他任何与源BranchNode中可能存在的分支相匹配的描述符。"
    )


class BranchEdge(Transfer[BranchEdgeProperty]):
    meta: _Meta = _Meta(
        type=ItemTypeEnum.BRANCH_EDGE,
        description="条件分支节点的出边.",
    )

    def to_awel(self, **kwargs) -> list[AwelJsonData]:
        """
        transfer to awel json data
        """

        result: list[AwelJsonData] = []
        branch_operator: ActionBranchConditionOperator = _build_operator(ActionBranchConditionOperator, {
            "branch": self.properties.branch
        })
        result.append(AwelNodeData(node=branch_operator))
        result.append(AwelEdgeData(source_node_id=self.properties.source_node_id, target_node_id=branch_operator.node_id))
        result.append(AwelEdgeData(source_node_id=branch_operator.node_id, target_node_id=self.properties.target_node_id))
        return result


def _build_operator(cls: Type[OperatorType], values: Dict[str, Any]) -> OperatorType:
    view_meta: ViewMetadata = deepcopy(cls.metadata)
    for parameter in view_meta.parameters:
        if parameter.name in values:
            parameter.value = values[parameter.name]

    operator: BaseOperator = cls.build_from(view_meta)
    operator.metadata = view_meta
    return operator


async def _build_awel(messages: list[ModelMessage], flow_service=None, **kwargs) -> DAG:
    # =============== 第一步 调用模型 生成JSON =============== #
    out: ModelOutput = await _llm_client().generate(request=ModelRequest(
        model="DeepSeek-v3",
        messages=messages,
        trace_id=kwargs.get("trace_id", ""),
        rpc_id=kwargs.get("rpc_id", ""),
    ))
    content: str = (out.content[-1] if isinstance(out.content, list) else out.content).object.data
    logger.info("awel generated: " + content)
    parsed_json = find_json_objects(content)[-1]
    return build_model_awel(parsed_json, flow_service=flow_service, **kwargs)


def build_model_awel(parsed_json: dict, flow_service=None, **kwargs):
    # =============== 第二步 JSON解析为中间数据 =============== #
    trans: list[Transfer] = []
    for data in parsed_json["items"]:
        cls: Type[Transfer] = Transfer._item_cls_register.get(data["type"])
        instance = cls()
        instance.init_property(**(data["data"]))
        trans.append(instance)

    # =============== 第三步 转为AWEL =============== #
    nodes: dict[str, BaseOperator] = {}  # {llm生成的node_id: 最终的node}
    edges: dict[str, set[str]] = {}  # {llm生成的node_id对应的连接关系 注意转换}
    dag_id = f"flow_dag_llm_" + str(uuid.uuid4())
    with DAG(dag_id) as dag:
        for transfer in trans:
            datas: list[AwelJsonData] = transfer.to_awel(**kwargs)
            for data in datas:
                _data_to_awel(data, nodes=nodes, edges=edges)

        # 添加trigger
        all_down = set([down for downs in edges.values() for down in downs])  # 取出所有节点的下游节点
        heads = nodes.keys() - all_down  # 全量节点减掉下游节点 剩下没做过下游的 也即头结点
        trigger = AgentDummyTrigger()
        nodes[trigger.node_id] = trigger
        edges[trigger.node_id] = heads

        # 连接边
        _connect_edge(edges, nodes)

    # =============== 第四步 后处理 =============== #
    # 刷新node_id以免重复
    _nodes_by_key: dict[str, set[str]] = {}
    for id, node in nodes.items():
        key: str = node.metadata.get_operator_key()
        node_ids = _nodes_by_key.get(key, set())
        node_ids.add(id)
        new_node_id = f"{node.metadata.id}_{len(node_ids)}"
        node.metadata.id = new_node_id
        node.set_node_id(new_node_id)
        _nodes_by_key[key] = node_ids

    # =============== 第五步 结果落表 =============== #
    if flow_service:
        flow_service.create_and_save_dag(_dag_to_panel(dag_id=dag_id, nodes=nodes, edges=edges, **kwargs))
    return dag


def _data_to_awel(data: AwelJsonData, nodes: dict[str, BaseOperator], edges: dict[str, set[str]]):
    if isinstance(data, AwelNodeData):
        node: BaseOperator = data.node
        nodes[node.node_id] = node

    elif isinstance(data, AwelEdgeData):
        source_node_id: str = data.source_node_id
        target_node_id: str = data.target_node_id
        targets: set[str] = edges.get(source_node_id, set())
        targets.add(target_node_id)
        edges[source_node_id] = targets


def _connect_edge(edges: dict[str, set[str]], nodes: dict[str, BaseOperator]):
    for source, targets in edges.items():
        if source not in nodes:
            raise RuntimeError(f"source node [{source}] not exist")
        for target in targets:
            if source not in nodes:
                raise RuntimeError(f"target node [{target}] not exist")
            nodes[source] >> nodes[target]


def _node_to_data(node: DAGNode) -> FlowNodeData:
    return FlowNodeData(
        width=320,
        height=320,
        id=node.metadata.id,
        position=FlowPositionData(x=0, y=0, zoom=0),
        position_absolute=FlowPositionData(x=0, y=0, zoom=0),
        type="customNode",
        data=node.metadata
    )


def _edge_to_data(llm_source: str, llm_target: str, llm_nodes: dict[str, BaseOperator]) -> FlowEdgeData:
    source_node = llm_nodes.get(llm_source)
    target_node = llm_nodes.get(llm_target)
    return FlowEdgeData(
        source=source_node.node_id,
        source_order=0,
        target=target_node.node_id,
        target_order=0,
        id=f"{source_node.node_id}|{target_node.node_id}",
        source_handle=f"{source_node.node_id}|outputs|{0}",
        target_handle=f"{target_node.node_id}|inputs|{0}",
        type="buttonedge",
    )


def _dag_to_panel(dag_id: str, nodes: dict[str, BaseOperator], edges: dict[str, set[str]], **kwargs) -> FlowPanel:
    flow_data: FlowData = FlowData(
        nodes=[_node_to_data(node) for node in nodes.values()],
        edges=[_edge_to_data(llm_source=source, llm_target=target, llm_nodes=nodes) for source, targets in edges.items() for target in targets],
        viewport=FlowPositionData(x=0, y=0, zoom=0)
    )

    ts = datetime.datetime.now()
    tss = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    name = f"llm_{tss}_{int(ts.timestamp()) % 1000}_{random.randint(0, 9999):04d}"
    return FlowPanel(
        label="dag_" + name,
        name=name,
        dag_id=dag_id,
        flow_category=FlowCategory.CHAT_AGENT,
        flow_data=flow_data,
        # flow_dag=None,
        description="模型自动生成的DAG",
        state=State.DEPLOYED,
        user_name=kwargs.get("user_name", "")
    )


async def build_ability(resource: Resource, **kwargs) -> str:
    abilities: list[Ability] = [ability for r in resource.sub_resources if (ability := Ability.by(r))]
    return "\n\n".join([json.dumps({
        "ability_type": ability.actual_type.__name__,
        "ability_id": ability.name,
    }, ensure_ascii=False) for ability in abilities])


async def build_schema() -> str:
    prompts: list[str] = [prompt for _, cls \
                          in model_scan("derisk_ext.agent.agents.awel", Transfer).items() \
                          if (prompt := cls.to_prompt())]
    return "\n\n".join([""] + prompts).strip()


_SYSTEM_PROMPT = '''
你是一个智能助手，请将用户问题拆解为可执行的流程图。

## 图元素Schema
{{schema}}


## 可用能力清单（只能选用下列工具）
{{ability}}
**注意：只能使用上述工具！若无匹配工具或参数不足需终止任务并说明原因**

## 输出格式约束
严格按以下JSON格式输出，确保可直接解析：
{
  "reason": "解释拆解/未拆解出流程图的原因",
  "items"?: [{
    "type": "图元素类型。只能从`图元素Schema`中选择"
    "data": "图元素需要的信息。必须严格满足`图元素Schema`中对应类型的property描述"
  }]
'''


async def build_awel(sop: str, resource: Resource, example_query: str = None, **kwargs) -> DAG:
    system_prompt: str = render(_SYSTEM_PROMPT, {
        "ability": await build_ability(resource=resource, **kwargs),
        "schema": await build_schema(),
        "example_query": example_query
    })
    return await _build_awel([
        ModelMessage(role=ModelMessageRoleType.SYSTEM, content=system_prompt),
        ModelMessage(role=ModelMessageRoleType.HUMAN, content=sop),
    ], **kwargs)
