'use client';

import { useEffect, useRef } from 'react';
import { Alert, Button, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep } from './agent-types';
import { AgentWorkspaceInput } from './agent-workspace-input';
import { AgentWorkspaceRenderer } from './agent-workspace-renderer';
import type { AgentWorkspaceInputHandle } from './agent-workspace-types';
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
  playbooks?: { playbook_id: number; playbook_name: string }[];
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
  playbooks,
}: AgentWorkspaceProps) {
  const inputRef = useRef<AgentWorkspaceInputHandle>(null);
  const { steps, workspaceView, loading, error, lastInput, send, clearSteps, clearWorkspaceView } = useSceneAgentChat({
    convUid,
    appCode,
    workspaceId,
    taskId,
    onWorkspaceEvent,
  });

  useEffect(() => {
    clearSteps();
    clearWorkspaceView();
  }, [convUid, clearSteps, clearWorkspaceView]);

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
          <AgentWorkspaceRenderer
            view={workspaceView}
            onStepClick={onStepClick ? (s) => onStepClick({
              id: s.id,
              type: 'unknown',
              title: s.title,
              status: s.status === 'running' ? 'running' : s.status === 'failed' ? 'failed' : 'done',
              timestamp: Date.now(),
              payload: { action: s.action },
            }) : undefined}
          />
        )}
      </div>
      <div className="ws-agent-workspace__input">
        <AgentWorkspaceInput
          ref={inputRef}
          convUid={convUid}
          onSend={(p) => send(p)}
          loading={loading}
          disabled={!convUid || switchingTask}
          lastInput={lastInput ? { text: typeof lastInput.text === 'string' ? lastInput.text : '' } : null}
          onRetry={lastInput ? () => send(lastInput) : undefined}
          playbooks={playbooks}
        />
      </div>
    </div>
  );
}