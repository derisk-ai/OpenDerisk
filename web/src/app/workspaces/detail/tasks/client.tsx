'use client';

import { apiInterceptors, listTasks, getWorkspaceInfo } from '@/client/api';
import { Button, Empty, Spin } from 'antd';
import { PlusOutlined, ThunderboltOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import Table from 'antd/es/table';
import '../../workspaces.css';

interface TaskRow {
  id: number;
  title: string;
  status: string;
  type?: string;
  triggered_by?: string;
  gmt_created?: string;
}

const STATUS_VARIANT: Record<string, string> = {
  draft: 'neutral',
  pending_trigger: 'attention',
  running: 'running',
  awaiting_human: 'attention',
  blocked: 'danger',
  delivered: 'success',
  closed: 'neutral',
  archived: 'neutral',
  failed: 'danger',
};

function statusVariant(s: string) { return STATUS_VARIANT[s] || 'neutral'; }
function statusLabel(s: string) { return (s || '').replace(/_/g, ' '); }

export default function TaskListPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: tasks, loading } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listTasks({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const columns: ColumnsType<TaskRow> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 70,
      render: (v: number) => <span className="ws-table-id">#{v}</span>,
    },
    {
      title: t('tasks.title') || 'Title',
      dataIndex: 'title',
      render: (v: string, r: TaskRow) => (
        <Link href={`/workspaces/detail/tasks/detail?id=${workspaceCode}&task_id=${r.id}`} className="ws-table-link">
          {v}
        </Link>
      ),
    },
    {
      title: t('tasks.status') || 'Status',
      dataIndex: 'status',
      width: 140,
      render: (s: string) => (
        <span className={`ws-status ws-status--${statusVariant(s)}`}>
          <span className="ws-status-dot" />
          {statusLabel(s)}
        </span>
      ),
    },
    {
      title: t('tasks.type') || 'Type',
      dataIndex: 'type',
      width: 120,
      render: (v?: string) => v ? <span className="ws-chip ws-chip--outline">{v}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
    {
      title: t('tasks.triggered_by') || 'Trigger',
      dataIndex: 'triggered_by',
      width: 120,
      render: (v?: string) => v ? <span className="ws-chip ws-chip--mono">{v}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
    {
      title: t('tasks.created') || 'Created',
      dataIndex: 'gmt_created',
      width: 170,
      render: (v?: string) => v ? <span className="ws-table-time">{new Date(v).toLocaleString()}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
  ];

  if (loading) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content" style={{ display: 'flex', justifyContent: 'center', padding: '120px 24px' }}>
          <Spin size="large" />
        </div>
      </div>
    );
  }

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content">
        <div className="ws-page-header">
          <div className="ws-page-header-left">
            <div className="ws-page-icon"><ThunderboltOutlined /></div>
            <div>
              <div className="ws-page-eyebrow">
                {t('workspaces.tasks') || 'Tasks'}
                {(tasks || []).length > 0 && (
                  <span className="ws-page-eyebrow-code">{(tasks || []).length} total</span>
                )}
              </div>
              <h1 className="ws-page-title">{t('tasks.title_page') || 'Tasks'}</h1>
              <p className="ws-page-subtitle">
                {t('tasks.subtitle') || 'Every run of a playbook — manual, triggered, or alert-driven — lands here.'}
              </p>
            </div>
          </div>
          <div className="ws-page-actions">
            <Link href={`/workspaces/detail?id=${workspaceCode}`}>
              <Button icon={<ArrowLeftOutlined />}>{t('back') || 'Back'}</Button>
            </Link>
            <Link href={`/workspaces/detail/tasks/create?id=${workspaceCode}`}>
              <Button type="primary" icon={<PlusOutlined />}>{t('tasks.create') || 'New Task'}</Button>
            </Link>
          </div>
        </div>

        <div className="ws-table-wrap">
          <Table<TaskRow>
            rowKey="id"
            columns={columns}
            dataSource={tasks || []}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            locale={{
              emptyText: <Empty description={t('tasks.empty') || 'No tasks'} style={{ padding: '48px 0' }} />,
            }}
          />
        </div>
      </div>
    </div>
  );
}
