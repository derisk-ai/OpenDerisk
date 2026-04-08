'use client';

import ChatContent from './chat-content';
import { ChatContentContext } from '@/contexts';
import { IChatDialogueMessageSchema } from '@/types/chat';
import { cloneDeep } from 'lodash';
import React, { memo, useContext, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import ChatHeader from '../header/chat-header';
import UnifiedChatInput from '../input/unified-chat-input';
import { Tooltip } from 'antd';
import { LeftOutlined, DesktopOutlined } from '@ant-design/icons';
import classNames from 'classnames';
import { ee, EVENTS } from '@/utils/event-emitter';
import markdownComponents, { markdownPlugins } from '@/components/chat/chat-content-components/config';
import { GPTVis } from '@antv/gpt-vis';

interface ManusChatContentProps {
  ctrl: AbortController;
}

/**
 * Extract running_window data from chat history
 * Same pattern as useDetailPanel in chat-detail-content.tsx
 */
function useManusRunningWindow(chatList: any[]): {
  runningWindow: string;
  hasData: boolean;
} {
  const [runningWindow, setRunningWindow] = useState<string>('');

  useEffect(() => {
    if (!Array.isArray(chatList) || chatList.length === 0) {
      setRunningWindow('');
      return;
    }

    // Search from latest message backwards for running_window
    for (let i = chatList.length - 1; i >= 0; i--) {
      const item = chatList[i];
      try {
        if (typeof item.context !== 'string' || !item.context.trim().startsWith('{')) {
          continue;
        }

        const context = JSON.parse(item.context);
        const rw = context.running_window || '';

        if (rw) {
          setRunningWindow(rw);
          return;
        }
      } catch {
        // Skip invalid items
      }
    }

    setRunningWindow('');
  }, [chatList]);

  return {
    runningWindow,
    hasData: !!runningWindow,
  };
}

const ManusChatContent: React.FC<ManusChatContentProps> = ({ ctrl }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { history, replyLoading } = useContext(ChatContentContext);

  const { runningWindow, hasData } = useManusRunningWindow(history);
  const [userClosedPanel, setUserClosedPanel] = useState(false);

  const showMessages = useMemo(() => {
    const tempMessage: IChatDialogueMessageSchema[] = cloneDeep(history);
    return tempMessage
      .filter((item) => ['view', 'human'].includes(item.role))
      .map((item, index) => ({
        ...item,
        key: `${item.role}_${item.order ?? index}`,
      }));
  }, [history]);

  // Listen for panel open/close events
  useEffect(() => {
    const handleClose = () => setUserClosedPanel(true);
    const handleOpen = () => setUserClosedPanel(false);
    ee.on(EVENTS.CLOSE_PANEL, handleClose);
    ee.on(EVENTS.OPEN_PANEL, handleOpen);
    return () => {
      ee.off(EVENTS.CLOSE_PANEL, handleClose);
      ee.off(EVENTS.OPEN_PANEL, handleOpen);
    };
  }, []);

  // Reset userClosedPanel when new data arrives
  const prevRunningWindowRef = useRef(runningWindow);
  useEffect(() => {
    if (prevRunningWindowRef.current !== runningWindow) {
      prevRunningWindowRef.current = runningWindow;
      if (hasData) {
        setUserClosedPanel(false);
      }
    }
  }, [runningWindow, hasData]);

  // Auto-scroll
  useEffect(() => {
    setTimeout(() => {
      scrollRef.current?.scrollTo(0, scrollRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  const hasMessages = showMessages.length > 0;
  const isProcessing = replyLoading || (history.length > 0 && history[history.length - 1]?.thinking);
  const isRightPanelVisible = !userClosedPanel;

  return (
    <div className="flex h-full w-full overflow-hidden bg-slate-50">
      {/* Left Panel - Chat messages (planning_window VIS tags render inline) */}
      <div
        className={classNames(
          'flex flex-col h-full transition-all duration-300 ease-out border-r border-slate-200/60',
          isRightPanelVisible ? 'w-[38%] min-w-[340px]' : 'flex-1'
        )}
      >
        <ChatHeader isProcessing={isProcessing} />

        {/* Chat messages area - manus-left-panel VIS tags render here via ChatContent */}
        <div className="flex-1 overflow-y-auto min-w-0" ref={scrollRef}>
          {hasMessages ? (
            <div className="w-full px-3 py-3">
              <div className="w-full space-y-2">
                {showMessages.map((content) => (
                  <div key={content.key}>
                    <ChatContent content={content} messages={showMessages} />
                  </div>
                ))}
                <div className="h-8" />
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="w-14 h-14 mx-auto mb-3 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                  <span className="text-2xl text-white font-bold">M</span>
                </div>
                <h3 className="text-base font-medium text-slate-700 mb-1">
                  Manus Workspace
                </h3>
                <p className="text-slate-400 text-sm">
                  输入消息开始对话
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Chat input */}
        <div className="flex-shrink-0 pb-3 pt-1 px-3">
          <div className="w-full">
            <UnifiedChatInput ctrl={ctrl} showFloatingActions={hasMessages} />
          </div>
        </div>
      </div>

      {/* Toggle button when right panel is hidden */}
      {userClosedPanel && (
        <div className="fixed right-4 top-1/2 -translate-y-1/2 z-40">
          <Tooltip title="显示工作区" placement="left">
            <button
              onClick={() => setUserClosedPanel(false)}
              className="w-10 h-10 rounded-full bg-white shadow-lg border border-slate-200 flex items-center justify-center hover:bg-slate-50 transition-colors"
            >
              <LeftOutlined className="text-slate-500" />
            </button>
          </Tooltip>
        </div>
      )}

      {/* Right Panel - Workspace (always rendered, shows running_window VIS content) */}
      {isRightPanelVisible && (
        <div
          className={classNames(
            'flex flex-col transition-all duration-300 ease-out',
            'w-[62%] min-w-[480px] h-full p-2 pl-0'
          )}
        >
          <ManusRightPanelContainer runningWindow={runningWindow} />
        </div>
      )}
    </div>
  );
};

/**
 * Right panel container - renders running_window content via GPTVis
 * Same pattern as ChatDetailContent for vis_window3
 */
const ManusRightPanelContainer: React.FC<{ runningWindow: string }> = memo(({ runningWindow }) => {
  const { appInfo } = useContext(ChatContentContext);
  const handleClose = useCallback(() => {
    ee.emit(EVENTS.CLOSE_PANEL);
  }, []);

  const headerTitle = useMemo(() => {
    const name = appInfo?.app_name;
    return name ? `${name}的电脑` : 'OpenDerisk Computer';
  }, [appInfo?.app_name]);

  return (
    <div className="flex flex-col h-full bg-white rounded-xl overflow-hidden border border-gray-200/80">
      {/* macOS-style header bar */}
      <div className="flex items-center px-4 py-2.5 bg-[#f8f8fa] border-b border-gray-200/60">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <div
              className="w-3 h-3 rounded-full bg-[#ff5f57] cursor-pointer hover:brightness-90 transition-all"
              onClick={handleClose}
            />
            <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
            <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          </div>
          <div className="flex items-center gap-1.5 ml-2 text-[13px] text-gray-600">
            <DesktopOutlined className="text-gray-400 text-xs" />
            <span>{headerTitle}</span>
          </div>
        </div>
      </div>

      {/* Content area - render running_window VIS tags via GPTVis */}
      <div className="flex-1 overflow-hidden">
        {runningWindow ? (
          <div className="h-full [&>div]:h-full [&>div>div]:h-full">
            <GPTVis
              components={markdownComponents}
              {...markdownPlugins}
            >
              {runningWindow}
            </GPTVis>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="w-16 h-16 rounded-2xl bg-gray-50 flex items-center justify-center mb-4">
              <DesktopOutlined className="text-3xl text-gray-300" />
            </div>
            <div className="text-sm font-medium text-gray-400 mb-1">Workspace</div>
            <div className="text-xs text-gray-300">
              等待执行...
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

ManusRightPanelContainer.displayName = 'ManusRightPanelContainer';

export default memo(ManusChatContent);
