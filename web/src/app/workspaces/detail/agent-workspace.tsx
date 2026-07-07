'use client';

import { useEffect, useRef } from 'react';
import { Alert, Button, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep } from './agent-types';
import { AgentChatInput, AgentChatInputHandle } from './agent-chat-input';
import { AgentProcessPanel } from './agent-process-panel';
import { useSceneAgentChat } from './use-scene-agent-chat';

export interface AgentWorkspaceProps {
  convUid?: string;
  appCode?: string;
  workspaceId?: number | string;
  taskId?: number | string;
  autoFocus?: boolean;
  onFocusHandled?: () => void;
  onStepClick?: (step: AgentStep) => void;
  onWorkspaceEvent?: (event: WorkspaceEvent) => void;
  switchingTask?: boolean;
  convLoadError?: string | null;
  retryLoadConv?: () => void;
}

export function AgentWorkspace({
  convUid,
  appCode,
  workspaceId,
  taskId,
  autoFocus,
  onFocusHandled,
  onStepClick,
  onWorkspaceEvent,
  switchingTask,
  convLoadError,
  retryLoadConv,
}: AgentWorkspaceProps) {
  const inputRef = useRef<AgentChatInputHandle>(null);
  const { steps, loading, error, lastInput, send, clearSteps } = useSceneAgentChat({
    convUid,
    appCode,
    workspaceId,
    taskId,
    onWorkspaceEvent,
  });

  useEffect(() => {
    clearSteps();
  }, [convUid, clearSteps]);

  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus();
      onFocusHandled?.();
    }
  }, [autoFocus, onFocusHandled]);

  return (
    <div className="ws-agent-workspace">
      <div className="ws-agent-workspace__process">
        {error && <Alert message={error} type="error" showIcon className="ws-agent-workspace__error" />}
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
          <AgentProcessPanel steps={steps} loading={loading} onStepClick={onStepClick} />
        )}
      </div>
      <div className="ws-agent-workspace__input">
        <AgentChatInput
          ref={inputRef}
          onSend={send}
          loading={loading}
          disabled={!convUid || switchingTask}
          lastInput={lastInput}
          onRetry={lastInput ? () => send(lastInput) : undefined}
        />
      </div>
    </div>
  );
}
