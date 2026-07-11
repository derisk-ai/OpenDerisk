'use client';

import './scene-workspace.css';
import { useEffect, useRef, useState } from 'react';
import { Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { apiInterceptors, getTaskInfo, listPlaybooks } from '@/client/api';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep, DetailContext } from './agent-types';
import { AgentWorkspace } from './agent-workspace';
import { SceneSpace } from './scene-space';
import { SceneTaskRail } from './scene-task-rail';

/** 判断当前任务列表里是否有活跃任务(running 等会变化的状态),决定是否开轮询。 */
export function hasActiveTask(tasks: any[]): boolean {
  const active = new Set(['running', 'pending_trigger', 'blocked', 'awaiting_human', 'draft']);
  return (tasks || []).some((t) => active.has(t?.status));
}

interface SceneWorkspaceShellProps {
  workspace: any;
  tasks: any[];
  interventions: any[];
  workspaceConvUid: string;
  appCode: string;
  onRefreshLists?: () => void;
  convLoadError?: string | null;
  retryLoadConv?: () => void;
}

export function SceneWorkspaceShell({
  workspace,
  tasks,
  interventions,
  workspaceConvUid,
  appCode,
  onRefreshLists,
  convLoadError,
  retryLoadConv,
}: SceneWorkspaceShellProps) {
  const workspaceId = workspace?.id;
  const [previewItem, setPreviewItem] = useState<any>(null);
  const [detailContext, setDetailContext] = useState<DetailContext>('dashboard');
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null);
  const [activeTask, setActiveTask] = useState<any>(null);
  const [taskConvUid, setTaskConvUid] = useState<string>('');
  const [focusAgentInput, setFocusAgentInput] = useState(false);
  const [switchingTask, setSwitchingTask] = useState(false);
  const prevActiveTaskId = useRef<number | null>(null);

  const { data: playbooks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [, data] = await apiInterceptors(listPlaybooks({ workspace_id: Number(workspaceId) }));
    return (data || []).map((p: any) => ({ playbook_id: p.id, playbook_name: p.name }));
  }, { refreshDeps: [workspaceId] });

  useEffect(() => {
    if (activeTaskId === prevActiveTaskId.current) return;
    prevActiveTaskId.current = activeTaskId;

    if (!activeTaskId) {
      setTaskConvUid('');
      setActiveTask(null);
      setSwitchingTask(false);
      return;
    }

    setSwitchingTask(true);
    setActiveTask(null);
    let cancelled = false;
    apiInterceptors(getTaskInfo(activeTaskId))
      .then(([, res]) => {
        if (!cancelled) {
          setTaskConvUid(res?.conv_session_id || '');
          setActiveTask(res || null);
          setSwitchingTask(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSwitchingTask(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeTaskId]);

  // 运行时轮询:有活跃任务时每 4s 刷新任务/介入列表,无活跃任务时停。
  // 后台 run_task 的状态变更无法走 workspace 事件流(fire-and-forget,无 SSE 连接),
  // 用轮询替代;task_created 事件触发的 onRefreshLists 仍保留。
  useEffect(() => {
    if (!hasActiveTask(tasks) || !onRefreshLists) return;
    const timer = setInterval(onRefreshLists, 4000);
    return () => clearInterval(timer);
  }, [tasks, onRefreshLists]);

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
    switch (event.type) {
      case 'artifact_produced':
        if (event.payload?.file_id) {
          setPreviewItem(event);
          setDetailContext('file-preview');
        }
        break;
      case 'task_created':
      case 'delivery_sent':
        onRefreshLists?.();
        break;
      case 'asset_referenced':
        setPreviewItem(event);
        setDetailContext('entity-card');
        break;
      case 'intervention_triggered':
        if (event.payload?.task_id) {
          const task = tasks.find((t) => t.id === event.payload.task_id);
          if (task) {
            setPreviewItem(task);
            setDetailContext('task-detail');
          } else {
            setPreviewItem(event);
            setDetailContext('entity-card');
          }
        } else {
          setPreviewItem(event);
          setDetailContext('entity-card');
        }
        break;
      case 'context_loaded':
        // no-op: context was loaded
        break;
      default:
        break;
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
          disabled={switchingTask}
          playbooks={playbooks}
          onPreview={handlePreview}
          onEnterConversation={handleEnterConversation}
        />
      </div>
      <div className="ws-scene-shell__space">
        <SceneSpace
          context={detailContext}
          previewItem={previewItem}
          activeTask={activeTask}
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
            <Button size="small" icon={<CloseOutlined />} onClick={() => setActiveTaskId(null)}>退出任务对话</Button>
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
          switchingTask={switchingTask}
          convLoadError={convLoadError}
          retryLoadConv={retryLoadConv}
          playbooks={playbooks}
        />
      </div>
    </div>
  );
}