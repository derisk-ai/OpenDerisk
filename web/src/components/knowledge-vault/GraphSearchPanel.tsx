'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiInterceptors } from '@/client/api';
import {
  getSpaceFullGraph,
  graphBacklinks,
  traverseGraph,
} from '@/client/api/knowledge-vault';
import type { EdgeOut, Subgraph } from '@/types/knowledge-vault';
import {
  ApartmentOutlined,
  ArrowRightOutlined,
  LinkOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Empty, Input, Spin, Tag, Tooltip } from 'antd';
import { useSpace } from './SpaceContext';

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

export default function GraphSearchPanel() {
  const { slug, selectedGraphEntity, setSelectedGraphEntity } = useSpace();
  const [data, setData] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [neighbors, setNeighbors] = useState<Subgraph | null>(null);
  const [backlinks, setBacklinks] = useState<EdgeOut[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

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

  useEffect(() => {
    if (!selectedGraphEntity) {
      setNeighbors(null);
      setBacklinks([]);
      return;
    }

    let mounted = true;
    setDetailLoading(true);
    Promise.all([
      apiInterceptors(traverseGraph(slug, selectedGraphEntity, 2, 'bfs')),
      apiInterceptors(graphBacklinks(slug, selectedGraphEntity)),
    ])
      .then(([resNeighbors, resBacklinks]) => {
        if (!mounted) return;
        setNeighbors(resNeighbors[1] || null);
        setBacklinks(resBacklinks[1] || []);
      })
      .finally(() => {
        if (!mounted) return;
        setDetailLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [slug, selectedGraphEntity]);

  const matchedEntities = useMemo(() => {
    const nodes = data?.nodes || [];
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return nodes
      .filter((n) => nodeLabel(n).toLowerCase().includes(q))
      .slice(0, 20);
  }, [data, query]);

  const entityStats = useMemo(() => {
    const nodes = data?.nodes || [];
    const edges = data?.edges || [];
    const degree = new Map<string, number>();
    for (const e of edges) {
      degree.set(e.subject, (degree.get(e.subject) || 0) + 1);
      degree.set(e.object, (degree.get(e.object) || 0) + 1);
    }
    const sorted = [...degree.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    return { nodes: nodes.length, edges: edges.length, topCentrality: sorted };
  }, [data]);

  function handleSelectEntity(entity: string) {
    setSelectedGraphEntity(entity);
    setQuery('');
  }

  const selectedLabel = selectedGraphEntity ? nodeLabel(selectedGraphEntity) : null;
  const selectedType = selectedGraphEntity ? nodeType(selectedGraphEntity) : null;

  return (
    <Spin spinning={loading} wrapperClassName="h-full">
      <div className="flex flex-col h-full p-3 gap-3">
        <div className="text-sm font-medium text-gray-700 flex items-center gap-1">
          <NodeIndexOutlined />
          图检索
        </div>

        <Input.Search
          size="small"
          placeholder="搜索实体 / 节点…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          allowClear
        />

        {query.trim() && (
          <div className="flex flex-col gap-1">
            <div className="text-xs text-gray-400">
              匹配 {matchedEntities.length} 个节点
            </div>
            {matchedEntities.length === 0 ? (
              <Empty description="无匹配" imageStyle={{ height: 40 }} />
            ) : (
              <div className="flex flex-col gap-0.5 max-h-40 overflow-auto custom-scrollbar">
                {matchedEntities.map((entity) => {
                  const type = nodeType(entity);
                  const label = nodeLabel(entity);
                  return (
                    <button
                      key={entity}
                      onClick={() => handleSelectEntity(entity)}
                      className="text-left px-2 py-1.5 rounded hover:bg-gray-50 border border-transparent hover:border-gray-200"
                    >
                      <div className="flex items-center gap-1.5">
                        <Tag
                          color={nodeColor(type)}
                          className="!text-[10px] !px-1 !py-0 !m-0"
                        >
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
        )}

        {!selectedGraphEntity && !query.trim() && (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-1">
              <Tag color="blue" className="!text-[10px] !m-0">
                {entityStats.nodes} 节点
              </Tag>
              <Tag color="cyan" className="!text-[10px] !m-0">
                {entityStats.edges} 边
              </Tag>
            </div>
            <div className="text-xs font-medium text-gray-700 mt-1">关键连接</div>
            {entityStats.topCentrality.length === 0 ? (
              <Empty description="暂无边数据" imageStyle={{ height: 40 }} />
            ) : (
              <div className="flex flex-col gap-1">
                {entityStats.topCentrality.map(([entity, count]) => (
                  <button
                    key={entity}
                    onClick={() => handleSelectEntity(entity)}
                    className="text-left px-2 py-1.5 rounded hover:bg-gray-50 border border-transparent hover:border-gray-200"
                  >
                    <div className="flex items-center gap-1.5">
                      <Tag
                        color={nodeColor(nodeType(entity))}
                        className="!text-[10px] !px-1 !py-0 !m-0"
                      >
                        {nodeType(entity)}
                      </Tag>
                      <span className="text-xs truncate flex-1" title={nodeLabel(entity)}>
                        {nodeLabel(entity)}
                      </span>
                      <span className="text-[10px] text-gray-400">{count}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {selectedGraphEntity && (
          <Spin spinning={detailLoading} wrapperClassName="flex-1 min-h-0">
            <div className="flex flex-col gap-3 overflow-auto custom-scrollbar">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 min-w-0">
                  <Tag
                    color={nodeColor(selectedType as string)}
                    className="!text-[10px] !px-1 !py-0 !m-0"
                  >
                    {selectedType}
                  </Tag>
                  <span className="text-sm font-medium truncate" title={selectedLabel || undefined}>
                    {selectedLabel}
                  </span>
                </div>
                <Tooltip title="清除选择">
                  <button
                    onClick={() => setSelectedGraphEntity(null)}
                    className="text-xs text-gray-400 hover:text-[#0C75FC]"
                  >
                    清除
                  </button>
                </Tooltip>
              </div>

              <div>
                <div className="text-xs font-medium text-gray-700 mb-1 flex items-center gap-1">
                  <ApartmentOutlined />
                  邻接节点 ({neighbors?.nodes.length || 0})
                </div>
                <div className="flex flex-col gap-0.5 max-h-48 overflow-auto custom-scrollbar">
                  {(neighbors?.nodes || []).length <= 1 ? (
                    <Empty description="无邻接节点" imageStyle={{ height: 40 }} />
                  ) : (
                    (neighbors?.nodes || []).map((entity) => {
                      if (entity === selectedGraphEntity) return null;
                      const type = nodeType(entity);
                      const label = nodeLabel(entity);
                      return (
                        <button
                          key={entity}
                          onClick={() => handleSelectEntity(entity)}
                          className="text-left px-2 py-1.5 rounded hover:bg-gray-50 border border-transparent hover:border-gray-200"
                        >
                          <div className="flex items-center gap-1.5">
                            <Tag
                              color={nodeColor(type)}
                              className="!text-[10px] !px-1 !py-0 !m-0"
                            >
                              {type}
                            </Tag>
                            <span className="text-xs truncate flex-1" title={label}>
                              {label}
                            </span>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>

              <div>
                <div className="text-xs font-medium text-gray-700 mb-1 flex items-center gap-1">
                  <LinkOutlined />
                  反向链接 ({backlinks.length})
                </div>
                <div className="flex flex-col gap-0.5 max-h-48 overflow-auto custom-scrollbar">
                  {backlinks.length === 0 ? (
                    <Empty description="无反向链接" imageStyle={{ height: 40 }} />
                  ) : (
                    backlinks.map((edge) => (
                      <div
                        key={edge.id}
                        className="text-xs px-2 py-1.5 rounded bg-gray-50 border border-gray-100"
                      >
                        <div className="flex items-center gap-1 flex-wrap">
                          <span className="truncate max-w-[80px]" title={edge.subject}>
                            {nodeLabel(edge.subject)}
                          </span>
                          <ArrowRightOutlined className="text-gray-400" />
                          <Tag color="blue" className="!text-[10px] !px-1 !py-0 !m-0">
                            {edge.predicate}
                          </Tag>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </Spin>
        )}
      </div>
    </Spin>
  );
}
