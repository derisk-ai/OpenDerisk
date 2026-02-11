import React, { useState, useEffect } from 'react';
import { Modal, Tabs, List, Avatar, Button, Tag, Typography, Spin, Input, Checkbox } from 'antd';
import { useRequest } from 'ahooks';
import { apiInterceptors, getMCPList, getSkillList } from '@/client/api';
import { AppstoreOutlined, ApiOutlined, ToolOutlined, PlusOutlined, CheckOutlined, SearchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Paragraph } = Typography;

interface ConnectorsModalProps {
  open: boolean;
  onCancel: () => void;
  defaultTab?: string;
  selectedSkills?: any[];
  onSkillsChange?: (skills: any[]) => void;
}

interface Skill {
  skill_code: string;
  name: string;
  description: string;
  type: string;
  icon?: string;
  author?: string;
  version?: string;
  repo_url?: string;
}

export const ConnectorsModal: React.FC<ConnectorsModalProps> = ({
  open,
  onCancel,
  defaultTab = 'skill',
  selectedSkills = [],
  onSkillsChange
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [selectedSkillCodes, setSelectedSkillCodes] = useState<string[]>([]);
  const [skillSearch, setSkillSearch] = useState('');

  // Update active tab when defaultTab changes and modal opens
  useEffect(() => {
    if (open) {
      setActiveTab(defaultTab);
    }
  }, [open, defaultTab]);

  // Initialize selected skills from props
  useEffect(() => {
    setSelectedSkillCodes(selectedSkills.map(s => s.skill_code));
  }, [selectedSkills]);

  // --- MCP Data Fetching ---
  const { data: mcpList = [], loading: mcpLoading } = useRequest(async () => {
    const [, res] = await apiInterceptors(getMCPList({ filter: '' }, { page: "1", page_size: "100" }));
    // @ts-ignore
    return (res?.items || []) as any[];
  });

  // --- Skills Data Fetching ---
  const { data: skillListData = [], loading: skillLoading } = useRequest(async () => {
    if (activeTab !== 'skill') return [];
    const [, res] = await apiInterceptors(getSkillList({ filter: skillSearch }, { page: "1", page_size: "100" }));
    // @ts-ignore
    return (res?.items || []) as Skill[];
  }, {
    refreshDeps: [activeTab, skillSearch]
  });

  // Filter skills based on search
  const filteredSkills = skillListData.filter((skill: Skill) => {
    if (!skillSearch) return true;
    const searchLower = skillSearch.toLowerCase();
    return skill.name?.toLowerCase().includes(searchLower) ||
           skill.description?.toLowerCase().includes(searchLower);
  });

  const handleSkillToggle = (skill: Skill) => {
    const newSelected = selectedSkillCodes.includes(skill.skill_code)
      ? selectedSkillCodes.filter(code => code !== skill.skill_code)
      : [...selectedSkillCodes, skill.skill_code];
    
    setSelectedSkillCodes(newSelected);
    
    if (onSkillsChange) {
      const selectedSkillsData = skillListData.filter((s: Skill) => newSelected.includes(s.skill_code));
      onSkillsChange(selectedSkillsData);
    }
  };

  const handleApplySkills = () => {
    if (onSkillsChange) {
      const selectedSkillsData = skillListData.filter((s: Skill) => selectedSkillCodes.includes(s.skill_code));
      onSkillsChange(selectedSkillsData);
    }
    onCancel();
  };

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

  const renderListItem = (item: any, type: 'mcp' | 'local' | 'skill') => {
    const isSelected = type === 'skill' && selectedSkillCodes.includes(item.skill_code);
    
    return (
      <List.Item
        className={`
          cursor-pointer rounded-lg transition-colors px-4 py-3 border-b-0 mb-1
          ${isSelected 
            ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800' 
            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50 border border-transparent'
          }
        `}
        onClick={() => {
          if (type === 'skill') {
            handleSkillToggle(item);
          }
        }}
        actions={
          type === 'skill'
            ? [
                <Checkbox
                  key="checkbox"
                  checked={isSelected}
                  onChange={() => handleSkillToggle(item)}
                  onClick={(e) => e.stopPropagation()}
                  className="text-gray-400 hover:text-blue-500"
                />
              ]
            : [
                <Button key="action" type="text" shape="circle" icon={<PlusOutlined />} className="text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20" />
              ]
        }
      >
        <List.Item.Meta
          avatar={
            <Avatar 
              shape="circle" 
              size={48} 
              src={item.icon} 
              icon={!item.icon && (type === 'mcp' ? <ApiOutlined /> : type === 'local' ? <ToolOutlined /> : <AppstoreOutlined />)}
              className={`
                bg-white dark:bg-gray-800 border-2
                ${isSelected 
                  ? 'border-blue-500 text-blue-500' 
                  : 'border-gray-200 dark:border-gray-700 text-gray-500'
                }
              `}
            />
          }
          title={
            <div className="flex items-center gap-2">
              <span className={`font-medium text-base ${isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-gray-900 dark:text-gray-100'}`}>
                {item.name}
              </span>
              {isSelected && <CheckOutlined className="text-blue-500 text-sm" />}
              {type === 'mcp' && item.available && (
                <Tag color="success" className="mr-0 rounded-full px-2 scale-75 origin-left">Active</Tag>
              )}
              {type === 'skill' && item.type && (
                <Tag color={isSelected ? 'blue' : 'default'} className="mr-0 rounded-full px-2 scale-75 origin-left">{item.type}</Tag>
              )}
            </div>
          }
          description={
            <div>
              <Paragraph 
                ellipsis={{ rows: 2 }} 
                className={`!mb-0 text-xs mt-1 ${isSelected ? 'text-gray-600 dark:text-gray-400' : 'text-gray-500 dark:text-gray-400'}`}
              >
                {item.description}
              </Paragraph>
              {type === 'skill' && item.author && (
                <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">
                  By {item.author} {item.version && `· v${item.version}`}
                  {item.repo_url && <span className="ml-1">· Git</span>}
                </div>
              )}
            </div>
          }
        />
      </List.Item>
    );
  };

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
          {selectedSkillCodes.length > 0 && (
            <Tag color="blue" className="rounded-full px-1.5 scale-75 origin-left">{selectedSkillCodes.length}</Tag>
          )}
        </span>
      ),
      children: (
        <Spin spinning={skillLoading}>
          <div className="flex flex-col h-[500px]">
            <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
              <Input
                prefix={<SearchOutlined className="text-gray-400" />}
                placeholder={t('Search skills...', { defaultValue: 'Search skills...' })}
                bordered={false}
                className="!bg-gray-50 dark:!bg-gray-800 rounded-md"
                value={skillSearch}
                onChange={(e) => setSkillSearch(e.target.value)}
                allowClear
              />
            </div>
            <List
              itemLayout="horizontal"
              dataSource={filteredSkills}
              renderItem={(item) => renderListItem(item, 'skill')}
              className="flex-1 overflow-y-auto px-2"
            />
            {filteredSkills.length === 0 && !skillLoading && (
              <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
                {skillSearch ? t('No skills found', { defaultValue: 'No skills found' }) : t('No skills available', { defaultValue: 'No skills available' })}
              </div>
            )}
          </div>
        </Spin>
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
      footer={
        activeTab === 'skill' ? (
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-500">
              {t('Selected', { defaultValue: 'Selected' })}: {selectedSkillCodes.length}
            </div>
            <div className="flex gap-2">
              <Button onClick={onCancel}>
                {t('Cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button type="primary" onClick={handleApplySkills} className="bg-black hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200">
                {t('Apply', { defaultValue: 'Apply' })}
              </Button>
            </div>
          </div>
        ) : null
      }
      width={720}
      className="rounded-2xl overflow-hidden"
      styles={{ body: { padding: '0' }, footer: { padding: '16px 24px', borderTop: '1px solid #f0f0f0' } }}
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
