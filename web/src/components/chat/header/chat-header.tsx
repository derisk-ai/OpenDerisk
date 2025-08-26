import { apiInterceptors, collectApp, unCollectApp } from '@/client/api';
import { ChatContentContext } from "@/contexts";
import { ExportOutlined, LoadingOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { Spin, Tag, Typography, message } from 'antd';
import copy from 'copy-to-clipboard';
import React, { useContext, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequest } from 'ahooks';
import AppDefaultIcon from '../../icons/app-default-icon';
import { App } from 'antd';

const tagColors = ['magenta', 'orange', 'geekblue', 'purple', 'cyan', 'green'];

const ChatHeader: React.FC<{ isScrollToTop: boolean }> = ({ isScrollToTop }) => {
  
  const { message } = App.useApp();
  const { appInfo, refreshAppInfo} =
    useContext(ChatContentContext);
  
  const { t } = useTranslation();

  const appScene = useMemo(() => {
    return appInfo?.team_context?.chat_scene || 'chat_agent';
  }, [appInfo]);

  const icon = useMemo(() => {
    return appInfo?.icon || '';
  }, [appInfo]);

  // 应用收藏状态
  const isCollected = useMemo(() => {
    return appInfo?.is_collected === 'true';
  }, [appInfo]);

  const { run: operate, loading } = useRequest(
    async () => {
      const [error] = await apiInterceptors(
        isCollected ? unCollectApp({ app_code: appInfo.app_code }) : collectApp({ app_code: appInfo.app_code }),
      );
      if (error) {
        return;
      }
      return await refreshAppInfo();
    },
    {
      manual: true,
    },
  );

  const paramKey: string[] = useMemo(() => {
    return appInfo.param_need?.map(i => i.type) || [];
  }, [appInfo.param_need]);

  if (!Object.keys(appInfo).length) {
    return null;
  }

  const shareApp = async () => {
    const success = copy(location.href);
    message[success ? 'success' : 'error'](success ? t('copy_success') : t('copy_failed'));
  };

  // 吸顶header
  const topHeaderContent = () => {
    return (
      <header className='flex items-center justify-between w-full h-14 bg-[#F1F5F9] dark:bg-[rgba(41,63,89,0.4)]  px-8 transition-all duration-500 ease-in-out py-2'>
        <div className='flex items-center'>
          <div className='flex items-center justify-center w-8 h-8 rounded-lg mr-2 bg-white'>
            {icon ? (
              <img src={icon} alt={appInfo?.app_name} className='w-8 min-w-8 rounded-full max-w-none' />
            ) : (
              <AppDefaultIcon scene={appScene} width={16} height={16} />
            )}
          </div>
          <div className='flex items-center text-base text-[#1c2533] dark:text-[rgba(255,255,255,0.85)] font-semibold gap-2'>
            <span>{appInfo?.app_name}</span>
            <div className='flex gap-1'>
              {appInfo?.team_mode && <Tag color='green'>{appInfo?.team_mode}</Tag>}
              {appInfo?.team_context?.chat_scene && <Tag color='cyan'>{appInfo?.team_context?.chat_scene}</Tag>}
            </div>
          </div>
        </div>
        <div
          className='flex gap-8'
          onClick={async () => {
            await operate();
          }}
        >
          {/* {loading ? (
            <Spin spinning={loading} indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />
          ) : (
            <>
              {isCollected ? (
                <StarFilled style={{ fontSize: 18 }} className='text-yellow-400 cursor-pointer' />
              ) : (
                <StarOutlined style={{ fontSize: 18, cursor: 'pointer' }} />
              )}
            </>
          )} */}
          <ExportOutlined
            className='text-lg'
            onClick={e => {
              e.stopPropagation();
              shareApp();
            }}
          />
        </div>
      </header>
    );
  };

  return (
    <div
      className={`mt-1 mb-4 bg-[#E0E7F2] ${
      appInfo?.recommend_questions && appInfo?.recommend_questions?.length > 0 ? 'mb-4' : ''
      } sticky top-0 bg-transparent z-30 transition-all duration-400 ease-in-out shadow-[0_4px_12px_-4px_rgba(0,0,0,0.08)]`}
    >
      {topHeaderContent()}
    </div>
  );
};

export default ChatHeader;
