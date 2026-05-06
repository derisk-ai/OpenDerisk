'use client';
import { getResourceV2 } from '@/client/api';
import { AppContext } from '@/contexts';
import {
  CheckCircleFilled,
  SearchOutlined,
  PlusOutlined,
  ReloadOutlined,
  BulbOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Switch, Tooltip, InputNumber } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function TabMemory() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');

  // Fetch all available Memory-type knowledge spaces
  const {  memoryData, loading, refresh } = useRequest(
    async () => await getResourceV2({ type: 'knowledge' })
  );

  // Extract memory-compatible knowledge spaces (storage_type=Memory or all)
  const allMemorySpaces = useMemo(() => {
    const items: any[] = [];
    memoryData?.data?.data?.forEach((group: any) => {
      if (group.param_name === 'knowledge') {
        group.valid_values?.forEach((item: any) => {
          items.push({ ...item });
        });
      }
    });
    return items;
  }, [memoryData]);

  // Get currently enabled memory space ids
  const enabledMemoryIds = useMemo(() => {
    const resourceMemory = appInfo?.resource_memory?.[0]?.value;
    if (!resourceMemory) return [];
    try {
      const parsed = JSON.parse(resourceMemory);
      return (parsed?.memories || []).map((m: any) => m.memory_id);
    } catch {
      return [];
    }
  }, [appInfo?.resource_memory]);

  // Get memory config from resource_memory
  const memoryConfig = useMemo(() => {
    const resourceMemory = appInfo?.resource_memory?.[0]?.value;
    if (!resourceMemory) return { auto_memory: true, enable_kg: true, top_k: 5 };
    try {
      const parsed = JSON.parse(resourceMemory);
      return {
        auto_memory: parsed?.auto_memory ?? true,
        enable_kg: parsed?.enable_kg ?? true,
        top_k: parsed?.top_k ?? 5,
      };
    } catch {
      return { auto_memory: true, enable_kg: true, top_k: 5 };
    }
  }, [appInfo?.resource_memory]);

  // Filter by search
  const filteredSpaces = useMemo(() => {
    if (!searchValue) return allMemorySpaces;
    const lower = searchValue.toLowerCase();
    return allMemorySpaces.filter(
      (k) =>
        (k.label || k.name || '').toLowerCase().includes(lower) ||
        (k.key || '').toLowerCase().includes(lower)
    );
  }, [allMemorySpaces, searchValue]);

  // Build the resource_memory value
  const buildResourceMemory = (
    memories: any[],
    config: { auto_memory: boolean; enable_kg: boolean; top_k: number }
  ) => {
    return [
      {
        ...(appInfo?.resource_memory?.[0] || {}),
        type: 'memory',
        name: 'memory',
        value: JSON.stringify({
          memories,
          auto_memory: config.auto_memory,
          enable_kg: config.enable_kg,
          top_k: config.top_k,
        }),
      },
    ];
  };

  // Get current memories list
  const getCurrentMemories = () => {
    try {
      const resourceMemory = appInfo?.resource_memory?.[0]?.value;
      if (resourceMemory) {
        return JSON.parse(resourceMemory)?.memories || [];
      }
    } catch {}
    return [];
  };

  // Toggle memory space on/off
  const handleToggle = (space: any) => {
    const memoryId = space.key || space.value;
    const memoryName = space.label || space.name;
    const isEnabled = enabledMemoryIds.includes(memoryId);
    const currentMemories = getCurrentMemories();

    if (isEnabled) {
      const updated = currentMemories.filter((m: any) => m.memory_id !== memoryId);
      fetchUpdateApp({
        ...appInfo,
        resource_memory: updated.length > 0 ? buildResourceMemory(updated, memoryConfig) : [],
      });
    } else {
      const updated = [...currentMemories, { memory_id: memoryId, memory_name: memoryName }];
      fetchUpdateApp({
        ...appInfo,
        resource_memory: buildResourceMemory(updated, memoryConfig),
      });
    }
  };

  // Update config toggles
  const handleConfigChange = (key: string, value: any) => {
    const currentMemories = getCurrentMemories();
    const newConfig = { ...memoryConfig, [key]: value };
    fetchUpdateApp({
      ...appInfo,
      resource_memory: buildResourceMemory(currentMemories, newConfig),
    });
  };

  // Navigate to create a new knowledge space (Memory type)
  const handleCreateMemorySpace = () => {
    window.open('/knowledge', '_blank');
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col h-full">
      {/* Config section */}
      <div className="px-5 py-3 border-b border-gray-100/40">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <BulbOutlined className="text-violet-500 text-sm" />
            <span className="text-[13px] text-gray-600">{t('memory_auto_memory')}</span>
            <Switch
              size="small"
              checked={memoryConfig.auto_memory}
              onChange={(v) => handleConfigChange('auto_memory', v)}
            />
          </div>
          <div className="flex items-center gap-2">
            <NodeIndexOutlined className="text-violet-500 text-sm" />
            <span className="text-[13px] text-gray-600">{t('memory_enable_kg')}</span>
            <Switch
              size="small"
              checked={memoryConfig.enable_kg}
              onChange={(v) => handleConfigChange('enable_kg', v)}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[13px] text-gray-600">{t('memory_top_k')}</span>
            <InputNumber
              size="small"
              min={1}
              max={20}
              value={memoryConfig.top_k}
              onChange={(v) => handleConfigChange('top_k', v || 5)}
              className="w-16"
            />
          </div>
        </div>
      </div>

      {/* Search + Actions bar */}
      <div className="px-5 py-3 border-b border-gray-100/40 flex items-center gap-2">
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('builder_search_placeholder')}
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
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
          onClick={handleCreateMemorySpace}
          className="h-9 px-3 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-500 to-purple-600 text-white text-[13px] font-medium shadow-lg shadow-violet-500/25 hover:shadow-xl hover:shadow-violet-500/30 transition-all flex-shrink-0"
        >
          <PlusOutlined className="text-xs" />
          {t('builder_create_new')}
        </button>
      </div>

      {/* Memory spaces list */}
      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={loading}>
          {filteredSpaces.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {filteredSpaces.map((space, idx) => {
                const key = space.key || space.value;
                const isEnabled = enabledMemoryIds.includes(key);
                return (
                  <div
                    key={`${key}-${idx}`}
                    className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                      isEnabled
                        ? 'border-violet-200/80 bg-violet-50/30 shadow-sm'
                        : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                    }`}
                    onClick={() => handleToggle(space)}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          isEnabled ? 'bg-violet-100' : 'bg-gray-100'
                        }`}
                      >
                        <BulbOutlined
                          className={`text-sm ${isEnabled ? 'text-violet-500' : 'text-gray-400'}`}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-medium text-gray-700 truncate">
                          {space.label || space.name}
                        </div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">
                          {space.description || space.key || '--'}
                        </div>
                      </div>
                    </div>
                    {isEnabled && (
                      <CheckCircleFilled className="text-violet-500 text-base ml-2 flex-shrink-0" />
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
