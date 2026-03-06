'use client';
import React from 'react';
import { Card, Tag, Typography, Space } from 'antd';
import {
  BulbOutlined,
  ToolOutlined,
  MessageOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import type { CanvasBlock } from '@/types/v2';

const { Text, Paragraph } = Typography;

interface CanvasRendererProps {
  blocks: CanvasBlock[];
}

const BlockIcon: React.FC<{ type: string }> = ({ type }) => {
  const icons: Record<string, React.ReactNode> = {
    thinking: <BulbOutlined style={{ color: '#1890ff' }} />,
    tool_call: <ToolOutlined style={{ color: '#722ed1' }} />,
    message: <MessageOutlined style={{ color: '#52c41a' }} />,
    task: <CheckCircleOutlined style={{ color: '#13c2c2' }} />,
    plan: <ClockCircleOutlined style={{ color: '#fa8c16' }} />,
    error: <ExclamationCircleOutlined style={{ color: '#f5222d' }} />,
    code: <CodeOutlined style={{ color: '#2f54eb' }} />,
  };
  return <>{icons[type] || <MessageOutlined />}</>;
};

const ThinkingBlock: React.FC<{ block: CanvasBlock }> = ({ block }) => (
  <Card size="small" style={{ marginBottom: 8, backgroundColor: '#f0f5ff', borderLeft: '4px solid #1890ff' }}>
    <Space>
      <BlockIcon type="thinking" />
      <Text strong>Thinking</Text>
    </Space>
    <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>{block.content}</Paragraph>
  </Card>
);

const ToolCallBlock: React.FC<{ block: CanvasBlock }> = ({ block }) => {
  const status = block.metadata?.status || 'pending';
  const statusColors: Record<string, string> = { pending: 'orange', completed: 'green', failed: 'red' };
  return (
    <Card size="small" style={{ marginBottom: 8, backgroundColor: '#f9f0ff', borderLeft: '4px solid #722ed1' }}>
      <Space>
        <BlockIcon type="tool_call" />
        <Text strong>{block.metadata?.tool_name || 'Tool'}</Text>
        <Tag color={statusColors[status]}>{status}</Tag>
      </Space>
      {block.content && <pre style={{ marginTop: 8, marginBottom: 0, backgroundColor: '#f5f5f5', padding: 8, borderRadius: 4, fontSize: 12, overflow: 'auto' }}>{block.content}</pre>}
    </Card>
  );
};

const TaskBlock: React.FC<{ block: CanvasBlock }> = ({ block }) => {
  const status = block.metadata?.status || 'pending';
  const statusColors: Record<string, string> = { pending: 'default', running: 'processing', completed: 'success', failed: 'error' };
  return (
    <Card size="small" style={{ marginBottom: 8, borderLeft: '4px solid #13c2c2' }}>
      <Space>
        <BlockIcon type="task" />
        <Text strong>{block.metadata?.task_name || block.content}</Text>
        <Tag color={statusColors[status]}>{status}</Tag>
      </Space>
      {block.metadata?.description && <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>{block.metadata.description}</Paragraph>}
    </Card>
  );
};

const CodeBlock: React.FC<{ block: CanvasBlock }> = ({ block }) => (
  <Card size="small" style={{ marginBottom: 8, borderLeft: '4px solid #2f54eb' }}>
    <Space>
      <BlockIcon type="code" />
      <Tag>{block.metadata?.language || 'code'}</Tag>
    </Space>
    <pre style={{ marginTop: 8, marginBottom: 0, backgroundColor: '#1e1e1e', color: '#d4d4d4', padding: 12, borderRadius: 4, fontSize: 12, overflow: 'auto' }}>{block.metadata?.code || block.content}</pre>
  </Card>
);

const ErrorBlock: React.FC<{ block: CanvasBlock }> = ({ block }) => (
  <Card size="small" style={{ marginBottom: 8, backgroundColor: '#fff1f0', borderLeft: '4px solid #f5222d' }}>
    <Space>
      <BlockIcon type="error" />
      <Text type="danger" strong>Error: {block.metadata?.error_type}</Text>
    </Space>
    <Paragraph type="danger" style={{ marginTop: 8, marginBottom: 0 }}>{block.metadata?.error_message || block.content}</Paragraph>
  </Card>
);

const BlockRenderer: React.FC<{ block: CanvasBlock }> = ({ block }) => {
  switch (block.block_type) {
    case 'thinking': return <ThinkingBlock block={block} />;
    case 'tool_call': return <ToolCallBlock block={block} />;
    case 'task': return <TaskBlock block={block} />;
    case 'code': return <CodeBlock block={block} />;
    case 'error': return <ErrorBlock block={block} />;
    default: return <Card size="small" style={{ marginBottom: 8 }}><Paragraph>{block.content}</Paragraph></Card>;
  }
};

export const CanvasRenderer: React.FC<CanvasRendererProps> = ({ blocks }) => {
  if (!blocks || blocks.length === 0) return null;
  return <div>{blocks.map((block) => <BlockRenderer key={block.block_id} block={block} />)}</div>;
};

export default CanvasRenderer;
