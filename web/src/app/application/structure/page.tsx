'use client';

import { apiInterceptors, getAppInfo, newDialogue, updateApp, getAppVersion } from '@/client/api';
import { AppContext } from '@/contexts';
import { IApp } from '@/types/app';
import { useRequest } from 'ahooks';
import { Spin, App } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import AppConfig from './components/base-config';
import CharacterConfig from './components/character-config';
import ChatContent from './components/chat-content';
import Header from './components/header';

export default function Structure() {
  const { message, notification } = App.useApp();
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);
  const [appInfo, setAppInfo] = useState<any>({});
  const [versionData, setVersionData] = useState<any>(null);
  const [chatId, setChatId] = useState<string>('');
  const searchParams = useSearchParams();
  const appCode = searchParams.get('app_code');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (appCode) {
      queryAppInfo(appCode);
      initChatId(appCode);
    }
  }, [appCode]);

  const {
    run: queryAppInfo,
    refresh: refreshAppInfo,
    loading: refreshAppInfoLoading,
  } = useRequest(
    async (app_code: string, config_code?: string) =>
      await apiInterceptors(
        getAppInfo({
          app_code,
          config_code,
        }),
        notification
      ),
    {
      manual: true,
      onSuccess: data => {
        const [, res] = data;
        setAppInfo(res || ({} as IApp));
      },
    }
  );

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
    }
  );

  const { refreshAsync: refetchVersionData } = useRequest(
    async () => await getAppVersion({ app_code: appInfo.app_code }),
    {
      manual: !appInfo?.app_code,
      ready: !!appInfo?.app_code,
      refreshDeps: [appInfo?.app_code ?? ''],
      onSuccess: data => {
        setVersionData(data);
      },
    }
  );

  const initChatId = async (appCode: string) => {
    const [, res] = await apiInterceptors(newDialogue({ app_code: appCode }), notification);
    if (res) {
      setChatId(res.conv_uid);
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
        fetchUpdateApp,
        fetchUpdateAppLoading,
        refetchVersionData,
        versionData,
      }}
    >
      <div className="flex flex-col h-screen w-full bg-gray-100 overflow-hidden">
        <Header />
        <Spin spinning={refreshAppInfoLoading} wrapperClassName="flex-1 overflow-hidden">
          <div className="flex flex-1 h-full overflow-hidden" ref={containerRef}>
            <div 
              className={`h-full flex-shrink-0 bg-white shadow-sm transition-all duration-300 ease-in-out overflow-hidden ${
                collapsed ? 'w-0 opacity-0' : 'w-[380px] opacity-100'
              }`}
            >
              <div className="w-[380px] h-full">
                <AppConfig />
              </div>
            </div>
            
            <div 
              className={`h-full bg-white shadow-sm relative transition-all duration-300 ease-in-out overflow-hidden mx-1 ${
                collapsed ? 'w-0 min-w-0 flex-none opacity-0 mx-0' : 'flex-1 min-w-[320px] opacity-100'
              }`}
            >
              <CharacterConfig />
            </div>

            <div 
              className={`h-full bg-white shadow-sm transition-all duration-300 ease-in-out overflow-hidden ${
                collapsed ? 'flex-1 w-full' : 'w-[480px] flex-shrink-0'
              }`}
            >
              <ChatContent />
            </div>
          </div>
        </Spin>
      </div>
    </AppContext.Provider>
  );
}

