'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiInterceptors } from '@/client/api';
import { getWikiTree, listDocs } from '@/client/api/knowledge-vault';
import type { DocMeta, TreeNode } from '@/types/knowledge-vault';
import { BookOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Empty, Spin, Tag, Tooltip, Typography } from 'antd';
import TreeView from './TreeView';
import { useSpace } from './SpaceContext';

const { Title } = Typography;

const PAGE_TYPE_META: Record<string, { color: string; label: string }> = {
  concept: { color: 'violet', label: '概念' },
  note: { color: 'blue', label: '笔记' },
  source: { color: 'green', label: '原文' },
  person: { color: 'orange', label: '人物' },
  org: { color: 'cyan', label: '组织' },
  event: { color: 'red', label: '事件' },
  reference: { color: 'purple', label: '参考' },
  index: { color: 'geekblue', label: '索引' },
};

function metaFor(type: string) {
  return PAGE_TYPE_META[type] || { color: 'default', label: type || '其他' };
}

export default function KnowledgeTreePanel({ onCreate }: { onCreate: () => void }) {
  const { slug, selectedDoc, openDoc, refreshKey } = useSpace();
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [loading, setLoading] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [, t] = await apiInterceptors(getWikiTree(slug));
      const [, d] = await apiInterceptors(listDocs(slug, 200, 0));
      setTree(t || []);
      setDocs(d || []);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    loadAll();
  }, [loadAll, refreshKey]);

  const grouped = useMemo(() => {
    const map: Record<string, DocMeta[]> = {};
    for (const d of docs) {
      const key = d.type || 'other';
      (map[key] ||= []).push(d);
    }
    return map;
  }, [docs]);

  return (
    <Spin spinning={loading} className="h-full">
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 bg-white">
          <Title level={5} className="!mb-0 flex items-center gap-2 text-sm">
            <BookOutlined /> Wiki ({docs.length})
          </Title>
          <div className="flex items-center gap-1">
            <Tooltip title="刷新">
              <button
                onClick={loadAll}
                className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-400"
              >
                <ReloadOutlined className={`text-xs ${loading ? 'animate-spin' : ''}`} />
              </button>
            </Tooltip>
            <Tooltip title="新建文档">
              <Button size="small" type="primary" icon={<PlusOutlined />} onClick={onCreate} />
            </Tooltip>
          </div>
        </div>
        <div className="p-3 flex flex-col gap-2 overflow-hidden flex-1 bg-white">
          {docs.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {Object.entries(grouped).map(([type, items]) => {
                const m = metaFor(type);
                return (
                  <Tag key={type} color={m.color} className="!text-[10px] !m-0">
                    {m.label} · {items.length}
                  </Tag>
                );
              })}
            </div>
          )}
          {tree.length ? (
            <TreeView
              nodes={tree}
              onSelect={openDoc}
              selectedKey={selectedDoc || undefined}
              height="auto"
              className="flex-1 min-h-0"
            />
          ) : (
            <Empty description="暂无 wiki 文档" imageStyle={{ height: 40 }} />
          )}
        </div>
      </div>
    </Spin>
  );
}
