'use client';

import { Button, Card, Tag } from 'antd';
import { useRequest } from 'ahooks';
import {
  apiInterceptors,
  listTasks,
  listArtifacts,
  listDeliveries,
  listPlaybooks,
} from '@/client/api';
import { GrowthCard } from './growth-card';
import './lobby.css';

export interface LobbyProps {
  workspaceId: number;
  onSelectTask: (taskId: number) => void;
  onQuickStart: (playbookId: number) => void;
}

export function Lobby({ workspaceId, onSelectTask, onQuickStart }: LobbyProps) {
  const { data: tasksRes } = useRequest(
    async () => apiInterceptors(listTasks({ workspace_id: workspaceId, status: 'running' })),
    { refreshDeps: [workspaceId] },
  );
  const tasks = tasksRes?.[1];

  const { data: deliveriesRes } = useRequest(
    async () => apiInterceptors(listDeliveries({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const deliveries = deliveriesRes?.[1];

  const { data: artifactsRes } = useRequest(
    async () => apiInterceptors(listArtifacts({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const artifacts = artifactsRes?.[1];

  const { data: playbooksRes } = useRequest(
    async () => apiInterceptors(listPlaybooks({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const playbooks = playbooksRes?.[1];

  const runningTasks = (tasks || []).slice(0, 5);
  const recentDeliveries = (deliveries || []).slice(0, 3);
  const hostedArtifacts = (artifacts || [])
    .filter((a: any) => a.hosting_status === 'running')
    .slice(0, 4);

  return (
    <div className="ws-lobby">
      <div className="ws-lobby__main">
        {/* 进行中任务 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>进行中任务 ({runningTasks.length})</h3>
          </div>
          <div className="ws-lobby__task-list">
            {runningTasks.length === 0 && <div className="ws-empty">暂无进行中任务</div>}
            {runningTasks.map((t: any) => (
              <Card
                key={t.id}
                size="small"
                className="ws-lobby__task-card"
                hoverable
                onClick={() => onSelectTask(t.id)}
              >
                <div className="ws-lobby__task-title">{t.title}</div>
                <div className="ws-lobby__task-meta">
                  <Tag color="blue">{t.status}</Tag>
                  <span>{t.triggered_by}</span>
                </div>
              </Card>
            ))}
          </div>
        </section>

        {/* 栖居的交付物 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>栖居的交付物 ({hostedArtifacts.length})</h3>
          </div>
          <div className="ws-lobby__hosted-grid">
            {hostedArtifacts.length === 0 && (
              <div className="ws-empty">P8 上线后这里展示托管运行的交付物</div>
            )}
            {hostedArtifacts.map((a: any) => (
              <Card key={a.id} size="small" className="ws-lobby__hosted-card">
                <div>{a.title}</div>
                <Tag color="green">running</Tag>
                <Button size="small" type="link">打开</Button>
              </Card>
            ))}
          </div>
        </section>

        {/* 最近交付 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>最近交付 ({recentDeliveries.length})</h3>
          </div>
          <div className="ws-lobby__delivery-list">
            {recentDeliveries.map((d: any) => (
              <div key={d.id} className="ws-lobby__delivery-item">
                <Tag>{d.category}</Tag>
                <span>{d.channel}</span>
                <span className="ws-lobby__delivery-status">{d.status}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 快捷发起 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>快捷发起</h3>
          </div>
          <div className="ws-lobby__quick">
            {(playbooks || []).slice(0, 4).map((p: any) => (
              <Button key={p.id} onClick={() => onQuickStart(p.id)}>
                + {p.name}
              </Button>
            ))}
            <Button type="dashed">+ 自定义</Button>
          </div>
        </section>
      </div>

      {/* 侧栏：成长卡 */}
      <aside className="ws-lobby__rail">
        <GrowthCard workspaceId={workspaceId} />
      </aside>
    </div>
  );
}
