'use client';

import { apiInterceptors, listWorkspaces, createWorkspace } from '@/client/api';
import { getUserId } from '@/utils/storage';
import { Button, Form, Input, Modal, Select, Spin, message } from 'antd';
import {
  PlusOutlined,
  AppstoreOutlined,
  TeamOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useRequest } from 'ahooks';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import './workspaces.css';

export default function WorkspacesPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [createOpen, setCreateOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const { data: list, loading: listLoading, refresh } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listWorkspaces({ user_id: Number(getUserId()) || 0 }));
    if (err) return [];
    return res || [];
  });

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      const [err] = await apiInterceptors(createWorkspace({
        ...values,
        owner_user_id: Number(getUserId()) || 0,
      }));
      setLoading(false);
      if (err) {
        message.error(err.message);
        return;
      }
      message.success(t('workspaces.create_success') || 'Workspace created');
      setCreateOpen(false);
      form.resetFields();
      refresh();
    } catch (e) {
      // validation failed
    }
  };

  const activeCount = (list || []).filter((w: any) => !w.is_archived).length;

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />

      <div className="ws-page-content">
        <div className="ws-page-header">
          <div className="ws-page-header-left">
            <div className="ws-page-icon">
              <AppstoreOutlined />
            </div>
            <div>
              <div className="ws-page-eyebrow">
                {t('workspaces') || 'Scenario Workspaces'}
                <span className="ws-page-eyebrow-code">{activeCount} active</span>
              </div>
              <h1 className="ws-page-title">{t('workspaces.title') || 'Scenario Workspaces'}</h1>
              <p className="ws-page-subtitle">
                {t('workspaces.subtitle') ||
                  'Operational spaces where playbooks run, interventions are reviewed, and outcomes distill into memory.'}
              </p>
            </div>
          </div>
          <div className="ws-page-actions">
            <button
              className="ws-btn-icon"
              onClick={refresh}
              title={t('workspaces.reload') || 'Refresh'}
              aria-label="Refresh"
            >
              <ReloadOutlined />
            </button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateOpen(true)}
            >
              {t('workspaces.create') || 'New Workspace'}
            </Button>
          </div>
        </div>

        {listLoading ? (
          <div className="ws-empty">
            <Spin />
          </div>
        ) : !list || list.length === 0 ? (
          <div className="ws-empty">
            <div className="ws-empty-icon"><AppstoreOutlined /></div>
            <p className="ws-empty-title">{t('workspaces.empty') || 'No workspaces yet'}</p>
            <p className="ws-empty-desc">
              {t('workspaces.empty_desc') ||
                'Create your first scenario workspace to start running playbooks and collecting operational memory.'}
            </p>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              {t('workspaces.create') || 'New Workspace'}
            </Button>
          </div>
        ) : (
          <div className="ws-list-grid">
            {list.map((ws: any) => {
              const scenario = ws.scenario_type || ws.type || 'scenario';
              return (
                <div
                  key={ws.id}
                  className={`ws-card${ws.is_archived ? ' ws-card-archived' : ''}`}
                  onClick={() => router.push(`/workspaces/detail?id=${ws.workspace_code}`)}
                >
                  <div className="ws-card-top">
                    <span className="ws-card-id">{ws.workspace_code}</span>
                    <span className={`ws-chip ${ws.is_archived ? 'ws-chip--outline' : 'ws-chip--accent'}`}>
                      {scenario}
                    </span>
                  </div>
                  <h3 className="ws-card-name">{ws.name}</h3>
                  <p className="ws-card-desc">{ws.description || '—'}</p>
                  <div className="ws-card-foot">
                    <span className="ws-card-foot-item">
                      <TeamOutlined />
                      <strong>{ws.member_count || 0}</strong> {t('workspaces.members') || 'members'}
                    </span>
                    {ws.task_count != null && (
                      <span className="ws-card-foot-item">
                        <ThunderboltOutlined />
                        <strong>{ws.task_count}</strong> {t('workspaces.tasks') || 'tasks'}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Modal
        title={t('workspaces.create_title') || 'Create Workspace'}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={loading}
        okText={t('create') || 'Create'}
        width={520}
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="workspace_code" label="Code" rules={[{ required: true }]}>
            <Input placeholder="e.g. data_ops_team" />
          </Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="Workspace name" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} placeholder="What this space is for — e.g. SRE incident response for the payments platform" />
          </Form.Item>
          <Form.Item name="type" label="Type" initialValue="scenario">
            <Select options={[
              { value: 'scenario', label: 'Scenario' },
              { value: 'team', label: 'Team' },
            ]} />
          </Form.Item>
          <Form.Item name="scenario_type" label="Scenario Type">
            <Select allowClear options={[
              { value: 'sre', label: 'SRE' },
              { value: 'data_ops', label: 'Data Operations' },
            ]} />
          </Form.Item>
          <Form.Item name="default_agent_app_code" label="Default Agent App Code">
            <Input placeholder="e.g. data_ops_agent" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
