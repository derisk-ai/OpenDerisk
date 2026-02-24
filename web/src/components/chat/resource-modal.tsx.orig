import React, { useState, useEffect } from 'react';
import { Modal, Button, Avatar, Tag, Typography, Spin, Tabs, Empty, Space, Divider } from 'antd';
import { useRequest } from 'ahooks';
import { apiInterceptors, getResourceV2, getMCPList } from '@/client/api';
import { PlusOutlined, CheckOutlined, AppstoreOutlined, ToolOutlined, ApiOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Paragraph, Text } = Typography;

export type ResourceType = 'skill' | 'tool' | 'mcp';

export interface SelectedResource {
  id: string;
  name: string;
  type: ResourceType;
  icon?: string;
  description?: string;
}

interface ResourceModalProps {
  open: boolean;
  onCancel: () => void;
  defaultTab?: ResourceType;
  onResourcesChange: (resources: SelectedResource[]) => void;
  selectedResources: SelectedResource[];
  recommendedSkills?: Array<{ name: string; description: string }>;
}

export const ResourceModal: React.FC<ResourceModalProps> = ({
  open,
  onCancel,
  defaultTab = 'skill',
  onResourcesChange,
  selectedResources,
  recommendedSkills = [],
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<ResourceType>(defaultTab);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(selectedResources.map(r => r.id))
  );

  // Update selectedIds when selectedResources prop changes
  useEffect(() => {
    setSelectedIds(new Set(selectedResources.map(r => r.id)));
  }, [selectedResources]);

  // Update active tab when defaultTab changes and modal opens
  useEffect(() => {
    if (open) {
      setActiveTab(defaultTab);
    }
  }, [open, defaultTab]);

  // Fetch Skills
  const { data: skillsData = [], loading: skillsLoading } = useRequest(async () => {
    const [, res] = await apiInterceptors(
      getResourceV2({ type: 'tool(skill)' })
    );
    // Parse valid_values from response
    const param = res?.find((p: any) => p.param_name === 'name');
    return param?.valid_values || [];
  });

  // Fetch Tools
  const { data: toolsData = [], loading: toolsLoading } = useRequest(async () => {
    const [, res] = await apiInterceptors(
      getResourceV2({ type: 'tool(local)' })
    );
    const param = res?.find((p: any) => p.param_name === 'name');
    return param?.valid_values || [];
  });

  // Fetch MCP Servers
  const { data: mcpData = [], loading: mcpLoading } = useRequest(async () => {
    const [, res] = await apiInterceptors(
      getMCPList({ filter: '' }, { page: '1', page_size: '100' })
    );
    return (res?.items || []) as any[];
  });

  const toggleResource = (resource: SelectedResource) => {
    const newSelectedIds = new Set(selectedIds);
    if (newSelectedIds.has(resource.id)) {
      newSelectedIds.delete(resource.id);
    } else {
      newSelectedIds.add(resource.id);
    }
    setSelectedIds(newSelectedIds);

    // Calculate new selected resources list
    const allResourcesMap = new Map<string, SelectedResource>();

    // Add skills
    skillsData.forEach((s: any) => {
      allResourcesMap.set(s.key, {
        id: s.key,
        name: s.name,
        type: 'skill' as ResourceType,
        description: s.description,
      });
    });

    // Add tools
    toolsData.forEach((t: any) => {
      allResourcesMap.set(t.key, {
        id: t.key,
        name: t.name,
        type: 'tool' as ResourceType,
        description: t.description,
      });
    });

    // Add MCP servers
    mcpData.forEach((m: any) => {
      allResourcesMap.set(m.uuid || m.id, {
        id: m.uuid || m.id,
        name: m.name || m.app_name,
        type: 'mcp' as ResourceType,
        description: m.description,
      });
    });

    const newSelected: SelectedResource[] = [];
    newSelectedIds.forEach(id => {
      const resource = allResourcesMap.get(id);
      if (resource) {
        newSelected.push(resource);
      }
    });
    onResourcesChange(newSelected);
  };

  const renderResourceItem = (resource: SelectedResource, type: ResourceType) => {
    const isSelected = selectedIds.has(resource.id);
    return (
      <div
        key={resource.id}
        className={`
          flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-all
          ${isSelected ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800' : 'hover:bg-gray-50 dark:hover:bg-gray-800 border-transparent'}
          border
        `}
        onClick={() => toggleResource(resource)}
      >
        <Avatar
          size={40}
          shape="circle"
          className={`
            flex-shrink-0 ${isSelected ? 'bg-blue-100 dark:bg-blue-900' : 'bg-gray-100 dark:bg-gray-700'}
          `}
          icon={
            type === 'skill' ? <AppstoreOutlined className="text-blue-500" /> :
            type === 'tool' ? <ToolOutlined className="text-green-500" /> :
            <ApiOutlined className="text-purple-500" />
          }
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
              {resource.name}
            </span>
            <Tag color={type === 'skill' ? 'blue' : type === 'tool' ? 'green' : 'purple'} className="m-0 scale-75 origin-left">
              {type.toUpperCase()}
            </Tag>
          </div>
          <Paragraph
            ellipsis={{ rows: 1 }}
            className="!mb-0 text-gray-500 dark:text-gray-400 text-xs"
          >
            {resource.description}
          </Paragraph>
        </div>
        <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
          isSelected
            ? 'bg-blue-500 text-white'
            : 'border-2 border-gray-200 dark:border-gray-600'
        }`}>
          {isSelected && <CheckOutlined className="text-xs" />}
        </div>
      </div>
    );
  };

  const resourceItems: { key: ResourceType; label: string; icon: React.ReactNode }[] = [
    { key: 'skill', label: t('Skills', { defaultValue: 'Skills' }), icon: <AppstoreOutlined /> },
    { key: 'tool', label: t('Tools', { defaultValue: 'Tools' }), icon: <ToolOutlined /> },
    { key: 'mcp', label: t('MCP Servers', { defaultValue: 'MCP Servers' }), icon: <ApiOutlined /> },
  ];

  const tabContent = (
    <div className="h-[500px] overflow-y-auto p-4">
      <Spin spinning={skillsLoading || toolsLoading || mcpLoading}>
        {activeTab === 'skill' && (
          <Space direction="vertical" size="small" className="w-full">
            {skillsData.length === 0 ? (
              <Empty description={t('No skills available', { defaultValue: 'No skills available' })} />
            ) : (
              skillsData.map((skill: any) => renderResourceItem({
                id: skill.key,
                name: skill.name,
                type: 'skill',
                description: skill.description,
              }, 'skill'))
            )}
          </Space>
        )}
        {activeTab === 'tool' && (
          <Space direction="vertical" size="small" className="w-full">
            {toolsData.length === 0 ? (
              <Empty description={t('No tools available', { defaultValue: 'No tools available' })} />
            ) : (
              toolsData.map((tool: any) => renderResourceItem({
                id: tool.key,
                name: tool.name,
                type: 'tool',
                description: tool.description,
              }, 'tool'))
            )}
          </Space>
        )}
        {activeTab === 'mcp' && (
          <Space direction="vertical" size="small" className="w-full">
            {mcpData.length === 0 ? (
              <Empty description={t('No MCP servers available', { defaultValue: 'No MCP servers available' })} />
            ) : (
              mcpData.map((mcp: any) => renderResourceItem({
                id: mcp.uuid || mcp.id,
                name: mcp.name || mcp.app_name,
                type: 'mcp',
                description: mcp.description,
              }, 'mcp'))
            )}
          </Space>
        )}
      </Spin>
    </div>
  );

  const renderRecommendedSection = () => {
    // Only show recommended skills if provided
    if (!recommendedSkills || recommendedSkills.length === 0) return null;

    const recommended = recommendedSkills.map((skill, index) => ({
      id: `recommended-${index}`,
      name: skill.name,
      description: skill.description,
      type: 'skill' as ResourceType,
    }));

    return (
      <div className="px-4 pb-4">
        <Text type="secondary" className="text-sm mb-3 block">
          {t('Recommended Skills', { defaultValue: 'Recommended Skills' })}
        </Text>
        <Space direction="vertical" size="small" className="w-full">
          {recommended.map((skill) => renderResourceItem(skill, skill.type))}
        </Space>
        <Divider className="my-4" />
      </div>
    );
  };

  return (
    <Modal
      title={
        <div className="flex items-center justify-between pr-4">
          <span className="text-lg font-semibold">
            {t('Select Resources', { defaultValue: 'Select Resources' })}
          </span>
          <Text type="secondary" className="text-sm">
            {selectedIds.size} {t('selected', { defaultValue: 'selected' })}
          </Text>
        </div>
      }
      open={open}
      onCancel={onCancel}
      footer={null}
      width={680}
      className="rounded-2xl overflow-hidden"
      styles={{ body: { padding: '0' } }}
      centered
    >
      <div className="flex flex-col h-full bg-white dark:bg-[#1f1f1f]">
        {/* Tabs Section */}
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as ResourceType)}
          items={resourceItems.map(item => ({
            key: item.key,
            label: (
              <span className="flex items-center gap-2 px-2">
                {item.icon}
                {item.label}
              </span>
            ),
          }))}
          tabBarStyle={{ padding: '0 24px', marginBottom: 16 }}
          className="custom-tabs pt-2"
        />

        {/* Resource List */}
        {tabContent}
      </div>
    </Modal>
  );
};