'use client';
import { getResourceV2 } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, UsergroupAddOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tooltip } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function TabAgents() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');

  // Fetch all available agents
  const { data: agentData, loading, refresh } = useRequest(async () => await getResourceV2({ type: 'app' }));

  // Extract available agents (filter by param_name === 'app_code')
  const allAgents = useMemo(() => {
    const agents: any[] = [];
    agentData?.data?.data?.forEach((group: any) => {
      if (group.param_name === 'app_code') {
        group.valid_values?.forEach((item: any) => {
          agents.push({ ...item });
        });
      }
    });
    return agents;
  }, [agentData]);

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

  // Navigate to create a new agent in a new tab
  const handleCreateAgent = () => {
    window.open('/application/app', '_blank');
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
            onClick={refresh}
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
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isEnabled ? 'bg-emerald-100' : 'bg-gray-100'
                      }`}>
                        <UsergroupAddOutlined className={`text-sm ${isEnabled ? 'text-emerald-500' : 'text-gray-400'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-medium text-gray-700 truncate">{agent.label || agent.name}</div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">{agent.description || agent.key || '--'}</div>
                      </div>
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
