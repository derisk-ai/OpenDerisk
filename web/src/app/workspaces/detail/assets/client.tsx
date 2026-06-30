'use client';

import { apiInterceptors, listAssets, getWorkspaceInfo } from '@/client/api';
import { Button, Card, Empty, Modal, Spin, Table, Tabs, Tag } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function AssetsPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [typeFilter, setTypeFilter] = useState('all');
  const [activeAsset, setActiveAsset] = useState<any | null>(null);

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: assets, loading } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listAssets({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const filtered = (assets || []).filter((a: any) =>
    typeFilter === 'all' || a.type === typeFilter
  );

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: t('assets.name') || 'Name', dataIndex: 'name' },
    { title: t('assets.type') || 'Type', dataIndex: 'type', width: 150,
      render: (v: string) => <Tag color={v === 'historical_artifact' ? 'purple' : 'cyan'}>{v}</Tag> },
    { title: 'Source Task', dataIndex: 'source_task_id', width: 110 },
    { title: 'Published', dataIndex: 'is_published', width: 100,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? 'yes' : 'no'}</Tag> },
    { title: 'Tags', dataIndex: 'tags', render: (tags: string[]) =>
      (tags || []).map((tg, i) => <Tag key={i}>{tg}</Tag>) },
    { title: 'Created', dataIndex: 'gmt_created', width: 180 },
    {
      title: '', key: 'view', width: 80,
      render: (_: any, r: any) => (
        <Button size="small" onClick={() => setActiveAsset(r)}>View</Button>
      ),
    },
  ];

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">{t('assets.title') || 'Workspace Memory (Assets)'}</h1>
        <Link href={`/workspaces/detail?id=${workspaceCode}`}><Button>{t('back') || 'Back'}</Button></Link>
      </div>
      <Card>
        <Tabs
          activeKey={typeFilter}
          onChange={setTypeFilter}
          items={[
            { key: 'all', label: 'All' },
            { key: 'historical_artifact', label: 'Historical Artifacts' },
            { key: 'case', label: 'Cases' },
          ]}
        />
        {loading ? <div className="flex justify-center py-8"><Spin /></div> : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={filtered}
            pagination={{ pageSize: 20 }}
            locale={{ emptyText: <Empty description="No assets yet — distilled tasks will produce them" /> }}
          />
        )}
      </Card>

      <Modal
        open={!!activeAsset}
        onCancel={() => setActiveAsset(null)}
        footer={null}
        width={900}
        title={activeAsset?.name}
      >
        {activeAsset && (
          <div>
            <p className="text-sm text-gray-600 mb-2">
              <Tag color="purple">{activeAsset.type}</Tag>
              {' '}v{activeAsset.current_version} · Source Task #{activeAsset.source_task_id}
            </p>
            <p className="text-sm">{activeAsset.description}</p>
            <h3 className="text-sm font-medium mt-4">Content</h3>
            <pre className="text-xs bg-gray-50 p-3 max-h-96 overflow-auto whitespace-pre-wrap">
              {activeAsset.content_text || activeAsset.content_ref || '(no content stored)'}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
}
