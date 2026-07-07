'use client';

import './scene-workspace.css';
import { useEffect, useState } from 'react';
import { apiInterceptors, getTaskInfo } from '@/client/api';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep, DetailContext } from './agent-types';
import { AgentWorkspace } from './agent-workspace';
import { SceneSpace } from './scene-space';
import { SceneTaskRail } from './scene-task-rail';

interface SceneWorkspaceShellProps {
  workspace: any;
  tasks: any[];
  interventions: any[];
  workspaceConvUid: string;
  appCode: string;
}

export function SceneWorkspaceShell({
  workspace,
  tasks,
  interventions,
  workspaceConvUid,
  appCode,
}: SceneWorkspaceShellProps) {
  const workspaceId = workspace?.id;
  const [previewItem, setPreviewItem] = useState<any>(null);
  const [detailContext, setDetailContext] = useState<DetailContext>('dashboard');
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null);
  const [taskConvUid, setTaskConvUid] = useState<string>('');
  const [focusAgentInput, setFocusAgentInput] = useState(false);

  useEffect(() => {
    if (!activeTaskId) {
      setTaskConvUid('');
      return;
    }
    let cancelled = false;
    apiInterceptors(getTaskInfo(activeTaskId)).then(([, res]) => {
      if (!cancelled) setTaskConvUid(res?.conv_session_id || '');
    });
    return () => {
      cancelled = true;
    };
  }, [activeTaskId]);

  const handlePreview = (item: any, kind: 'task' | 'intervention') => {
    setPreviewItem(item);
    setDetailContext(kind === 'task' ? 'task-detail' : 'entity-card');
  };

  const handleEnterConversation = (taskId: number) => {
    setActiveTaskId(taskId);
    const task = tasks.find((t) => t.id === taskId);
    if (task) {
      setPreviewItem(task);
      setDetailContext('task-detail');
    }
  };

  const handleBackToDashboard = () => {
    setDetailContext('dashboard');
    setPreviewItem(null);
  };

  const handleStepClick = (step: AgentStep) => {
    if (step.type === 'tool_call') {
      setPreviewItem(step);
      setDetailContext('tool-result');
    } else if (step.payload?.file_id || step.payload?.file_name) {
      setPreviewItem(step);
      setDetailContext('file-preview');
    } else if (step.payload?.task_id || step.payload?.asset_id) {
      setPreviewItem(step);
      setDetailContext('entity-card');
    }
  };

  const handleWorkspaceEvent = (event: WorkspaceEvent) => {
    if (event.type === 'artifact_produced' && event.payload?.file_id) {
      setPreviewItem(event);
      setDetailContext('file-preview');
    }
  };

  const rightConvUid = activeTaskId ? taskConvUid : workspaceConvUid;
  const rightTaskId = activeTaskId ? activeTaskId : undefined;

  return (
    <div className="ws-scene-shell">
      <div className="ws-scene-shell__rail">
        <SceneTaskRail
          tasks={tasks}
          interventions={interventions}
          activeTaskId={activeTaskId}
          onPreview={handlePreview}
          onEnterConversation={handleEnterConversation}
        />
      </div>
      <div className="ws-scene-shell__space">
        <SceneSpace
          context={detailContext}
          previewItem={previewItem}
          workspaceId={workspaceId}
          workspaceCode={workspace?.workspace_code}
          onBack={handleBackToDashboard}
          onFocusAgentInput={() => setFocusAgentInput(true)}
          onSelectTask={(taskId) => {
            const task = tasks.find((t) => t.id === taskId);
            if (task) handlePreview(task, 'task');
          }}
        />
      </div>
      <div className="ws-scene-shell__agent">
        {activeTaskId && (
          <div className="ws-scene-shell__agent-mode">
            <span>任务对话: {activeTaskId}</span>
            <button onClick={() => setActiveTaskId(null)}>退出任务对话</button>
          </div>
        )}
        <AgentWorkspace
          convUid={rightConvUid}
          appCode={appCode}
          workspaceId={workspaceId}
          taskId={rightTaskId}
          autoFocus={focusAgentInput}
          onFocusHandled={() => setFocusAgentInput(false)}
          onStepClick={handleStepClick}
          onWorkspaceEvent={handleWorkspaceEvent}
        />
      </div>
    </div>
  );
}
