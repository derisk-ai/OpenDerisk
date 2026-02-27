'use client';
import { getResourceV2 } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, ToolOutlined, ReloadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tag, Tooltip } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

type ToolSource = 'all' | 'tool' | 'local';

export default function TabTools() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');
  const [activeSource, setActiveSource] = useState<ToolSource>('all');

  const { data: toolData, loading: loadingTools, refresh: refreshTools } = useRequest(async () => await getResourceV2({ type: 'tool' }));
  const { data: localData, loading: loadingLocal, refresh: refreshLocal } = useRequest(async () => await getResourceV2({ type: 'tool(local)' }));

  const builtInTools = useMemo(() => {
    const tools: any[] = [];
    const addItems = (data: any, type: string) => {
      data?.data?.data?.forEach((group: any) => {
        group.valid_values?.forEach((item: any) => {
          tools.push({ ...item, toolType: type, groupName: group.param_name, isBuiltIn: true });
        });
      });
    };
    addItems(toolData, 'tool');
    addItems(localData, 'tool(local)');
    return tools;
  }, [toolData, localData]);

  const filteredBySource = useMemo(() => {
    switch (activeSource) {
      case 'tool':
        return builtInTools.filter((t: any) => t.toolType === 'tool');
      case 'local':
        return builtInTools.filter((t: any) => t.toolType === 'tool(local)');
      default:
        return builtInTools;
    }
  }, [builtInTools, activeSource]);

  const enabledToolKeys = useMemo(() => {
    return (appInfo?.resource_tool || []).map((item: any) => {
      const parsed = JSON.parse(item.value || '{}');
      return parsed?.key || parsed?.name;
    }).filter(Boolean);
  }, [appInfo?.resource_tool]);

  const filteredTools = useMemo(() => {
    if (!searchValue) return filteredBySource;
    const lower = searchValue.toLowerCase();
    return filteredBySource.filter((item: any) => (item.label || item.name || '').toLowerCase().includes(lower) || (item.key || '').toLowerCase().includes(lower));
  }, [filteredBySource, searchValue]);

  const toolCount = builtInTools.filter((t: any) => t.toolType === 'tool').length;
  const localCount = builtInTools.filter((t: any) => t.toolType === 'tool(local)').length;

  const handleToggle = (tool: any) => {
    const key = tool.key || tool.name;
    const toolType = tool.toolType;
    const toolName = tool.label || tool.name;
    const isEnabled = enabledToolKeys.includes(key);

    if (isEnabled) {
      // Remove - by both key AND (type + name) to handle any re-creation scenario
      const updatedTools = (appInfo.resource_tool || []).filter((item: any) => {
        const parsed = JSON.parse(item.value || '{}');
        const itemKey = parsed?.key || parsed?.name;
        const itemType = parsed?.toolType || item.type;
        const itemName = parsed?.name || item.name;
        // Remove if matches key OR matches (type + name)
        const matchesKey = itemKey === key;
        const matchesTypeAndName = itemType === toolType && itemName === toolName;
        return !matchesKey && !matchesTypeAndName;
      });
      fetchUpdateApp({ ...appInfo, resource_tool: updatedTools });
    } else {
      const newTool = {
        type: toolType,
        name: toolName,
        value: JSON.stringify({ key: key, name: toolName, ...tool }),
      };
      const existingTools = (appInfo.resource_tool || []).filter((item: any) => {
        const parsed = JSON.parse(item.value || '{}');
        const itemType = parsed?.toolType || item.type;
        const itemName = parsed?.name || item.name;
        // Remove if same type AND same name
        const hasSameTypeAndName = itemType === toolType && itemName === toolName;
        return !hasSameTypeAndName;
      });
      fetchUpdateApp({ ...appInfo, resource_tool: [...existingTools, newTool] });
    }
  };

  const handleRefresh = () => {
    refreshTools();
    refreshLocal();
  };

  const loading = loadingTools || loadingLocal;

  const getToolTypeTag = (tool: any) => {
    if (tool.toolType.includes('local')) return { label: 'Local', color: 'green' };
    return { label: 'Built-IN', color: 'blue' };
  };

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
      </div>

      <div className="px-5 pt-2 pb-0 border-b border-gray-100/40">
        <div className="flex items-center gap-0">
          {([
            { key: 'all', label: t('builder_tool_all'), count: builtInTools.length },
            { key: 'tool', label: t('builder_tool_builtin'), count: toolCount },
            { key: 'local', label: t('builder_tool_local'), count: localCount },
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
                        <ToolOutlined className={`text-sm ${isEnabled ? 'text-blue-500' : 'text-gray-400'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-medium text-gray-700 truncate">{tool.label || tool.name}</span>
                        </div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">
                          {tool.description || tool.toolType}
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