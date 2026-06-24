'use client';

import { apiInterceptors } from '@/client/api';
import { getSpaceFullGraph } from '@/client/api/knowledge-vault';
import type { Subgraph } from '@/types/knowledge-vault';
import { Empty, Spin } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useSpace } from './SpaceContext';

let GraphClass: any;

export default function GraphCanvas() {
  const { slug } = useSpace();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Subgraph | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    import('@antv/g6')
      .then((mod) => {
        GraphClass = mod.Graph || mod.default;
        return apiInterceptors(getSpaceFullGraph(slug));
      })
      .then(([, sub]) => {
        if (!mounted) return;
        setData(sub || null);
      })
      .catch(() => {
        if (!mounted) return;
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [slug]);

  useEffect(() => {
    if (!GraphClass || !containerRef.current || !data) return;

    const nodes = (data.nodes || []).map((n) => ({
      id: n,
      data: { label: n },
      style: {
        labelText: n.length > 20 ? `${n.slice(0, 20)}…` : n,
        size: 16,
        fill: n.startsWith('doc:') ? '#5470c6' : n.startsWith('verbat:') ? '#91cc75' : '#fac858',
      },
    }));

    const edges = (data.edges || []).map((e) => ({
      id: e.id,
      source: e.subject,
      target: e.object,
      data: { predicate: e.predicate },
      style: {
        labelText: e.predicate,
        stroke: '#999',
      },
    }));

    const graph = new GraphClass({
      container: containerRef.current,
      data: { nodes, edges },
      layout: { type: 'force' },
      autoFit: 'view',
      node: {
        style: {
          labelFill: '#333',
          labelFontSize: 10,
        },
      },
      edge: {
        style: {
          labelFontSize: 9,
          labelFill: '#666',
          endArrow: true,
        },
      },
      behaviors: ['zoom-canvas', 'drag-canvas', 'drag-node'],
    });

    graphRef.current = graph;
    graph.render().catch(() => {});

    return () => {
      try {
        graph.destroy();
      } catch {
        // ignore
      }
      graphRef.current = null;
    };
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin tip="加载图谱中..." />
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return <Empty description="当前空间暂无图谱数据" className="mt-12" />;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-gray-200 bg-white flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">
          {data.nodes.length} 节点 / {data.edges.length} 边
        </span>
      </div>
      <div ref={containerRef} className="flex-1 bg-gray-50 min-h-0" />
    </div>
  );
}
