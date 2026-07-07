'use client';

import { useEffect, useRef } from 'react';
import { Alert, Spin } from 'antd';
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
}: AgentWorkspaceProps) {
  const inputRef = useRef<AgentChatInputHandle>(null);
  const { steps, loading, error, send, clearSteps } = useSceneAgentChat({
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
        {!convUid ? (
          <div className="ws-agent-workspace__loading"><Spin /></div>
        ) : (
          <AgentProcessPanel steps={steps} loading={loading} onStepClick={onStepClick} />
        )}
      </div>
      <div className="ws-agent-workspace__input">
        <AgentChatInput ref={inputRef} onSend={send} loading={loading} disabled={!convUid} />
      </div>
    </div>
  );
}