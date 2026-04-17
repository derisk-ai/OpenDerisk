'use client';

import UnifiedChatInput from '@/components/chat/input/unified-chat-input';
import { ChatContentContext } from '@/contexts';
import { IChatDialogueMessageSchema } from '@/types/chat';
import React, { memo, useContext, useEffect, useMemo, useRef, useState } from 'react';
import ChatHeader from '../header/chat-header';
import ChatContent from './chat-content';
import { WarningOutlined } from '@ant-design/icons';

interface BasicChatContentProps {
  ctrl: AbortController;
}

// Data size limits to prevent browser crash
const MAX_HISTORY_COUNT = 500;        // Maximum number of messages to render
const MAX_CONTEXT_SIZE = 10_000_000; // Maximum characters per message context (10MB)
const MAX_TOTAL_SIZE = 50_000_000;   // Maximum total context size for all messages (50MB)

/**
 * Check if conversation data is too large to safely render
 */
const isDataTooLarge = (messages: IChatDialogueMessageSchema[]): boolean => {
  if (messages.length > MAX_HISTORY_COUNT) return true;
  // Check total size
  const totalSize = messages.reduce((sum, m) => sum + (m.context && typeof m.context === 'string' ? m.context.length : 0), 0);
  if (totalSize > MAX_TOTAL_SIZE) return true;
  // Check individual message context size
  for (const msg of messages) {
    if (msg.context && typeof msg.context === 'string' && msg.context.length > MAX_CONTEXT_SIZE) {
      return true;
    }
  }
  return false;
};

const BasicChatContent: React.FC<BasicChatContentProps> = ({ ctrl }) => {
  const scrollableRef = useRef<HTMLDivElement>(null);
  const { history, replyLoading } = useContext(ChatContentContext);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [jsonValue, setJsonValue] = useState<string>('');

  // Check if data is too large
  const dataTooLarge = useMemo(() => isDataTooLarge(history), [history]);

  // Use shallow copy instead of cloneDeep to avoid memory issues
  const showMessages = useMemo(() => {
    if (dataTooLarge) return []; // Don't process if too large
    return history
      .filter(item => ['view', 'human'].includes(item.role))
      .map((item, index) => ({
        ...item,
        key: `${item.role}_${item.order ?? index}`,
      }));
  }, [history, dataTooLarge]);

  useEffect(() => {
    setTimeout(() => {
      scrollableRef.current?.scrollTo(0, scrollableRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  const hasMessages = showMessages.length > 0;
  const isProcessing = replyLoading || (history.length > 0 && history[history.length - 1]?.thinking);

  // Show warning if data is too large
  if (dataTooLarge) {
    return (
      <div className="flex flex-col h-full bg-[#FAFAFA] dark:bg-[#111] overflow-hidden">
        <ChatHeader isProcessing={false} />
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <WarningOutlined className="text-4xl text-orange-500 mb-4" />
          <h3 className="text-lg font-medium text-gray-700 dark:text-gray-300 mb-2">
            会话数据过大
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 text-center max-w-md">
            当前会话包含 {history.length} 条消息，数据量过大可能导致浏览器崩溃。
            为保护系统稳定性，已暂停渲染此会话。
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            建议导出会话记录查看历史内容，或联系管理员处理
          </p>
        </div>
        <div className="flex-shrink-0 pt-2 pb-2 px-3">
          <div className="w-full">
            <UnifiedChatInput ctrl={ctrl} showFloatingActions={false} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#FAFAFA] dark:bg-[#111] overflow-hidden">
      {/* 标题栏 */}
      <ChatHeader isProcessing={isProcessing} />

      <div
        ref={scrollableRef}
        className="flex-1 overflow-y-auto min-h-0"
      >
        {hasMessages && (
          <div className="w-full px-3 py-4">
            <div className="w-full">
              {showMessages.map((content) => (
                <div key={content.key} className="mb-4">
                  <ChatContent
                    content={content}
                    onLinkClick={() => {
                      setJsonModalOpen(true);
                      setJsonValue(JSON.stringify(content?.context, null, 2));
                    }}
                    messages={showMessages}
                  />
                </div>
              ))}
              <div className="h-8" />
            </div>
          </div>
        )}
      </div>

      <div className="flex-shrink-0 pt-2 pb-2 px-3">
        <div className="w-full">
          <UnifiedChatInput ctrl={ctrl} showFloatingActions={hasMessages} />
        </div>
      </div>
    </div>
  );
};

export default memo(BasicChatContent);
