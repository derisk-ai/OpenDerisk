'use client';
import { apiInterceptors } from '@/client/api';
import { getSkillList } from '@/client/api/skill';
import { getMCPList } from '@/client/api/request';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, ReloadOutlined, ThunderboltOutlined, ApiOutlined, PlusOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tag, Tooltip, Dropdown } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

type ResourceType = 'skills' | 'mcp';

export default function TabSkills() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');
  const [activeResource, setActiveResource] = useState<ResourceType>('skills');

  const { data: skillData, loading: loadingSkills, refresh: refreshSkills } = useRequest(
    async () => await apiInterceptors(getSkillList({ filter: '' }, { page: 1, page_size: 200 })),
  );

  const { data: mcpData, loading: loadingMcp, refresh: refreshMcp } = useRequest(
    async () => await apiInterceptors(getMCPList({ filter: '' }, { page: '1', page_size: '200' })),
  );

  const skills = useMemo(() => {
    const [, res] = skillData || [];
    const items = (res as any)?.items || [];
    return items.map((item: any) => ({
      key: item.skill_code,
      name: item.name,
      label: item.name,
      description: item.description || '',
      toolType: 'skill(derisk)',
      isCustom: true,
      skillCode: item.skill_code,
      skill_path: item.path || item.skill_code,
      author: item.author,
      available: item.available,
    }));
  }, [skillData]);

  const mcps = useMemo(() => {
    const [, res] = mcpData || [];
    const items = (res as any)?.items || [];
    return items.map((item: any) => ({
      key: item.mcp_code || item.name,
      name: item.name,
      label: item.name,
      description: item.description || '',
      toolType: 'tool(mcp(sse))',
      isCustom: true,
      mcpCode: item.mcp_code,
      author: item.author,
      available: item.available,
      sse_headers: item.sse_headers,
    }));
  }, [mcpData]);

  const currentList = useMemo(() => {
    return activeResource === 'skills' ? skills : mcps;
  }, [skills, mcps, activeResource]);

  const enabledResourceKeys = useMemo(() => {
    return (appInfo?.resource_tool || []).map((item: any) => {
      const parsed = JSON.parse(item.value || '{}');
      return parsed?.key || parsed?.name || parsed?.skill_code || parsed?.mcp_code;
    }).filter(Boolean);
  }, [appInfo?.resource_tool]);

  const filteredItems = useMemo(() => {
    if (!searchValue) return currentList;
    const lower = searchValue.toLowerCase();
    return currentList.filter((item: any) =>
      (item.label || item.name || '').toLowerCase().includes(lower) ||
      (item.description || '').toLowerCase().includes(lower)
    );
  }, [currentList, searchValue]);

  const skillsCount = skills.length;
  const mcpsCount = mcps.length;

  const handleToggle = (item: any) => {
    const key = item.key || item.name;
    const isEnabled = enabledResourceKeys.includes(key);

    if (isEnabled) {
      const updated = (appInfo.resource_tool || []).filter((i: any) => {
        const parsed = JSON.parse(i.value || '{}');
        return (parsed?.key || parsed?.name || parsed?.skill_code || parsed?.mcp_code) !== key;
      });
      fetchUpdateApp({ ...appInfo, resource_tool: updated });
    } else {
      const newItem = {
        type: item.toolType,
        name: item.label || item.name,
        value: JSON.stringify({
          key: item.key || item.name,
          name: item.label || item.name,
          skill_code: item.skillCode || item.mcpCode,
          ...item
        }),
      };
      const existing = appInfo.resource_tool || [];
      fetchUpdateApp({ ...appInfo, resource_tool: [...existing, newItem] });
    }
  };

  const handleRefresh = () => {
    refreshSkills();
    refreshMcp();
  };

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

  return (
    <div className="flex-1 overflow-hidden flex flex-col h-full">
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

      <div className="px-5 pt-2 pb-0 border-b border-gray-100/40">
        <div className="flex items-center gap-0">
          {([
            { key: 'skills', label: t('builder_skills_tab'), count: skillsCount },
            { key: 'mcp', label: t('builder_mcp_tab'), count: mcpsCount },
          ] as const).map(tab => (
            <button
              key={tab.key}
              className={`px-3 py-2 text-[12px] font-medium transition-all duration-200 border-b-2 ${
                activeResource === tab.key
                  ? 'text-blue-600 border-blue-500'
                  : 'text-gray-400 border-transparent hover:text-gray-600'
              }`}
              onClick={() => setActiveResource(tab.key)}
            >
              {tab.label}
              <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full ${
                activeResource === tab.key ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'
              }`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={loading}>
          {filteredItems.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {filteredItems.map((item: any, idx: number) => {
                const key = item.key || item.name;
                const isEnabled = enabledResourceKeys.includes(key);
                return (
                  <div
                    key={`${key}-${idx}`}
                    className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                      isEnabled
                        ? 'border-blue-200/80 bg-blue-50/30 shadow-sm'
                        : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                    }`}
                    onClick={() => handleToggle(item)}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isEnabled ? 'bg-blue-100' : 'bg-gray-100'
                      }`}>
                        {activeResource === 'skills' ? (
                          <ThunderboltOutlined className={`text-sm ${isEnabled ? 'text-blue-500' : 'text-gray-400'}`} />
                        ) : (
                          <ApiOutlined className={`text-sm ${isEnabled ? 'text-purple-500' : 'text-gray-400'}`} />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-medium text-gray-700 truncate">{item.label || item.name}</span>
                        </div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">
                          {item.description || (activeResource === 'skills' ? 'Custom Skill' : 'MCP Server')}
                          {item.author && ` · ${item.author}`}
                        </div>
                      </div>
                      <Tag className="mr-0 text-[10px] rounded-md border-0 font-medium px-1.5" color={activeResource === 'skills' ? 'blue' : 'purple'}>
                        {activeResource === 'skills' ? 'Skill' : 'MCP'}
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