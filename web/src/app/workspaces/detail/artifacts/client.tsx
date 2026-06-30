'use client';

import { apiInterceptors, listArtifacts, getArtifactInfo, getWorkspaceInfo } from '@/client/api';
import { Button, Card, Empty, Modal, Spin, Table, Tabs, Tag } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function ArtifactsPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [typeFilter, setTypeFilter] = useState('all');
  const [activeArt, setActiveArt] = useState<any | null>(null);

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: artifacts, loading } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listArtifacts({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const filtered = (artifacts || []).filter((a: any) =>
    typeFilter === 'all' || a.type === typeFilter
  );

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: t('artifacts.title') || 'Title', dataIndex: 'title' },
    { title: t('artifacts.type') || 'Type', dataIndex: 'type', width: 100,
      render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: 'Task', dataIndex: 'task_id', width: 80 },
    { title: 'Version', dataIndex: 'current_version', width: 80 },
    { title: 'Shared', dataIndex: 'is_shared', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? 'yes' : 'no'}</Tag> },
    { title: 'Created', dataIndex: 'gmt_created', width: 180 },
    {
      title: '', key: 'view', width: 80,
      render: (_: any, r: any) => (
        <Button size="small" onClick={() => setActiveArt(r)}>View</Button>
      ),
    },
  ];

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">{t('artifacts.title_page') || 'Artifacts'}</h1>
        <Link href={`/workspaces/detail?id=${workspaceCode}`}><Button>{t('back') || 'Back'}</Button></Link>
      </div>
      <Card>
        <Tabs
          activeKey={typeFilter}
          onChange={setTypeFilter}
          items={[
            { key: 'all', label: 'All' },
            { key: 'report', label: 'Reports' },
            { key: 'analysis', label: 'Analyses' },
            { key: 'dataset', label: 'Datasets' },
          ]}
        />
        {loading ? <div className="flex justify-center py-8"><Spin /></div> : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={filtered}
            pagination={{ pageSize: 20 }}
            locale={{ emptyText: <Empty /> }}
          />
        )}
      </Card>

      <Modal
        open={!!activeArt}
        onCancel={() => setActiveArt(null)}
        footer={null}
        width={900}
        title={activeArt?.title}
      >
        {activeArt && (
          <div>
            <p className="text-sm text-gray-600 mb-2">
              <Tag color="blue">{activeArt.type}</Tag>
              {' '}v{activeArt.current_version} · Task #{activeArt.task_id}
            </p>
            <h3 className="text-sm font-medium mt-4">Content</h3>
            <pre className="text-xs bg-gray-50 p-3 max-h-96 overflow-auto whitespace-pre-wrap">
              {activeArt.content_text || activeArt.content_ref || '(no content stored; see content_ref for reference)'}
            </pre>
            <h3 className="text-sm font-medium mt-4">Provenance</h3>
            <pre className="text-xs bg-gray-50 p-3 max-h-40 overflow-auto">
              {JSON.stringify(activeArt.provenance || {}, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
}
