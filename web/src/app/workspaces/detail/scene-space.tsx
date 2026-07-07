'use client';

import { Button, Card, Spin, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { apiInterceptors, getTaskInfo, listArtifacts } from '@/client/api';
import { Lobby } from './lobby';
import type { DetailContext } from './agent-types';

export interface SceneSpaceProps {
  context: DetailContext;
  previewItem?: any;
  workspaceId: number;
  workspaceCode: string;
  onBack: () => void;
  onFocusAgentInput?: () => void;
  onSelectTask?: (taskId: number) => void;
}

export function SceneSpace({
  context,
  previewItem,
  workspaceId,
  workspaceCode,
  onBack,
  onFocusAgentInput,
  onSelectTask,
}: SceneSpaceProps) {
  const taskId = context === 'task-detail' && previewItem?.id ? previewItem.id : undefined;

  const { data: taskRes, loading: taskLoading } = useRequest(
    async () => (taskId ? apiInterceptors(getTaskInfo(taskId)) : null),
    { refreshDeps: [taskId] }
  );
  const task = taskRes?.[1];

  const { data: artifactsRes } = useRequest(
    async () => (taskId ? apiInterceptors(listArtifacts({ task_id: taskId })) : null),
    { refreshDeps: [taskId] }
  );
  const artifacts = artifactsRes?.[1] || [];

  if (context === 'dashboard') {
    return (
      <div className="ws-scene-space ws-scene-space--dashboard">
        <Lobby
          workspaceId={workspaceId}
          workspaceCode={workspaceCode}
          onSelectTask={onSelectTask || (() => {})}
          onSendFirstMessage={onFocusAgentInput || (() => {})}
        />
      </div>
    );
  }

  return (
    <div className="ws-scene-space">
      <div className="ws-scene-space__header">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack} size="small">
          返回 dashboard
        </Button>
      </div>
      {context === 'task-detail' && (
        <div className="ws-scene-space__body">
          {taskLoading && <Spin />}
          {!taskLoading && task && (
            <Card title={task.title || `Task ${task.id}`}>
              <p><Tag>{task.status}</Tag></p>
              <p>触发源: {task.triggered_by || '—'}</p>
              <p>创建时间: {task.created_at || '—'}</p>
              <p>更新时间: {task.updated_at || '—'}</p>
              {artifacts.length > 0 && (
                <div>
                  <strong>交付物:</strong>
                  {artifacts.map((a: any) => (
                    <div key={a.id}>{a.title || `artifact_${a.id}`} <Tag>{a.type}</Tag></div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
      {context === 'file-preview' && (
        <div className="ws-scene-space__body">
          <Card title="文件预览">
            <pre>{JSON.stringify(previewItem?.payload || previewItem, null, 2)}</pre>
          </Card>
        </div>
      )}
      {context === 'tool-result' && (
        <div className="ws-scene-space__body">
          <Card title="工具结果">
            <pre>{JSON.stringify(previewItem?.payload || previewItem, null, 2)}</pre>
          </Card>
        </div>
      )}
      {context === 'entity-card' && (
        <div className="ws-scene-space__body">
          <Card title="实体信息">
            <pre>{JSON.stringify(previewItem?.payload || previewItem, null, 2)}</pre>
          </Card>
        </div>
      )}
    </div>
  );
}