'use client';

import { Button, Card, Tag } from 'antd';

export interface TaskCreatedCardPayload {
  task_id: number;
  title: string;
  status: string;
  playbook_id?: number;
  playbook_name?: string;
  triggered_by?: string;
  workspace_id?: number;
}

export interface TaskCreatedCardProps {
  payload: TaskCreatedCardPayload;
  onViewTask?: (taskId: number) => void;
}

export function TaskCreatedCard({ payload, onViewTask }: TaskCreatedCardProps) {
  return (
    <Card size="small" className="chat-task-created-card" style={{ margin: '12px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 18 }}>🚀</span>
        <strong>{payload.title || `任务 #${payload.task_id}`}</strong>
        <Tag>{payload.status}</Tag>
      </div>
      <div style={{ color: '#666', fontSize: 13, marginBottom: 12 }}>
        {payload.playbook_name && <span>剧本：{payload.playbook_name}</span>}
        {payload.triggered_by && (
          <span style={{ marginLeft: payload.playbook_name ? 12 : 0 }}>
            触发：{payload.triggered_by}
          </span>
        )}
      </div>
      <Button
        type="primary"
        size="small"
        onClick={() => onViewTask?.(payload.task_id)}
      >
        查看任务进展
      </Button>
    </Card>
  );
}
