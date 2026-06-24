'use client';

import { FileOutlined, FolderOutlined } from '@ant-design/icons';
import { Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import type { TreeNode } from '@/types/knowledge-vault';

function toDataNodes(nodes: TreeNode[] | null | undefined, onClick: (path: string) => void): DataNode[] {
  if (!nodes || !nodes.length) return [];
  return nodes.map((n) => ({
    key: n.path,
    title: (
      <span onClick={() => onClick(n.path)} className="cursor-pointer">
        {n.name}
      </span>
    ),
    icon: n.is_dir ? <FolderOutlined /> : <FileOutlined />,
    isLeaf: !n.is_dir,
    children: n.is_dir ? toDataNodes(n.children, onClick) : undefined,
  }));
}

export default function TreeView({
  nodes,
  onSelect,
  selectedKey,
  height = 480,
  className,
}: {
  nodes: TreeNode[];
  onSelect: (path: string) => void;
  selectedKey?: string;
  height?: number | string;
  className?: string;
}) {
  const style: React.CSSProperties = { overflow: 'auto' };
  if (height !== 'auto') {
    style.maxHeight = height;
  }
  return (
    <div className={['kv-tree', className || ''].filter(Boolean).join(' ')} style={style}>
      <Tree
        showIcon
        treeData={toDataNodes(nodes, onSelect)}
        selectedKeys={selectedKey ? [selectedKey] : []}
        onSelect={(keys) => {
          if (keys.length > 0) onSelect(String(keys[0]));
        }}
      />
    </div>
  );
}
