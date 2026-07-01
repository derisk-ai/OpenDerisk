'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Graph from 'graphology';
import type { Attributes } from 'graphology-types';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import {
  SigmaContainer,
  useLoadGraph,
  useRegisterEvents,
  useSetSettings,
  useSigma,
} from '@react-sigma/core';
import '@react-sigma/core/lib/style.css';
import { apiInterceptors } from '@/client/api';
import { getSpaceFullGraph } from '@/client/api/knowledge-vault';
import type { Subgraph } from '@/types/knowledge-vault';
import { Empty, Spin } from 'antd';
import { ApartmentOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons';
import { useSpace } from './SpaceContext';

const TYPE_COLORS: Record<string, string> = {
  doc: '#5470c6',
  verbat: '#91cc75',
  concept: '#c084fc',
  entity: '#fac858',
  default: '#94a3b8',
};

function detectType(id: string): string {
  if (id.startsWith('doc:')) return 'doc';
  if (id.startsWith('verbat:')) return 'verbat';
  if (id.startsWith('concept:')) return 'concept';
  if (id.startsWith('entity:')) return 'entity';
  return 'default';
}

function nodeColor(id: string): string {
  return TYPE_COLORS[detectType(id)] || TYPE_COLORS.default;
}

function nodeLabel(id: string): string {
  return id.replace(/^(doc|verbat|concept|entity):/, '');
}

function nodeSizeByDegree(degree: number, maxDegree: number): number {
  if (maxDegree === 0) return 5;
  const minSize = 4;
  const maxSize = 18;
  return minSize + Math.sqrt(degree / maxDegree) * (maxSize - minSize);
}

// ---------------------------------------------------------------------------
// Graph loader: builds graphology graph and runs ForceAtlas2 layout
// ---------------------------------------------------------------------------

function GraphLoader({ data }: { data: Subgraph }) {
  const loadGraph = useLoadGraph();

  useEffect(() => {
    const graph = new Graph();

    const nodeDegrees = new Map<string, number>();
    for (const edge of data.edges || []) {
      nodeDegrees.set(edge.subject, (nodeDegrees.get(edge.subject) || 0) + 1);
      nodeDegrees.set(edge.object, (nodeDegrees.get(edge.object) || 0) + 1);
    }
    const maxDegree = Math.max(1, ...nodeDegrees.values());

    for (const id of data.nodes || []) {
      graph.addNode(id, {
        label: nodeLabel(id),
        size: nodeSizeByDegree(nodeDegrees.get(id) || 0, maxDegree),
        color: nodeColor(id),
        x: Math.random() * 100,
        y: Math.random() * 100,
      });
    }

    for (const edge of data.edges || []) {
      if (graph.hasNode(edge.subject) && graph.hasNode(edge.object)) {
        const key = `${edge.subject}->${edge.object}`;
        if (!graph.hasEdge(key)) {
          graph.addEdgeWithKey(key, edge.subject, edge.object, {
            size: 0.5 + (edge.weight || 0) * 2,
            color: '#94a3b8',
            predicate: edge.predicate,
          });
        }
      }
    }

    const nodeCount = graph.order;
    if (nodeCount > 1) {
      const settings = forceAtlas2.inferSettings(graph);
      forceAtlas2.assign(graph, {
        iterations: nodeCount > 500 ? 50 : 120,
        settings: {
          ...settings,
          gravity: 1,
          scalingRatio: nodeCount > 300 ? 4 : 2,
          strongGravityMode: true,
          barnesHutOptimize: nodeCount > 50,
        },
      });
    }

    loadGraph(graph);
  }, [data, loadGraph]);

  return null;
}

// ---------------------------------------------------------------------------
// Render settings: highlight selected node + dim others
// ---------------------------------------------------------------------------

function GraphRenderSettings({
  selectedNode,
  nodeCount,
}: {
  selectedNode: string | null;
  nodeCount: number;
}) {
  const sigma = useSigma();
  const setSettings = useSetSettings();

  useEffect(() => {
    setSettings({
      hideEdgesOnMove: true,
      hideLabelsOnMove: true,
      labelDensity: nodeCount > 1000 ? 0.1 : nodeCount > 300 ? 0.2 : 0.4,
      labelRenderedSizeThreshold: nodeCount > 1000 ? 16 : 8,
      renderEdgeLabels: false,
      nodeReducer: (node, attrs) => {
        const res: Attributes = { ...attrs };
        if (selectedNode) {
          if (node === selectedNode) {
            res.size = (attrs.size || 5) * 1.5;
            res.zIndex = 10;
            res.forceLabel = true;
          } else if (!sigma.getGraph().neighbors(selectedNode).includes(node)) {
            res.color = '#e2e8f0';
            res.label = '';
          }
        }
        return res;
      },
      edgeReducer: (edge, attrs) => {
        const res: Attributes = { ...attrs };
        if (selectedNode) {
          const graph = sigma.getGraph();
          const [source, target] = graph.extremities(edge);
          const connected = source === selectedNode || target === selectedNode;
          if (connected) {
            res.size = 2;
            res.color = '#ff4d4f';
          } else {
            res.color = '#f1f5f9';
          }
        }
        return res;
      },
    });
    sigma.refresh();
  }, [setSettings, sigma, selectedNode, nodeCount]);

  return null;
}

// ---------------------------------------------------------------------------
// Event handler: click / hover
// ---------------------------------------------------------------------------

function EventHandler({
  onNodeClick,
  onHoverChange,
}: {
  onNodeClick: (node: string) => void;
  onHoverChange: (node: string | null) => void;
}) {
  const registerEvents = useRegisterEvents();

  useEffect(() => {
    registerEvents({
      clickNode: (event) => onNodeClick(event.node),
      enterNode: (event) => onHoverChange(event.node),
      leaveNode: () => onHoverChange(null),
    });
  }, [registerEvents, onNodeClick, onHoverChange]);

  return null;
}

// ---------------------------------------------------------------------------
// Zoom controls
// ---------------------------------------------------------------------------

function ZoomControls() {
  const sigma = useSigma();
  return (
    <div className="absolute top-3 right-3 flex flex-col gap-1 z-10">
      <button
        onClick={() => sigma.getCamera().animatedZoom({ duration: 200 })}
        className="w-7 h-7 flex items-center justify-center rounded bg-white/90 border border-gray-200 text-gray-600 hover:bg-gray-50"
      >
        <ZoomInOutlined className="text-xs" />
      </button>
      <button
        onClick={() => sigma.getCamera().animatedUnzoom({ duration: 200 })}
        className="w-7 h-7 flex items-center justify-center rounded bg-white/90 border border-gray-200 text-gray-600 hover:bg-gray-50"
      >
        <ZoomOutOutlined className="text-xs" />
      </button>
      <button
        onClick={() => sigma.getCamera().animatedReset({ duration: 300 })}
        className="w-7 h-7 flex items-center justify-center rounded bg-white/90 border border-gray-200 text-gray-600 hover:bg-gray-50 text-xs"
      >
        ⌘
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function GraphCanvas() {
  const { slug, selectedGraphEntity, setSelectedGraphEntity } = useSpace();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Subgraph | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    apiInterceptors(getSpaceFullGraph(slug))
      .then(([, sub]) => {
        if (!mounted) return;
        setData(sub || null);
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [slug]);

  const handleNodeClick = useCallback(
    (node: string) => {
      setSelectedGraphEntity(node);
    },
    [setSelectedGraphEntity],
  );

  const hoverNodeRef = (node: string | null) => {
    // Placeholder for future hover interactions
  };

  const nodeCount = data?.nodes.length || 0;

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
        <div className="flex items-center gap-2">
          <ApartmentOutlined className="text-[#0C75FC]" />
          <span className="text-sm font-medium text-gray-700">
            {data.nodes.length} 节点 / {data.edges.length} 边
          </span>
        </div>
        {selectedGraphEntity && (
          <span className="text-xs text-[#0C75FC] truncate max-w-[200px]">
            已选择: {nodeLabel(selectedGraphEntity)}
          </span>
        )}
      </div>
      <div className="flex-1 relative min-h-0">
        <SigmaContainer
          style={{ width: '100%', height: '100%', background: 'transparent' }}
          settings={{
            defaultNodeType: 'circle',
            defaultNodeColor: '#94a3b8',
            defaultEdgeColor: '#cbd5e1',
            labelSize: 12,
            labelWeight: 'bold',
            labelColor: { color: '#1e293b' },
            renderEdgeLabels: false,
            hideEdgesOnMove: true,
            hideLabelsOnMove: true,
            stagePadding: 20,
          }}
        >
          <GraphLoader data={data} />
          <GraphRenderSettings selectedNode={selectedGraphEntity} nodeCount={nodeCount} />
          <EventHandler onNodeClick={handleNodeClick} onHoverChange={hoverNodeRef} />
          <ZoomControls />
        </SigmaContainer>
      </div>
    </div>
  );
}
