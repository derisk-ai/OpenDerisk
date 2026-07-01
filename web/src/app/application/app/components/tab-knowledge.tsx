'use client';
import { apiInterceptors } from '@/client/api';
import { listSpaces } from '@/client/api/knowledge-vault';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, DatabaseOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tooltip } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SpaceInfo } from '@/types/knowledge-vault';

export default function TabKnowledge() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');

  // Fetch knowledge spaces from the new vault backend.
  const { data: knowledgeData, loading, refresh } = useRequest(
    async () => {
      const [, data] = await apiInterceptors(listSpaces());
      return data || [];
    }
  );

  const allKnowledge = useMemo(() => {
    return (knowledgeData || [])
      .filter((space: SpaceInfo) => !(space.slug || '').startsWith('memory-'))
      .map((space: SpaceInfo) => ({
        key: space.slug,
        value: space.slug,
        label: space.slug,
        name: space.slug,
        description: space.root,
      }));
  }, [knowledgeData]);

  // Currently enabled knowledge slugs (legacy `knowledge_id` field name kept
  // for back-compat with the App builder resource_knowledge structure).
  const enabledKnowledgeIds = useMemo(() => {
    const resourceKnowledge = appInfo?.resource_knowledge?.[0]?.value;
    if (!resourceKnowledge) return [];
    try {
      const parsed = JSON.parse(resourceKnowledge);
      return (parsed?.knowledges || []).map((k: any) => k.knowledge_id || k.slug);
    } catch {
      return [];
    }
  }, [appInfo?.resource_knowledge]);

  const filteredKnowledge = useMemo(() => {
    if (!searchValue) return allKnowledge;
    const lower = searchValue.toLowerCase();
    return allKnowledge.filter(k => (k.label || k.name || '').toLowerCase().includes(lower) || (k.key || '').toLowerCase().includes(lower));
  }, [allKnowledge, searchValue]);

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
      const updatedKnowledges = currentKnowledges.filter((k: any) => (k.knowledge_id || k.slug) !== knowledgeId);
      const newResourceKnowledge = [{
        ...(appInfo.resource_knowledge?.[0] || {}),
        type: 'knowledge_pack',
        name: 'knowledge',
        value: JSON.stringify({ knowledges: updatedKnowledges }),
      }];
      fetchUpdateApp({ ...appInfo, resource_knowledge: updatedKnowledges.length > 0 ? newResourceKnowledge : [] });
    } else {
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

  const handleCreateKnowledge = () => {
    window.open('/knowledge-vault', '_blank');
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
