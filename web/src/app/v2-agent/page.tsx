'use client';
import React, { useState } from 'react';
import { Layout, Card, Select, Typography, Row, Col, Divider } from 'antd';
import { RobotOutlined } from '@ant-design/icons';
import V2Chat from '@/components/v2-chat';

const { Content } = Layout;
const { Title, Text } = Typography;

const AGENT_OPTIONS = [
  { value: 'simple_chat', label: 'Simple Chat Agent', description: 'Basic conversation agent' },
  { value: 'tool_agent', label: 'Tool Agent', description: 'Agent with bash tool support' },
  { value: 'pdca_agent', label: 'PDCA Agent', description: 'Planning and execution agent' },
];

export default function V2AgentPage() {
  const [selectedAgent, setSelectedAgent] = useState('simple_chat');
  const [sessionId, setSessionId] = useState<string | null>(null);

  const currentAgent = AGENT_OPTIONS.find((a) => a.value === selectedAgent);

  return (
    <Content style={{ minHeight: '100vh', padding: 24, background: '#f5f5f5' }}>
      <Row justify="center">
        <Col xs={24} lg={16} xl={12}>
          <Card>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
              <RobotOutlined style={{ fontSize: 32, color: '#1890ff', marginRight: 16 }} />
              <div style={{ flex: 1 }}>
                <Title level={3} style={{ margin: 0 }}>Core_v2 Agent</Title>
                <Text type="secondary">Powered by new Core_v2 architecture</Text>
              </div>
              <Select
                value={selectedAgent}
                onChange={setSelectedAgent}
                options={AGENT_OPTIONS}
                style={{ width: 200 }}
              />
            </div>
            {currentAgent && (
              <div style={{ marginBottom: 16 }}>
                <Text strong>{currentAgent.label}</Text>
                <Text type="secondary" style={{ marginLeft: 8 }}>{currentAgent.description}</Text>
              </div>
            )}
            <Divider />
            <V2Chat
              key={selectedAgent}
              agentName={selectedAgent}
              height={500}
              onSessionChange={setSessionId}
            />
            {sessionId && (
              <div style={{ marginTop: 8, textAlign: 'right' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>Session: {sessionId.slice(0, 8)}...</Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </Content>
  );
}
