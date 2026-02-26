'use client';

import UnifiedChatInput from '@/components/chat/input/unified-chat-input';
import { ChatContentContext } from '@/contexts';
import { IChatDialogueMessageSchema } from '@/types/chat';
import { cloneDeep } from 'lodash';
import React, { memo, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { v4 as uuid } from 'uuid';
import ChatHeader from '../header/chat-header';
import ChatContent from './chat-content';

interface BasicChatContentProps {
  ctrl: AbortController;
}

const BasicChatContent: React.FC<BasicChatContentProps> = ({ ctrl }) => {
  const scrollableRef = useRef<HTMLDivElement>(null);
  const { history, replyLoading } = useContext(ChatContentContext);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [jsonValue, setJsonValue] = useState<string>('');

  const showMessages = useMemo(() => {
    const tempMessage: IChatDialogueMessageSchema[] = cloneDeep(history);
    return tempMessage
      .filter(item => ['view', 'human'].includes(item.role))
      .map(item => ({
        ...item,
        key: uuid(),
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
    <div className="flex flex-col h-full bg-[#FAFAFA] dark:bg-[#111]">
      {/* 标题栏 */}
      <ChatHeader isProcessing={isProcessing} />
      
      {/* 消息列表区域 */}
      <div 
        ref={scrollableRef}
        className="flex-1 overflow-y-auto"
      >
        {hasMessages && (
          <div className="w-full px-4 sm:px-6 lg:px-8 py-6">
            <div className="max-w-3xl mx-auto">
              {showMessages.map((content, index) => (
                <div key={index} className="mb-6">
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
              {/* 底部留白 */}
              <div className="h-20" />
            </div>
          </div>
        )}
      </div>

      {/* 输入框区域 - 居中且限制宽度 */}
      <div className="flex-shrink-0 pb-6 pt-2 px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mx-auto">
          <UnifiedChatInput ctrl={ctrl} showFloatingActions={hasMessages} />
        </div>
      </div>
    </div>
  );
};

export default memo(BasicChatContent);
