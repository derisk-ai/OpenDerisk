'use client';

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  InboxOutlined, 
  CloseOutlined, 
  LoadingOutlined,
  ThunderboltOutlined,
  MessageOutlined
} from '@ant-design/icons';
import { Button, Tooltip, Badge } from 'antd';

interface QueuedMessage {
  id: string;
  content: string;
  sender: string;
  timestamp: number;
}

interface InputQueueDisplayProps {
  messages: QueuedMessage[];
  isLoading?: boolean;
  onClear?: () => void;
  maxPreviewLength?: number;
}

const InputQueueDisplay: React.FC<InputQueueDisplayProps> = ({
  messages,
  isLoading = false,
  onClear,
  maxPreviewLength = 60,
}) => {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [pulseCount, setPulseCount] = useState(messages.length);

  useEffect(() => {
    if (messages.length > pulseCount) {
      setPulseCount(messages.length);
    }
  }, [messages.length, pulseCount]);

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const truncateContent = (content: string) => {
    if (content.length <= maxPreviewLength) return content;
    return content.substring(0, maxPreviewLength) + '...';
  };

  if (messages.length === 0 && !isLoading) {
    return null;
  }

  return (
    <div className="w-full mb-3">
      {/* Header with badge and controls */}
      <div 
        className={`
          flex items-center justify-between px-4 py-2.5 
          bg-gradient-to-r from-blue-50/80 to-indigo-50/80 
          dark:from-blue-900/20 dark:to-indigo-900/20
          border border-blue-100 dark:border-blue-800/50
          rounded-t-xl cursor-pointer
          hover:from-blue-50 hover:to-indigo-50
          dark:hover:from-blue-900/30 dark:hover:to-indigo-900/30
          transition-all duration-200
          ${isExpanded ? 'rounded-b-none' : 'rounded-b-xl'}
        `}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className="relative">
            <Badge 
              count={messages.length} 
              size="small"
              style={{ 
                backgroundColor: '#3b82f6',
                fontSize: '10px',
                minWidth: '16px',
                height: '16px',
                lineHeight: '16px'
              }}
            >
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <InboxOutlined className="text-blue-600 dark:text-blue-400 text-sm" />
              </div>
            </Badge>
            {messages.length > pulseCount - 1 && (
              <div
                className="absolute inset-0 rounded-full bg-blue-400/30"
              />
            )}
          </div>
          
          <div className="flex flex-col">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
              {t('input_queue_title') || 'Input Queue'}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {t('input_queue_count', { count: messages.length }) || `${messages.length} messages waiting`}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isLoading && (
            <Tooltip title="Thinking...">
              <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50">
                <LoadingOutlined className="text-amber-500 text-xs" />
                <span className="text-xs text-amber-600 dark:text-amber-400">
                  Thinking...
                </span>
              </div>
            </Tooltip>
          )}
          
          {messages.length > 0 && onClear && (
            <Tooltip title="Clear queue">
              <Button
                type="text"
                size="small"
                icon={<CloseOutlined className="text-gray-400 hover:text-red-500 transition-colors" />}
                onClick={(e) => {
                  e.stopPropagation();
                  onClear();
                }}
                className="flex items-center justify-center w-7 h-7"
              />
            </Tooltip>
          )}
          
          <div
            className={`text-gray-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M2.5 4.5L6 8L9.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
        </div>
      </div>

      {/* Expanded message list */}
      {isExpanded && messages.length > 0 && (
        <div className="overflow-hidden">
          <div className="bg-white/50 dark:bg-gray-900/30 border-x border-b border-blue-100 dark:border-blue-800/50 rounded-b-xl max-h-48 overflow-y-auto">
            {messages.map((msg, index) => (
              <div
                key={msg.id}
                className={`
                  flex items-start gap-3 px-4 py-3 
                  ${index !== messages.length - 1 ? 'border-b border-gray-100 dark:border-gray-800' : ''}
                  hover:bg-blue-50/50 dark:hover:bg-blue-900/10 transition-colors
                `}
              >
                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <MessageOutlined className="text-white text-xs" />
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                      {msg.sender}
                    </span>
                    <span className="text-[10px] text-gray-400 dark:text-gray-500">
                      {formatTime(msg.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed break-words">
                    {truncateContent(msg.content)}
                  </p>
                </div>

                <div className="flex-shrink-0">
                  <Tooltip title="Queued">
                    <div className="w-6 h-6 rounded-md bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                      <ThunderboltOutlined className="text-amber-500 text-xs" />
                    </div>
                  </Tooltip>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state when expanded */}
      {isExpanded && messages.length === 0 && (
        <div className="bg-white/50 dark:bg-gray-900/30 border-x border-b border-blue-100 dark:border-blue-800/50 rounded-b-xl px-4 py-6 text-center">
          <InboxOutlined className="text-3xl text-gray-300 dark:text-gray-600 mb-2" />
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('input_queue_empty') || 'Queue is empty'}
          </p>
        </div>
      )}
    </div>
  );
};

export default InputQueueDisplay;