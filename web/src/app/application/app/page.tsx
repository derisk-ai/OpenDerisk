'use client';

import { apiInterceptors, getAppInfo, newDialogue, updateApp, getAppVersion } from '@/client/api';
import { AppContext } from '@/contexts';
import { IApp } from '@/types/app';
import { useRequest } from 'ahooks';
import { Spin, App } from 'antd';
import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import AgentList from './components/agent-list';
import AgentHeader from './components/agent-header';
import TabOverview from './components/tab-overview';
import TabPrompts from './components/tab-prompts';
import TabSkills from './components/tab-skills';
import TabAgents from './components/tab-agents';
import TabKnowledge from './components/tab-knowledge';
import ChatContent from './components/chat-content';
import { AppstoreOutlined } from '@ant-design/icons';

export default function AgentBuilder() {
  const { message, notification } = App.useApp();
  const { t } = useTranslation();

  // Agent selection
  const [selectedAppCode, setSelectedAppCode] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  // AppContext state (mirrors structure/page.tsx)
  const [collapsed, setCollapsed] = useState(false);
  const [appInfo, setAppInfo] = useState<any>({});
  const [versionData, setVersionData] = useState<any>(null);
  const [chatId, setChatId] = useState<string>('');

  // Query agent info
  const {
    run: queryAppInfo,
    refresh: refreshAppInfo,
    loading: refreshAppInfoLoading,
  } = useRequest(
    async (app_code: string, config_code?: string) =>
      await apiInterceptors(
        getAppInfo({ app_code, config_code }),
        notification,
      ),
    {
      manual: true,
      onSuccess: data => {
        const [, res] = data;
        setAppInfo(res || ({} as IApp));
      },
    },
  );

  // Update agent
  const { run: fetchUpdateApp, loading: fetchUpdateAppLoading } = useRequest(
    async (app: any) => await apiInterceptors(updateApp(app), notification),
    {
      manual: true,
      onSuccess: data => {
        const [, res] = data;
        if (!res) {
          message.error(t('application_update_failed'));
          return;
        }
        setAppInfo(res || ({} as IApp));
      },
      onError: err => {
        message.error(t('application_update_failed'));
        console.error('update app error', err);
      },
    },
  );

  // Version data
  const { refreshAsync: refetchVersionData } = useRequest(
    async () => await getAppVersion({ app_code: appInfo.app_code }),
    {
      manual: !appInfo?.app_code,
      ready: !!appInfo?.app_code,
      refreshDeps: [appInfo?.app_code ?? ''],
      onSuccess: data => {
        setVersionData(data);
      },
    },
  );

  // Create new chat session for preview
  const initChatId = useCallback(
    async (appCode: string) => {
      const [, res] = await apiInterceptors(newDialogue({ app_code: appCode }), notification);
      if (res) {
        setChatId(res.conv_uid);
      }
    },
    [notification],
  );

  // Handle agent selection from the left list
  const handleSelectAgent = useCallback(
    (app: IApp) => {
      if (app.app_code === selectedAppCode) return;
      setSelectedAppCode(app.app_code);
      setActiveTab('overview');
      setCollapsed(false);
      queryAppInfo(app.app_code);
      initChatId(app.app_code);
    },
    [selectedAppCode, queryAppInfo, initChatId],
  );

  // Auto-select first agent when list is initially loaded
  const hasAutoSelected = useRef(false);
  const handleListLoaded = useCallback(
    (apps: IApp[]) => {
      if (!hasAutoSelected.current && apps.length > 0 && !selectedAppCode) {
        hasAutoSelected.current = true;
        const first = apps[0];
        setSelectedAppCode(first.app_code);
        queryAppInfo(first.app_code);
        initChatId(first.app_code);
      }
    },
    [selectedAppCode, queryAppInfo, initChatId],
  );

  // Render the active tab content
  const renderTabContent = () => {
    if (!selectedAppCode || !appInfo?.app_code) return null;
    switch (activeTab) {
      case 'overview':
        return <TabOverview />;
      case 'prompts':
        return <TabPrompts />;
      case 'skills':
        return <TabSkills />;
      case 'sub-agents':
        return <TabAgents />;
      case 'knowledge':
        return <TabKnowledge />;
      default:
        return <TabOverview />;
    }
  };

  return (
    <AppContext.Provider
      value={{
        collapsed,
        setCollapsed,
        appInfo,
        setAppInfo,
        refreshAppInfo,
        queryAppInfo,
        refreshAppInfoLoading,
        chatId,
        setChatId,
        fetchUpdateApp,
        fetchUpdateAppLoading,
        refetchVersionData,
        versionData,
      }}
    >
      <div className="flex h-screen w-full bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30 overflow-hidden">
        {/* Column 1: Agent List */}
        <div className="w-[280px] flex-shrink-0 p-3 pr-0">
          <AgentList selectedAppCode={selectedAppCode} onSelect={handleSelectAgent} onListLoaded={handleListLoaded} />
        </div>

        {/* Column 2: Config Tabs — collapsible */}
        <div
          className={`flex-shrink-0 p-3 flex flex-col transition-all duration-400 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden ${
            collapsed
              ? 'w-0 min-w-0 opacity-0 p-0 pointer-events-none'
              : 'flex-1 min-w-[320px] opacity-100'
          }`}
        >
          {selectedAppCode && appInfo?.app_code ? (
            <Spin spinning={refreshAppInfoLoading} wrapperClassName="flex-1 flex flex-col overflow-hidden">
              <div className="flex flex-col h-full bg-white/80 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_8px_32px_rgba(0,0,0,0.06)] overflow-hidden">
                <AgentHeader activeTab={activeTab} onTabChange={setActiveTab} />
                <div className="flex-1 overflow-y-auto">
                  {renderTabContent()}
                </div>
              </div>
            </Spin>
          ) : (
            <div className="flex-1 flex items-center justify-center bg-white/80 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_8px_32px_rgba(0,0,0,0.06)]">
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-gray-100 to-gray-50 flex items-center justify-center">
                  <AppstoreOutlined className="text-2xl text-gray-300" />
                </div>
                <p className="text-gray-400 text-sm font-medium">{t('builder_select_agent')}</p>
                <p className="text-gray-300 text-xs mt-1">{t('builder_select_agent')}</p>
              </div>
            </div>
          )}
        </div>

        {/* Column 3: Chat Preview */}
        <div
          className={`flex-shrink-0 p-3 pl-0 transition-all duration-400 ease-[cubic-bezier(0.4,0,0.2,1)] ${
            collapsed ? 'flex-1' : 'w-[480px]'
          }`}
        >
          <div className="h-full bg-white/80 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_8px_32px_rgba(0,0,0,0.06)] overflow-hidden">
            {selectedAppCode && appInfo?.app_code ? (
              <ChatContent />
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-gradient-to-br from-green-50 to-emerald-50 flex items-center justify-center">
                    <svg className="w-6 h-6 text-green-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <p className="text-gray-400 text-sm font-medium">{t('builder_chat_preview')}</p>
                  <p className="text-gray-300 text-xs mt-1">{t('builder_chat_preview_desc')}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppContext.Provider>
  );
}
