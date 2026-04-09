'use client';

import { apiInterceptors, collectApp, unCollectApp } from '@/client/api';
import { AppContext, ChatContentContext } from "@/contexts";
import {
  StarFilled,
  StarOutlined,
  MoreOutlined,
  ShareAltOutlined,
  MessageOutlined,
  FileTextOutlined,
  DesktopOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { message, Dropdown, Tooltip } from 'antd';
import copy from 'copy-to-clipboard';
import React, { useContext, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequest } from 'ahooks';
import AppDefaultIcon from '../../icons/app-default-icon';
import { useSearchParams } from 'next/navigation';
import { useContextMetrics } from '@/contexts/context-metrics-context';
import ContextMetricsDisplay from '../chat-content-components/ContextMetricsDisplay';

interface ChatHeaderProps {
  isScrollToTop?: boolean;
  isProcessing?: boolean;
  /** When true, omit the outer border-b (parent manages the border) */
  noBorder?: boolean;
}

const ChatHeader: React.FC<ChatHeaderProps> = ({ isScrollToTop = false, isProcessing = false }) => {
  const { appInfo, refreshAppInfo, history, setHistory } = useContext(ChatContentContext);
  const { initChatId } = useContext(AppContext);
  const { t } = useTranslation();
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

  const getShareUrl = (mode: string) => {
    const url = new URL(location.href);
    url.searchParams.set('share_mode', mode);
    return url.toString();
  };

  const shareWithMode = (mode: string, label: string) => {
    const url = getShareUrl(mode);
    const success = copy(url);
    message[success ? 'success' : 'error'](
      success ? `${label}链接已复制` : t('copy_failed')
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
      key: 'collect',
      icon: isCollected ? <StarFilled className="text-amber-400" /> : <StarOutlined />,
      label: isCollected ? t('uncollect', '取消收藏') : t('collect', '收藏应用'),
      onClick: () => operate(),
    },
  ];

  const shareMenuItems = [
    {
      key: 'conversation',
      icon: <MessageOutlined />,
      label: '分享对话',
      onClick: () => shareWithMode('conversation', '对话'),
    },
    {
      key: 'process',
      icon: <DesktopOutlined />,
      label: '分享执行过程',
      onClick: () => shareWithMode('process', '执行过程'),
    },
    {
      key: 'report',
      icon: <FileTextOutlined />,
      label: '分享结论报告',
      onClick: () => shareWithMode('report', '结论报告'),
    },
  ];

  const messageCount = history.filter(h => h.role === 'human').length;

  return (
    <div className="w-full flex-shrink-0 flex items-center px-5 py-3">
      {/* App icon — no extra bg, just the image/icon directly */}
      <div className="relative flex-shrink-0 mr-3">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center overflow-hidden">
          {icon && icon !== 'smart-plugin' ? (
            <img src={icon} alt={appInfo?.app_name} className="w-9 h-9 object-cover rounded-xl" />
          ) : icon === 'smart-plugin' ? (
            <img src="/icons/colorful-plugin.png" alt={appInfo?.app_name} className="w-9 h-9 object-cover rounded-xl" />
          ) : (
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <AppDefaultIcon scene={appScene} width={18} height={18} />
            </div>
          )}
        </div>
        {isProcessing && (
          <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5">
            <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-60" />
            <span className="absolute inset-0.5 rounded-full bg-emerald-500" />
          </div>
        )}
      </div>

      {/* App info */}
      <div className="flex flex-col flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold text-gray-700 dark:text-white truncate leading-tight">
            {appInfo?.app_name}
          </span>
          {isCollected && (
            <StarFilled className="text-amber-400 text-[10px] flex-shrink-0" />
          )}
          {appInfo?.team_mode && (
            <span className="text-[10px] px-1.5 py-px rounded bg-gray-500/15 text-gray-600 flex-shrink-0 font-medium">
              {appInfo?.team_mode}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-gray-500 leading-tight">
          {messageCount > 0 && (
            <span>{messageCount} 轮对话</span>
          )}
          {metrics && (
            <ContextMetricsDisplay metrics={metrics} compact />
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <Tooltip title="新会话" placement="bottom">
          <button
            onClick={handleNewChat}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-white/60 transition-all"
          >
            <PlusOutlined style={{ fontSize: 14 }} />
          </button>
        </Tooltip>
        <Dropdown menu={{ items: moreMenuItems }} placement="bottomRight" trigger={['click']}>
          <button className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-white/60 transition-all">
            <MoreOutlined style={{ fontSize: 14 }} />
          </button>
        </Dropdown>
        <Dropdown menu={{ items: shareMenuItems }} placement="bottomRight" trigger={['click']}>
          <button className="h-8 px-3 rounded-lg flex items-center gap-1.5 text-gray-500 hover:text-gray-700 hover:bg-white/60 transition-all text-[12px]">
            <ShareAltOutlined style={{ fontSize: 12 }} />
            <span>分享</span>
          </button>
        </Dropdown>
      </div>
    </div>
  );
};

export default ChatHeader;
