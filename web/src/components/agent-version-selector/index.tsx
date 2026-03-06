'use client';
/**
 * AgentVersionSelector - Agent 版本选择组件
 */
import React from 'react';
import { Space, Typography, Card } from 'antd';
import { ThunderboltOutlined, RocketOutlined } from '@ant-design/icons';
import type { AgentVersion } from '@/types/app';

const { Text, Paragraph } = Typography;

interface AgentVersionSelectorProps {
  value?: AgentVersion;
  onChange?: (value: AgentVersion) => void;
}

const versionConfig = {
  v1: {
    icon: <ThunderboltOutlined style={{ fontSize: 24, color: '#1890ff' }} />,
    title: 'V1 经典版',
    description: '稳定的 PDCA Agent，适合生产环境',
    features: ['成熟的 PDCA 循环', '完整的历史支持', '稳定的工具集成'],
  },
  v2: {
    icon: <RocketOutlined style={{ fontSize: 24, color: '#52c41a' }} />,
    title: 'V2 Core_v2',
    description: '新架构，支持 Canvas 可视化和更多特性',
    features: ['Canvas 可视化', '实时进度推送', '类型安全', '权限控制'],
  },
};

const VersionCard: React.FC<{
  version: AgentVersion;
  selected: boolean;
  onClick: () => void;
}> = ({ version, selected, onClick }) => {
  const config = versionConfig[version];
  return (
    <Card
      hoverable
      onClick={onClick}
      style={{
        borderColor: selected ? '#1890ff' : '#d9d9d9',
        borderWidth: selected ? 2 : 1,
        backgroundColor: selected ? '#f0f5ff' : 'white',
        cursor: 'pointer',
        transition: 'all 0.3s',
      }}
      bodyStyle={{ padding: 16 }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space>
          {config.icon}
          <Text strong style={{ fontSize: 16 }}>{config.title}</Text>
        </Space>
        <Paragraph type="secondary" style={{ marginBottom: 8 }}>
          {config.description}
        </Paragraph>
        <div style={{ marginTop: 8 }}>
          {config.features.map((feature, i) => (
            <Text key={i} style={{ display: 'block', fontSize: 12, color: '#666' }}>
              + {feature}
            </Text>
          ))}
        </div>
      </Space>
    </Card>
  );
};

export const AgentVersionSelector: React.FC<AgentVersionSelectorProps> = ({ value = 'v1', onChange }) => {
  return (
    <div>
      <Text strong style={{ display: 'block', marginBottom: 12 }}>Agent Version</Text>
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1 }}>
          <VersionCard version="v1" selected={value === 'v1'} onClick={() => onChange?.('v1')} />
        </div>
        <div style={{ flex: 1 }}>
          <VersionCard version="v2" selected={value === 'v2'} onClick={() => onChange?.('v2')} />
        </div>
      </div>
    </div>
  );
};

export default AgentVersionSelector;