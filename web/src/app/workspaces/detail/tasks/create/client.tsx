'use client';

import {
  apiInterceptors, createTask, getWorkspaceInfo, listPlaybooks,
} from '@/client/api';
import {
  Button, Card, Form, Input, Select, Spin, Typography, Tag, Divider, message,
} from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useState, useMemo } from 'react';
import { getUserId } from '@/utils/storage';
import {
  ArrowLeftOutlined, ThunderboltOutlined, FileTextOutlined,
  ClockCircleOutlined, GlobalOutlined, AlertOutlined, InfoCircleOutlined,
} from '@ant-design/icons';
import Link from 'next/link';

const { TextArea } = Input;
const { Title, Text } = Typography;

const TASK_TYPE_OPTIONS = [
  { value: 'adhoc', label: 'Ad-hoc', color: 'default', desc: '一次性临时任务，创建后手动启动' },
  { value: 'incident', label: 'Incident', color: 'red', desc: '异常事件响应任务，创建后手动启动' },
];

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

export default function TaskCreatePage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const router = useRouter();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [selectedPlaybookId, setSelectedPlaybookId] = useState<number | null>(null);

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: playbooks, loading: pbLoading } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listPlaybooks({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  interface PlaybookOption {
    id: number;
    name: string;
    scenario_type?: string;
    task_type?: string;
    declaration?: { skills?: string[] };
  }

  const selectedPlaybook = useMemo(() => {
    return (playbooks || []).find((p: PlaybookOption) => p.id === selectedPlaybookId);
  }, [playbooks, selectedPlaybookId]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (!ws?.id) return;
      setSubmitting(true);
      const [err, res] = await apiInterceptors(createTask({
        workspace_id: ws.id,
        title: values.title,
        description: values.description,
        type: values.type,
        triggered_by: 'manual',
        playbook_id: values.playbook_id || null,
        priority: values.priority || 'medium',
        created_by_user_id: Number(getUserId()) || 0,
        status: 'pending_trigger',
      }));
      setSubmitting(false);
      if (err) {
        message.error(err.message);
        return;
      }
      message.success(t('tasks.create_success') || 'Task created');
      router.push(`/workspaces/detail/tasks/detail?id=${workspaceCode}&task_id=${res?.id}`);
    } catch {
      // validation failed
    }
  };

  if (wsLoading) {
    return (
      <div className="flex justify-center items-center h-screen bg-gray-50">
        <Spin size="large" />
      </div>
    );
  }

  if (!ws) {
    return (
      <div className="flex justify-center items-center h-screen bg-gray-50">
        <Card>Workspace not found</Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50/50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto">
          <Link href={`/workspaces/detail/tasks?id=${workspaceCode}`} className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-2">
            <ArrowLeftOutlined className="mr-1" />
            {t('tasks.title_page') || 'Tasks'}
          </Link>
          <Title level={4} className="!m-0">
            {t('tasks.create_title') || 'Create Task'}
            <span className="text-gray-400 font-normal mx-2">·</span>
            <span className="text-gray-600 font-normal text-base">{ws.name}</span>
          </Title>
          <Text type="secondary" className="block mt-1">
            创建一个手动执行的即时任务。定时 / Webhook / 告警触发的任务请使用触发器配置。
          </Text>
        </div>
      </div>

      {/* Form */}
      <div className="max-w-6xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main form */}
          <div className="lg:col-span-2">
            <Card className="shadow-sm">
              <Form
                form={form}
                layout="vertical"
                initialValues={{ type: 'adhoc', priority: 'medium' }}
                onValuesChange={(_, all) => setSelectedPlaybookId(all.playbook_id || null)}
              >
                <Form.Item
                  name="title"
                  label={<span className="font-medium">{t('tasks.title') || 'Title'}</span>}
                  rules={[{ required: true, message: 'Please enter a task title' }]}
                >
                  <Input size="large" placeholder="e.g. Investigate CPU spike on prod-db-01" />
                </Form.Item>

                <Form.Item
                  name="description"
                  label={<span className="font-medium">{t('tasks.description') || 'Description'}</span>}
                >
                  <TextArea
                    rows={4}
                    placeholder="Describe the goal, expected output, and any special notes..."
                  />
                </Form.Item>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Form.Item
                    name="type"
                    label={<span className="font-medium">{t('tasks.type') || 'Type'}</span>}
                  >
                    <Select size="large">
                      {TASK_TYPE_OPTIONS.map(opt => (
                        <Select.Option key={opt.value} value={opt.value}>
                          <div className="flex items-center gap-2">
                            <Tag color={opt.color}>{opt.label}</Tag>
                            <Text type="secondary" className="text-xs">{opt.desc}</Text>
                          </div>
                        </Select.Option>
                      ))}
                    </Select>
                  </Form.Item>

                  <Form.Item
                    name="priority"
                    label={<span className="font-medium">{t('tasks.priority') || 'Priority'}</span>}
                  >
                    <Select size="large">
                      {PRIORITY_OPTIONS.map(opt => (
                        <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
                      ))}
                    </Select>
                  </Form.Item>
                </div>

                <Form.Item
                  name="playbook_id"
                  label={<span className="font-medium">{t('tasks.playbook') || 'Playbook'}</span>}
                >
                  <Select
                    size="large"
                    allowClear
                    loading={pbLoading}
                    placeholder="Select a playbook"
                  >
                    {(playbooks || []).map((p: PlaybookOption) => (
                      <Select.Option key={p.id} value={p.id}>
                        <div className="flex items-center justify-between">
                          <span>{p.name}</span>
                          <Tag size="small" color="blue">{p.scenario_type || p.task_type}</Tag>
                        </div>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>

                <Divider />

                <div className="flex justify-end gap-3">
                  <Link href={`/workspaces/detail/tasks?id=${workspaceCode}`}>
                    <Button size="large">{t('tasks.cancel') || 'Cancel'}</Button>
                  </Link>
                  <Button type="primary" size="large" loading={submitting} onClick={handleSubmit}>
                    {t('create') || 'Create'}
                  </Button>
                </div>
              </Form>
            </Card>
          </div>

          {/* Helper sidebar */}
          <div className="lg:col-span-1 space-y-4">
            <Card
              size="small"
              title={
                <span className="flex items-center gap-2">
                  <InfoCircleOutlined className="text-blue-500" />
                  <span>What happens next?</span>
                </span>
              }
              className="shadow-sm"
            >
              <div className="space-y-3 text-sm text-gray-600">
                <p>A Task is a single execution context. After creation, click <b>Start</b> to run the selected playbook immediately.</p>
                <p>Each task owns one conversation session. You can review artifacts, deliveries, and interventions in the task detail.</p>
                <p>Closing a task requires distilling the outcome into a workspace asset.</p>
              </div>
            </Card>

            {selectedPlaybook && (
              <Card
                size="small"
                title={
                  <span className="flex items-center gap-2">
                    <FileTextOutlined className="text-purple-500" />
                    <span>Selected Playbook</span>
                  </span>
                }
                className="shadow-sm"
              >
                <Title level={5} className="!m-0 !text-base">{selectedPlaybook.name}</Title>
                <div className="flex gap-2 mt-2">
                  <Tag size="small" color="blue">{selectedPlaybook.scenario_type}</Tag>
                  <Tag size="small">{selectedPlaybook.task_type}</Tag>
                </div>
                {selectedPlaybook.declaration?.skills && (
                  <div className="mt-3">
                    <Text type="secondary" className="text-xs">Skills</Text>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {selectedPlaybook.declaration.skills.map((s: string, i: number) => (
                        <Tag key={i} size="small">{s}</Tag>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            )}

            <Card
              size="small"
              title={
                <span className="flex items-center gap-2">
                  <ThunderboltOutlined className="text-orange-500" />
                  <span>Need automatic triggers?</span>
                </span>
              }
              className="shadow-sm"
            >
              <div className="space-y-2 text-sm text-gray-600">
                <p>For recurring or event-driven execution, create a Trigger Source instead:</p>
                <div className="flex items-center gap-2"><ClockCircleOutlined /> Timer — cron schedule</div>
                <div className="flex items-center gap-2"><GlobalOutlined /> Webhook — external POST</div>
                <div className="flex items-center gap-2"><AlertOutlined /> Alert — monitoring event</div>
                <Link href={`/workspaces/detail/triggers/create?id=${workspaceCode}`}>
                  <Button type="primary" size="small" className="mt-2" block>
                    Create Trigger Source
                  </Button>
                </Link>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
