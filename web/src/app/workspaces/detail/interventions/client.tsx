'use client';

import {
  apiInterceptors, listInterventions, resolveAndExecuteIntervention, abortIntervention,
  getWorkspaceInfo, createAsset,
} from '@/client/api';
import { getUserId } from '@/utils';
import { Button, Form, Input, Modal, message } from 'antd';
import { WarningOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import Table from 'antd/es/table';
import '../../workspaces.css';

const { TextArea } = Input;

interface InterventionRow {
  id: number;
  task_id: number;
  type?: string;
  status: string;
  requested_by?: string;
  question?: any;
  resolved_at?: string;
}

function questionToText(q: any): string {
  if (!q) return '';
  if (typeof q === 'string') return q;
  if (q.question || q.message || q.summary) return q.question || q.message || q.summary;
  try {
    return JSON.stringify(q);
  } catch {
    return '';
  }
}

const STATUS_VARIANT: Record<string, string> = {
  requested: 'attention',
  resolved: 'success',
  aborted: 'neutral',
};

export default function InterventionsPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const taskFilter = searchParams?.get('task_id');
  const { t } = useTranslation();
  const [resolveOpen, setResolveOpen] = useState<InterventionRow | null>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: interventions, loading, refresh } = useRequest(async () => {
    if (!ws?.id) return [];
    const filter: any = { workspace_id: ws.id, limit: 200 };
    if (taskFilter) filter.task_id = Number(taskFilter);
    const [err, res] = await apiInterceptors(listInterventions(filter));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id, taskFilter] });

  const handleResolve = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const [errAsset, assetRes] = await apiInterceptors(createAsset({
        workspace_id: ws?.id,
        type: values.asset_type || 'historical_artifact',
        name: values.asset_name,
        description: values.summary,
        scope: 'workspace',
        content_text: values.summary,
        source_task_id: resolveOpen?.task_id,
        is_published: true,
        created_by: 'reviewer',
      }));
      if (errAsset) {
        setSaving(false);
        message.error(errAsset.message);
        return;
      }
      const assetId = assetRes?.id;
      const userId = getUserId();
      const [err] = await apiInterceptors(resolveAndExecuteIntervention(resolveOpen!.id, {
        decision: { action: 'approved', comment: values.decision },
        distillation: {
          asset_name: values.asset_name,
          summary: values.summary,
          asset_id: assetId,
        },
        linked_asset_id: assetId,
        resolved_by_user_id: userId ? Number(userId) : undefined,
      }));
      setSaving(false);
      if (err) { message.error(err.message); return; }
      message.success(t('interventions.resolved') || 'Executed + Asset created');
      setResolveOpen(null);
      form.resetFields();
      refresh();
    } catch (e) {}
  };

  const handleAbort = async (id: number) => {
    const [err] = await apiInterceptors(abortIntervention(id));
    if (err) { message.error(err.message); return; }
    message.success('Aborted');
    refresh();
  };

  const columns: ColumnsType<InterventionRow> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 70,
      render: (v: number) => <span className="ws-table-id">#{v}</span>,
    },
    {
      title: 'Task',
      dataIndex: 'task_id',
      width: 90,
      render: (v: number) => (
        <Link href={`/workspaces/detail/tasks/detail?id=${workspaceCode}&task_id=${v}`} className="ws-table-link">#{v}</Link>
      ),
    },
    {
      title: t('interventions.type') || 'Type',
      dataIndex: 'type',
      width: 120,
      render: (v?: string) => v ? <span className="ws-chip ws-chip--outline">{v}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
    {
      title: t('interventions.status') || 'Status',
      dataIndex: 'status',
      width: 120,
      render: (s: string) => (
        <span className={`ws-status ws-status--${STATUS_VARIANT[s] || 'neutral'}`}>
          <span className="ws-status-dot" />
          {s}
        </span>
      ),
    },
    {
      title: 'Requested by',
      dataIndex: 'requested_by',
      width: 130,
      render: (v?: string) => v ? <span className="ws-chip ws-chip--mono">{v}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
    {
      title: 'Question',
      render: (_: any, r: InterventionRow) => {
        const text = questionToText(r.question);
        return text
          ? <span className="ws-table-question" title={text}>{text}</span>
          : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>;
      },
    },
    {
      title: '',
      key: 'actions',
      width: 200,
      render: (_: any, r: InterventionRow) => r.status === 'requested' ? (
        <div style={{ display: 'flex', gap: 6 }}>
          <Button size="small" type="primary" onClick={() => { setResolveOpen(r); form.resetFields(); }}>
            {t('interventions.resolve') || 'Resolve'}
          </Button>
          <Button size="small" danger onClick={() => handleAbort(r.id)}>
            {t('interventions.abort') || 'Abort'}
          </Button>
        </div>
      ) : (
        <span className="ws-table-time">{r.resolved_at ? new Date(r.resolved_at).toLocaleString() : '—'}</span>
      ),
    },
  ];

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content">
        <div className="ws-page-header">
          <div className="ws-page-header-left">
            <div className="ws-page-icon"><WarningOutlined /></div>
            <div>
              <div className="ws-page-eyebrow">
                {t('workspaces.interventions') || 'Interventions'}
                {(interventions || []).filter((i: InterventionRow) => i.status === 'requested').length > 0 && (
                  <span className="ws-page-eyebrow-code" style={{ color: 'var(--ws-attention)', background: 'var(--ws-attention-light)' }}>
                    {(interventions || []).filter((i: InterventionRow) => i.status === 'requested').length} pending
                  </span>
                )}
              </div>
              <h1 className="ws-page-title">{t('interventions.title') || 'Intervention Center'}</h1>
              <p className="ws-page-subtitle">
                {t('interventions.subtitle') || 'Questions agents escalated for human decision. Resolving one distills the outcome into workspace memory.'}
              </p>
            </div>
          </div>
          <div className="ws-page-actions">
            <Link href={`/workspaces/detail?id=${workspaceCode}`}>
              <Button icon={<ArrowLeftOutlined />}>{t('back') || 'Back'}</Button>
            </Link>
          </div>
        </div>

        <div className="ws-table-wrap">
          <Table<InterventionRow>
            rowKey="id"
            columns={columns}
            dataSource={interventions || []}
            loading={loading}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            locale={{ emptyText: <span style={{ color: 'var(--ws-ink-3)', padding: '48px 0', display: 'inline-block' }}>No interventions</span> }}
          />
        </div>
      </div>

      <Modal
        open={!!resolveOpen}
        onCancel={() => setResolveOpen(null)}
        onOk={handleResolve}
        confirmLoading={saving}
        title={t('interventions.resolve_title') || 'Resolve — Distill to Asset'}
        width={640}
        okText={t('interventions.resolve_confirm') || 'Resolve + Save Asset'}
      >
        <p style={{ fontSize: 13, color: 'var(--ws-ink-2)', lineHeight: 1.6, margin: '12px 0 18px' }}>
          {t('interventions.resolve_notice') ||
            'Review the question, decide, and distill the resolution into a workspace Asset (the agent will use this as memory next time).'}
        </p>
        <Form form={form} layout="vertical">
          <Form.Item name="decision" label="Decision note">
            <Input placeholder="approved / rejected / deferred" />
          </Form.Item>
          <Form.Item name="asset_name" label="Asset Name" rules={[{ required: true }]}>
            <Input placeholder="e.g. Capacity baseline anomaly — June 2026" />
          </Form.Item>
          <Form.Item name="asset_type" label="Asset Type" initialValue="historical_artifact">
            <Input />
          </Form.Item>
          <Form.Item name="summary" label="Distill Summary" rules={[{ required: true }]}>
            <TextArea rows={5} placeholder="Key facts, decision rationale, what to reuse next time..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
