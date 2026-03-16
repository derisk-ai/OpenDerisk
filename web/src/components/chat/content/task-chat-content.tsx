'use client';

import ChatContent from "./chat-content";
import { ChatContentContext } from "@/contexts";
import { IChatDialogueMessageSchema } from "@/types/chat";
import { cloneDeep } from "lodash";
import React, { memo, useContext, useEffect, useMemo, useRef, useState } from "react";
import { v4 as uuid } from "uuid";
import { useDetailPanel } from "./chat-detail-content";
import ChatDetailContent from "./chat-detail-content";
import ChatHeader from "../header/chat-header";
import UnifiedChatInput from "../input/unified-chat-input";
import { Button, Tooltip } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import classNames from 'classnames';
import { ee, EVENTS } from '@/utils/event-emitter';

interface TaskChatContentProps {
  ctrl: AbortController;
}

const TaskChatContent: React.FC<TaskChatContentProps> = ({ ctrl }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { history, replyLoading } = useContext(ChatContentContext);

  const { runningWindowData } = useDetailPanel(history);
  const [isRunningWindowVisible, setIsRunningWindowVisible] = useState(false);
  const [userClosedPanel, setUserClosedPanel] = useState(false);

  const showMessages = useMemo(() => {
    const tempMessage: IChatDialogueMessageSchema[] = cloneDeep(history);
    return tempMessage
      .filter((item) => ["view", "human"].includes(item.role))
      .map((item) => ({
        ...item,
        key: uuid(),
      }));
  }, [history]);

  const hasRunningWindowData = useMemo(() => {
    return !!(runningWindowData?.running_window || 
              (runningWindowData?.items && runningWindowData.items.length > 0));
  }, [runningWindowData]);

  // 监听关闭事件
  useEffect(() => {
    const handleClose = () => {
      setUserClosedPanel(true);
      setIsRunningWindowVisible(false);
    };
    const handleOpen = () => {
      setUserClosedPanel(false);
      setIsRunningWindowVisible(true);
    };
    ee.on(EVENTS.CLOSE_PANEL, handleClose);
    ee.on(EVENTS.OPEN_PANEL, handleOpen);
    return () => {
      ee.off(EVENTS.CLOSE_PANEL, handleClose);
      ee.off(EVENTS.OPEN_PANEL, handleOpen);
    };
  }, []);

  // 当有新的 running window 数据时自动显示（仅当用户没有手动关闭时）
  useEffect(() => {
    if (hasRunningWindowData && !isRunningWindowVisible && !userClosedPanel) {
      setIsRunningWindowVisible(true);
    }
  }, [hasRunningWindowData, isRunningWindowVisible, userClosedPanel]);

  // 当数据变化时重置 userClosedPanel
  const prevDataRef = useRef(runningWindowData);
  useEffect(() => {
    // 检查数据是否真正变化了
    if (JSON.stringify(prevDataRef.current) !== JSON.stringify(runningWindowData)) {
      prevDataRef.current = runningWindowData;
      if (hasRunningWindowData) {
        setUserClosedPanel(false);
        setIsRunningWindowVisible(true);
      }
    }
  }, [runningWindowData, hasRunningWindowData]);

  useEffect(() => {
    setTimeout(() => {
      scrollRef.current?.scrollTo(0, scrollRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  const hasMessages = showMessages.length > 0;
  const isProcessing = replyLoading || (history.length > 0 && history[history.length - 1]?.thinking);

  return (
    <div className="flex h-full w-full overflow-hidden bg-gradient-to-br from-slate-100 to-slate-50">
      {/* Planning Window */}
      <div className={classNames(
        "flex flex-col h-full transition-all duration-300 ease-out",
        isRunningWindowVisible && hasRunningWindowData ? "w-[38%] min-w-[340px]" : "flex-1"
      )}>
        <ChatHeader isProcessing={isProcessing} />
        
        <div className="flex-1 overflow-y-auto" ref={scrollRef}>
          {hasMessages ? (
            <div className="w-full px-3 py-3">
              <div className="w-full space-y-2">
                {showMessages.map((content, index) => (
                  <div key={index}>
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
                  <span className="text-2xl">✨</span>
                </div>
                <h3 className="text-base font-medium text-slate-700 mb-1">
                  开始新的对话
                </h3>
                <p className="text-slate-400 text-sm">
                  输入消息开始与应用对话
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="flex-shrink-0 pb-3 pt-1 px-3">
          <div className="w-full">
            <UnifiedChatInput ctrl={ctrl} showFloatingActions={hasMessages} />
          </div>
        </div>
      </div>

      {/* 显示 Running Window 的按钮 */}
      {hasRunningWindowData && !isRunningWindowVisible && (
        <div className="fixed right-4 top-1/2 -translate-y-1/2 z-40">
          <Tooltip title="显示工作区" placement="left">
            <Button
              type="default"
              shape="circle"
              size="large"
              icon={<RightOutlined />}
              onClick={() => {
                setUserClosedPanel(false);
                setIsRunningWindowVisible(true);
              }}
              className="shadow-lg border-slate-200 bg-white/95 hover:bg-slate-50"
            />
          </Tooltip>
        </div>
      )}

      {/* Running Window 面板 */}
      {isRunningWindowVisible && hasRunningWindowData && (
        <div 
          className={classNames(
            "flex flex-col bg-white border-l border-slate-200 transition-all duration-300 ease-out",
            "w-[62%] min-w-[480px] h-full"
          )}
        >
          <div className="h-full w-full overflow-hidden">
            <ChatDetailContent data={runningWindowData} />
          </div>
        </div>
      )}
    </div>
  );
};

export default memo(TaskChatContent);