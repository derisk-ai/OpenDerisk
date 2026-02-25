'use client';
import { getResourceV2 } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, ToolOutlined, PlusOutlined, ReloadOutlined, ThunderboltOutlined, ApiOutlined, CodeOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tag, Dropdown, Tooltip } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function TabSkills() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');

  // Fetch all available skills (tool type)
  const { data: toolData, loading: loadingTools, refresh: refreshTools } = useRequest(async () => await getResourceV2({ type: 'tool' }));
  const { data: mcpData, loading: loadingMcp, refresh: refreshMcp } = useRequest(async () => await getResourceV2({ type: 'tool(mcp(sse))' }));
  const { data: localData, loading: loadingLocal, refresh: refreshLocal } = useRequest(async () => await getResourceV2({ type: 'tool(local)' }));

  // Combine all available tools
  const allTools = useMemo(() => {
    const tools: any[] = [];
    const addItems = (data: any, type: string) => {
      data?.data?.data?.forEach((group: any) => {
        group.valid_values?.forEach((item: any) => {
          tools.push({ ...item, toolType: type, groupName: group.param_name });
        });
      });
    };
    addItems(toolData, 'tool');
    addItems(mcpData, 'tool(mcp(sse))');
    addItems(localData, 'tool(local)');
    return tools;
  }, [toolData, mcpData, localData]);

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
    return allTools.filter(t => (t.label || t.name || '').toLowerCase().includes(lower) || (t.key || '').toLowerCase().includes(lower));
  }, [allTools, searchValue]);

  // Toggle a tool on/off
  const handleToggle = (tool: any) => {
    const key = tool.key || tool.name;
    const isEnabled = enabledToolKeys.includes(key);

    if (isEnabled) {
      // Remove
      const updatedTools = (appInfo.resource_tool || []).filter((item: any) => {
        const parsed = JSON.parse(item.value || '{}');
        return (parsed?.key || parsed?.name) !== key;
      });
      fetchUpdateApp({ ...appInfo, resource_tool: updatedTools });
    } else {
      // Add
      const newTool = {
        type: tool.toolType,
        name: tool.label || tool.name,
        value: JSON.stringify({ key: tool.key || tool.name, name: tool.label || tool.name, ...tool }),
      };
      const existingTools = appInfo.resource_tool || [];
      fetchUpdateApp({ ...appInfo, resource_tool: [...existingTools, newTool] });
    }
  };

  // Refresh all data
  const handleRefresh = () => {
    refreshTools();
    refreshMcp();
    refreshLocal();
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

  const loading = loadingTools || loadingMcp || loadingLocal;

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

      {/* Tool list */}
      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={loading}>
          {filteredTools.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {filteredTools.map((tool, idx) => {
                const key = tool.key || tool.name;
                const isEnabled = enabledToolKeys.includes(key);
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
                        <ToolOutlined className={`text-sm ${isEnabled ? 'text-blue-500' : 'text-gray-400'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-medium text-gray-700 truncate">{tool.label || tool.name}</div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">{tool.description || tool.toolType}</div>
                      </div>
                      <Tag className="mr-0 text-[10px] rounded-md border-0 font-medium px-1.5" color={tool.toolType.includes('mcp') ? 'purple' : tool.toolType.includes('local') ? 'green' : 'blue'}>
                        {tool.toolType.includes('mcp') ? 'MCP' : tool.toolType.includes('local') ? 'Local' : 'Skill'}
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
