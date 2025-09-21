import json
from datetime import datetime
import logging
import timeit
from enum import Enum
from typing import Optional

from derisk import SystemApp
from derisk.component import ComponentType
from derisk.core import LLMClient
from derisk.model import DefaultLLMClient
from derisk.model.cluster import WorkerManagerFactory
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService
from ...api.schemas import SpaceServeRequest, SpaceServeResponse, CreateGraphRelationRequest, QueryGraphProjectRequest, \
    GraphProject
from ...config import SERVE_GRAPH_SERVICE_COMPONENT_NAME, GraphRagServeConfig
from ...models.graph_node_db import GraphNodeDao, GraphNodeEntity
from ...models.knowledge_space_graph_relation_db import KnowledgeSpaceGraphRelationEntity, \
    KnowledgeSpaceGraphRelationDao
from ...models.models import KnowledgeSpaceEntity, KnowledgeSpaceDao
from ...storage_manager import StorageManager


class KnowledgeGraphType(Enum):
    AKG = "知蛛平台"
    OTHER = "其他知识图谱平台"

logger = logging.getLogger(__name__)

class GraphService(BaseService[KnowledgeSpaceEntity, SpaceServeRequest, SpaceServeResponse]):
    name = SERVE_GRAPH_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: GraphRagServeConfig,
        dao: Optional[KnowledgeSpaceDao] = None,
        relation_dao: Optional[KnowledgeSpaceGraphRelationDao] = None,
        node_dao: Optional[GraphNodeDao] = None
    ):
        self._dao: KnowledgeSpaceDao = dao
        self._relation_dao: KnowledgeSpaceGraphRelationDao = relation_dao
        self._node_dao: GraphNodeDao = node_dao
        self._graph_serve_config = config

        super().__init__(system_app)


    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or KnowledgeSpaceDao()
        self._relation_dao = self._relation_dao or KnowledgeSpaceGraphRelationDao()
        self._node_dao = self._node_dao or GraphNodeDao()
        self._system_app = system_app


    @property
    def storage_manager(self):
        return StorageManager.get_instance(self._system_app)

    @property
    def dao(
        self,
    ) -> BaseDao[KnowledgeSpaceEntity, SpaceServeRequest, SpaceServeResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> GraphRagServeConfig:
        """Returns the internal ServeConfig."""
        return self._graph_serve_config

    @property
    def llm_client(self) -> LLMClient:
        worker_manager = self._system_app.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        return DefaultLLMClient(worker_manager, True)


    def get_graph_projects(self, request: QueryGraphProjectRequest):
        logger.info(f"get_graph_projects request is {request}")
        start_time = timeit.default_timer()

        if not request or not request.user_token:
            raise Exception("user_token is required")


        return None


    def get_nodes_from_schema_tree(self, schema_tree: dict, project_id: str, is_first: bool = True):
        # 解析当前节点
        if is_first:
            current_node_detail = schema_tree.entityTypeDetail
            current_node_children = schema_tree.children
        else:
            current_node_detail = schema_tree.get('entityTypeDetail')
            current_node_children = schema_tree.get('children')

        # 组装node
        version = datetime.now().strftime('%Y-%m-%d')
        node = GraphNodeEntity(
            project_id=project_id,
            node_id=str(current_node_detail.get('id')),
            name=current_node_detail.get('name'),
            name_zh=current_node_detail.get('nameZh'),
            description=current_node_detail.get('desc'),
            scope=current_node_detail.get('visibleScopeEnumCode'),
            version=version
        )
        nodes = [node]

        # 递归查询
        for children in current_node_children:
            temp_node = self.get_nodes_from_schema_tree(children, project_id, False)
            nodes.extend(temp_node)

        # 结束条件
        if not current_node_children:
            return nodes
        logger.info(f"nodes len is {len(nodes)}")

        return nodes

    def init_graph_nodes(self, request: CreateGraphRelationRequest):
        logger.info(f"init_graph_nodes request is {request}")

        if not request.project_id or not request.user_token:
            raise Exception("project_id and user_token is required")

        return None
    def create_graph_relation(self, request: CreateGraphRelationRequest):
        logger.info(f"create_graph_relation request is {request}")

        # 检查知识空间权限
        if not request.knowledge_id:
            raise Exception("knowledge_id is required")
        spaces = self._dao.get_knowledge_space_by_knowledge_ids([request.knowledge_id])
        if not spaces:
            raise Exception("knowledge_id is not exist")

        # 检查知识图谱权限
        if not request or not request.user_token or not request.user_login_name or not request.project_id:
            raise Exception("user_token, user_login_name and project_id is required")
        return None


    def get_graph_relation(self, knowledge_id: str):
        logger.info(f"get_graph_relation knowledge_id is {knowledge_id}")

        # 检查空间是否存在
        spaces = self._dao.get_knowledge_space_by_knowledge_ids([knowledge_id])
        if not spaces:
            raise Exception("knowledge_id is not exist")

        # 查询关联关系
        relations = self._relation_dao.get_relations(query=KnowledgeSpaceGraphRelationEntity(
            knowledge_id=knowledge_id,
            storage_type=KnowledgeGraphType.AKG.name
        ))

        # 展示数据
        res = []
        for relation in relations:
            res.append(CreateGraphRelationRequest(
                project_id=str(relation.project_id),
                project_name=relation.project_name,
                storage_type=relation.storage_type
            ))
        logger.info(f"get_graph_relation res is {res}")

        return res

    def get_full_graph(self, request: CreateGraphRelationRequest):
        logger.info(f"get_full_graph request is {request}")

        # 检查参数
        if not request or not request.knowledge_id:
            raise Exception("knowledge_id is required")
        if not request.project_id:
            raise Exception("project_id is required")

        # 检查关联关系
        relations = self._relation_dao.get_relations(query=KnowledgeSpaceGraphRelationEntity(
            knowledge_id=request.knowledge_id,
            storage_type=KnowledgeGraphType.AKG.name,
            project_id=request.project_id
        ))
        if not relations:
            logger.error("relation is empty, need to create relation first")

            raise Exception(
                f"relation is empty, need to create relation first: {request.knowledge_id}, {request.project_id}")

        return None



