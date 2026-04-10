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
import { useSearchParams } from 'next/navigation';

type ShareMode = 'conversation' | 'process' | 'report' | null;

interface ManusChatContentProps {
  ctrl: AbortController;
}

/**
 * Extract the latest running_window and build routing maps for cross-round switching:
 * - fileRunningWindowMap: deliverable file_id → running_window
 * - stepRunningWindowMap: step UID (from steps_map keys) → running_window
 */
function useRunningWindows(
  showMessages: Array<IChatDialogueMessageSchema & { key: string }>
): {
  latestRunningWindow: string;
  latestHasData: boolean;
  fileRunningWindowMap: Map<string, string>;
  stepRunningWindowMap: Map<string, string>;
} {
  return useMemo(() => {
    let latestRunningWindow = '';
    const fileMap = new Map<string, string>();
    const stepMap = new Map<string, string>();

    for (const msg of showMessages) {
      if (msg.role !== 'view') continue;
      try {
        if (typeof msg.context !== 'string' || !msg.context.trim().startsWith('{')) continue;
        const context = JSON.parse(msg.context);
        const rw = context.running_window || '';
        if (!rw) continue;

        latestRunningWindow = rw;

        // Parse manus-right-panel to index file_ids and step UIDs → this running_window
        const match = rw.match(/```manus-right-panel\s*\n([\s\S]*?)\n```/);
        if (match) {
          try {
            const data = JSON.parse(match[1]);
            // Index deliverable files
            for (const f of data.deliverable_files || []) {
              if (f.file_id) fileMap.set(f.file_id, rw);
            }
            if ((data.task_files || []).length > 0) {
              fileMap.set('task_files', rw);
            }
            // Index step UIDs from steps_map
            if (data.steps_map) {
              for (const uid of Object.keys(data.steps_map)) {
                stepMap.set(uid, rw);
              }
            }
          } catch {
            // skip
          }
        }
      } catch {
        // Skip parse errors
      }
    }

    return {
      latestRunningWindow,
      latestHasData: !!latestRunningWindow,
      fileRunningWindowMap: fileMap,
      stepRunningWindowMap: stepMap,
    };
  }, [showMessages]);
}

const ManusChatContent: React.FC<ManusChatContentProps> = ({ ctrl }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const searchParams = useSearchParams();
  const shareMode = (searchParams?.get('share_mode') as ShareMode) || null;
  const isSharedView = !!shareMode;
  const { history, replyLoading } = useContext(ChatContentContext);
  const [userClosedPanel, setUserClosedPanel] = useState(false);
  const [overrideRunningWindow, setOverrideRunningWindow] = useState<string | null>(null);

  const showMessages = useMemo(() => {
    const tempMessage: IChatDialogueMessageSchema[] = cloneDeep(history);
    return tempMessage
      .filter((item) => ['view', 'human'].includes(item.role))
      .map((item, index) => ({
        ...item,
        key: `${item.role}_${item.order ?? index}`,
      }));
  }, [history]);

  const { latestRunningWindow, latestHasData, fileRunningWindowMap, stepRunningWindowMap } = useRunningWindows(showMessages);

  // The running window shown in right panel: override (from deliverable click) or latest
  const displayRunningWindow = overrideRunningWindow || latestRunningWindow;

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

  // Listen for SWITCH_TAB to route deliverable clicks to the correct round's running_window
  useEffect(() => {
    const handleSwitchTab = (payload: { tab?: string }) => {
      if (!payload?.tab) return;
      const tab = payload.tab;
      // Check if this is a deliverable or task_files tab that needs a running_window switch
      if (tab.startsWith('deliverable_')) {
        const fileId = tab.replace('deliverable_', '');
        const rw = fileRunningWindowMap.get(fileId);
        if (rw && rw !== displayRunningWindow) {
          setOverrideRunningWindow(rw);
        }
      } else if (tab === 'task_files') {
        const rw = fileRunningWindowMap.get('task_files');
        if (rw && rw !== displayRunningWindow) {
          setOverrideRunningWindow(rw);
        }
      }
    };
    ee.on(EVENTS.SWITCH_TAB, handleSwitchTab);
    return () => {
      ee.off(EVENTS.SWITCH_TAB, handleSwitchTab);
    };
  }, [fileRunningWindowMap, displayRunningWindow]);

  // Listen for CLICK_FOLDER to route step clicks to the correct round's running_window
  useEffect(() => {
    const handleClickFolder = (payload: { uid?: string }) => {
      if (!payload?.uid) return;
      const rw = stepRunningWindowMap.get(payload.uid);
      if (rw && rw !== displayRunningWindow) {
        setOverrideRunningWindow(rw);
      }
    };
    ee.on(EVENTS.CLICK_FOLDER, handleClickFolder);
    return () => {
      ee.off(EVENTS.CLICK_FOLDER, handleClickFolder);
    };
  }, [stepRunningWindowMap, displayRunningWindow]);

  // When new streaming data arrives, auto-open panel and reset override
  const prevLatestRef = useRef(latestRunningWindow);
  useEffect(() => {
    if (prevLatestRef.current !== latestRunningWindow) {
      prevLatestRef.current = latestRunningWindow;
      if (replyLoading) {
        setOverrideRunningWindow(null);
      }
      if (latestHasData) {
        setUserClosedPanel(false);
      }
    }
  }, [latestRunningWindow, latestHasData, replyLoading]);

  // Auto-scroll
  useEffect(() => {
    setTimeout(() => {
      scrollRef.current?.scrollTo(0, scrollRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  const hasMessages = showMessages.length > 0;
  const isProcessing = replyLoading || (history.length > 0 && history[history.length - 1]?.thinking);
  // conversation: only left panel (chat-only, read-only)
  // process: both panels (read-only)
  // report: only right panel (deliverable content)
  const isRightPanelVisible = shareMode === 'conversation' ? false
    : shareMode === 'report' ? true
    : !userClosedPanel;
  const showLeftPanel = shareMode !== 'report';
  const showInput = !isSharedView;

  return (
    <div className="flex h-full w-full overflow-hidden" style={{ background: 'linear-gradient(160deg, #fdfcfb 0%, #fbfaf8 40%, #faf9f6 100%)' }}>
      {/* ═══ Left panel — conversation on canvas ═══ */}
      {showLeftPanel && (
        <div className={classNames(
          'flex flex-col h-full transition-all duration-300 ease-out',
          isRightPanelVisible
            ? shareMode === 'report' ? 'hidden' : 'w-[38%] min-w-[340px]'
            : 'flex-1'
        )}>
          {/* Left header */}
          {!isSharedView ? (
            <ChatHeader isProcessing={isProcessing} />
          ) : (
            <div className="px-5 py-3">
              <div className="text-sm text-gray-500">共享对话 · 只读</div>
            </div>
          )}

          {/* Chat messages */}
          <div className="flex-1 overflow-y-auto min-w-0" ref={scrollRef}>
            {hasMessages ? (
              <div className={classNames("w-full px-4 py-4", !isRightPanelVisible && "max-w-3xl mx-auto")}>
                <div className="w-full space-y-3">
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
                  <h3 className="text-base font-medium text-gray-600 mb-1">Manus Workspace</h3>
                  <p className="text-gray-400 text-sm">输入消息开始对话</p>
                </div>
              </div>
            )}
          </div>
          {showInput && (
            <div className={classNames("flex-shrink-0 pb-4 pt-2 px-4", !isRightPanelVisible && "max-w-3xl mx-auto w-full")}>
              <div className="w-full">
                <UnifiedChatInput ctrl={ctrl} showFloatingActions={hasMessages} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══ Right panel — floating white card ═══ */}
      {isRightPanelVisible && (
        <div
          className={classNames(
            'h-full transition-all duration-300 ease-out pt-2 pr-2 pb-2',
            shareMode === 'report' ? 'flex-1 pl-2' : 'w-[62%] min-w-[480px]'
          )}
        >
          <div
            className="flex flex-col h-full bg-white rounded-xl overflow-hidden"
            style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.05)' }}
          >
            <WorkspaceHeader shareMode={shareMode} showLeftPanel={showLeftPanel} />
            <ManusRightPanelContent runningWindow={displayRunningWindow} isProcessing={!!isProcessing} />
          </div>
        </div>
      )}

      {/* Toggle button when right panel is hidden */}
      {!isSharedView && userClosedPanel && (
        <div className="fixed right-4 top-1/2 -translate-y-1/2 z-40">
          <Tooltip title="显示工作区" placement="left">
            <button
              onClick={() => setUserClosedPanel(false)}
              className="w-10 h-10 rounded-full bg-white shadow-lg border border-gray-200 flex items-center justify-center hover:bg-gray-50 transition-colors"
            >
              <LeftOutlined className="text-gray-500" />
            </button>
          </Tooltip>
        </div>
      )}
    </div>
  );
};

/**
 * Workspace header — macOS-style title bar, height-matched with ChatHeader.
 */
const WorkspaceHeader: React.FC<{ shareMode: ShareMode; showLeftPanel: boolean }> = memo(({ shareMode, showLeftPanel }) => {
  const { appInfo } = useContext(ChatContentContext);
  const handleClose = useCallback(() => {
    ee.emit(EVENTS.CLOSE_PANEL);
  }, []);

  const headerTitle = useMemo(() => {
    const name = appInfo?.app_name;
    return name ? `${name}的电脑` : 'OpenDerisk Computer';
  }, [appInfo?.app_name]);

  return (
    <div className="flex items-center px-4 h-10 flex-shrink-0 bg-[#f6f6f6] border-b border-gray-200/50">
      <div className="flex items-center gap-2.5 flex-1">
        <div className="flex items-center gap-1.5">
          <div
            className="w-3 h-3 rounded-full bg-[#ff5f57] cursor-pointer hover:brightness-90 transition-all"
            onClick={handleClose}
          />
          <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
          <div className="w-3 h-3 rounded-full bg-[#28c840]" />
        </div>
      </div>
      <div className="flex items-center gap-1.5 text-[12px] text-gray-500">
        <DesktopOutlined className="text-gray-400 text-[11px]" />
        <span className="font-medium">{headerTitle}</span>
      </div>
      <div className="flex-1" />
    </div>
  );
});
WorkspaceHeader.displayName = 'WorkspaceHeader';

/**
 * Right panel content — just the workspace content, no header (header is in the shared row).
 */
const ManusRightPanelContent: React.FC<{ runningWindow: string; isProcessing: boolean }> = memo(({ runningWindow, isProcessing }) => {
  return (
    <div className="flex-1 overflow-hidden h-full">
      {runningWindow ? (
        <div className="h-full [&>div]:h-full [&>div>div]:h-full [&>div>div>div]:h-full">
          <GPTVis
            components={markdownComponents}
            {...markdownPlugins}
          >
            {runningWindow}
          </GPTVis>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center h-full">
          <div className="relative w-16 h-16 mb-5">
            <div className={classNames(
              'w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-500',
              isProcessing ? 'bg-gradient-to-br from-blue-50 to-indigo-50' : 'bg-gray-50'
            )}>
              <DesktopOutlined className={classNames(
                'text-3xl transition-colors duration-500',
                isProcessing ? 'text-blue-400' : 'text-gray-300'
              )} />
            </div>
            {isProcessing && (
              <div className="absolute inset-0 rounded-2xl border-2 border-blue-200 animate-ping opacity-30" />
            )}
          </div>
          <div className={classNames(
            'text-sm font-medium mb-2 transition-colors duration-500',
            isProcessing ? 'text-gray-700' : 'text-gray-400'
          )}>Workspace</div>
          <div className="flex items-center gap-1.5 h-5">
            {isProcessing ? (
              <>
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:0ms]" />
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:150ms]" />
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:300ms]" />
                <span className="ml-0.5 text-xs text-blue-400">准备中...</span>
              </>
            ) : (
              <span className="text-xs text-gray-300">等待开始</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
});
ManusRightPanelContent.displayName = 'ManusRightPanelContent';

export default memo(ManusChatContent);
