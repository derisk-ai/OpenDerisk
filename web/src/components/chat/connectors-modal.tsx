import React, { useState, useEffect } from 'react';
import { Modal, Tabs, List, Avatar, Button, Tag, Typography, Spin, Input, Checkbox } from 'antd';
import { useRequest } from 'ahooks';
import { apiInterceptors, getMCPList, getSkillList, getToolList } from '@/client/api';
import { AppstoreOutlined, ApiOutlined, ToolOutlined, CheckOutlined, SearchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Paragraph } = Typography;

interface ConnectorsModalProps {
  open: boolean;
  onCancel: () => void;
  defaultTab?: string;
  selectedSkills?: Skill[];
  onSkillsChange?: (skills: Skill[]) => void;
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

interface MCP {
  id?: string;
  uuid?: string;
  name: string;
  description?: string;
  icon?: string;
  available?: boolean;
}

interface LocalTool {
  id: string;
  name: string;
  description: string;
  icon?: React.ReactNode;
  enabled?: boolean;
  author?: string;
}

export const ConnectorsModal: React.FC<ConnectorsModalProps> = ({
  open,
  onCancel,
  defaultTab = 'skill',
  selectedSkills = [],
  onSkillsChange
}: ConnectorsModalProps) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [selectedSkillCodes, setSelectedSkillCodes] = useState<string[]>([]);
  const [skillSearch, setSkillSearch] = useState('');
  const [selectedMcpCodes, setSelectedMcpCodes] = useState<string[]>([]);
  const [mcpSearch, setMcpSearch] = useState('');
  const [selectedLocalTools, setSelectedLocalTools] = useState<string[]>([]);
  const [localToolSearch, setLocalToolSearch] = useState('');

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
    return ((res as any)?.items || []) as MCP[];
  });

  // --- Skills Data Fetching ---
  const { data: skillListData = [], loading: skillLoading } = useRequest(async () => {
    const [, res] = await apiInterceptors(getSkillList({ filter: skillSearch }, { page: "1", page_size: "100" }));
    return ((res as any)?.items || []) as Skill[];
  }, {
    refreshDeps: [skillSearch]
  });

  // --- Local Tools Data Fetching ---
  const { data: localTools = [] } = useRequest(async () => {
    const [, res] = await apiInterceptors(getToolList('local'));
    return (res || []) as any[];
  });

  const filteredSkills = skillListData.filter((skill: Skill) => {
    if (!skillSearch) return true;
    const searchLower = skillSearch.toLowerCase();
    return skill.name?.toLowerCase().includes(searchLower) ||
           skill.description?.toLowerCase().includes(searchLower);
  });

  const filteredMcpList = mcpList.filter((mcp: MCP) => {
    if (!mcpSearch) return true;
    const searchLower = mcpSearch.toLowerCase();
    return mcp.name?.toLowerCase().includes(searchLower) ||
           mcp.description?.toLowerCase().includes(searchLower);
  });

  const filteredLocalTools = localTools.filter((tool: any) => {
    if (!localToolSearch) return true;
    const searchLower = localToolSearch.toLowerCase();
    const toolName = tool.tool_name || '';
    // Tools from /api/v1/tool endpoint don't have description field in the base model
    // The config field contains JSON with details
    let toolDesc = '';
    if (tool.config) {
      try {
        const config = JSON.parse(tool.config);
        toolDesc = config.description || config.desc || '';
      } catch {
        // ignore parse error
      }
    }
    return toolName.toLowerCase().includes(searchLower) ||
           toolDesc.toLowerCase().includes(searchLower);
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

  const handleMcpToggle = (mcp: MCP) => {
    const mcpCode = mcp.id || mcp.uuid || mcp.name;
    const newSelected = selectedMcpCodes.includes(mcpCode || '')
      ? selectedMcpCodes.filter(code => code !== mcpCode)
      : [...selectedMcpCodes, mcpCode || ''];
    setSelectedMcpCodes(newSelected);
  };

  const handleLocalToolToggle = (tool: any) => {
    const toolId = tool.tool_id;
    const newSelected = selectedLocalTools.includes(toolId)
      ? selectedLocalTools.filter(id => id !== toolId)
      : [...selectedLocalTools, toolId];
    setSelectedLocalTools(newSelected);
  };

  const renderListItem = (item: Skill | MCP | LocalTool, type: 'mcp' | 'local' | 'skill') => {
    let isSelected = false;
    if (type === 'skill') {
      isSelected = selectedSkillCodes.includes((item as Skill).skill_code);
    } else if (type === 'mcp') {
      const mcpCode = (item as MCP).id || (item as MCP).uuid || (item as MCP).name;
      isSelected = selectedMcpCodes.includes(mcpCode || '');
    } else if (type === 'local') {
      const toolItem = item as any;
      const toolId = toolItem.tool_id;
      isSelected = selectedLocalTools.includes(toolId);
    }

    let selectedColor: 'blue' | 'green' | 'orange' = 'blue';
    if (type === 'skill') {
      selectedColor = 'blue';
    } else if (type === 'mcp') {
      selectedColor = 'green';
    } else if (type === 'local') {
      selectedColor = 'orange';
    }

    return (
      <List.Item
        className={`
          cursor-pointer rounded-lg transition-colors px-4 py-3 border-b-0 mb-1
          ${isSelected
            ? `bg-${selectedColor}-50 dark:bg-${selectedColor}-900/20 border border-${selectedColor}-200 dark:border-${selectedColor}-800`
            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50 border border-transparent'
          }
        `}
        onClick={() => {
          if (type === 'skill') {
            handleSkillToggle(item as Skill);
          } else if (type === 'mcp') {
            handleMcpToggle(item as MCP);
          } else if (type === 'local') {
            handleLocalToolToggle(item as LocalTool);
          }
        }}
        actions={type !== 'local' && type !== 'mcp'
          ? [
              <Checkbox
                key="checkbox"
                checked={isSelected}
                onChange={() => type === 'skill' ? handleSkillToggle(item as Skill) : type === 'mcp' ? handleMcpToggle(item as MCP) : handleLocalToolToggle(item as LocalTool)}
                onClick={(e) => e.stopPropagation()}
                className="text-gray-400 hover:text-blue-500"
              />
            ]
          : [
              <Checkbox
                key="checkbox"
                checked={isSelected}
                onChange={() => type === 'mcp' ? handleMcpToggle(item as MCP) : handleLocalToolToggle(item as LocalTool)}
                onClick={(e) => e.stopPropagation()}
                className="text-gray-400 hover:text-blue-500"
              />
            ]
        }
      >
        <List.Item.Meta
avatar={
            <Avatar
              shape="circle"
              size={48}
              src={item.icon}
              icon={!item.icon && (type === 'mcp' ? <ApiOutlined /> : type === 'local' ? <ToolOutlined /> : undefined)}
              className={`
                bg-white dark:bg-gray-800 border-2
                ${isSelected
                  ? `border-${selectedColor}-500 text-${selectedColor}-500`
                  : 'border-gray-200 dark:border-gray-700 text-gray-500'
                }
              `}
              style={!item.icon && type === 'skill' ? { fontSize: '20px', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' } : undefined}
            >
              {!item.icon && type === 'skill' && (item.name ? item.name.charAt(0).toUpperCase() : 'S')}
            </Avatar>
          }
          title={
            <div className="flex items-center gap-2">
              <span className={`font-medium text-base ${isSelected ? `text-${selectedColor}-600 dark:text-${selectedColor}-400` : 'text-gray-900 dark:text-gray-100'}`}>
                {type === 'local' ? (item as any).tool_name : item.name}
              </span>
              {isSelected && <CheckOutlined className={`text-${selectedColor}-500 text-sm`} />}
              {type === 'mcp' && (item as MCP).available && (
                <Tag color="success" className="mr-0 rounded-full px-2 scale-75 origin-left">Active</Tag>
              )}
              {type === 'skill' && (item as Skill).type && (
                <Tag color={isSelected ? selectedColor : 'default'} className="mr-0 rounded-full px-2 scale-75 origin-left">{(item as Skill).type}</Tag>
              )}
            </div>
          }
          description={
            <div>
              <Paragraph
                ellipsis={{ rows: 2 }}
                className={`!mb-0 text-xs mt-1 ${isSelected ? 'text-gray-600 dark:text-gray-400' : 'text-gray-500 dark:text-gray-400'}`}
              >
                {type === 'local' 
                  ? (() => {
                      try {
                        const config = JSON.parse((item as any).config || '{}');
                        return config.description || config.desc || '';
                      } catch {
                        return '';
                      }
                    })()
                  : item.description
                }
              </Paragraph>
              {type === 'skill' && (item as Skill).author && (
                <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">
                  By {(item as Skill).author} {(item as Skill).version && `· v${(item as Skill).version}`}
                  {(item as Skill).repo_url && <span className="ml-1">· Git</span>}
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
    {
      key: 'local',
      label: (
        <span className="flex items-center gap-2 px-2">
          <ToolOutlined />
          {t('Local Tools', { defaultValue: 'Local Tools' })}
          {selectedLocalTools.length > 0 && (
            <Tag color="orange" className="rounded-full px-1.5 scale-75 origin-left">{selectedLocalTools.length}</Tag>
          )}
        </span>
      ),
      children: (
        <div className="flex flex-col h-[500px]">
          <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
            <Input
              prefix={<SearchOutlined className="text-gray-400" />}
              placeholder={t('Search tools...', { defaultValue: 'Search tools...' })}
              bordered={false}
              className="!bg-gray-50 dark:!bg-gray-800 rounded-md"
              value={localToolSearch}
              onChange={(e) => setLocalToolSearch(e.target.value)}
              allowClear
            />
          </div>
          <List
            itemLayout="horizontal"
            dataSource={filteredLocalTools}
            renderItem={(item) => renderListItem(item, 'local')}
            className="flex-1 overflow-y-auto px-2"
          />
          {filteredLocalTools.length === 0 && (
            <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
              {localToolSearch ? t('No tools found', { defaultValue: 'No tools found' }) : t('No tools available', { defaultValue: 'No tools available' })}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'mcp',
      label: (
        <span className="flex items-center gap-2 px-2">
          <ApiOutlined />
          {t('MCP Servers', { defaultValue: 'MCP Servers' })}
          {selectedMcpCodes.length > 0 && (
            <Tag color="green" className="rounded-full px-1.5 scale-75 origin-left">{selectedMcpCodes.length}</Tag>
          )}
        </span>
      ),
      children: (
        <Spin spinning={mcpLoading}>
          <div className="flex flex-col h-[500px]">
            <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
              <Input
                prefix={<SearchOutlined className="text-gray-400" />}
                placeholder={t('Search MCP servers...', { defaultValue: 'Search MCP servers...' })}
                bordered={false}
                className="!bg-gray-50 dark:!bg-gray-800 rounded-md"
                value={mcpSearch}
                onChange={(e) => setMcpSearch(e.target.value)}
                allowClear
              />
            </div>
            <List
              itemLayout="horizontal"
              dataSource={filteredMcpList}
              renderItem={(item) => renderListItem(item, 'mcp')}
              className="flex-1 overflow-y-auto px-2"
            />
            {filteredMcpList.length === 0 && !mcpLoading && (
              <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
                {mcpSearch ? t('No MCP servers found', { defaultValue: 'No MCP servers found' }) : t('No MCP servers available', { defaultValue: 'No MCP servers available' })}
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
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {t('Selected', { defaultValue: 'Selected' })}: {
              activeTab === 'skill' ? selectedSkillCodes.length :
              activeTab === 'mcp' ? selectedMcpCodes.length :
              selectedLocalTools.length
            }
          </div>
          <div className="flex gap-2">
            <Button onClick={onCancel}>
              {t('Cancel', { defaultValue: 'Cancel' })}
            </Button>
            <Button type="primary" onClick={() => {
              if (onSkillsChange) {
                const selectedSkillsData = skillListData.filter((s: Skill) => selectedSkillCodes.includes(s.skill_code));
                onSkillsChange(selectedSkillsData);
              }
              onCancel();
            }} className="bg-black hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200">
              {t('Apply', { defaultValue: 'Apply' })}
            </Button>
          </div>
        </div>
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
