import ChatInputPanel from '@/components/chat/input/chat-input-panel';
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
  const {
    history,
    isDebug,
    isShowDetail,
  } = useContext(ChatContentContext);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [jsonValue, setJsonValue] = useState<string>('');

  const showMessages = useMemo(() => {
    const tempMessage: IChatDialogueMessageSchema[] = cloneDeep(history);
    return tempMessage
      .filter(item => ['view', 'human'].includes(item.role))
      .map(item => {
        return {
          ...item,
          key: uuid(),
        };
      });
  }, [history]);

  useEffect(() => {
    setTimeout(() => {
      scrollableRef.current?.scrollTo(0, scrollableRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  console.log('Rendering content3...', ctrl);

  return (
    <div className="flex flex-1 h-full">
    <div
      className={`${isDebug ? 'bg-[transparent]' : 'bg-white'} dark:bg-[rgba(255,255,255,0.16)] flex flex-1 flex-col p-2 items-center relative`}
      ref={scrollableRef}
    >
      <div className={`flex flex-col flex-1 ${isShowDetail ? 'w-3/5' : 'w-full'} h-full`}>
        <div className='flex-1 overflow-y-scroll'>
          <ChatHeader isScrollToTop={true} />
          {!!showMessages.length &&
            showMessages.map((content, index) => {
              return (
                <ChatContent
                  key={index}
                  content={content}
                  onLinkClick={() => {
                    setJsonModalOpen(true);
                    setJsonValue(JSON.stringify(content?.context, null, 2));
                  }}
                  messages={showMessages}
                />
              );
            })}
        </div>

        <div className='w-full flex justify-center'>
          <div className='w-full'>
            <ChatInputPanel ctrl={ctrl} />
          </div>
        </div>
      </div>
    </div>
    </div>
  );
};

export default memo(BasicChatContent);
