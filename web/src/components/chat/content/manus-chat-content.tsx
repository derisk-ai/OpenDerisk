'use client';

import ChatContent from './chat-content';
import { ChatContentContext } from '@/contexts';
import { IChatDialogueMessageSchema } from '@/types/chat';
import { cloneDeep } from 'lodash';
import React, { memo, useContext, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import ChatHeader from '../header/chat-header';
import UnifiedChatInput from '../input/unified-chat-input';
import { Tooltip } from 'antd';
import { LeftOutlined, DesktopOutlined, FileTextOutlined, FolderOpenOutlined } from '@ant-design/icons';
import classNames from 'classnames';
import { ee, EVENTS } from '@/utils/event-emitter';
import markdownComponents, { markdownPlugins } from '@/components/chat/chat-content-components/config';
import { GPTVis } from '@antv/gpt-vis';
import type { ManusDeliverableFile } from '@/types/manus';
import { useSearchParams } from 'next/navigation';

type ShareMode = 'conversation' | 'process' | 'report' | null;

interface ManusChatContentProps {
  ctrl: AbortController;
}

/** Per-message deliverable info */
interface MessageDeliverableInfo {
  runningWindow: string;
  deliverableFiles: Pick<ManusDeliverableFile, 'file_id' | 'file_name'>[];
  hasTaskFiles: boolean;
}

/**
 * Extract running_window + deliverable files for EACH view message.
 * Returns a map keyed by message key, plus the latest running_window for the right panel default.
 */
function usePerMessageDeliverables(
  showMessages: Array<IChatDialogueMessageSchema & { key: string }>
): {
  deliverablesMap: Map<string, MessageDeliverableInfo>;
  latestRunningWindow: string;
  latestHasData: boolean;
} {
  return useMemo(() => {
    const map = new Map<string, MessageDeliverableInfo>();
    let latestRunningWindow = '';

    for (const msg of showMessages) {
      if (msg.role !== 'view') continue;
      try {
        if (typeof msg.context !== 'string' || !msg.context.trim().startsWith('{')) continue;
        const context = JSON.parse(msg.context);
        const rw = context.running_window || '';
        if (!rw) continue;

        // Track latest running_window
        latestRunningWindow = rw;

        // Parse manus-right-panel VIS tag for deliverable/task files
        const match = rw.match(/```manus-right-panel\s*\n([\s\S]*?)\n```/);
        if (!match) continue;

        const data = JSON.parse(match[1]);
        const deliverableFiles = (data.deliverable_files || []).map((f: any) => ({
          file_id: f.file_id,
          file_name: f.file_name,
        }));
        const hasTaskFiles = (data.task_files || []).length > 0;

        if (deliverableFiles.length > 0 || hasTaskFiles) {
          map.set(msg.key, { runningWindow: rw, deliverableFiles, hasTaskFiles });
        }
      } catch {
        // Skip parse errors
      }
    }

    return {
      deliverablesMap: map,
      latestRunningWindow,
      latestHasData: !!latestRunningWindow,
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
  // Tracks which round's running_window to show in right panel (null = follow latest)
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

  const { deliverablesMap, latestRunningWindow, latestHasData } = usePerMessageDeliverables(showMessages);

  // The running window shown in right panel: user override or latest
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

  // When new streaming data arrives, reset override to follow latest
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

  // Handler: click deliverable from any round → switch right panel to that round
  const handleDeliverableClick = useCallback((runningWindow: string, fileId: string) => {
    setOverrideRunningWindow(runningWindow);
    setTimeout(() => {
      ee.emit(EVENTS.SWITCH_TAB, { tab: `deliverable_${fileId}` });
      ee.emit(EVENTS.OPEN_PANEL);
    }, 50);
  }, []);

  // Handler: click task files from any round
  const handleTaskFilesClick = useCallback((runningWindow: string) => {
    setOverrideRunningWindow(runningWindow);
    setTimeout(() => {
      ee.emit(EVENTS.SWITCH_TAB, { tab: 'task_files' });
      ee.emit(EVENTS.OPEN_PANEL);
    }, 50);
  }, []);

  return (
    <div className="flex h-full w-full overflow-hidden" style={{ background: 'linear-gradient(160deg, #fdfcfb 0%, #fbfaf8 40%, #faf9f6 100%)' }}>
      {/* ═══ Left panel — conversation on gray canvas ═══ */}
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
                  {showMessages.map((content) => {
                    const deliverableInfo = deliverablesMap.get(content.key);
                    const isViewMsg = content.role === 'view';

                    return (
                      <div key={content.key}>
                        <ChatContent content={content} messages={showMessages} />
                        {isViewMsg && deliverableInfo && (
                          <div className="flex flex-wrap gap-3 mt-4 ml-11">
                            {deliverableInfo.deliverableFiles.map((f) => (
                              <button
                                key={f.file_id}
                                className="flex items-center gap-4 px-5 py-4 rounded-xl bg-white/90 border border-gray-200/70 hover:border-blue-300 hover:bg-white cursor-pointer transition-all text-left group shadow-sm min-w-[200px]"
                                onClick={() => handleDeliverableClick(deliverableInfo.runningWindow, f.file_id)}
                              >
                                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                                  <DesktopOutlined className="text-blue-500 text-lg" />
                                </div>
                                <div className="flex flex-col min-w-0">
                                  <span className="text-[14px] font-medium text-gray-800 truncate max-w-[200px] group-hover:text-blue-600 transition-colors">{f.file_name}</span>
                                  <span className="text-[12px] text-gray-400 mt-0.5">网页报告</span>
                                </div>
                              </button>
                            ))}
                            {deliverableInfo.hasTaskFiles && (
                              <button
                                className="flex items-center gap-4 px-5 py-4 rounded-xl bg-white/90 border border-gray-200/70 hover:border-amber-300 hover:bg-white cursor-pointer transition-all text-left group shadow-sm min-w-[240px]"
                                onClick={() => handleTaskFilesClick(deliverableInfo.runningWindow)}
                              >
                                <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center flex-shrink-0">
                                  <FolderOpenOutlined className="text-amber-500 text-lg" />
                                </div>
                                <div className="flex flex-col">
                                  <span className="text-[14px] font-medium text-gray-800 group-hover:text-amber-600 transition-colors">查看此任务中的所有文件</span>
                                </div>
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
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

      {/* ═══ Right panel — floating white card on shared gray canvas ═══ */}
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
