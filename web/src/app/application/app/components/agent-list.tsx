'use client';
import { apiInterceptors, getAppList, delApp } from '@/client/api';
import { IApp } from '@/types/app';
import { PlusOutlined, ReloadOutlined, WarningOutlined, DeleteOutlined } from '@ant-design/icons';
import { useDebounceFn, useRequest } from 'ahooks';
import { App, Button, Input, Spin, Tooltip } from 'antd';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import CreateAppModal from '@/components/create-app-modal';

interface AgentListProps {
  selectedAppCode: string | null;
  onSelect: (app: IApp) => void;
  onListLoaded?: (apps: IApp[]) => void;
  refreshTrigger?: number;
}

export default function AgentList({ selectedAppCode, onSelect, onListLoaded, refreshTrigger }: AgentListProps) {
  const { t } = useTranslation();
  const { modal, notification } = App.useApp();
  const [apps, setApps] = useState<IApp[]>([]);
  const [filterValue, setFilterValue] = useState('');
  const [createModalOpen, setCreateModalOpen] = useState(false);

  const onListLoadedRef = useRef(onListLoaded);
  onListLoadedRef.current = onListLoaded;

  const { run: fetchList, loading } = useRequest(
    async (params?: any) => {
      const obj = {
        page: 1,
        page_size: 200,
        ...params,
      };
      const [error, data] = await apiInterceptors(getAppList(obj), notification);
      if (error || !data) return;
      const appList = data.app_list || [];
      setApps(appList);
      return appList;
    },
    {
      manual: true,
      onSuccess: (appList) => {
        if (appList && appList.length > 0) {
          onListLoadedRef.current?.(appList);
        }
      },
    },
  );

  const debouncedFetch = useDebounceFn(
    (name_filter: string) => {
      fetchList({ name_filter });
    },
    { wait: 300 },
  );

  useEffect(() => {
    fetchList();
  }, []);

  useEffect(() => {
    if (refreshTrigger) {
      fetchList();
    }
  }, [refreshTrigger]);

  const handleCreate = () => {
    setCreateModalOpen(true);
  };

  const handleCreateSuccess = async (newApp?: IApp) => {
    await fetchList();
    if (newApp) {
      onSelect(newApp);
    }
  };

  const handleDelete = (e: React.MouseEvent, app: IApp) => {
    e.stopPropagation();
    modal.confirm({
      title: t('Tips'),
      icon: <WarningOutlined />,
      content: t('app_delete_confirm'),
      okText: t('app_delete_yes'),
      okType: 'danger',
      cancelText: t('app_delete_no'),
      async onOk() {
        await apiInterceptors(delApp({ app_code: app.app_code }));
        await fetchList();
      },
    });
  };

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setFilterValue(v);
    debouncedFetch.run(v);
  };

  return (
    <div className="flex flex-col h-full bg-white/80 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_8px_32px_rgba(0,0,0,0.06)]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-100/60">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-[14px] text-gray-800 tracking-[-0.01em]">
              {t('builder_agent_list_title')}
            </h3>
            <span className="text-[11px] text-gray-400 bg-gray-100/60 rounded-full px-2 py-0.5 font-medium">
              {apps.length}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Tooltip title={t('builder_agent_list_refresh')}>
              <Button
                type="text"
                size="small"
                icon={<ReloadOutlined />}
                className="text-gray-400 hover:text-blue-500 rounded-lg h-7 w-7"
                onClick={() => fetchList()}
                loading={loading}
              />
            </Tooltip>
            <Tooltip title={t('create_app')}>
              <Button
                type="text"
                size="small"
                icon={<PlusOutlined />}
                className="text-blue-500 hover:bg-blue-50/80 rounded-lg h-7 w-7"
                onClick={handleCreate}
              />
            </Tooltip>
          </div>
        </div>
        <Input
          size="small"
          placeholder={t('builder_search_placeholder')}
          value={filterValue}
          onChange={handleSearch}
          allowClear
          className="rounded-lg h-8"
        />
      </div>

      {/* Agent List */}
      <div className="flex-1 overflow-y-auto px-2 py-2 custom-scrollbar">
        <Spin spinning={loading && apps.length === 0} className="w-full">
          {apps.length > 0 ? (
            <div className="flex flex-col gap-0.5">
              {apps.map(app => (
                <div
                  key={app.app_code}
                  className={`group flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 ${
                    selectedAppCode === app.app_code
                      ? 'bg-gradient-to-r from-blue-50 to-indigo-50/50 border border-blue-200/60 shadow-sm'
                      : 'hover:bg-gray-50/80 border border-transparent'
                  }`}
                  onClick={() => onSelect(app)}
                >
                  <div className="w-9 h-9 rounded-xl overflow-hidden ring-1 ring-gray-200/60 shadow-sm flex-shrink-0">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={app.icon?.trim() && app.icon !== 'smart-plugin' ? app.icon : '/icons/colorful-plugin.png'}
                      alt={app.app_name || 'Agent'}
                      className="object-cover w-full h-full"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.onerror = null;
                        target.src = '/icons/colorful-plugin.png';
                      }}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className={`text-[13px] truncate ${
                      selectedAppCode === app.app_code
                        ? 'text-blue-700 font-semibold'
                        : 'text-gray-700 font-medium'
                    }`}>
                      {app.app_name || 'Untitled Agent'}
                    </div>
                    <div className="text-[11px] text-gray-400 truncate mt-0.5">
                      {app.app_describe || '--'}
                    </div>
                  </div>
                  <Tooltip title={t('Delete')}>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined className="text-[12px]" />}
                      className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 rounded-lg h-6 w-6 flex items-center justify-center"
                      onClick={(e) => handleDelete(e, app)}
                    />
                  </Tooltip>
                </div>
              ))}
            </div>
          ) : (
            !loading && (
              <div className="text-center py-12 text-gray-300 text-xs">
                {t('builder_agent_list_empty')}
              </div>
            )
          )}
        </Spin>
      </div>
      <CreateAppModal
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        refresh={handleCreateSuccess}
        type="add"
        skipRedirect={true}
      />
    </div>
  );
}
