'use client';
import { getResourceV2, getAppList, apiInterceptors } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, UsergroupAddOutlined, PlusOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tag, Tooltip } from 'antd';
import Image from 'next/image';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

type AgentSource = 'all' | 'built-in' | 'custom';

export default function TabAgents() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');
  const [activeSource, setActiveSource] = useState<AgentSource>('all');

  // Fetch built-in agents from resource API
  const { data: agentData, loading: loadingBuiltIn, refresh: refreshBuiltIn } = useRequest(async () => await getResourceV2({ type: 'app' }));

  // Fetch user-created agents from app list API
  const { data: appListData, loading: loadingAppList, refresh: refreshAppList } = useRequest(
    async () => await apiInterceptors(getAppList({ page: 1, page_size: 200 })),
  );

  // Extract built-in agents (filter by param_name === 'app_code')
  const builtInAgents = useMemo(() => {
    const agents: any[] = [];
    agentData?.data?.data?.forEach((group: any) => {
      if (group.param_name === 'app_code') {
        group.valid_values?.forEach((item: any) => {
          agents.push({ ...item, isBuiltIn: true });
        });
      }
    });
    return agents;
  }, [agentData]);

  // Extract user-created agents from app list, excluding current agent and already in built-in
  const customAgents = useMemo(() => {
    const [, res] = appListData || [];
    const appList = res?.app_list || [];
    const builtInKeys = new Set(builtInAgents.map((a: any) => a.key || a.name));
    return appList
      .filter((app: any) => app.app_code !== appInfo?.app_code && !builtInKeys.has(app.app_code))
      .map((app: any) => ({
        key: app.app_code,
        name: app.app_name || 'Untitled Agent',
        label: app.app_name || 'Untitled Agent',
        description: app.app_describe || '',
        icon: app.icon,
        isBuiltIn: false,
      }));
  }, [appListData, appInfo?.app_code, builtInAgents]);

  // Combine agents based on active filter
  const allAgents = useMemo(() => {
    switch (activeSource) {
      case 'built-in':
        return builtInAgents;
      case 'custom':
        return customAgents;
      default:
        return [...builtInAgents, ...customAgents];
    }
  }, [builtInAgents, customAgents, activeSource]);

  // Get currently enabled agent keys
  const enabledAgentKeys = useMemo(() => {
    return (appInfo?.resource_agent || []).map((item: any) => {
      return JSON.parse(item.value || '{}')?.key;
    }).filter(Boolean);
  }, [appInfo?.resource_agent]);

  // Filter by search
  const filteredAgents = useMemo(() => {
    if (!searchValue) return allAgents;
    const lower = searchValue.toLowerCase();
    return allAgents.filter(a => (a.label || a.name || '').toLowerCase().includes(lower) || (a.key || '').toLowerCase().includes(lower));
  }, [allAgents, searchValue]);

  // Counts
  const builtInCount = builtInAgents.length;
  const customCount = customAgents.length;

  // Toggle an agent on/off
  const handleToggle = (agent: any) => {
    const key = agent.key || agent.name;
    const isEnabled = enabledAgentKeys.includes(key);

    if (isEnabled) {
      // Remove
      const updatedAgents = (appInfo.resource_agent || []).filter((item: any) => {
        return JSON.parse(item.value || '{}')?.key !== key;
      });
      fetchUpdateApp({ ...appInfo, resource_agent: updatedAgents });
    } else {
      // Add
      const newAgent = {
        type: 'app',
        name: agent.label || agent.name,
        value: JSON.stringify({ key: agent.key || agent.name, name: agent.label || agent.name, ...agent }),
      };
      const existingAgents = appInfo.resource_agent || [];
      fetchUpdateApp({ ...appInfo, resource_agent: [...existingAgents, newAgent] });
    }
  };

  // Refresh all data
  const handleRefresh = () => {
    refreshBuiltIn();
    refreshAppList();
  };

  // Navigate to create a new agent in a new tab
  const handleCreateAgent = () => {
    window.open('/application/app', '_blank');
  };

  const loading = loadingBuiltIn || loadingAppList;

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
        <button
          onClick={handleCreateAgent}
          className="h-9 px-3 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 text-white text-[13px] font-medium shadow-lg shadow-emerald-500/25 hover:shadow-xl hover:shadow-emerald-500/30 transition-all flex-shrink-0"
        >
          <PlusOutlined className="text-xs" />
          {t('builder_create_new')}
        </button>
      </div>

      {/* Source filter tabs */}
      <div className="px-5 pt-2 pb-0 border-b border-gray-100/40">
        <div className="flex items-center gap-0">
          {([
            { key: 'all', label: t('builder_agent_source_all'), count: builtInCount + customCount },
            { key: 'built-in', label: t('builder_agent_source_built_in'), count: builtInCount },
            { key: 'custom', label: t('builder_agent_source_custom'), count: customCount },
          ] as const).map(tab => (
            <button
              key={tab.key}
              className={`px-3 py-2 text-[12px] font-medium transition-all duration-200 border-b-2 ${
                activeSource === tab.key
                  ? 'text-emerald-600 border-emerald-500'
                  : 'text-gray-400 border-transparent hover:text-gray-600'
              }`}
              onClick={() => setActiveSource(tab.key)}
            >
              {tab.label}
              <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full ${
                activeSource === tab.key ? 'bg-emerald-100 text-emerald-600' : 'bg-gray-100 text-gray-400'
              }`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={loading}>
          {filteredAgents.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {filteredAgents.map((agent, idx) => {
                const key = agent.key || agent.name;
                const isEnabled = enabledAgentKeys.includes(key);
                return (
                  <div
                    key={`${key}-${idx}`}
                    className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                      isEnabled
                        ? 'border-emerald-200/80 bg-emerald-50/30 shadow-sm'
                        : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                    }`}
                    onClick={() => handleToggle(agent)}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 overflow-hidden ${
                        isEnabled ? 'bg-emerald-100' : 'bg-gray-100'
                      }`}>
                        {!agent.isBuiltIn && agent.icon ? (
                          <Image src={agent.icon} width={32} height={32} alt={agent.label || agent.name} className="object-cover w-full h-full" />
                        ) : agent.isBuiltIn ? (
                          <UsergroupAddOutlined className={`text-sm ${isEnabled ? 'text-emerald-500' : 'text-gray-400'}`} />
                        ) : (
                          <RobotOutlined className={`text-sm ${isEnabled ? 'text-orange-500' : 'text-gray-400'}`} />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-medium text-gray-700 truncate">{agent.label || agent.name}</span>
                        </div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">{agent.description || agent.key || '--'}</div>
                      </div>
                      <Tag className="mr-0 text-[10px] rounded-md border-0 font-medium px-1.5" color={agent.isBuiltIn ? 'blue' : 'orange'}>
                        {agent.isBuiltIn ? 'Built-IN' : 'Custom'}
                      </Tag>
                    </div>
                    {isEnabled && (
                      <CheckCircleFilled className="text-emerald-500 text-base ml-2 flex-shrink-0" />
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
