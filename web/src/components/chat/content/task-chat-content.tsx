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
import { 
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RightOutlined
} from '@ant-design/icons';
import classNames from 'classnames';

interface TaskChatContentProps {
  ctrl: AbortController;
}

const TaskChatContent: React.FC<TaskChatContentProps> = ({ ctrl }) => {
  const scrollableRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { history, isDebug, replyLoading } = useContext(ChatContentContext);

  const { runningWindowData } = useDetailPanel(history);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [jsonValue, setJsonValue] = useState<string>("");
  const [isRunningWindowVisible, setIsRunningWindowVisible] = useState(false);
  const [isRunningWindowCollapsed, setIsRunningWindowCollapsed] = useState(false);

  const showMessages = useMemo(() => {
    const tempMessage: IChatDialogueMessageSchema[] = cloneDeep(history);
    return tempMessage
      .filter((item) => ["view", "human"].includes(item.role))
      .map((item) => ({
        ...item,
        key: uuid(),
      }));
  }, [history]);

  // 检查是否有 running window 数据
  const hasRunningWindowData = useMemo(() => {
    return !!(runningWindowData?.running_window || 
              (runningWindowData?.items && runningWindowData.items.length > 0));
  }, [runningWindowData]);

  // 当有 running window 数据时自动显示
  useEffect(() => {
    if (hasRunningWindowData && !isRunningWindowVisible) {
      setIsRunningWindowVisible(true);
    }
  }, [hasRunningWindowData, isRunningWindowVisible]);

  useEffect(() => {
    setTimeout(() => {
      scrollableRef.current?.scrollTo(0, scrollableRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  const hasMessages = showMessages.length > 0;
  const isProcessing = replyLoading || (history.length > 0 && history[history.length - 1]?.thinking);

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* 主内容区域 */}
      <div className={classNames(
        "flex flex-col h-full transition-all duration-500 ease-in-out",
        isDebug ? 'bg-transparent' : 'bg-[#FAFAFA] dark:bg-[#111]',
        isRunningWindowVisible && !isRunningWindowCollapsed
          ? "w-[45%] min-w-[45%]" 
          : "flex-1"
      )}>
        {/* 头部 */}
        <ChatHeader isProcessing={isProcessing} />
        
        {/* 消息列表 */}
        <div 
          className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-8"
          ref={scrollRef}
        >
          {hasMessages ? (
            <div className="w-full py-6 pb-4">
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
                <div className="h-20" />
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-xl shadow-indigo-500/20">
                  <span className="text-4xl">✨</span>
                </div>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  开始新的对话
                </h3>
                <p className="text-gray-500 dark:text-gray-400">
                  输入消息开始与应用对话
                </p>
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

      {/* Running Window 切换按钮 */}
      {hasRunningWindowData && (
        <div className="fixed right-4 top-1/2 -translate-y-1/2 z-40">
          {!isRunningWindowVisible ? (
            <Tooltip title="显示 Running Window" placement="left">
              <Button
                type="primary"
                shape="circle"
                icon={<RightOutlined />}
                onClick={() => setIsRunningWindowVisible(true)}
                className="shadow-lg bg-indigo-500 hover:bg-indigo-600 border-0"
              />
            </Tooltip>
          ) : isRunningWindowCollapsed ? (
            <Tooltip title="展开 Running Window" placement="left">
              <Button
                type="primary"
                shape="circle"
                icon={<MenuUnfoldOutlined />}
                onClick={() => setIsRunningWindowCollapsed(false)}
                className="shadow-lg bg-indigo-500 hover:bg-indigo-600 border-0"
              />
            </Tooltip>
          ) : null}
        </div>
      )}

      {/* Running Window 面板 - 无标题栏，无边框分割 */}
      {isRunningWindowVisible && hasRunningWindowData && (
        <div 
          id="running-window"
          className={classNames(
            "flex flex-col bg-[#FAFAFA] dark:bg-[#111] transition-all duration-500 ease-in-out z-30 overflow-auto",
            isRunningWindowCollapsed 
              ? "w-0 opacity-0 overflow-hidden" 
              : "w-[55%] min-w-[55%]"
          )}
        >
          {/* 内容区域 - 直接渲染，无标题栏 */}
          <div className="flex-1 p-5">
            <ChatDetailContent data={runningWindowData} />
          </div>
        </div>
      )}
    </div>
  );
};

export default memo(TaskChatContent);
