'use client';

import { apiInterceptors, listPlaybooks, getWorkspaceInfo, createPlaybook, deletePlaybook, seedBuiltinPlaybooks } from '@/client/api';
import { Button, Card, Empty, Modal, Spin, Table, Tag, message } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

const DEFAULT_DSL = JSON.stringify({
  skills: [],
  context: { assets_required: [], resources: [] },
  deliverables: [
    { type: 'report', delivery: [{ category: 'notify', channel: 'in_app', target: 'self' }] },
  ],
  distill: { forced: true, produce: [{ type: 'historical_artifact', from: 'deliverable.0' }] },
}, null, 2);

export default function PlaybookListPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const router = useRouter();
  const { t } = useTranslation();
  const [createOpen, setCreateOpen] = useState(false);
  const [dsl, setDsl] = useState(DEFAULT_DSL);

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: playbooks, loading, refresh } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listPlaybooks({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const handleCreate = async () => {
    try {
      let parsed;
      try {
        parsed = JSON.parse(dsl);
      } catch (e) {
        message.error('DSL must be valid JSON');
        return;
      }
      const [err] = await apiInterceptors(createPlaybook({
        workspace_id: ws?.id,
        name: 'New Playbook',
        scenario_type: 'data_ops',
        task_type: 'routine',
        trigger: { type: 'manual' },
        declaration: parsed,
      }));
      if (err) {
        message.error(err.message);
        return;
      }
      message.success('Playbook created');
      setCreateOpen(false);
      refresh();
    } catch (e) {}
  };

  const handleDelete = async (id: number) => {
    Modal.confirm({
      title: 'Delete playbook?',
      onOk: async () => {
        const [err] = await apiInterceptors(deletePlaybook(id));
        if (err) { message.error(err.message); return; }
        message.success('Deleted');
        refresh();
      },
    });
  };

  const handleSeedBuiltin = async () => {
    if (!ws?.id) return;
    const [err, res] = await apiInterceptors(seedBuiltinPlaybooks(ws.id));
    if (err) { message.error(err.message); return; }
    message.success('Built-in playbooks seeded');
    refresh();
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: t('playbooks.name') || 'Name', dataIndex: 'name' },
    { title: t('playbooks.scenario') || 'Scenario', dataIndex: 'scenario_type', width: 120 },
    { title: t('playbooks.task_type') || 'Task Type', dataIndex: 'task_type', width: 110 },
    { title: 'Version', dataIndex: 'current_version', width: 90 },
    {
      title: t('playbooks.active') || 'Active', dataIndex: 'is_active', width: 90,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? 'yes' : 'no'}</Tag>,
    },
    {
      title: '', key: 'actions', width: 180,
      render: (_: any, r: any) => (
        <div className="flex gap-2">
          <Link href={`/workspaces/detail/playbooks/detail?id=${workspaceCode}&playbook_id=${r.id}`}>
            <Button size="small">{t('playbooks.edit') || 'Edit'}</Button>
          </Link>
          <Button size="small" danger onClick={() => handleDelete(r.id)}>{t('delete') || 'Delete'}</Button>
        </div>
      ),
    },
  ];

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">{t('playbooks.title') || 'Playbooks'}</h1>
        <div className="flex gap-2">
          <Link href={`/workspaces/detail?id=${workspaceCode}`}>
            <Button>{t('back') || 'Back'}</Button>
          </Link>
          <Button onClick={handleSeedBuiltin}>{t('playbooks.seed_builtin') || 'Seed Built-in Examples'}</Button>
          <Button type="primary" onClick={() => setCreateOpen(true)}>{t('playbooks.create') || '+ New Playbook'}</Button>
        </div>
      </div>
      <Card>
        {loading ? <div className="flex justify-center py-12"><Spin /></div> : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={playbooks || []}
            pagination={{ pageSize: 20 }}
            locale={{ emptyText: <Empty description="No playbooks yet" /> }}
          />
        )}
      </Card>

      <Modal
        title={t('playbooks.create_title') || 'Create Playbook'}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        width={800}
        okText={t('create') || 'Create'}
      >
        <p className="text-sm text-gray-600 mb-2">
          {t('playbooks.dsl_hint') || 'Edit the declaration DSL below. The backend will validate it on creation.'}
        </p>
        <textarea
          className="w-full h-96 font-mono text-xs p-2 border rounded"
          value={dsl}
          onChange={(e) => setDsl(e.target.value)}
        />
      </Modal>
    </div>
  );
}
