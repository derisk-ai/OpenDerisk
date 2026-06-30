'use client';

import {
  apiInterceptors, createTrigger, getWorkspaceInfo, listPlaybooks, getTriggerInfo, updateTrigger,
} from '@/client/api';
import {
  Button, Card, Form, Input, Select, Switch, Spin, Typography, Tag, message,
} from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useState, useMemo, useEffect } from 'react';
import {
  ArrowLeftOutlined, ClockCircleOutlined, GlobalOutlined, AlertOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import Link from 'next/link';

const { Title, Text } = Typography;

const useTriggerTypeOptions = (t: (key: string) => string) => [
  {
    value: 'timer',
    label: t('triggers.type_timer') || 'Timer',
    icon: <ClockCircleOutlined />,
    desc: t('triggers.type_timer_desc') || 'Run on a cron schedule',
    color: 'blue',
  },
  {
    value: 'webhook',
    label: t('triggers.type_webhook') || 'Webhook',
    icon: <GlobalOutlined />,
    desc: t('triggers.type_webhook_desc') || 'Run when an external POST hits the URL',
    color: 'purple',
  },
  {
    value: 'alert',
    label: t('triggers.type_alert') || 'Alert',
    icon: <AlertOutlined />,
    desc: t('triggers.type_alert_desc') || 'Run when a monitoring alert is received',
    color: 'red',
  },
];

interface PlaybookOption {
  id: number;
  name: string;
}

export default function TriggerCreatePage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const editTriggerId = Number(searchParams?.get('trigger_id') || '0');
  const router = useRouter();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('timer');
  const triggerTypeOptions = useTriggerTypeOptions(t);

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

  const { data: existingTrigger, loading: editLoading } = useRequest(async () => {
    if (!editTriggerId) return null;
    const [err, res] = await apiInterceptors(getTriggerInfo(editTriggerId));
    return err ? null : res;
  }, { refreshDeps: [editTriggerId] });

  useEffect(() => {
    if (!existingTrigger) return;
    form.setFieldsValue({
      name: existingTrigger.name,
      type: existingTrigger.type,
      target_playbook_id: existingTrigger.target_playbook_id,
      is_active: existingTrigger.is_active ?? true,
      cron: existingTrigger.config?.cron || '',
      secret: existingTrigger.config?.secret || '',
      alert_name: existingTrigger.config?.alert_name || '',
    });
    setSelectedType(existingTrigger.type);
  }, [existingTrigger, form]);

  const publicWebhookUrl = useMemo(() => {
    if (!ws?.id || selectedType !== 'webhook') return '';
    const base = typeof window !== 'undefined' ? window.location.origin : '';
    return `${base}/api/v1/serve_trigger_service/triggers/{trigger_id}/webhook`;
  }, [ws?.id, selectedType]);

  const publicAlertUrl = useMemo(() => {
    if (!ws?.id || selectedType !== 'alert') return '';
    const base = typeof window !== 'undefined' ? window.location.origin : '';
    return `${base}/api/v1/serve_trigger_service/triggers/{trigger_id}/alert`;
  }, [ws?.id, selectedType]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (!ws?.id) return;
      setSubmitting(true);

      const config: Record<string, string> = {};
      if (values.type === 'timer') {
        config.cron = values.cron;
      } else if (values.type === 'webhook') {
        config.secret = values.secret || '';
      } else if (values.type === 'alert') {
        config.alert_name = values.alert_name || '';
      }

      const payload = {
        workspace_id: ws.id,
        type: values.type,
        name: values.name,
        target_playbook_id: values.target_playbook_id,
        is_active: values.is_active,
        config,
      };

      const [err] = await apiInterceptors(
        editTriggerId
          ? updateTrigger({ id: editTriggerId, ...payload })
          : createTrigger(payload)
      );
      setSubmitting(false);
      if (err) {
        message.error(err.message);
        return;
      }
      message.success(editTriggerId
        ? (t('triggers.update_success') || 'Trigger source updated')
        : (t('triggers.create_success') || 'Trigger source created')
      );
      router.push(`/workspaces/detail/triggers?id=${workspaceCode}`);
    } catch {
      // validation failed
    }
  };

  if (wsLoading || editLoading) {
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
      <div className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto">
          <Link href={`/workspaces/detail/triggers?id=${workspaceCode}`} className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-2">
            <ArrowLeftOutlined className="mr-1" />
            {t('triggers.title') || 'Trigger Sources'}
          </Link>
          <Title level={4} className="!m-0">
            {editTriggerId
              ? (t('triggers.edit_title') || 'Edit Trigger Source')
              : (t('triggers.create_title') || 'Create Trigger Source')}
            <span className="text-gray-400 font-normal mx-2">·</span>
            <span className="text-gray-600 font-normal text-base">{ws.name}</span>
          </Title>
          <Text type="secondary" className="block mt-1">
            {t('triggers.create_hint') || 'Configure how tasks are spawned automatically. Manual one-off tasks should be created from the Tasks page.'}
          </Text>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <Card className="shadow-sm">
              <Form
                form={form}
                layout="vertical"
                initialValues={{ type: 'timer', is_active: true }}
                onValuesChange={(changed) => {
                  if (changed.type) setSelectedType(changed.type);
                }}
              >
                <Form.Item
                  name="name"
                  label={<span className="font-medium">{t('triggers.name') || 'Name'}</span>}
                  rules={[{ required: true, message: 'Please enter a trigger name' }]}
                >
                  <Input size="large" placeholder="e.g. Weekly DB Report" />
                </Form.Item>

                <Form.Item
                  name="type"
                  label={<span className="font-medium">{t('triggers.type') || 'Trigger Type'}</span>}
                  rules={[{ required: true }]}
                >
                  <Select size="large">
                    {triggerTypeOptions.map(opt => (
                      <Select.Option key={opt.value} value={opt.value}>
                        <div className="flex items-center gap-2">
                          {opt.icon}
                          <Tag color={opt.color}>{opt.label}</Tag>
                          <Text type="secondary" className="text-xs">{opt.desc}</Text>
                        </div>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>

                <Form.Item
                  name="target_playbook_id"
                  label={<span className="font-medium">{t('tasks.playbook') || 'Target Playbook'}</span>}
                  rules={[{ required: true, message: 'Please select a playbook' }]}
                >
                  <Select
                    size="large"
                    loading={pbLoading}
                    placeholder="Select a playbook"
                  >
                    {(playbooks || []).map((p: PlaybookOption) => (
                      <Select.Option key={p.id} value={p.id}>{p.name}</Select.Option>
                    ))}
                  </Select>
                </Form.Item>

                {selectedType === 'timer' && (
                  <Form.Item
                    name="cron"
                    label={<span className="font-medium">{t('triggers.cron_expression') || 'Cron Expression'}</span>}
                    rules={[{ required: true, message: t('triggers.cron_required') || 'Please enter a cron expression' }]}
                  >
                    <Input size="large" placeholder="0 9 * * 1" />
                  </Form.Item>
                )}

                {selectedType === 'webhook' && (
                  <Form.Item
                    name="secret"
                    label={<span className="font-medium">{t('triggers.webhook_secret') || 'Secret (optional)'}</span>}
                  >
                    <Input size="large" placeholder={t('triggers.webhook_secret_placeholder') || 'Bearer token or signature secret'} />
                  </Form.Item>
                )}

                {selectedType === 'alert' && (
                  <Form.Item
                    name="alert_name"
                    label={<span className="font-medium">{t('triggers.alert_name_filter') || 'Alert Name Filter'}</span>}
                  >
                    <Input size="large" placeholder={t('triggers.alert_name_placeholder') || 'e.g. cpu_usage_high'} />
                  </Form.Item>
                )}

                <Form.Item
                  name="is_active"
                  label={<span className="font-medium">{t('triggers.active') || 'Active'}</span>}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <div className="flex justify-end gap-3 mt-8 pt-4 border-t border-gray-100">
                  <Link href={`/workspaces/detail/triggers?id=${workspaceCode}`}>
                    <Button size="large">{t('tasks.cancel') || 'Cancel'}</Button>
                  </Link>
                  <Button type="primary" size="large" loading={submitting} onClick={handleSubmit}>
                    {editTriggerId
                      ? (t('save') || 'Save')
                      : (t('create') || 'Create')}
                  </Button>
                </div>
              </Form>
            </Card>
          </div>

          <div className="lg:col-span-1 space-y-4">
            <Card
              size="small"
              title={
                <span className="flex items-center gap-2">
                  <ThunderboltOutlined className="text-orange-500" />
                  <span>{t('triggers.how_it_works') || 'How it works'}</span>
                </span>
              }
              className="shadow-sm"
            >
              <div className="space-y-3 text-sm text-gray-600">
                <p>{t('triggers.how_desc') || 'A trigger source defines when a task should be created automatically.'}</p>
                <div className="flex items-center gap-2"><ClockCircleOutlined /> {t('triggers.timer_desc') || 'Timer — cron schedule'}</div>
                <div className="flex items-center gap-2"><GlobalOutlined /> {t('triggers.webhook_desc') || 'Webhook — external POST'}</div>
                <div className="flex items-center gap-2"><AlertOutlined /> {t('triggers.alert_desc') || 'Alert — monitoring event'}</div>
              </div>
            </Card>

            {selectedType === 'timer' && (
              <Card
                size="small"
                title={
                  <span className="flex items-center gap-2">
                    <ClockCircleOutlined className="text-blue-500" />
                    <span>{t('triggers.cron_examples') || 'Cron Examples'}</span>
                  </span>
                }
                className="shadow-sm"
              >
                <div className="space-y-2 text-sm text-gray-600">
                  <div className="flex justify-between">
                    <code className="text-xs bg-gray-50 px-1 rounded">0 9 * * 1</code>
                    <span>{t('triggers.cron_monday_9am') || 'Every Monday 09:00'}</span>
                  </div>
                  <div className="flex justify-between">
                    <code className="text-xs bg-gray-50 px-1 rounded">0 2 * * *</code>
                    <span>{t('triggers.cron_daily_2am') || 'Daily 02:00'}</span>
                  </div>
                  <div className="flex justify-between">
                    <code className="text-xs bg-gray-50 px-1 rounded">0 */6 * * *</code>
                    <span>{t('triggers.cron_every_6h') || 'Every 6 hours'}</span>
                  </div>
                </div>
              </Card>
            )}

            {selectedType === 'webhook' && publicWebhookUrl && (
              <Card
                size="small"
                title={
                  <span className="flex items-center gap-2">
                    <GlobalOutlined className="text-purple-500" />
                    <span>Webhook URL</span>
                  </span>
                }
                className="shadow-sm"
              >
                <Text type="secondary" className="text-xs block mb-2">
                  Replace {'{trigger_id}'} with the actual ID after creation.
                </Text>
                <code className="block text-xs bg-gray-50 p-2 rounded break-all">{publicWebhookUrl}</code>
              </Card>
            )}

            {selectedType === 'alert' && publicAlertUrl && (
              <Card
                size="small"
                title={
                  <span className="flex items-center gap-2">
                    <AlertOutlined className="text-red-500" />
                    <span>Alert URL</span>
                  </span>
                }
                className="shadow-sm"
              >
                <Text type="secondary" className="text-xs block mb-2">
                  Replace {'{trigger_id}'} with the actual ID after creation.
                </Text>
                <code className="block text-xs bg-gray-50 p-2 rounded break-all">{publicAlertUrl}</code>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
