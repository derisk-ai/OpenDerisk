from datetime import datetime
from typing import List

from sqlalchemy import Column, DateTime, Integer, String, Text

from derisk.storage.metadata import Model, BaseDao


class GraphNodeEntity(Model):
    __tablename__ = "graph_node"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer)
    node_id = Column(String(100))
    name = Column(String(100))
    name_zh = Column(String(100))
    description = Column(Text)
    scope = Column(String(100))
    version = Column(String(100))
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)

    def __repr__(self):
        return (
            f"GraphNodeEntity(id={self.id}, project_id='{self.project_id}', "
            f"node_id='{self.node_id}', name='{self.name}', name_zh='{self.name_zh}', "
            f"description='{self.description}', scope='{self.scope}',version='{self.version}',"
            f"gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}'"
        )

    def to_dict(self):
        return {
            "__tablename__": self.__tablename__,
            "id": self.id,
            "project_id": self.project_id,
            "node_id": self.node_id,
            "name": self.name,
            "name_zh": self.name_zh,
            "description": self.description,
            "scope": self.scope,
            "version": self.version,
            "gmt_created": self.gmt_created,
            "gmt_modified": self.gmt_modified,
        }


class GraphNodeDao(BaseDao):
    def create_node(self, node: GraphNodeEntity):
        session = self.get_raw_session()
        graph_node = GraphNodeEntity(
            project_id=node.project_id,
            node_id=node.node_id,
            name=node.name,
            name_zh=node.name_zh,
            description=node.description,
            scope=node.scope,
            version=node.version,
            gmt_created=datetime.now(),
            gmt_modified=datetime.now(),
        )
        session.add(graph_node)
        session.commit()
        node_id = graph_node.id
        session.close()

        return node_id

    def batch_create_nodes(self, nodes: List[GraphNodeEntity]) -> None:
        session = self.get_raw_session()
        try:
            batch_size = 200
            current_time = datetime.now()

            # 分批次处理数据
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i : i + batch_size]

                # 转换为数据库兼容的字典格式
                mappings = [
                    {
                        "project_id": node.project_id,
                        "node_id": node.node_id,
                        "name": node.name,
                        "name_zh": node.name_zh,
                        "description": node.description,
                        "scope": node.scope,
                        "version": node.version,
                        "gmt_created": current_time,
                        "gmt_modified": current_time,
                    }
                    for node in batch
                ]

                # 批量插入（绕过 ORM 事件，直接生成 SQL）
                session.bulk_insert_mappings(GraphNodeEntity, mappings)

            # 统一提交事务（原子性保证）
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()


    def get_nodes(self, query: GraphNodeEntity, page=1, page_size=20):
        session = self.get_raw_session()
        nodes = session.query(GraphNodeEntity)
        if query.id is not None:
            nodes = nodes.filter(GraphNodeEntity.id == query.id)
        if query.project_id is not None:
            nodes = nodes.filter(GraphNodeEntity.project_id == query.project_id)
        if query.node_id is not None:
            nodes = nodes.filter(GraphNodeEntity.node_id == query.node_id)
        if query.name is not None:
            nodes = nodes.filter(GraphNodeEntity.name == query.name)
        if query.name_zh is not None:
            nodes = nodes.filter(GraphNodeEntity.name_zh == query.name_zh)
        if query.version is not None:
            nodes = nodes.filter(GraphNodeEntity.version == query.version)
        nodes = nodes.order_by(GraphNodeEntity.id.asc())
        nodes = nodes.offset((page - 1) * page_size).limit(page_size)

        result = nodes.all()
        session.close()
        return result


