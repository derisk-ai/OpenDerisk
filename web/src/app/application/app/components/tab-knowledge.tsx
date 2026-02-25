'use client';
import { getResourceV2 } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, DatabaseOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tooltip } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function TabKnowledge() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');

  // Fetch all available knowledge
  const { data: knowledgeData, loading, refresh } = useRequest(async () => await getResourceV2({ type: 'knowledge' }));

  // Extract available knowledge items
  const allKnowledge = useMemo(() => {
    const items: any[] = [];
    knowledgeData?.data?.data?.forEach((group: any) => {
      if (group.param_name === 'knowledge') {
        group.valid_values?.forEach((item: any) => {
          items.push({ ...item });
        });
      }
    });
    return items;
  }, [knowledgeData]);

  // Get currently enabled knowledge ids
  const enabledKnowledgeIds = useMemo(() => {
    const resourceKnowledge = appInfo?.resource_knowledge?.[0]?.value;
    if (!resourceKnowledge) return [];
    try {
      const parsed = JSON.parse(resourceKnowledge);
      return (parsed?.knowledges || []).map((k: any) => k.knowledge_id);
    } catch {
      return [];
    }
  }, [appInfo?.resource_knowledge]);

  // Filter by search
  const filteredKnowledge = useMemo(() => {
    if (!searchValue) return allKnowledge;
    const lower = searchValue.toLowerCase();
    return allKnowledge.filter(k => (k.label || k.name || '').toLowerCase().includes(lower) || (k.key || '').toLowerCase().includes(lower));
  }, [allKnowledge, searchValue]);

  // Toggle knowledge on/off
  const handleToggle = (knowledge: any) => {
    const knowledgeId = knowledge.key || knowledge.value;
    const knowledgeName = knowledge.label || knowledge.name;
    const isEnabled = enabledKnowledgeIds.includes(knowledgeId);

    let currentKnowledges: any[] = [];
    try {
      const resourceKnowledge = appInfo?.resource_knowledge?.[0]?.value;
      if (resourceKnowledge) {
        currentKnowledges = JSON.parse(resourceKnowledge)?.knowledges || [];
      }
    } catch {
      currentKnowledges = [];
    }

    if (isEnabled) {
      // Remove
      const updatedKnowledges = currentKnowledges.filter((k: any) => k.knowledge_id !== knowledgeId);
      const newResourceKnowledge = [{
        ...(appInfo.resource_knowledge?.[0] || {}),
        type: 'knowledge_pack',
        name: 'knowledge',
        value: JSON.stringify({ knowledges: updatedKnowledges }),
      }];
      fetchUpdateApp({ ...appInfo, resource_knowledge: updatedKnowledges.length > 0 ? newResourceKnowledge : [] });
    } else {
      // Add
      const updatedKnowledges = [...currentKnowledges, { knowledge_id: knowledgeId, knowledge_name: knowledgeName }];
      const newResourceKnowledge = [{
        ...(appInfo.resource_knowledge?.[0] || {}),
        type: 'knowledge_pack',
        name: 'knowledge',
        value: JSON.stringify({ knowledges: updatedKnowledges }),
      }];
      fetchUpdateApp({ ...appInfo, resource_knowledge: newResourceKnowledge });
    }
  };

  // Navigate to create a new knowledge base in a new tab
  const handleCreateKnowledge = () => {
    window.open('/knowledge', '_blank');
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
          onClick={handleCreateKnowledge}
          className="h-9 px-3 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-sky-500 to-cyan-600 text-white text-[13px] font-medium shadow-lg shadow-sky-500/25 hover:shadow-xl hover:shadow-sky-500/30 transition-all flex-shrink-0"
        >
          <PlusOutlined className="text-xs" />
          {t('builder_create_new')}
        </button>
      </div>

      {/* Knowledge list */}
      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={loading}>
          {filteredKnowledge.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {filteredKnowledge.map((knowledge, idx) => {
                const key = knowledge.key || knowledge.value;
                const isEnabled = enabledKnowledgeIds.includes(key);
                return (
                  <div
                    key={`${key}-${idx}`}
                    className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                      isEnabled
                        ? 'border-sky-200/80 bg-sky-50/30 shadow-sm'
                        : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                    }`}
                    onClick={() => handleToggle(knowledge)}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isEnabled ? 'bg-sky-100' : 'bg-gray-100'
                      }`}>
                        <DatabaseOutlined className={`text-sm ${isEnabled ? 'text-sky-500' : 'text-gray-400'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-medium text-gray-700 truncate">{knowledge.label || knowledge.name}</div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">{knowledge.description || knowledge.key || '--'}</div>
                      </div>
                    </div>
                    {isEnabled && (
                      <CheckCircleFilled className="text-sky-500 text-base ml-2 flex-shrink-0" />
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
