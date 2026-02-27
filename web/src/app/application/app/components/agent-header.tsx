'use client';
import { publishAppNew } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleOutlined, ExclamationCircleFilled, CloudUploadOutlined, DownOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Dropdown, Modal, Button, Tag } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';

interface AgentHeaderProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const tabs = [
  { key: 'overview', labelKey: 'builder_tab_overview' },
  { key: 'prompts', labelKey: 'builder_tab_prompts' },
  { key: 'tools', labelKey: 'builder_tab_tools' },
  { key: 'skills', labelKey: 'builder_tab_skills' },
  { key: 'sub-agents', labelKey: 'builder_tab_sub_agents' },
  { key: 'knowledge', labelKey: 'builder_tab_knowledge' },
];

export default function AgentHeader({ activeTab, onTabChange }: AgentHeaderProps) {
  const { t } = useTranslation();
  const { modal } = App.useApp();
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const {
    appInfo,
    refreshAppInfo,
    fetchUpdateAppLoading,
    refreshAppInfoLoading,
    refetchVersionData,
    versionData,
    queryAppInfo,
  } = useContext(AppContext);

  const { runAsync: fetchPublishApp, loading: fetchPublishAppLoading } = useRequest(
    async (params: any) => await publishAppNew(params),
    {
      manual: true,
      onSuccess: async () => {
        modal.success({ content: t('header_publish_success') });
        if (typeof refreshAppInfo === 'function') await refreshAppInfo();
        if (typeof refetchVersionData === 'function') await refetchVersionData();
      },
      onError: () => {
        modal.error({ content: t('header_publish_failed') });
      },
    },
  );

  const handlePublishOk = async () => {
    await fetchPublishApp({
      app_code: appInfo?.app_code,
      config_code: appInfo?.config_code,
    });
    setPublishModalOpen(false);
  };

  const versionItems = useMemo(() => {
    return (
      versionData?.data?.data?.items?.map((option: any) => ({
        ...option,
        key: option.version_info,
        label: (
          <div className="flex items-center justify-between min-w-[150px]">
            <span className={option.version_info === appInfo?.config_version ? 'font-medium text-blue-600' : 'text-gray-700'}>
              {option.version_info}
            </span>
            {option.version_info === appInfo?.config_version && <CheckCircleOutlined className="ml-2 text-green-500" />}
          </div>
        ),
      })) || []
    );
  }, [versionData, appInfo?.config_version]);

  const handleMenuClick = async (event: any) => {
    const versionInfo = versionData?.data?.data?.items.find((item: any) => item.version_info === event.key);
    if (versionInfo && typeof queryAppInfo === 'function') {
      queryAppInfo(appInfo.app_code, versionInfo.code);
    }
  };

  return (
    <div className="bg-white/80 backdrop-blur-xl rounded-t-2xl border-b border-gray-100/60">
      {/* Top bar: agent info + actions */}
      <div className="flex items-center justify-between px-5 py-3 gap-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="w-10 h-10 rounded-xl overflow-hidden ring-2 ring-white shadow-lg shadow-gray-200/50 flex-shrink-0">
            <Image
              src={appInfo?.icon || '/agents/agent1.jpg'}
              alt="Agent Icon"
              width={40}
              height={40}
              className="object-cover"
            />
          </div>
          <div className="flex flex-col min-w-0">
            <div className="font-semibold text-gray-800 text-[15px] leading-tight tracking-[-0.01em] truncate">
              {appInfo?.app_name || 'Untitled Agent'}
            </div>
            {appInfo?.app_describe && (
              <div className="text-[12px] text-gray-400 mt-0.5 truncate">
                {appInfo.app_describe}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-shrink-0">
          {appInfo?.config_version && (
            <Dropdown menu={{ items: versionItems, onClick: handleMenuClick }} trigger={['click']}>
              <Tag className="cursor-pointer m-0 border-0 bg-gradient-to-r from-gray-50 to-gray-100 hover:from-gray-100 hover:to-gray-150 text-gray-600 rounded-lg px-3 py-1 text-[12px] font-medium flex items-center gap-1.5 transition-all shadow-sm hover:shadow-md">
                <ClockCircleOutlined className="text-[10px] text-gray-400" />
                {appInfo?.config_version}
                <DownOutlined className="text-[9px] opacity-60" />
              </Tag>
            </Dropdown>
          )}
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            className="border-none shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/30 transition-all duration-300 rounded-xl h-9 px-5 font-medium bg-gradient-to-r from-blue-500 via-blue-600 to-indigo-600"
            onClick={() => setPublishModalOpen(true)}
            loading={fetchPublishAppLoading}
          >
            {t('builder_publish')}
          </Button>
        </div>
      </div>

      {/* Tab bar + status */}
      <div className="flex items-center justify-between px-5 border-t border-gray-50/80 gap-3">
        <div className="flex items-center gap-0 overflow-x-auto flex-1 min-w-0">
          {tabs.map(tab => (
            <button
              key={tab.key}
              className={`px-4 py-2.5 text-[13px] font-medium transition-all duration-200 border-b-2 relative whitespace-nowrap flex-shrink-0 ${
                activeTab === tab.key
                  ? 'text-blue-600 border-blue-500'
                  : 'text-gray-500 border-transparent hover:text-gray-700 hover:border-gray-200'
              }`}
              onClick={() => onTabChange(tab.key)}
            >
              {t(tab.labelKey as any)}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2.5 text-[11px] py-2 flex-shrink-0">
          {fetchUpdateAppLoading ? (
            <span className="flex items-center gap-1.5 text-blue-500 font-medium">
              <ClockCircleOutlined spin className="text-[10px]" /> Saving...
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-emerald-500 font-medium">
              <CheckCircleOutlined className="text-[10px]" /> Saved
            </span>
          )}
          {appInfo?.updated_at && (
            <>
              <span className="w-px h-3 bg-gray-200 inline-block" />
              <span className="text-gray-400 font-normal">{appInfo.updated_at}</span>
            </>
          )}
        </div>
      </div>

      {/* Publish Modal */}
      <Modal
        title={
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-amber-50 flex items-center justify-center">
              <ExclamationCircleFilled className="text-amber-500 text-base" />
            </div>
            <span className="text-gray-800 font-semibold text-[15px]">{t('header_publish_app')}</span>
          </div>
        }
        open={publishModalOpen}
        onCancel={() => setPublishModalOpen(false)}
        okButtonProps={{
          loading: refreshAppInfoLoading || fetchUpdateAppLoading || fetchPublishAppLoading,
          className: 'rounded-xl h-9 bg-gradient-to-r from-blue-500 to-indigo-600 border-none shadow-lg shadow-blue-500/25',
        }}
        cancelButtonProps={{ className: 'rounded-xl h-9' }}
        onOk={handlePublishOk}
        centered
        width={420}
        className="[&_.ant-modal-content]:rounded-2xl [&_.ant-modal-content]:overflow-hidden"
      >
        <div className="py-5 text-gray-500 text-sm leading-relaxed">{t('header_publish_confirm')}</div>
      </Modal>
    </div>
  );
}
