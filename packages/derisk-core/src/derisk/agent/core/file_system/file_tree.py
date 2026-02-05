from __future__ import annotations
import dataclasses
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Generic, TypeVar, Protocol, Tuple

from derisk.core.interface.file import FileStorageSystem, LocalFileStorage

logger = logging.getLogger(__name__)

# 泛型类型变量，用于自定义节点内容
T = TypeVar('T')



class ContentValidator(Protocol[T]):
    """内容验证器协议"""

    def __call__(self, content: T) -> bool: ...


@dataclass
class TreeNodeData(Generic[T]):
    """树节点数据基类，包含通用的树结构信息"""
    node_id: str
    """节点唯一标识"""
    name: str
    """节点名称"""
    parent_id: Optional[str] = None
    """父节点ID"""
    layer_count: int = 0
    """节点层级"""
    description: Optional[str] = None
    """节点描述"""
    content: Optional[T] = None
    """节点内容，类型由具体场景决定"""
    child_ids: List[str] = field(default_factory=list)
    """子节点列表"""
    state: Optional[str] = None
    """节点状态"""
    updated_at: datetime = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)


class TreeManager(Generic[T]):
    """通用树管理器 - 重构版本"""

    def __init__(
        self,
        storage_system: Optional[FileStorageSystem] = None,
        content_validator: Optional[ContentValidator[T]] = None,
        max_cache_size: int = 1000
    ):
        self.node_map: Dict[str, TreeNodeData[T]] = {}
        self.layer_index: Dict[int, List[str]] = defaultdict(list)
        self.storage_system = storage_system
        self.content_validator = content_validator

        # 自动加载持久化数据
        self._load_from_storage()

    def _load_from_storage(self) -> None:
        """从存储系统加载数据"""
        if not self.storage_system:
            return

        # data = self.storage_system.load() ## TODO
        data: Optional[dict] = None
        if data:
            self._deserialize_tree(data)

    def _deserialize_tree(self, data: Dict[str, Any]) -> None:
        """反序列化树结构"""
        try:
            # 首先创建所有节点
            for node_data in data.get('nodes', []):
                node = TreeNodeData(
                    node_id=node_data['node_id'],
                    name=node_data['name'],
                    parent_id=node_data.get('parent_id'),
                    layer_count=node_data.get('layer_count', 0),
                    description=node_data.get('description'),
                    state=node_data.get('state'),
                    created_at=datetime.fromisoformat(node_data['created_at']),
                    updated_at=datetime.fromisoformat(node_data['updated_at'])
                )
                self.node_map[node.node_id] = node

            # 然后建立父子关系
            for node_data in data.get('nodes', []):
                parent_id = node_data.get('parent_id')
                if parent_id and parent_id in self.node_map:
                    parent_nod = self.node_map[parent_id]
                    parent_nod.child_ids.append(node_data['node_id'])

            # 重建层级索引
            self._rebuild_layer_index()

        except Exception as e:
            logger.error(f"Failed to deserialize tree: {e}")

    def _rebuild_layer_index(self) -> None:
        """重建层级索引"""
        self.layer_index.clear()
        for node in self.node_map.values():
            self.layer_index[node.layer_count].append(node.node_id)

    def save_to_storage(self) -> bool:
        """保存到存储系统"""
        if not self.storage_system:
            return False

        data = self._serialize_for_storage()
        ## 文件系统写入存储

    def _serialize_for_storage(self) -> Dict[str, Any]:
        """序列化用于存储的数据"""
        return {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "name": node.name,
                    "parent_id": node.parent_id,
                    "layer_count": node.layer_count,
                    "description": node.description,
                    "state": node.state,
                    "created_at": node.created_at.isoformat(),
                    "updated_at": node.updated_at.isoformat()
                }
                for node in self.node_map.values()
            ],
            "metadata": {
                "total_nodes": len(self.node_map),
                "total_layers": max(self.layer_index.keys()) if self.layer_index else 0,
                "saved_at": datetime.now().isoformat()
            }
        }

    def upsert_node(
        self,
        node: TreeNodeData[T],
        parent_id: Optional[str] = None
    ) -> Tuple[bool,bool]:
        """添加或更新节点
        return
            bool(是否成功),bool(是否新增)
        """

        try:
            now = datetime.now()
            is_new = node.node_id not in self.node_map

            if is_new:
                return self._add_new_node(node, parent_id, now), True
            else:
                return self._update_existing_node(node, now), False
        except Exception as e:
            logger.error(f"Failed to upsert node {node.node_id}: {e}")
            return False, False

    def _update_existing_node(self, node: TreeNodeData[T], timestamp: datetime) -> bool:
        """更新现有节点 - 使用合并策略保留原有字段"""
        existing = self.node_map[node.node_id]

        # 验证内容
        if (node.content is not None and
            self.content_validator and
            not self.content_validator(node.content)):
            return False

        # 更新字段（显式传递的更新，未传递的保留原值）
        if node.name is not None:
            existing.name = node.name
        if node.description is not None:
            existing.description = node.description
        if node.state is not None:
            existing.state = node.state
        existing.updated_at = timestamp

        # 合并 content 而不是替换 - 保留原有字段，更新传递的字段
        if node.content is not None:
            if existing.content is None:
                existing.content = node.content
            else:
                # 合并策略：新值覆盖旧值，但未传递的字段保留
                for key, value in node.content.__dict__.items():
                    if value is not None:  # 只更新显式传递的非 None 值
                        setattr(existing.content, key, value)
        return True

    def _add_new_node(self, node: TreeNodeData[T], parent_id: Optional[str], timestamp: datetime) -> bool:
        """添加新节点"""
        # 验证内容
        if (node.content is not None and
            self.content_validator and
            not self.content_validator(node.content)):
            return False

        node.created_at = timestamp
        node.updated_at = timestamp

        if parent_id and parent_id != node.node_id:
            if parent_id not in self.node_map:
                logger.error(f"Parent node {parent_id} not found")
                return False

            node.parent_id = parent_id
            parent_node = self.node_map[parent_id]
            node.layer_count = parent_node.layer_count + 1

            # 更新父子关系
            # 避免重复添加
            if node.node_id not in parent_node.child_ids:
                parent_node.child_ids.append(node.node_id)

        self.node_map[node.node_id] = node

        # 更新层级索引
        self.layer_index[node.layer_count].append(node.node_id)
        return True


    def get_node(self, node_id: str) -> Optional[TreeNodeData[T]]:
        """获取节点"""
        return self.node_map.get(node_id)

    def get_children(self, node_id: str) -> List[TreeNodeData[T]]:
        """获取直接子节点 - 保持插入顺序"""
        current_node = self.node_map[node_id]
        if current_node:
            child_ids = current_node.child_ids
            return [self.node_map[child_id] for child_id in child_ids if child_id in self.node_map]
        else:
            return []

    def add_child_ordered(
        self,
        parent_id: str,
        child_node: TreeNodeData[T],
        position: Optional[int] = None
    ) -> bool:
        """在指定位置添加子节点"""
        if parent_id not in self.node_map or child_node.node_id in self.node_map:
            return False

        # 验证内容
        if (child_node.content is not None and
            self.content_validator and
            not self.content_validator(child_node.content)):
            return False

        # 设置父子关系
        child_node.parent_id = parent_id
        parent_node = self.node_map[parent_id]
        child_node.layer_count = parent_node.layer_count + 1

        # 插入到指定位置
        children_list = parent_node.child_ids
        if position is not None and 0 <= position <= len(children_list):
            children_list.insert(position, child_node.node_id)
        else:
            children_list.append(child_node.node_id)

        # 更新主映射和层级索引
        self.node_map[child_node.node_id] = child_node
        self.layer_index[child_node.layer_count].append(child_node.node_id)

        parent_node.updated_at = datetime.now()
        return True

    def move_child_position(
        self,
        parent_id: str,
        child_id: str,
        new_position: int
    ) -> bool:
        """移动子节点到新位置"""
        parent_node = self.node_map[parent_id]
        if (not parent_node or
            child_id not in parent_node.child_ids):
            return False

        children_list = parent_node.child_ids
        if child_id not in children_list:
            return False

        # 从原位置移除并插入到新位置
        children_list.remove(child_id)

        if new_position < 0:
            new_position = 0
        elif new_position > len(children_list):
            new_position = len(children_list)

        children_list.insert(new_position, child_id)
        self.node_map[parent_id].updated_at = datetime.now()
        return True

    def get_subtree(self, root_id: str) -> Optional[Dict[str, Any]]:
        """获取子树 - 使用BFS保持顺序"""
        return self._build_subtree(root_id)

    def _build_subtree(self, root_id: str) -> Optional[Dict[str, Any]]:
        """构建子树结构"""
        root_node = self.get_node(root_id)
        if not root_node:
            return None

        subtree = {
            'node': root_node,
            'children': []
        }

        # 使用队列进行BFS遍历
        queue = deque([(root_id, subtree['children'])])

        while queue:
            current_id, current_children = queue.popleft()
            current_node = self.node_map[current_id]
            # 按顺序处理子节点
            child_ids =current_node.child_ids
            for child_id in child_ids:
                child_node = self.get_node(child_id)
                if child_node:
                    child_data = {
                        'node': child_node,
                        'children': []
                    }
                    current_children.append(child_data)
                    queue.append((child_id, child_data['children']))

        return subtree

    def get_layer_nodes(self, layer_count: int) -> List[TreeNodeData[T]]:
        """获取指定层级的所有节点"""
        node_ids = self.layer_index[layer_count]
        return [self.node_map[node_id] for node_id in node_ids if node_id in self.node_map]

    def find_nodes(
        self,
        predicate: Callable[[TreeNodeData[T]], bool],
        limit: Optional[int] = None
    ) -> List[TreeNodeData[T]]:
        """根据条件查找节点"""
        result = []
        for node in self.node_map.values():
            if predicate(node):
                result.append(node)
                if limit and len(result) >= limit:
                    break
        return result

    def to_dict(
        self,
        content_serializer: Optional[Callable[[T], Any]] = None,
        max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        """序列化树结构"""
        roots = [node for node in self.node_map.values() if not node.parent_id]

        return {
            "roots": [
                self._serialize_node(root, content_serializer, max_depth, 0)
                for root in roots
            ],
            "total_nodes": len(self.node_map),
            "total_layers": max(self.layer_index.keys()) if self.layer_index else 0
        }

    def _serialize_node(
        self,
        node: TreeNodeData[T],
        content_serializer: Optional[Callable[[T], Any]],
        max_depth: Optional[int],
        current_depth: int
    ) -> Dict[str, Any]:
        """序列化单个节点 - 修复了缩进问题"""
        if max_depth is not None and current_depth > max_depth:
            return {'node_id': node.node_id, 'name': node.name, '_truncated': True}

        result = dataclasses.asdict(node, dict_factory=lambda x: {k: v for k, v in x if k != 'content'})

        # 处理内容序列化
        if node.content is not None:
            if content_serializer:
                result['content'] = content_serializer(node.content)
            else:
                result['content'] = str(node.content)

        # 处理子节点 - 按插入顺序
        children_data = []

        for child_id in node.child_ids:
            child_node = self.get_node(child_id)
            if child_node:
                children_data.append(
                    self._serialize_node(child_node, content_serializer, max_depth, current_depth + 1)
                )
        result['children'] = children_data

        return result

    def get_child_position(self, parent_id: str, child_id: str) -> Optional[int]:
        """获取子节点在父节点中的位置"""
        parent_node = self.node_map[parent_id]
        if not parent_node:
            return None

        try:
            return parent_node.child_ids.index(child_id)
        except ValueError:
            return None

    def swap_children(
        self,
        parent_id: str,
        first_child_id: str,
        second_child_id: str
    ) -> bool:
        """交换两个子节点的位置"""
        parent_node = self.node_map[parent_id]
        if not parent_node:
            return False

        children_list = parent_node.child_ids
        if first_child_id not in children_list or second_child_id not in children_list:
            return False

        first_pos = children_list.index(first_child_id)
        second_pos = children_list.index(second_child_id)

        children_list[first_pos], children_list[second_pos] = children_list[second_pos], children_list[first_pos]

        self.node_map[parent_id].updated_at = datetime.now()
        return True

    def remove_node(self, node_id: str, remove_children: bool = False) -> bool:
        if node_id not in self.node_map:
            return False

        node = self.node_map[node_id]

        # 检查是否有子节点
        if node.child_ids and not remove_children:
            return False

        # 先收集所有要删除的节点ID
        nodes_to_remove = set()
        if remove_children:
            self._collect_descendants(node_id, nodes_to_remove)

        # 一次性删除所有节点
        for remove_id in nodes_to_remove:
            self._remove_single_node(remove_id)

        return True

    def _collect_descendants(self, node_id: str, result: set) -> None:
        """收集所有后代节点ID"""
        node = self.node_map[node_id]
        for child_id in node.child_ids:
            result.add(child_id)
            self._collect_descendants(child_id, result)

    def _remove_single_node(self, node_id: str) -> None:
        """删除单个节点（内部方法）"""
        node = self.node_map[node_id]

        # 从父节点中移除
        if node.parent_id and node.parent_id in self.node_map:
            parent = self.node_map[node.parent_id]
            if node_id in parent.child_ids:
                parent.child_ids.remove(node_id)

        # 从层级索引中移除
        if node_id in self.layer_index[node.layer_count]:
            self.layer_index[node.layer_count].remove(node_id)

        del self.node_map[node_id]

    def validate_tree_integrity(self) -> List[str]:
        """验证树结构的完整性"""
        issues = []

        for node_id, node in self.node_map.items():
            # 检查父节点是否存在
            if node.parent_id and node.parent_id not in self.node_map:
                issues.append(f"Node {node_id} has non-existent parent {node.parent_id}")

            # 检查子节点是否存在且指向正确的父节点
            for child_id in node.child_ids:
                if child_id not in self.node_map:
                    issues.append(f"Node {node_id} has non-existent child {child_id}")

            # 检查层级一致性
            if node.parent_id:
                parent = self.node_map[node.parent_id]
                if node.layer_count != parent.layer_count + 1:
                    issues.append(f"Node {node_id} layer count inconsistent with parent")

        return issues

@dataclass
class DocumentContent:
    """文档管理场景的节点内容"""
    document_id: str
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_type: str = "text"
    size: int = 0


def example_usage():
    # 2. 创建文档树
    doc_manager = TreeManager()

    doc_manager.upsert_node(TreeNodeData(
        node_id="doc_001",
        name="Document Root",
        content=DocumentContent(
            document_id="doc_0011",
            content="Root document content",
            file_type="markdown"
        )
    ))
    doc_manager.upsert_node(TreeNodeData(
        node_id="doc_002",
        name="Document Root2",
        content=DocumentContent(
            document_id="doc_0021",
            content="Root2 document content",
            file_type="markdown"
        )
    ), "doc_001")

    doc_dict = doc_manager.to_dict()

    print("Document Tree:", doc_dict)


if __name__ == "__main__":
    example_usage()
