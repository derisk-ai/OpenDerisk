'use client';

import {
  apiInterceptors, listTriggers, getWorkspaceInfo, deleteTrigger, fireTrigger,
} from '@/client/api';
import { Button, Modal, Spin, message } from 'antd';
import { PlusOutlined, ThunderboltOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import Table from 'antd/es/table';
import '../../workspaces.css';

interface TriggerRow {
  id: number;
  workspace_id: number;
  name: string;
  type: string;
  target_playbook_id: number;
  is_active: boolean;
  last_fired_at?: string;
  gmt_modified?: string;
}

const TYPE_VARIANT: Record<string, string> = {
  timer: 'info',
  webhook: 'purple',
  alert: 'attention',
  manual: 'neutral',
};

export default function TriggerListPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: triggers, loading, refresh } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listTriggers({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const handleFire = async (item: TriggerRow) => {
    const [err, res] = await apiInterceptors(fireTrigger({
      workspace_id: item.workspace_id,
      trigger_id: item.id,
      payload: {},
    }));
    if (err) { message.error(err.message); return; }
    message.success(`${t('triggers.fired') || 'Fired'} — Task #${res?.task_id}`);
    refresh();
  };

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: t('triggers.delete_confirm') || 'Delete trigger source?',
      okText: t('delete') || 'Delete',
      okButtonProps: { danger: true },
      cancelText: t('cancel') || 'Cancel',
      onOk: async () => {
        const [err] = await apiInterceptors(deleteTrigger(id));
        if (err) { message.error(err.message); return; }
        message.success(t('triggers.deleted') || 'Deleted');
        refresh();
      },
    });
  };

  const columns: ColumnsType<TriggerRow> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 70,
      render: (v: number) => <span className="ws-table-id">#{v}</span>,
    },
    {
      title: t('triggers.name') || 'Name',
      dataIndex: 'name',
      render: (v: string, r: TriggerRow) => (
        <Link href={`/workspaces/detail/triggers/create?id=${workspaceCode}&trigger_id=${r.id}`} className="ws-table-link">
          {v}
        </Link>
      ),
    },
    {
      title: t('triggers.type') || 'Type',
      dataIndex: 'type',
      width: 120,
      render: (v: string) => (
        <span className={`ws-chip ws-chip--${TYPE_VARIANT[v] || 'outline'} ws-chip--mono`}>{v}</span>
      ),
    },
    {
      title: t('triggers.target_playbook') || 'Playbook',
      dataIndex: 'target_playbook_id',
      width: 120,
      render: (v: number) => <span className="ws-chip ws-chip--mono">#{v}</span>,
    },
    {
      title: t('triggers.active') || 'Active',
      dataIndex: 'is_active',
      width: 100,
      render: (v: boolean) => (
        <span className={`ws-status ws-status--${v ? 'success' : 'neutral'}`}>
          <span className="ws-status-dot" />
          {v ? 'active' : 'paused'}
        </span>
      ),
    },
    {
      title: t('triggers.last_fired') || 'Last Fired',
      dataIndex: 'last_fired_at',
      width: 180,
      render: (v?: string) => v ? <span className="ws-table-time">{new Date(v).toLocaleString()}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>never</span>,
    },
    {
      title: '',
      key: 'actions',
      width: 200,
      render: (_: unknown, r: TriggerRow) => (
        <div style={{ display: 'flex', gap: 6 }}>
          <Button size="small" type="primary" ghost icon={<ThunderboltOutlined />} onClick={() => handleFire(r)}>
            {t('triggers.fire') || 'Fire'}
          </Button>
          <Link href={`/workspaces/detail/triggers/create?id=${workspaceCode}&trigger_id=${r.id}`}>
            <Button size="small">{t('edit') || 'Edit'}</Button>
          </Link>
          <Button size="small" danger onClick={() => handleDelete(r.id)}>{t('delete') || 'Delete'}</Button>
        </div>
      ),
    },
  ];

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content">
        <div className="ws-page-header">
          <div className="ws-page-header-left">
            <div className="ws-page-icon"><ThunderboltOutlined /></div>
            <div>
              <div className="ws-page-eyebrow">
                {t('workspaces.triggers') || 'Triggers'}
                {(triggers || []).filter((tr: TriggerRow) => tr.is_active).length > 0 && (
                  <span className="ws-page-eyebrow-code">{(triggers || []).filter((tr: TriggerRow) => tr.is_active).length} active</span>
                )}
              </div>
              <h1 className="ws-page-title">{t('triggers.title') || 'Trigger Sources'}</h1>
              <p className="ws-page-subtitle">
                {t('triggers.subtitle') || 'Timer, webhook, and alert sources that spawn tasks automatically.'}
              </p>
            </div>
          </div>
          <div className="ws-page-actions">
            <Link href={`/workspaces/detail?id=${workspaceCode}`}>
              <Button icon={<ArrowLeftOutlined />}>{t('back') || 'Back'}</Button>
            </Link>
            <Link href={`/workspaces/detail/triggers/create?id=${workspaceCode}`}>
              <Button type="primary" icon={<PlusOutlined />}>{t('triggers.create') || 'New Trigger'}</Button>
            </Link>
          </div>
        </div>

        <div className="ws-table-wrap">
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}><Spin /></div>
          ) : (
            <Table<TriggerRow>
              rowKey="id"
              columns={columns}
              dataSource={triggers || []}
              pagination={{ pageSize: 20, showSizeChanger: true }}
              locale={{ emptyText: <span style={{ color: 'var(--ws-ink-3)', padding: '48px 0', display: 'inline-block' }}>{t('triggers.empty') || 'No trigger sources'}</span> }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
