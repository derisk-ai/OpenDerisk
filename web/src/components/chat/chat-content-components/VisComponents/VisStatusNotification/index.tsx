'use client';

import React, { useEffect, useState } from 'react';
import { Alert, Progress, Button } from 'antd';
import {
  CheckCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { VisStatusNotificationWrap } from './style';

export type NotificationLevel = 'info' | 'success' | 'warning' | 'error' | 'progress';

interface VisStatusNotificationProps {
  uid: string;
  type: 'incr' | 'all';
  title: string;
  message: string;
  level?: NotificationLevel;
  progress?: number;
  icon?: string;
  dismissible?: boolean;
  auto_dismiss?: number;
  actions?: Array<{
    label: string;
    action: string;
    [key: string]: any;
  }>;
}

const levelConfig: Record<NotificationLevel, {
  icon: React.ReactNode;
  alertType: 'info' | 'success' | 'warning' | 'error';
  bgClass: string;
}> = {
  info: {
    icon: <InfoCircleOutlined />,
    alertType: 'info',
    bgClass: 'bg-blue-50 dark:bg-blue-900/20',
  },
  success: {
    icon: <CheckCircleOutlined />,
    alertType: 'success',
    bgClass: 'bg-green-50 dark:bg-green-900/20',
  },
  warning: {
    icon: <WarningOutlined />,
    alertType: 'warning',
    bgClass: 'bg-yellow-50 dark:bg-yellow-900/20',
  },
  error: {
    icon: <CloseCircleOutlined />,
    alertType: 'error',
    bgClass: 'bg-red-50 dark:bg-red-900/20',
  },
  progress: {
    icon: <SyncOutlined spin />,
    alertType: 'info',
    bgClass: 'bg-blue-50 dark:bg-blue-900/20',
  },
};

const VisStatusNotification: React.FC<VisStatusNotificationProps> = ({
  title,
  message,
  level = 'info',
  progress,
  dismissible = true,
  auto_dismiss,
  actions,
}) => {
  const [visible, setVisible] = useState(true);
  const config = levelConfig[level];

  useEffect(() => {
    if (auto_dismiss && auto_dismiss > 0) {
      const timer = setTimeout(() => {
        setVisible(false);
      }, auto_dismiss * 1000);
      return () => clearTimeout(timer);
    }
  }, [auto_dismiss]);

  if (!visible) {
    return null;
  }

  return (
    <VisStatusNotificationWrap className={config.bgClass}>
      <div className="flex items-start gap-3 p-4 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="flex-shrink-0 mt-0.5">
          <span className={`text-${config.alertType === 'success' ? 'green' : config.alertType === 'error' ? 'red' : config.alertType === 'warning' ? 'yellow' : 'blue'}-500`}>
            {config.icon}
          </span>
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {title}
            </h4>
            {dismissible && (
              <button
                onClick={() => setVisible(false)}
                className="flex-shrink-0 ml-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                <CloseOutlined className="text-xs" />
              </button>
            )}
          </div>
          
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
            {message}
          </p>
          
          {level === 'progress' && progress !== undefined && (
            <div className="mt-2">
              <Progress 
                percent={Math.round(progress)} 
                size="small" 
                status={progress >= 100 ? 'success' : 'active'}
              />
            </div>
          )}
          
          {actions && actions.length > 0 && (
            <div className="mt-3 flex gap-2">
              {actions.map((action, idx) => (
                <Button
                  key={idx}
                  size="small"
                  type={idx === 0 ? 'primary' : 'default'}
                  onClick={() => {
                    console.log('Action:', action.action);
                  }}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          )}
        </div>
      </div>
    </VisStatusNotificationWrap>
  );
};

export default VisStatusNotification;