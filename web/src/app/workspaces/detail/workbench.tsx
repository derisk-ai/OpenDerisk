'use client';

import { useState, useMemo, useCallback } from 'react';
import { Button, Tag } from 'antd';
import { useRequest } from 'ahooks';
import {
  apiInterceptors,
  getTaskInfo,
  listInterventions,
  listArtifacts,
} from '@/client/api';
import ChatSession from '@/components/chat/chat-session';
import UnifiedChatInput from '@/components/chat/input/unified-chat-input';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import './workbench.css';

export interface WorkbenchProps {
  taskId: number;
  workspaceId: number;
  appCode: string;
  convUid: string;
  onBack: () => void;
}

export function Workbench({
  taskId,
  workspaceId,
  appCode,
  convUid,
  onBack,
}: WorkbenchProps) {
  const [dialogExpanded, setDialogExpanded] = useState(false);
  const [events, setEvents] = useState<WorkspaceEvent[]>([]);

  const { data: taskRes } = useRequest(
    async () => apiInterceptors(getTaskInfo(taskId)),
    { refreshDeps: [taskId] }
  );
  const task = taskRes?.[1];

  const { data: artifactsRes } = useRequest(
    async () => apiInterceptors(listArtifacts({ task_id: taskId })),
    { refreshDeps: [taskId] }
  );
  const artifacts = artifactsRes?.[1];

  const { data: interventionsRes } = useRequest(
    async () => apiInterceptors(listInterventions({ task_id: taskId })),
    { refreshDeps: [taskId] }
  );
  const interventions = interventionsRes?.[1];

  const handleWorkspaceEvent = useCallback((event: WorkspaceEvent) => {
    setEvents((prev) => [...prev, event]);
  }, []);

  const progressSteps = useMemo(() => {
    // 从 events 推导进展步骤（context_loaded → 后续 tool 调用）
    // P0 简化版：基于 task.status + events 渲染
    const steps: Array<{
      name: string;
      tool?: string;
      status: 'done' | 'running' | 'pending';
    }> = [];
    const ctxEvent = events.find((e) => e.type === 'context_loaded');
    if (ctxEvent) {
      steps.push({
        name: '上下文加载',
        tool: `${ctxEvent.payload.materialized_count} 项资源`,
        status: 'done',
      });
    }
    if (task?.status === 'running' || task?.status === 'awaiting_human') {
      steps.push({ name: 'Agent 执行中', status: 'running' });
    }
    if (task?.status === 'delivered' || task?.status === 'closed') {
      steps.push({ name: '交付完成', status: 'done' });
    }
    return steps;
  }, [events, task]);

  const dialogMessages = useMemo(() => {
    // P0 简化版：从 events 取 asset_referenced / artifact_produced 等
    return events.filter(
      (e) => e.type === 'asset_referenced' || e.type === 'artifact_produced'
    );
  }, [events]);

  return (
    <div className="ws-wb">
      <div className="ws-wb__header">
        <span className="ws-wb__back" onClick={onBack}>← 返回大厅</span>
        <span className="ws-wb__title">{task?.title || `task_${taskId}`}</span>
        {task?.triggered_by && (
          <span className="ws-wb__meta">{task.triggered_by}</span>
        )}
      </div>

      <div className="ws-wb__body">
        {/* 进展 */}
        <div className="ws-wb__section">
          <div className="ws-wb__section-title">进展</div>
          <div className="ws-wb__progress">
            {progressSteps.length === 0 && (
              <div className="ws-wb__step ws-wb__step--pending">
                <span className="ws-wb__step-icon">○</span>
                <span className="ws-wb__step-name">等待开始</span>
              </div>
            )}
            {progressSteps.map((step, i) => (
              <div key={i} className={`ws-wb__step ws-wb__step--${step.status}`}>
                <span className="ws-wb__step-icon">
                  {step.status === 'done' ? '✓' : step.status === 'running' ? '◐' : '○'}
                </span>
                <span className="ws-wb__step-name">{step.name}</span>
                {step.tool && <span className="ws-wb__step-tool">{step.tool}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* 交付物 */}
        {artifacts && artifacts.length > 0 && (
          <div className="ws-wb__section">
            <div className="ws-wb__section-title">交付物</div>
            <div className="ws-wb__artifact">
              {artifacts.map((a: any) => (
                <div key={a.id}>
                  <div className="ws-wb__artifact-title">
                    {a.title || `artifact_${a.id}`}
                  </div>
                  <Tag>{a.type}</Tag>
                  <div className="ws-wb__artifact-actions">
                    <Button size="small">预览</Button>
                    <Button size="small">发送</Button>
                    <Button size="small">沉淀为 Asset</Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 协作对话（折叠） */}
        <div className="ws-wb__section">
          <div className="ws-wb__section-title">协作对话</div>
          <div className="ws-wb__dialog">
            {dialogMessages.length === 0 && (
              <div className="ws-wb__dialog-msg">暂无对话</div>
            )}
            {dialogMessages.slice(0, dialogExpanded ? undefined : 3).map((e, i) => (
              <div key={i} className="ws-wb__dialog-msg">
                {e.type === 'artifact_produced' ? 'Agent 产出: ' : 'Agent 引用: '}
                {JSON.stringify(e.payload)}
              </div>
            ))}
            {dialogMessages.length > 3 && (
              <div
                className="ws-wb__dialog-expand"
                onClick={() => setDialogExpanded(!dialogExpanded)}
              >
                {dialogExpanded ? '收起' : `展开完整对话 (${dialogMessages.length})`}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 输入框常驻底部 —— 复用首页标准多模态 Agent 输入框 */}
      <div className="ws-wb__input">
        <ChatSession
          convUid={convUid}
          appCode={appCode}
          workspaceId={String(workspaceId)}
          taskId={String(taskId)}
          hideRightPanel={true}
          onWorkspaceEvent={handleWorkspaceEvent}
          inputSlot={(ctrl) => <UnifiedChatInput ctrl={ctrl} />}
        />
      </div>
    </div>
  );
}
