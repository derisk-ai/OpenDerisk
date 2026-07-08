'use client';

import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Alert, Button, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ChatSession from '@/components/chat/chat-session';
import { ChatContentContext } from '@/contexts';
import type { UserChatContent } from '@/types/chat';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { PlaybookItem } from './agent-types';
import { AgentChatInput, AgentChatInputHandle } from './agent-chat-input';

interface SceneAgentChatProps {
  convUid?: string;
  appCode?: string;
  workspaceId?: number | string;
  taskId?: number | string;
  playbooks?: PlaybookItem[];
  onWorkspaceEvent?: (event: WorkspaceEvent) => void;
  onPlaybookCommand?: (playbook: PlaybookItem, text: string) => void;
  switchingTask?: boolean;
  convLoadError?: string | null;
  retryLoadConv?: () => void;
}

function AgentChatInputSlot({
  convUid,
  playbooks,
  onPlaybookCommand,
  switchingTask,
}: {
  convUid?: string;
  playbooks?: PlaybookItem[];
  onPlaybookCommand?: (playbook: PlaybookItem, text: string) => void;
  switchingTask?: boolean;
}) {
  const { handleChat, replyLoading } = useContext(ChatContentContext);
  const [lastInput, setLastInput] = useState<UserChatContent | null>(null);
  const [lastModel, setLastModel] = useState<string | null>(null);
  const inputRef = useRef<AgentChatInputHandle>(null);

  useEffect(() => {
    setLastInput(null);
    setLastModel(null);
  }, [convUid]);

  const handleSend = useCallback(
    (payload: { text: string; resources: Record<string, unknown>[]; model?: string }) => {
      if (!handleChat) return;
      const { text, resources, model } = payload;
      let content: UserChatContent = text;
      if (resources && resources.length > 0) {
        const items = [...resources];
        if (text.trim()) {
          items.push({ type: 'text', text: text.trim() });
        }
        content = { role: 'user', content: items as { type: string; [key: string]: unknown }[] };
      }
      setLastInput(content);
      setLastModel(model || null);
      handleChat(content, model ? { model_name: model } : undefined);
    },
    [handleChat]
  );

  const handleRetry = useCallback(() => {
    if (!handleChat || !lastInput) return;
    handleChat(lastInput, lastModel ? { model_name: lastModel } : undefined);
  }, [handleChat, lastInput, lastModel]);

  return (
    <AgentChatInput
      ref={inputRef}
      onSend={handleSend}
      loading={replyLoading}
      disabled={!convUid || switchingTask}
      lastInput={typeof lastInput === 'string' ? lastInput : null}
      onRetry={lastInput ? handleRetry : undefined}
      convUid={convUid}
      playbooks={playbooks}
      onPlaybookCommand={onPlaybookCommand}
    />
  );
}

export function SceneAgentChat({
  convUid,
  appCode,
  workspaceId,
  taskId,
  playbooks,
  onWorkspaceEvent,
  onPlaybookCommand,
  switchingTask,
  convLoadError,
  retryLoadConv,
}: SceneAgentChatProps) {
  return (
    <div className="ws-agent-workspace">
      <div className="ws-agent-workspace__process">
        {switchingTask ? (
          <div className="ws-agent-workspace__loading">
            <Spin tip="切换任务对话中..." />
          </div>
        ) : convLoadError && !convUid ? (
          <div className="ws-agent-workspace__error-card">
            <Alert
              message="会话加载失败"
              description={convLoadError}
              type="error"
              showIcon
              action={
                retryLoadConv ? (
                  <Button size="small" icon={<ReloadOutlined />} onClick={retryLoadConv}>重试</Button>
                ) : undefined
              }
            />
          </div>
        ) : !convUid ? (
          <div className="ws-agent-workspace__loading"><Spin /></div>
        ) : (
          <ChatSession
            convUid={convUid}
            appCode={appCode}
            workspaceId={workspaceId}
            taskId={taskId}
            minimal
            hideRightPanel
            forceVisRender="vis_manus"
            onWorkspaceEvent={onWorkspaceEvent}
            inputSlot={() => (
              <div className="px-3 pb-3">
                <AgentChatInputSlot
                  convUid={convUid}
                  playbooks={playbooks}
                  onPlaybookCommand={onPlaybookCommand}
                  switchingTask={switchingTask}
                />
              </div>
            )}
          />
        )}
      </div>
    </div>
  );
}
