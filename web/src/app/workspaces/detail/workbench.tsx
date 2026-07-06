'use client';

import { useState, useMemo, useCallback } from 'react';
import { Button, Tag, Card } from 'antd';
import { useRequest } from 'ahooks';
import {
  apiInterceptors,
  getTaskInfo,
  listInterventions,
  listArtifacts,
} from '@/client/api';
import ChatSession from '@/components/chat/chat-session';
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
        <section className="ws-wb__section">
          <h3 className="ws-wb__section-title">📊 进展</h3>
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
        </section>

        {/* 交付物 */}
        <section className="ws-wb__section">
          <h3 className="ws-wb__section-title">📦 交付物</h3>
          {artifacts && artifacts.length > 0 ? (
            <div className="ws-wb__artifact-grid">
              {artifacts.map((a: any) => (
                <Card key={a.id} size="small" className="ws-wb__artifact-card">
                  <div className="ws-wb__artifact-title">{a.title || `artifact_${a.id}`}</div>
                  <Tag>{a.type}</Tag>
                  <div className="ws-wb__artifact-actions">
                    <Button size="small">预览</Button>
                    <Button size="small">发送</Button>
                    <Button size="small">沉淀为 Asset</Button>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <div className="ws-empty">暂无交付物</div>
          )}
        </section>

        {/* 协作对话（折叠） */}
        <section className="ws-wb__section">
          <h3
            className="ws-wb__section-title ws-wb__section-title--clickable"
            onClick={() => setDialogExpanded(!dialogExpanded)}
          >
            💬 协作对话 {dialogExpanded ? '收起' : '展开'}
          </h3>
          {dialogExpanded && (
            <div className="ws-wb__dialog">
              <ChatSession
                convUid={convUid}
                appCode={appCode}
                workspaceId={String(workspaceId)}
                taskId={String(taskId)}
                hideRightPanel={true}
                onWorkspaceEvent={handleWorkspaceEvent}
              />
            </div>
          )}
        </section>

        {/* 执行轨迹 */}
        <section className="ws-wb__section">
          <h3 className="ws-wb__section-title">📜 执行轨迹</h3>
          <div className="ws-wb__trace">
            <div className="ws-wb__trace-item">
              AgentRun · {task?.status} · {task?.updated_at || '—'}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
