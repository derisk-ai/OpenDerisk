import React, { useState } from 'react';
import { Modal, Tabs, List, Avatar, Button, Tag, Typography, Spin } from 'antd';
import { useRequest } from 'ahooks';
import { apiInterceptors, getMCPList } from '@/client/api';
import { AppstoreOutlined, ApiOutlined, ToolOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Paragraph } = Typography;

interface ConnectorsModalProps {
  open: boolean;
  onCancel: () => void;
  defaultTab?: string;
}

export const ConnectorsModal: React.FC<ConnectorsModalProps> = ({ open, onCancel, defaultTab = 'mcp' }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState(defaultTab);

  // Update active tab when defaultTab changes and modal opens
  React.useEffect(() => {
    if (open) {
      setActiveTab(defaultTab);
    }
  }, [open, defaultTab]);

  // --- MCP Data Fetching ---
  const { data: mcpList = [], loading: mcpLoading } = useRequest(async () => {
    const [, res] = await apiInterceptors(getMCPList({ filter: '' }, { page: "1", page_size: "100" }));
    // @ts-ignore
    return (res?.items || []) as any[];
  });

  // --- Mock Data for Local Tools ---
  const localTools = [
    {
      id: 'browser',
      name: 'My Browser',
      description: t('Use the browser to visit web pages', { defaultValue: 'Use the browser to visit web pages' }),
      icon: <GlobalIcon />,
      enabled: true,
      author: 'Derisk'
    },
    {
      id: 'interpreter',
      name: 'Code Interpreter',
      description: t('Execute Python code for data analysis', { defaultValue: 'Execute Python code for data analysis' }),
      icon: <CodeIcon />,
      enabled: true,
      author: 'Derisk'
    }
  ];

  // --- Mock Data for Skills (Sync with agent-skills page) ---
  const skills = [
    {
      id: '1',
      name: 'Web Search',
      description: 'Search the internet for information',
      type: 'tool',
      enabled: true
    },
    {
      id: '2',
      name: 'Knowledge Retrieval',
      description: 'Retrieve information from internal docs',
      type: 'retrieval',
      enabled: true
    }
  ];

  const renderListItem = (item: any, type: 'mcp' | 'local' | 'skill') => (
    <List.Item
      className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-lg transition-colors px-4 py-3 border-b-0 mb-1"
      actions={[
        <Button key="action" type="text" shape="circle" icon={<PlusOutlined />} className="text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20" />
      ]}
    >
      <List.Item.Meta
        avatar={
          <Avatar 
            shape="square" 
            size={48} 
            src={item.icon} 
            icon={!item.icon && (type === 'mcp' ? <ApiOutlined /> : type === 'local' ? <ToolOutlined /> : <AppstoreOutlined />)}
            className="bg-gray-100 dark:bg-gray-700 text-gray-500 rounded-xl"
          />
        }
        title={
          <div className="flex items-center gap-2">
            <span className="font-medium text-base text-gray-900 dark:text-gray-100">{item.name}</span>
            {type === 'mcp' && item.available && (
              <Tag color="success" className="mr-0 rounded-full px-2 scale-75 origin-left">Active</Tag>
            )}
            {type === 'skill' && (
              <Tag color="blue" className="mr-0 rounded-full px-2 scale-75 origin-left">{item.type}</Tag>
            )}
          </div>
        }
        description={
          <Paragraph 
            ellipsis={{ rows: 2 }} 
            className="!mb-0 text-gray-500 dark:text-gray-400 text-xs mt-1"
          >
            {item.description}
          </Paragraph>
        }
      />
    </List.Item>
  );

  const items = [
    {
      key: 'local',
      label: (
        <span className="flex items-center gap-2 px-2">
          <ToolOutlined />
          {t('Local Tools', { defaultValue: 'Local Tools' })}
        </span>
      ),
      children: (
        <List
          itemLayout="horizontal"
          dataSource={localTools}
          renderItem={(item) => renderListItem(item, 'local')}
          className="h-[500px] overflow-y-auto px-2"
        />
      ),
    },
    {
      key: 'mcp',
      label: (
        <span className="flex items-center gap-2 px-2">
          <ApiOutlined />
          {t('MCP Servers', { defaultValue: 'MCP Servers' })}
        </span>
      ),
      children: (
        <Spin spinning={mcpLoading}>
           <List
            itemLayout="horizontal"
            dataSource={mcpList}
            renderItem={(item) => renderListItem(item, 'mcp')}
            className="h-[500px] overflow-y-auto px-2"
          />
        </Spin>
      ),
    },
    {
      key: 'skill',
      label: (
        <span className="flex items-center gap-2 px-2">
          <AppstoreOutlined />
          {t('Skills', { defaultValue: 'Skills' })}
        </span>
      ),
      children: (
        <List
          itemLayout="horizontal"
          dataSource={skills}
          renderItem={(item) => renderListItem(item, 'skill')}
          className="h-[500px] overflow-y-auto px-2"
        />
      ),
    },
  ];

  return (
    <Modal
      title={
        <div className="text-lg font-semibold px-2 pt-2">
          {t('Connectors & Tools', { defaultValue: 'Connectors & Tools' })}
        </div>
      }
      open={open}
      onCancel={onCancel}
      footer={null}
      width={720}
      className="rounded-2xl overflow-hidden"
      styles={{ body: { padding: '0' } }}
      centered
    >
      <div className="flex flex-col h-full bg-white dark:bg-[#1f1f1f]">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={items}
          tabBarStyle={{ padding: '0 24px', marginBottom: 16 }}
          className="custom-tabs pt-2"
        />
        <div className="p-4 border-t border-gray-100 dark:border-gray-800 flex justify-start">
          <Button 
            type="dashed" 
            icon={<PlusOutlined />} 
            className="w-full"
            onClick={() => {
              // Add connector logic here
            }}
          >
            {t('Add Connector', { defaultValue: 'Add Connector' })}
          </Button>
        </div>
      </div>
    </Modal>
  );
};

// Simple Icons
const GlobalIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-blue-500">
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="2" y1="12" x2="22" y2="12"></line>
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
  </svg>
);

const CodeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-green-500">
    <polyline points="16 18 22 12 16 6"></polyline>
    <polyline points="8 6 2 12 8 18"></polyline>
  </svg>
);
