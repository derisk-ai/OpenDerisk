'use client';

import UnifiedChatInput from '@/components/chat/input/unified-chat-input';
import { ChatContentContext } from '@/contexts';
import { IChatDialogueMessageSchema } from '@/types/chat';
import React, { memo, useContext, useEffect, useMemo, useRef, useState } from 'react';
import ChatHeader from '../header/chat-header';
import ChatContent from './chat-content';
import { TaskCreatedCard, TaskCreatedCardPayload } from '../task-created-card';

interface BasicChatContentProps {
  ctrl: AbortController;
}

const MAX_RENDER_COUNT = 200;
const MAX_CONTEXT_SIZE = 10_000_000;

const isMessageTooLarge = (msg: IChatDialogueMessageSchema): boolean => {
  return !!(msg.context && typeof msg.context === 'string' && msg.context.length > MAX_CONTEXT_SIZE);
};

function getTaskCreatedPayload(item: IChatDialogueMessageSchema): TaskCreatedCardPayload | null {
  if (item.role !== 'view') return null;
  try {
    const ctx = typeof item.context === 'string' ? JSON.parse(item.context) : item.context;
    if (ctx && ctx.type === 'task_created') {
      return ctx.payload as TaskCreatedCardPayload;
    }
  } catch {
    // ignore
  }
  return null;
}

const BasicChatContent: React.FC<BasicChatContentProps> = ({ ctrl }) => {
  const scrollableRef = useRef<HTMLDivElement>(null);
  const { history, replyLoading } = useContext(ChatContentContext);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [jsonValue, setJsonValue] = useState<string>('');

  const showMessages = useMemo(() => {
    const filtered = history
      .filter(item => ['view', 'human'].includes(item.role) && !isMessageTooLarge(item));
    const windowed = filtered.length > MAX_RENDER_COUNT
      ? filtered.slice(-MAX_RENDER_COUNT)
      : filtered;
    return windowed.map((item, index) => ({
      ...item,
      key: `${item.role}_${item.order ?? index}`,
    }));
  }, [history]);

  useEffect(() => {
    setTimeout(() => {
      scrollableRef.current?.scrollTo(0, scrollableRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  const hasMessages = showMessages.length > 0;
  const isProcessing = replyLoading || (history.length > 0 && history[history.length - 1]?.thinking);

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
              {showMessages.map((content) => {
                const taskPayload = getTaskCreatedPayload(content);
                if (taskPayload) {
                  return (
                    <div key={content.key} className="mb-4">
                      <TaskCreatedCard
                        payload={taskPayload}
                        onViewTask={(taskId) => {
                          window.dispatchEvent(new CustomEvent('workspace:view-task', { detail: { taskId } }));
                        }}
                      />
                    </div>
                  );
                }
                return (
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
                );
              })}
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
