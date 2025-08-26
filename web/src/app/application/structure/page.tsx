'use client';

import { apiInterceptors, getAppInfo, newDialogue, updateApp } from '@/client/api';
import { AppContext } from '@/contexts';
import { IApp } from '@/types/app';
import { useRequest } from 'ahooks';
import { Spin } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import AppConfig from './components/base-config';
import CharacterConfig from './components/character-config';
import ChatContent from './components/chat-content';
import Header from './components/header';
import { getAppVersion } from '@/client/api';
import { App } from 'antd'

export default function Structure() {
  const { message, notification } = App.useApp()
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

  // 获取应用详情
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
      notification),
    {
      manual: true,
      onSuccess: data => {
        const [, res] = data;
        setAppInfo(res || ({} as IApp));
      },
    },
  );

  // 更新应用
  const { run: fetchUpdateApp, loading: fetchUpdateAppLoading } = useRequest(async (app: any) => await apiInterceptors(updateApp(app), notification), {
    manual: true,
    onSuccess: data => {
      const [, res] = data; 
      if (!res) {
        message.error('应用更新失败，请稍后重试');
        return;
      }
      setAppInfo(res || ({} as IApp));
    },
    onError: err => {
      message.error('应用更新失败，请稍后重试');
      console.log('update app error', err);
    }
  },);

  // 获取版本数据
  const { refreshAsync: refetchVersionData } = useRequest(
    async () => await getAppVersion({ app_code: appInfo.app_code }),
    {
      manual: !appInfo?.app_code,
      ready: !!appInfo?.app_code,
      refreshDeps: [appInfo?.app_code ?? ''],
      onSuccess: data => {   
        setVersionData(data);
      }
    },
  );
  // 初始化会话ID
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
      <Spin spinning={refreshAppInfoLoading} wrapperClassName='h-screen w-full'>
        <div className='flex flex-col h-full'>
          <Header />
          {/* 基础配置 */}
          <div className='flex flex-1 flex-row overflow-hidden' ref={containerRef}>
            {!collapsed && <AppConfig />}
            {/* 角色设定 */}
            {!collapsed && <CharacterConfig />}
            <ChatContent />
          </div>
        </div>
      </Spin>
    </AppContext.Provider>
  );
}
