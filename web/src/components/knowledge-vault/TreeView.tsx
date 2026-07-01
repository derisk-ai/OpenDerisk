'use client';

import { FileOutlined, FolderOutlined } from '@ant-design/icons';
import { Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import type { TreeNode } from '@/types/knowledge-vault';

function collectDirSet(nodes: TreeNode[]): Set<string> {
  const set = new Set<string>();
  for (const n of nodes) {
    if (n.is_dir) {
      set.add(n.path);
      if (n.children) {
        for (const p of collectDirSet(n.children)) {
          set.add(p);
        }
      }
    }
  }
  return set;
}

function toDataNodes(nodes: TreeNode[], onClick: (path: string) => void): DataNode[] {
  return nodes.map((n) => ({
    key: n.path,
    title: n.is_dir ? (
      <span className="truncate whitespace-nowrap text-gray-600 text-xs">{n.name}</span>
    ) : (
      <span
        onClick={() => onClick(n.path)}
        className="truncate whitespace-nowrap cursor-pointer text-xs"
      >
        {n.name}
      </span>
    ),
    icon: n.is_dir ? <FolderOutlined className="text-gray-400" /> : <FileOutlined className="text-gray-400" />,
    isLeaf: !n.is_dir,
    children: n.is_dir ? toDataNodes(n.children || [], onClick) : undefined,
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
  const dirSet = collectDirSet(nodes);

  const handleSelect = (keys: React.Key[]) => {
    if (keys.length === 0) return;
    const key = String(keys[0]);
    if (dirSet.has(key)) return;
    onSelect(key);
  };

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
        onSelect={handleSelect}
      />
    </div>
  );
}
