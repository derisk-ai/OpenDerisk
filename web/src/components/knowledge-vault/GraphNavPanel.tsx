'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiInterceptors } from '@/client/api';
import { getSpaceFullGraph } from '@/client/api/knowledge-vault';
import type { Subgraph } from '@/types/knowledge-vault';
import { ApartmentOutlined, ReloadOutlined } from '@ant-design/icons';
import { Empty, Input, Spin, Tag, Tooltip, Typography } from 'antd';
import { useSpace } from './SpaceContext';

const { Title } = Typography;

function nodeType(id: string): string {
  if (id.startsWith('doc:')) return 'doc';
  if (id.startsWith('verbat:')) return 'verbat';
  return 'entity';
}

function nodeLabel(id: string): string {
  return id.replace(/^(doc|verbat):/, '');
}

function nodeColor(type: string): string {
  switch (type) {
    case 'doc':
      return 'blue';
    case 'verbat':
      return 'green';
    default:
      return 'violet';
  }
}

export default function GraphNavPanel() {
  const { slug, setView, setSelectedDoc } = useSpace();
  const [data, setData] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [, sub] = await apiInterceptors(getSpaceFullGraph(slug));
      setData(sub || null);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    const nodes = data?.nodes || [];
    const edges = data?.edges || [];
    const types = new Set<string>();
    for (const n of nodes) {
      types.add(nodeType(n));
    }
    return { nodes: nodes.length, edges: edges.length, types: Array.from(types) };
  }, [data]);

  const filteredNodes = useMemo(() => {
    const nodes = data?.nodes || [];
    const q = query.trim().toLowerCase();
    if (!q) return nodes;
    return nodes.filter((n) => nodeLabel(n).toLowerCase().includes(q));
  }, [data, query]);

  function handleNodeClick(id: string) {
    if (id.startsWith('doc:')) {
      setSelectedDoc(nodeLabel(id));
      setView('wiki');
    }
  }

  return (
    <Spin spinning={loading} wrapperClassName="h-full">
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 bg-white">
          <Title level={5} className="!mb-0 flex items-center gap-2 text-sm">
            <ApartmentOutlined /> Graph
          </Title>
          <div className="flex items-center gap-1">
            <Tooltip title="刷新">
              <button
                onClick={load}
                className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-400"
              >
                <ReloadOutlined className={`text-xs ${loading ? 'animate-spin' : ''}`} />
              </button>
            </Tooltip>
          </div>
        </div>

        <div className="p-2 flex flex-col gap-2 overflow-hidden flex-1 bg-white">
          {data ? (
            <>
              <div className="flex flex-wrap gap-1">
                <Tag color="blue" className="!text-[10px] !m-0">
                  {stats.nodes} 节点
                </Tag>
                <Tag color="cyan" className="!text-[10px] !m-0">
                  {stats.edges} 边
                </Tag>
                {stats.types.map((t) => (
                  <Tag key={t} color={nodeColor(t)} className="!text-[10px] !m-0">
                    {t}
                  </Tag>
                ))}
              </div>

              <Input.Search
                size="small"
                placeholder="搜索实体…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                allowClear
              />

              <div className="flex-1 min-h-0 overflow-auto custom-scrollbar">
                {filteredNodes.length === 0 ? (
                  <Empty description="无匹配实体" imageStyle={{ height: 40 }} />
                ) : (
                  <div className="flex flex-col gap-0.5">
                    {filteredNodes.map((id) => {
                      const type = nodeType(id);
                      const label = nodeLabel(id);
                      return (
                        <button
                          key={id}
                          onClick={() => handleNodeClick(id)}
                          className="text-left px-2 py-1.5 rounded hover:bg-gray-50 border border-transparent hover:border-gray-200"
                        >
                          <div className="flex items-center gap-1.5">
                            <Tag color={nodeColor(type)} className="!text-[10px] !px-1 !py-0 !m-0">
                              {type}
                            </Tag>
                            <span className="text-xs truncate flex-1" title={label}>
                              {label}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          ) : (
            <Empty description="暂无图谱数据" imageStyle={{ height: 40 }} />
          )}
        </div>
      </div>
    </Spin>
  );
}
