'use client';

import {
  apiInterceptors, getTaskInfo, listArtifacts, listDeliveries,
  listInterventions, listTaskAssetLinks, closeTask, startTask,
} from '@/client/api';
import {
  Button, Card, Descriptions, Empty, Form, Input, Modal, Spin,
  Table, Tag, Tabs, message,
} from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  MessageOutlined, ThunderboltOutlined,
  WarningOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import ChatSession from '@/components/chat/chat-session';

const { TextArea } = Input;

export default function TaskDetailPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const taskId = Number(searchParams?.get('task_id'));
  const { t } = useTranslation();
  const [closeOpen, setCloseOpen] = useState(false);
  const [distillForm] = Form.useForm();
  const [closing, setClosing] = useState(false);
  const [starting, setStarting] = useState(false);

  const { data: task, loading, refresh } = useRequest(async () => {
    if (!taskId) return null;
    const [err, res] = await apiInterceptors(getTaskInfo(taskId));
    return err ? null : res;
  }, { refreshDeps: [taskId] });

  const workspaceId = task?.workspace_id;
  const appCode = task?.context?.app_code || task?.assigned_agents?.[0] || 'main';


  const { data: artifacts } = useRequest(async () => {
    if (!task?.workspace_id) return [];
    const [err, res] = await apiInterceptors(listArtifacts({
      workspace_id: task.workspace_id, task_id: taskId, limit: 100,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [task?.workspace_id, taskId] });

  const { data: deliveries } = useRequest(async () => {
    if (!task?.workspace_id) return [];
    const [err, res] = await apiInterceptors(listDeliveries({
      workspace_id: task.workspace_id, task_id: taskId, limit: 100,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [task?.workspace_id, taskId] });

  const { data: interventions } = useRequest(async () => {
    if (!task?.workspace_id) return [];
    const [err, res] = await apiInterceptors(listInterventions({
      workspace_id: task.workspace_id, task_id: taskId, limit: 100,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [task?.workspace_id, taskId] });

  const { data: assetLinks } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listTaskAssetLinks(taskId));
    return err ? [] : res || [];
  }, { refreshDeps: [taskId] });

  const handleClose = async () => {
    try {
      await distillForm.validateFields();
      setClosing(true);
      const [err] = await apiInterceptors(closeTask({
        task_id: taskId,
        distill_completed: true,
      }));
      setClosing(false);
      if (err) {
        message.error(err.message);
        return;
      }
      message.success(t('tasks.closed') || 'Task closed');
      setCloseOpen(false);
      refresh();
    } catch {}
  };

  const handleStart = async () => {
    setStarting(true);
    const [err] = await apiInterceptors(startTask(taskId));
    setStarting(false);
    if (err) {
      message.error(err.message);
      return;
    }
    message.success('Task started');
    refresh();
  };

  if (loading) return <div className="flex justify-center py-20"><Spin /></div>;
  if (!task) return <div className="p-6"><Empty description="Task not found" /></div>;

  const isRunning = ['running', 'awaiting_human', 'pending_trigger'].includes(task.status);
  const isDone = ['delivered', 'closed'].includes(task.status);

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Header */}
      <div className="border-b px-4 py-3 flex items-center justify-between bg-white shrink-0">
        <div className="flex items-center gap-3">
          <Link href={`/workspaces/detail/tasks?id=${workspaceCode}`}>
            <Button size="small">{t('back') || '← Back'}</Button>
          </Link>
          <div>
            <h1 className="text-lg font-semibold leading-tight">#{task.id} {task.title}</h1>
            <div className="flex gap-2 mt-1">
              <Tag color={task.status === 'running' ? 'processing' : isDone ? 'success' : 'default'}>{task.status}</Tag>
              <Tag>{task.type}</Tag>
              <Tag>{task.triggered_by}</Tag>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {['draft', 'pending_trigger', 'failed'].includes(task.status) && (
            <Button type="primary" icon={<ThunderboltOutlined />} loading={starting} onClick={handleStart}>
              {t('tasks.start') || 'Start'}
            </Button>
          )}
          {task.status === 'awaiting_human' && (
            <Link href={`/workspaces/detail/interventions?id=${workspaceCode}&task_id=${taskId}`}>
              <Button type="primary" icon={<WarningOutlined />}>{t('tasks.review') || 'Review'}</Button>
            </Link>
          )}
          {(task.status === 'delivered' || task.status === 'running' || task.status === 'awaiting_human') && (
            <Button onClick={() => setCloseOpen(true)} type="primary" icon={<CheckCircleOutlined />}>
              {t('tasks.close') || 'Close (with distill)'}
            </Button>
          )}
        </div>
      </div>

      {/* Body: chat + tabs */}
      <div className="flex flex-1 overflow-hidden bg-gray-50/50">
        {/* Left: task-aware chat */}
        <div className="flex-1 flex flex-col min-w-0 m-3 mr-0 bg-white rounded-lg border shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b bg-white">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <MessageOutlined />
              <span className="font-medium">{isRunning ? (t('tasks.running_chat') || 'Task in progress') : (t('tasks.result_chat') || 'Task context')}</span>
              <Tag size="small" color="default">{appCode}</Tag>
            </div>
          </div>
          <div className="flex-1 relative bg-gray-50/30">
            {task?.conv_session_id ? (
              <ChatSession
                convUid={task.conv_session_id}
                appCode={appCode}
                workspaceId={workspaceId}
                taskId={taskId}
                minimal
              />
            ) : (
              <div className="flex justify-center items-center h-full text-gray-400">
                {t('tasks.no_conv') || 'No conversation session'}
              </div>
            )}
          </div>
        </div>

        {/* Right: task details tabs */}
        <div className="w-[480px] bg-white m-3 ml-0 rounded-lg border shadow-sm overflow-hidden flex flex-col">
          <Tabs
            className="flex-1 min-h-0 px-3 pt-2"
            items={[
              {
                key: 'overview',
                label: t('tasks.overview') || 'Overview',
                children: (
                  <div className="overflow-y-auto h-full pr-1">
                    <Descriptions column={1} bordered size="small" className="mb-4">
                      <Descriptions.Item label="ID">{task.id}</Descriptions.Item>
                      <Descriptions.Item label="Workspace">{task.workspace_id}</Descriptions.Item>
                      <Descriptions.Item label="Status"><Tag>{task.status}</Tag></Descriptions.Item>
                      <Descriptions.Item label="Type">{task.type}</Descriptions.Item>
                      <Descriptions.Item label="Trigger">{task.triggered_by}</Descriptions.Item>
                      <Descriptions.Item label="Trigger Ref">{task.trigger_ref || '-'}</Descriptions.Item>
                      <Descriptions.Item label="Playbook ID">{task.playbook_id || '-'}</Descriptions.Item>
                      <Descriptions.Item label="Priority">{task.priority || '-'}</Descriptions.Item>
                      <Descriptions.Item label="Conv Session">{task.conv_session_id || '-'}</Descriptions.Item>
                      <Descriptions.Item label="Created">{task.gmt_created}</Descriptions.Item>
                      <Descriptions.Item label="Description">{task.description || '-'}</Descriptions.Item>
                    </Descriptions>
                    <Card size="small" title="Context (JSON)">
                      <pre className="text-xs bg-gray-50 p-2 max-h-60 overflow-auto rounded">
                        {JSON.stringify(task.context || {}, null, 2)}
                      </pre>
                    </Card>
                  </div>
                ),
              },
              {
                key: 'artifacts',
                label: t('tasks.artifacts') || 'Artifacts',
                children: (
                  <div className="overflow-y-auto h-full pr-1">
                    <Table
                      rowKey="id"
                      size="small"
                      pagination={false}
                      dataSource={artifacts || []}
                      locale={{ emptyText: 'No artifacts produced yet' }}
                      columns={[
                        { title: 'ID', dataIndex: 'id', width: 60 },
                        { title: 'Title', dataIndex: 'title' },
                        { title: 'Type', dataIndex: 'type', width: 100 },
                        { title: 'Version', dataIndex: 'current_version', width: 80 },
                        { title: 'Created', dataIndex: 'gmt_created', width: 180 },
                      ]}
                    />
                  </div>
                ),
              },
              {
                key: 'deliveries',
                label: t('tasks.deliveries') || 'Deliveries',
                children: (
                  <div className="overflow-y-auto h-full pr-1">
                    <Table
                      rowKey="id"
                      size="small"
                      pagination={false}
                      dataSource={deliveries || []}
                      locale={{ emptyText: 'No deliveries' }}
                      columns={[
                        { title: 'ID', dataIndex: 'id', width: 60 },
                        { title: 'Channel', dataIndex: 'channel', width: 100 },
                        { title: 'Target', dataIndex: 'target' },
                        { title: 'Status', dataIndex: 'status', width: 100,
                          render: (s: string) => <Tag color={s === 'sent' ? 'green' : s === 'failed' ? 'red' : 'orange'}>{s}</Tag> },
                        { title: 'Sent At', dataIndex: 'sent_at', width: 180 },
                      ]}
                    />
                  </div>
                ),
              },
              {
                key: 'interventions',
                label: t('tasks.interventions') || 'Interventions',
                children: (
                  <div className="overflow-y-auto h-full pr-1">
                    <Table
                      rowKey="id"
                      size="small"
                      pagination={false}
                      dataSource={interventions || []}
                      locale={{ emptyText: 'No interventions' }}
                      columns={[
                        { title: 'ID', dataIndex: 'id', width: 60 },
                        { title: 'Type', dataIndex: 'type', width: 100 },
                        { title: 'Status', dataIndex: 'status', width: 100 },
                        { title: 'Requested By', dataIndex: 'requested_by', width: 120 },
                        { title: 'Resolved At', dataIndex: 'resolved_at', width: 180 },
                      ]}
                    />
                  </div>
                ),
              },
              {
                key: 'assets',
                label: t('tasks.assets') || 'Linked Assets',
                children: (
                  <div className="overflow-y-auto h-full pr-1">
                    <Table
                      rowKey="id"
                      size="small"
                      pagination={false}
                      dataSource={assetLinks || []}
                      locale={{ emptyText: 'No linked assets' }}
                      columns={[
                        { title: 'Asset ID', dataIndex: 'asset_id' },
                        { title: 'Link Type', dataIndex: 'link_type',
                          render: (s: string) => <Tag color={s === 'produced' ? 'green' : 'blue'}>{s}</Tag> },
                        { title: 'Linked At', dataIndex: 'gmt_created' },
                      ]}
                    />
                  </div>
                ),
              },
            ]}
          />
        </div>
      </div>

      <Modal
        title={t('tasks.close_with_distill') || 'Close Task — Distill Required'}
        open={closeOpen}
        onCancel={() => setCloseOpen(false)}
        onOk={handleClose}
        confirmLoading={closing}
        okText={t('tasks.confirm_close') || 'Confirm Close'}
      >
        <p className="text-sm text-gray-600 mb-4">
          {t('tasks.distill_notice') ||
            'Closing a task requires distilling the work into a workspace Asset. Confirm to finalize distillation and close.'}
        </p>
        <Form form={distillForm} layout="vertical">
          <Form.Item name="asset_name" label={t('tasks.asset_name') || 'Asset Name'} rules={[{ required: true }]}>
            <Input placeholder="e.g. Weekly DB Performance Report — June 2026" />
          </Form.Item>
          <Form.Item name="asset_type" label={t('tasks.asset_type') || 'Asset Type'} initialValue="historical_artifact">
            <Input />
          </Form.Item>
          <Form.Item name="summary" label={t('tasks.summary') || 'Summary'} rules={[{ required: true }]}>
            <TextArea rows={4} placeholder="Key learnings, anomalies, reusable patterns..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
