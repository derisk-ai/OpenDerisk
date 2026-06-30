'use client';

import { apiInterceptors, getWorkspaceInfo, listMembers, addMember, removeMember, updateMemberRole, updateWorkspace } from '@/client/api';
import { Button, Card, Descriptions, Empty, Form, Input, Modal, Select, Spin, Table, Tag, message } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function SettingsPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [memberForm] = Form.useForm();
  const [editOpen, setEditOpen] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const { data: ws, loading, refresh } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: members, refresh: refreshMembers } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listMembers(ws.id));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const handleEditSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const [err] = await apiInterceptors(updateWorkspace({
        ...values,
        workspace_code: ws?.workspace_code,
      }));
      setSaving(false);
      if (err) { message.error(err.message); return; }
      message.success('Saved');
      setEditOpen(false);
      refresh();
    } catch (e) {}
  };

  const handleAddMember = async () => {
    try {
      const values = await memberForm.validateFields();
      const [err] = await apiInterceptors(addMember({
        workspace_id: ws?.id,
        user_id: Number(values.user_id),
        role: values.role,
      }));
      if (err) { message.error(err.message); return; }
      message.success('Member added');
      setAddMemberOpen(false);
      memberForm.resetFields();
      refreshMembers();
    } catch (e) {}
  };

  const handleRoleChange = async (userId: number, role: string) => {
    const [err] = await apiInterceptors(updateMemberRole({
      workspace_id: ws?.id, user_id: userId, role,
    }));
    if (err) { message.error(err.message); return; }
    refreshMembers();
  };

  const handleRemoveMember = async (userId: number) => {
    const [err] = await apiInterceptors(removeMember({ workspace_id: ws?.id, user_id: userId }));
    if (err) { message.error(err.message); return; }
    refreshMembers();
  };

  if (loading) return <div className="flex justify-center py-20"><Spin /></div>;
  if (!ws) return <div className="p-6"><Empty /></div>;

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">{t('settings.title') || 'Workspace Settings'}</h1>
        <Link href={`/workspaces/detail?id=${workspaceCode}`}><Button>{t('back') || 'Back'}</Button></Link>
      </div>

      <Card title={t('settings.basic') || 'Basic Info'} className="mb-4"
        extra={<Button onClick={() => { form.setFieldsValue(ws); setEditOpen(true); }}>Edit</Button>}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="Code">{ws.workspace_code}</Descriptions.Item>
          <Descriptions.Item label="Name">{ws.name}</Descriptions.Item>
          <Descriptions.Item label="Type">{ws.type}</Descriptions.Item>
          <Descriptions.Item label="Scenario">{ws.scenario_type || '-'}</Descriptions.Item>
          <Descriptions.Item label="Owner">{ws.owner_user_id}</Descriptions.Item>
          <Descriptions.Item label="Default Agent">{ws.default_agent_app_code || '-'}</Descriptions.Item>
          <Descriptions.Item label="Description" span={2}>{ws.description || '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={t('settings.members') || 'Members'}
        extra={<Button onClick={() => setAddMemberOpen(true)}>+ {t('settings.add_member') || 'Add Member'}</Button>}>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={members || []}
          locale={{ emptyText: 'No members' }}
          columns={[
            { title: 'User ID', dataIndex: 'user_id', width: 100 },
            { title: 'Name', dataIndex: 'user_name' },
            {
              title: 'Role', dataIndex: 'role', width: 200,
              render: (role: string, r: any) => (
                <Select
                  size="small"
                  value={role}
                  onChange={(v) => handleRoleChange(r.user_id, v)}
                  options={['owner', 'contributor', 'approver', 'viewer'].map(v => ({ value: v, label: v }))}
                  disabled={role === 'owner'}
                />
              ),
            },
            {
              title: '', key: 'actions', width: 100,
              render: (_: any, r: any) => r.role !== 'owner' ? (
                <Button size="small" danger onClick={() => handleRemoveMember(r.user_id)}>Remove</Button>
              ) : null,
            },
          ]}
        />
      </Card>

      <Modal
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleEditSave}
        confirmLoading={saving}
        title="Edit Workspace"
        okText="Save"
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="scenario_type" label="Scenario Type"><Input /></Form.Item>
          <Form.Item name="default_agent_app_code" label="Default Agent App Code"><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal
        open={addMemberOpen}
        onCancel={() => setAddMemberOpen(false)}
        onOk={handleAddMember}
        title="Add Member"
        okText="Add"
      >
        <Form form={memberForm} layout="vertical" className="mt-4" initialValues={{ role: 'contributor' }}>
          <Form.Item name="user_id" label="User ID" rules={[{ required: true }]}><Input type="number" /></Form.Item>
          <Form.Item name="role" label="Role">
            <Select options={['contributor', 'approver', 'viewer'].map(v => ({ value: v, label: v }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
