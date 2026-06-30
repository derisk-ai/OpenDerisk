'use client';

import { apiInterceptors, listResources, addResource, removeResource, updateResource, getWorkspaceInfo } from '@/client/api';
import { Button, Card, Empty, Form, Input, Modal, Select, Spin, Table, Tag, message } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

const RESOURCE_TYPES = [
  'data_source', 'knowledge_space', 'environment', 'mcp', 'skill', 'llm_model',
];

export default function ResourcesPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: resources, loading, refresh } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listResources({ workspace_id: ws.id }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const handleAdd = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const [err] = await apiInterceptors(addResource({
        workspace_id: ws?.id,
        ...values,
        config: values.config ? (typeof values.config === 'string' ? JSON.parse(values.config) : values.config) : {},
      }));
      setSaving(false);
      if (err) { message.error(err.message); return; }
      message.success('Resource added');
      setAddOpen(false);
      form.resetFields();
      refresh();
    } catch (e) {}
  };

  const handleRemove = async (id: number) => {
    Modal.confirm({
      title: 'Remove resource?',
      onOk: async () => {
        const [err] = await apiInterceptors(removeResource(id));
        if (err) { message.error(err.message); return; }
        message.success('Removed');
        refresh();
      },
    });
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: 'Name', dataIndex: 'name' },
    { title: 'Type', dataIndex: 'type', width: 140,
      render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: 'Category', dataIndex: 'category', width: 130 },
    { title: 'Physical Ref', dataIndex: 'physical_ref' },
    { title: 'Access', dataIndex: 'access_mode', width: 80 },
    { title: 'Active', dataIndex: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? 'yes' : 'no'}</Tag> },
    {
      title: '', key: 'actions', width: 100,
      render: (_: any, r: any) => <Button size="small" danger onClick={() => handleRemove(r.id)}>Remove</Button>,
    },
  ];

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">{t('resources.title') || 'Workspace Resources'}</h1>
        <div className="flex gap-2">
          <Link href={`/workspaces/detail?id=${workspaceCode}`}><Button>{t('back') || 'Back'}</Button></Link>
          <Button type="primary" onClick={() => setAddOpen(true)}>+ {t('resources.add') || 'Add Resource'}</Button>
        </div>
      </div>
      <Card>
        {loading ? <div className="flex justify-center py-8"><Spin /></div> : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={resources || []}
            pagination={{ pageSize: 20 }}
            locale={{ emptyText: <Empty description="No resources bound yet" /> }}
          />
        )}
      </Card>

      <Modal
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={handleAdd}
        confirmLoading={saving}
        title={t('resources.add_title') || 'Bind Resource'}
        okText="Add"
      >
        <Form form={form} layout="vertical" className="mt-4" initialValues={{ category: 'scenario_bound', access_mode: 'read', is_active: true }}>
          <Form.Item name="type" label="Type" rules={[{ required: true }]}>
            <Select options={RESOURCE_TYPES.map(t => ({ value: t, label: t }))} />
          </Form.Item>
          <Form.Item name="name" label="Display Name" rules={[{ required: true }]}>
            <Input placeholder="e.g. prod_core_db" />
          </Form.Item>
          <Form.Item name="physical_ref" label="Physical Reference">
            <Input placeholder="connect_config.id / knowledge_space slug / app_code / ..." />
          </Form.Item>
          <Form.Item name="category" label="Category">
            <Select options={[
              { value: 'generic', label: 'generic' },
              { value: 'scenario_bound', label: 'scenario_bound' },
              { value: 'scenario_specific', label: 'scenario_specific' },
            ]} />
          </Form.Item>
          <Form.Item name="access_mode" label="Access Mode">
            <Select options={['read', 'write', 'admin'].map(v => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="config" label="Config (JSON)">
            <Input.TextArea rows={3} placeholder="{}" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
