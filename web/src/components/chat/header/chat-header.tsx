'use client';

import { apiInterceptors, collectApp, unCollectApp } from '@/client/api';
import { AppContext, ChatContentContext } from "@/contexts";
import { 
  ExportOutlined, 
  StarFilled, 
  StarOutlined,
  MoreOutlined,
  ShareAltOutlined,
  ThunderboltOutlined,
  MessageOutlined,
  AppstoreOutlined,
  PlusOutlined,
  CloudServerOutlined
} from '@ant-design/icons';
import { Button, message, Dropdown, Badge, Tag, Tooltip } from 'antd';
import copy from 'copy-to-clipboard';
import React, { useContext, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequest } from 'ahooks';
import classNames from 'classnames';
import AppDefaultIcon from '../../icons/app-default-icon';
import { useRouter, useSearchParams } from 'next/navigation';
import { useContextMetrics } from '@/contexts/context-metrics-context';
import ContextMetricsDisplay from '../chat-content-components/ContextMetricsDisplay';

interface ChatHeaderProps {
  isScrollToTop?: boolean;
  isProcessing?: boolean;
}

const ChatHeader: React.FC<ChatHeaderProps> = ({ isScrollToTop = false, isProcessing = false }) => {
  const { appInfo, refreshAppInfo, history, setHistory } = useContext(ChatContentContext);
  const { initChatId } = useContext(AppContext);
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { metrics } = useContextMetrics();

  const appScene = useMemo(() => {
    return appInfo?.team_context?.chat_scene || 'chat_agent';
  }, [appInfo]);

  const icon = useMemo(() => {
    return appInfo?.icon || '';
  }, [appInfo]);

  const isCollected = useMemo(() => {
    return appInfo?.is_collected === 'true';
  }, [appInfo]);

  const { run: operate } = useRequest(
    async () => {
      const [error] = await apiInterceptors(
        isCollected 
          ? unCollectApp({ app_code: appInfo.app_code }) 
          : collectApp({ app_code: appInfo.app_code }),
      );
      if (error) return;
      return await refreshAppInfo();
    },
    { manual: true }
  );

  if (!Object.keys(appInfo).length) {
    return null;
  }

  const shareApp = async () => {
    const success = copy(location.href);
    message[success ? 'success' : 'error'](
      success ? t('copy_success') : t('copy_failed')
    );
  };

  const handleNewChat = async () => {
    const appCode = appInfo?.app_code;
    if (appCode && initChatId) {
      setHistory?.([]);
      await initChatId(appCode);
    }
  };

  const moreMenuItems = [
    {
      key: 'share',
      icon: <ShareAltOutlined />,
      label: t('share', '分享对话'),
      onClick: shareApp,
    },
    {
      key: 'collect',
      icon: isCollected ? <StarFilled className="text-amber-400" /> : <StarOutlined />,
      label: isCollected ? t('uncollect', '取消收藏') : t('collect', '收藏应用'),
      onClick: () => operate(),
    },
  ];

  const messageCount = history.filter(h => h.role === 'human').length;

  return (
    <div className="w-full bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-100 dark:border-gray-800">
      <div className="max-w-3xl mx-auto px-4 sm:px-6">
        <div className="flex items-center gap-4 py-4">
          {/* 应用图标 */}
          <div className="relative flex-shrink-0">
            <div className={classNames(
              "w-11 h-11 rounded-xl flex items-center justify-center shadow-md transition-all duration-300",
              icon && icon !== 'smart-plugin' ? "bg-white ring-1 ring-gray-100" : "bg-white ring-1 ring-gray-100"
            )}>
              {icon && icon !== 'smart-plugin' ? (
                <img 
                  src={icon} 
                  alt={appInfo?.app_name} 
                  className="w-8 h-8 object-contain rounded-lg"
                />
              ) : icon === 'smart-plugin' ? (
                <img 
                  src="/icons/colorful-plugin.png" 
                  alt={appInfo?.app_name} 
                  className="w-8 h-8 object-contain rounded-lg"
                />
              ) : (
                <AppDefaultIcon scene={appScene} width={22} height={22} />
              )}
            </div>
            {/* 状态指示 - 呼吸效果，对话时展示 */}
            {isProcessing && (
              <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3">
                <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-75" />
                <span className="absolute inset-0.5 rounded-full bg-emerald-500" />
              </div>
            )}
          </div>

          {/* 应用信息 - 紧凑排列 */}
          <div className="flex flex-col gap-0.5 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold text-gray-900 dark:text-white truncate">
                {appInfo?.app_name}
              </h1>
              {isCollected && (
                <StarFilled className="text-amber-400 text-xs flex-shrink-0" />
              )}
              {appInfo?.team_mode && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 flex-shrink-0">
                  {appInfo?.team_mode}
                </span>
              )}
            </div>
<div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              {appInfo?.team_context?.chat_scene && (
                <span className="truncate">{appInfo?.team_context?.chat_scene}</span>
              )}
              {messageCount > 0 && (
                <span className="flex items-center gap-1 flex-shrink-0">
                  <span className="w-0.5 h-0.5 rounded-full bg-gray-300" />
                  {messageCount} 轮
                </span>
              )}
              {metrics && (
                <ContextMetricsDisplay metrics={metrics} compact />
              )}
            </div>
          </div>

          {/* 操作按钮 */}
            <div className="flex items-center gap-1 flex-shrink-0">
              <Tooltip title="新会话" placement="bottom">
                <Button
                  type="text"
                  size="small"
                  icon={<PlusOutlined className="text-sm" />}
                  onClick={handleNewChat}
                  className="w-7 h-7 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
                />
              </Tooltip>
             <Tooltip title="更多" placement="bottom">
               <Dropdown 
                 menu={{ items: moreMenuItems }} 
                 placement="bottomRight"
                 trigger={['click']}
               >
                 <Button
                   type="text"
                   size="small"
                   icon={<MoreOutlined className="text-sm" />}
                   className="w-7 h-7 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
                 />
               </Dropdown>
             </Tooltip>
             
             <Tooltip title="分享" placement="bottom">
               <Button
                 type="primary"
                 size="small"
                 icon={<ExportOutlined className="text-xs" />}
                 onClick={shareApp}
                 className="rounded-lg bg-gray-900 hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 border-0 text-xs h-7"
               >
                 分享
               </Button>
             </Tooltip>
           </div>
        </div>
      </div>
    </div>
  );
};

export default ChatHeader;
