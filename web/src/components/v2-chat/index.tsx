'use client';
import React, { useCallback, useRef, useEffect, useState } from 'react';
import { Input, Button, Spin, Empty, Typography, Tag, Card, Space, Alert } from 'antd';
import {
  SendOutlined,
  StopOutlined,
  ClearOutlined,
  RobotOutlined,
  UserOutlined,
  ToolOutlined,
  BulbOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useV2Chat } from '@/hooks/use-v2-chat';
import { InteractionHandler } from '@/components/interaction';
import type { V2StreamChunk } from '@/types/v2';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

interface V2ChatProps {
  agentName: string;
  placeholder?: string;
  height?: number | string;
  onSessionChange?: (sessionId: string | null) => void;
}

const ChunkRenderer: React.FC<{ chunk: V2StreamChunk }> = ({ chunk }) => {
  switch (chunk.type) {
    case 'thinking':
      return (
        <Card size="small" style={{ marginBottom: 8, backgroundColor: '#f0f5ff', borderColor: '#adc6ff' }}>
          <Space>
            <BulbOutlined style={{ color: '#1890ff' }} />
            <Text type="secondary">Thinking...</Text>
          </Space>
          <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 13, color: '#666' }}>
            {chunk.content}
          </Paragraph>
        </Card>
      );
    case 'tool_call':
      return (
        <Card size="small" style={{ marginBottom: 8, backgroundColor: '#f9f0ff', borderColor: '#d3adf7' }}>
          <Space>
            <ToolOutlined style={{ color: '#722ed1' }} />
            <Tag color="purple">{chunk.metadata?.tool_name || 'Tool'}</Tag>
          </Space>
          {chunk.content && (
            <pre style={{ marginTop: 8, marginBottom: 0, fontSize: 12, backgroundColor: '#f5f5f5', padding: 8, borderRadius: 4, whiteSpace: 'pre-wrap' }}>
              {chunk.content}
            </pre>
          )}
        </Card>
      );
    case 'error':
      return (
        <Alert
          type="error"
          showIcon
          closable
          icon={<ExclamationCircleOutlined />}
          message="Error"
          description={chunk.content}
          style={{ marginBottom: 8, borderRadius: 6 }}
          className="shadow-sm"
        />
      );
    case 'warning':
      return (
        <Alert
          type="warning"
          showIcon
          closable
          icon={<WarningOutlined />}
          message="Warning"
          description={chunk.content}
          style={{ marginBottom: 8, borderRadius: 6 }}
          className="shadow-sm"
        />
      );
    default:
      return null;
  }
};

const MessageItem: React.FC<{
  message: { role: 'user' | 'assistant'; content: string; chunks: V2StreamChunk[]; timestamp: number };
}> = ({ message }) => {
  const isUser = message.role === 'user';
  return (
    <div style={{ display: 'flex', marginBottom: 16, justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      <div style={{ display: 'flex', maxWidth: '80%', flexDirection: isUser ? 'row-reverse' : 'row' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: '50%', backgroundColor: isUser ? '#1890ff' : '#52c41a', marginLeft: isUser ? 8 : 0, marginRight: isUser ? 0 : 8 }}>
          {isUser ? <UserOutlined style={{ color: 'white' }} /> : <RobotOutlined style={{ color: 'white' }} />}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {message.chunks.map((chunk, index) => <ChunkRenderer key={index} chunk={chunk} />)}
          {message.content && (
            <div style={{ padding: 12, borderRadius: 8, backgroundColor: isUser ? '#1890ff' : '#f5f5f5', color: isUser ? 'white' : '#333', whiteSpace: 'pre-wrap' }}>
              {message.content}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const V2Chat: React.FC<V2ChatProps> = ({ agentName, placeholder = 'Type a message...', height = 500, onSessionChange }) => {
  const [input, setInput] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  const { session, messages, isStreaming, error, createSession, sendMessage, stopStream, clearMessages } = useV2Chat({
    agentName,
    onSessionCreated: (s) => onSessionChange?.(s.session_id),
  });

  useEffect(() => { if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight; }, [messages]);
  useEffect(() => { if (!session) createSession().catch(console.error); }, []);

  const handleSend = useCallback(() => {
    if (!input.trim() || isStreaming) return;
    const msg = input.trim();
    setInput('');
    sendMessage(msg);
  }, [input, isStreaming, sendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', backgroundColor: 'white', borderRadius: 8, border: '1px solid #e8e8e8' }}>
      <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: 16, height: typeof height === 'number' ? `${height}px` : height }}>
        {messages.length === 0 ? <Empty description="Start a conversation" style={{ marginTop: 80 }} /> : messages.map((msg, index) => <MessageItem key={index} message={msg} />)}
        {isStreaming && <div style={{ display: 'flex', justifyContent: 'flex-start' }}><Spin size="small" /></div>}
        {error && <div style={{ color: '#f5222d', textAlign: 'center', padding: 8 }}>Error: {error.message}</div>}
      </div>
      <div style={{ borderTop: '1px solid #e8e8e8', padding: 16 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <TextArea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} placeholder={placeholder} autoSize={{ minRows: 1, maxRows: 4 }} style={{ flex: 1 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {isStreaming ? <Button type="primary" danger onClick={stopStream}><StopOutlined /> Stop</Button> : <Button type="primary" onClick={handleSend}><SendOutlined /> Send</Button>}
            <Button onClick={clearMessages}><ClearOutlined /> Clear</Button>
          </div>
        </div>
      </div>
      <InteractionHandler />
    </div>
  );
};

export default V2Chat;
