'use client';
import { getDbList, apiInterceptors } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleFilled, SearchOutlined, DatabaseOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Input, Spin, Tag, Tooltip } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function TabDatabase() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');

  // Fetch all available databases
  const { data: dbListData, loading, refresh } = useRequest(async () => {
    const [, res] = await apiInterceptors(getDbList());
    return res ?? [];
  });

  const allDatabases = useMemo(() => dbListData || [], [dbListData]);

  // Get currently enabled database ids from resource_tool
  const enabledDbIds = useMemo(() => {
    const resourceTool = appInfo?.resource_tool || [];
    return resourceTool
      .filter((item: any) => item.type === 'datasource')
      .map((item: any) => {
        try {
          const parsed = JSON.parse(item.value || '{}');
          return parsed.id;
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }, [appInfo?.resource_tool]);

  // Filter by search
  const filteredDatabases = useMemo(() => {
    if (!searchValue) return allDatabases;
    const lower = searchValue.toLowerCase();
    return allDatabases.filter((db: any) =>
      (db.db_name || '').toLowerCase().includes(lower) ||
      (db.db_type || '').toLowerCase().includes(lower) ||
      (db.comment || '').toLowerCase().includes(lower),
    );
  }, [allDatabases, searchValue]);

  // Toggle database on/off
  const handleToggle = (db: any) => {
    const dbId = db.id;
    const isEnabled = enabledDbIds.includes(dbId);
    const currentResourceTool = appInfo?.resource_tool || [];

    if (isEnabled) {
      // Remove this database from resource_tool
      const updatedResourceTool = currentResourceTool.filter((item: any) => {
        if (item.type !== 'datasource') return true;
        try {
          const parsed = JSON.parse(item.value || '{}');
          return parsed.id !== dbId;
        } catch {
          return true;
        }
      });
      fetchUpdateApp({ ...appInfo, resource_tool: updatedResourceTool });
    } else {
      // Add this database to resource_tool
      const newEntry = {
        type: 'datasource',
        name: db.db_name,
        value: JSON.stringify({ db_name: db.db_name, db_type: db.db_type, id: db.id }),
      };
      fetchUpdateApp({ ...appInfo, resource_tool: [...currentResourceTool, newEntry] });
    }
  };

  // Navigate to database management page
  const handleCreateDatabase = () => {
    window.open('/database', '_blank');
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
          onClick={handleCreateDatabase}
          className="h-9 px-3 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-green-500 to-emerald-600 text-white text-[13px] font-medium shadow-lg shadow-green-500/25 hover:shadow-xl hover:shadow-green-500/30 transition-all flex-shrink-0"
        >
          <PlusOutlined className="text-xs" />
          {t('builder_create_new')}
        </button>
      </div>

      {/* Database list */}
      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={loading}>
          {filteredDatabases.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {filteredDatabases.map((db: any, idx: number) => {
                const isEnabled = enabledDbIds.includes(db.id);
                return (
                  <div
                    key={`${db.id}-${idx}`}
                    className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                      isEnabled
                        ? 'border-green-200/80 bg-green-50/30 shadow-sm'
                        : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                    }`}
                    onClick={() => handleToggle(db)}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          isEnabled ? 'bg-green-100' : 'bg-gray-100'
                        }`}
                      >
                        <DatabaseOutlined className={`text-sm ${isEnabled ? 'text-green-500' : 'text-gray-400'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-medium text-gray-700 truncate">{db.db_name}</span>
                          <Tag className="text-[10px] border-0 bg-gray-100 text-gray-500 rounded px-1.5 py-0 leading-5">{db.db_type}</Tag>
                        </div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">{db.comment || db.db_host || '--'}</div>
                      </div>
                    </div>
                    {isEnabled && <CheckCircleFilled className="text-green-500 text-base ml-2 flex-shrink-0" />}
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
