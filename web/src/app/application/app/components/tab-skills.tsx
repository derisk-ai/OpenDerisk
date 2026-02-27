'use client';
import { apiInterceptors, getMCPList } from '@/client/api';
import { getSkillList } from '@/client/api/skill';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, PlusOutlined, ReloadOutlined, ThunderboltOutlined, ApiOutlined, AppstoreOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tag, Dropdown, Tooltip } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

type SkillSource = 'all' | 'skills' | 'mcp';

export default function TabSkills() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');
  const [activeSource, setActiveSource] = useState<SkillSource>('all');

  // Fetch Skills from Agent Skills list
  const { data: skillData, loading: loadingSkills, refresh: refreshSkills } = useRequest(
    async () => await apiInterceptors(getSkillList({ filter: '' }, { page: 1, page_size: 200 })),
  );

  // Fetch MCP from MCP list
  const { data: mcpData, loading: loadingMcp, refresh: refreshMcp } = useRequest(
    async () => await apiInterceptors(getMCPList({ filter: '' }, { page: 1, page_size: 200 })),
  );

  // Extract Skills
  const skills = useMemo(() => {
    const [, res] = skillData || [];
    const items = res?.items || [];
    return items.map((item: any) => ({
      key: item.skill_code,
      name: item.name,
      label: item.name,
      skill_name: item.name,
      description: item.description || '',
      skill_description: item.description || '',
      toolType: 'skill(derisk)',
      groupName: 'skill',
      isBuiltIn: false,
      skillCode: item.skill_code,
      skill_path: item.path || item.skill_code,
      skill_author: item.author,
      skill_branch: item.branch || 'main',
      type: 'skill',
    }));
  }, [skillData]);

  // Extract MCP
  const mcpServers = useMemo(() => {
    const [, res] = mcpData || [];
    const items = res?.items || [];
    return items.map((item: any) => ({
      key: item.mcp_code,
      name: item.name,
      label: item.name,
      description: item.description || '',
      toolType: 'mcp(derisk)',
      groupName: 'mcp',
      isBuiltIn: false,
      mcp_code: item.mcp_code,
      available: item.available,
      author: item.author,
      version: item.version,
      icon: item.icon,
      type: 'mcp(derisk)',
    }));
  }, [mcpData]);

  // Combine all tools based on active filter
  const allTools = useMemo(() => {
    switch (activeSource) {
      case 'skills':
        return skills;
      case 'mcp':
        return mcpServers;
      default:
        return [...skills, ...mcpServers];
    }
  }, [skills, mcpServers, activeSource]);

  // Get currently enabled tool keys
  const enabledToolKeys = useMemo(() => {
    return (appInfo?.resource_tool || []).map((item: any) => {
      const parsed = JSON.parse(item.value || '{}');
      return parsed?.key || parsed?.name;
    }).filter(Boolean);
  }, [appInfo?.resource_tool]);

  // Filter by search
  const filteredTools = useMemo(() => {
    if (!searchValue) return allTools;
    const lower = searchValue.toLowerCase();
    return allTools.filter((item: any) => (item.label || item.name || '').toLowerCase().includes(lower) || (item.key || '').toLowerCase().includes(lower));
  }, [allTools, searchValue]);

  // Count by source
  const skillsCount = skills.length;
  const mcpCount = mcpServers.length;

  // Toggle a tool on/off
  const handleToggle = (tool: any) => {
    const key = tool.key || tool.name;
    const toolType = tool.toolType || tool.type;
    const toolName = tool.label || tool.name;
    const isEnabled = enabledToolKeys.includes(key);

    if (isEnabled) {
      // Remove - by both key AND (type + name) to handle MCP re-creation scenario
      const updatedTools = (appInfo.resource_tool || []).filter((item: any) => {
        const parsed = JSON.parse(item.value || '{}');
        const itemKey = parsed?.key || parsed?.name;
        const itemType = parsed?.toolType || parsed?.type || item.type;
        const itemName = parsed?.name || item.name;
        // Remove if matches key OR matches (type + name) for MCP re-creation case
        const matchesKey = itemKey === key;
        const matchesTypeAndName = itemType === toolType && itemName === toolName;
        return !matchesKey && !matchesTypeAndName;
      });
      fetchUpdateApp({ ...appInfo, resource_tool: updatedTools });
    } else {
      // Add - but first remove any existing tool with same type and name (to handle MCP re-creation with new mcp_code)
      const newTool = {
        type: toolType,
        name: toolName,
        value: JSON.stringify({ key: key, name: toolName, ...tool }),
      };
      const existingTools = (appInfo.resource_tool || []).filter((item: any) => {
        const parsed = JSON.parse(item.value || '{}');
        // Remove if same type AND same name (handles MCP re-creation scenario)
        const hasSameTypeAndName = (parsed?.toolType || parsed?.type || item.type) === toolType && (parsed?.name || item.name) === toolName;
        return !hasSameTypeAndName;
      });
      fetchUpdateApp({ ...appInfo, resource_tool: [...existingTools, newTool] });
    }
  };

  // Refresh all data
  const handleRefresh = () => {
    refreshSkills();
    refreshMcp();
  };

  // Create new items — navigate to dedicated pages in new tab
  const createMenuItems = [
    {
      key: 'skill',
      icon: <ThunderboltOutlined className="text-blue-500" />,
      label: (
        <div className="flex flex-col py-0.5">
          <span className="text-[13px] font-medium text-gray-700">{t('builder_create_skill')}</span>
          <span className="text-[11px] text-gray-400">{t('builder_create_skill_desc')}</span>
        </div>
      ),
    },
    {
      key: 'mcp',
      icon: <ApiOutlined className="text-purple-500" />,
      label: (
        <div className="flex flex-col py-0.5">
          <span className="text-[13px] font-medium text-gray-700">{t('builder_create_mcp')}</span>
          <span className="text-[11px] text-gray-400">{t('builder_create_mcp_desc')}</span>
        </div>
      ),
    },
  ];

  const handleCreateMenuClick = (e: any) => {
    switch (e.key) {
      case 'skill':
        window.open('/agent-skills', '_blank');
        break;
      case 'mcp':
        window.open('/mcp', '_blank');
        break;
    }
  };

  const loading = loadingSkills || loadingMcp;

  // Determine the type tag for a tool
  const getToolTypeTag = (tool: any) => {
    if (tool.type === 'mcp(derisk)' || tool.type === 'mcp') return { label: 'MCP', color: 'purple' };
    return { label: 'Skill', color: 'orange' };
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col h-full">
      {/* Search + Actions bar */}
      <div className="px-5 py-3 border-b border-gray-100/40 flex items-center gap-2">
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('builder_search_placeholder')}
          value={searchValue}
          onChange={e => setSearchValue(e.target.value)}
          allowClear
          className="rounded-lg h-9 flex-1"
        />
        <Tooltip title={t('builder_refresh')}>
          <button
            onClick={handleRefresh}
            className="w-9 h-9 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all flex-shrink-0"
          >
            <ReloadOutlined className={`text-sm ${loading ? 'animate-spin' : ''}`} />
          </button>
        </Tooltip>
        <Dropdown
          menu={{ items: createMenuItems, onClick: handleCreateMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <button
            className="h-9 px-3 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-600 text-white text-[13px] font-medium shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/30 transition-all flex-shrink-0"
          >
            <PlusOutlined className="text-xs" />
            {t('builder_create_new')}
          </button>
        </Dropdown>
      </div>

      {/* Source filter tabs */}
      <div className="px-5 pt-2 pb-0 border-b border-gray-100/40">
        <div className="flex items-center gap-0">
          {([
            { key: 'all', label: t('builder_skill_all'), count: skillsCount + mcpCount },
            { key: 'skills', label: 'Skills', count: skillsCount },
            { key: 'mcp', label: 'MCP', count: mcpCount },
          ] as const).map(tab => (
            <button
              key={tab.key}
              className={`px-3 py-2 text-[12px] font-medium transition-all duration-200 border-b-2 ${
                activeSource === tab.key
                  ? 'text-blue-600 border-blue-500'
                  : 'text-gray-400 border-transparent hover:text-gray-600'
              }`}
              onClick={() => setActiveSource(tab.key)}
            >
              {tab.label}
              <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full ${
                activeSource === tab.key ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'
              }`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Tool list */}
      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={loading}>
          {filteredTools.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {filteredTools.map((tool: any, idx: number) => {
                const key = tool.key || tool.name;
                const isEnabled = enabledToolKeys.includes(key);
                const typeTag = getToolTypeTag(tool);
                return (
                  <div
                    key={`${key}-${idx}`}
                    className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                      isEnabled
                        ? 'border-blue-200/80 bg-blue-50/30 shadow-sm'
                        : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                    }`}
                    onClick={() => handleToggle(tool)}
                  >
                     <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isEnabled ? 'bg-blue-100' : 'bg-gray-100'
                      }`}>
                        {tool.type === 'mcp(derisk)' || tool.type === 'mcp' ? (
                          <ApiOutlined className={`text-sm ${isEnabled ? 'text-purple-500' : 'text-gray-400'}`} />
                        ) : (
                          <AppstoreOutlined className={`text-sm ${isEnabled ? 'text-orange-500' : 'text-gray-400'}`} />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-medium text-gray-700 truncate">{tool.label || tool.name}</span>
                        </div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">
                          {tool.description || tool.toolType}
                          {tool.author && ` · ${tool.author}`}
                        </div>
                      </div>
                      <Tag className="mr-0 text-[10px] rounded-md border-0 font-medium px-1.5" color={typeTag.color}>
                        {typeTag.label}
                      </Tag>
                    </div>
                    {isEnabled && (
                      <CheckCircleFilled className="text-blue-500 text-base ml-2 flex-shrink-0" />
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            !loading && (
              <div className="text-center py-12 text-gray-300 text-xs">
                {t('builder_no_items')}
              </div>
            )
          )}
        </Spin>
      </div>
    </div>
  );
}
