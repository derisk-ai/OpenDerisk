'use client';

import { apiInterceptors, getCronJob, updateCronJob, deleteCronJob, runCronJob } from '@/client/api';
import { CronJob } from '@/client/api/cron';
import { ArrowLeftOutlined, DeleteOutlined, PlayCircleOutlined, SaveOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Card, Descriptions, Space, Spin, Form, Popconfirm, Tag, Typography } from 'antd';
import moment from 'moment';
import { useRouter, useSearchParams } from 'next/navigation';
import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import CronForm from '../components/cron-form';

const { Text } = Typography;

export default function EditCronPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const jobId = searchParams?.get('id');
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();

  // Fetch job details
  const { data: jobData, loading: jobLoading, refresh: refreshJob } = useRequest(
    async () => {
      if (!jobId) return null;
      const [err, res] = await apiInterceptors(getCronJob(jobId));
      if (err) {
        throw err;
      }
      return res || null;
    },
    {
      ready: !!jobId,
      refreshDeps: [jobId],
    }
  );

  // Update job
  const { run: runUpdateJob, loading: updateLoading } = useRequest(
    async (values: any) => {
      if (!jobId) return;
      // Parse tool_args if it's a string
      if (values.payload?.tool_args && typeof values.payload.tool_args === 'string') {
        try {
          values.payload.tool_args = JSON.parse(values.payload.tool_args);
        } catch {
          // Keep as is if not valid JSON
        }
      }
      const [err] = await apiInterceptors(updateCronJob(jobId, values));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('cron_save_success'));
        refreshJob();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  // Delete job
  const { run: runDeleteJob, loading: deleteLoading } = useRequest(
    async () => {
      if (!jobId) return;
      const [err] = await apiInterceptors(deleteCronJob(jobId));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('cron_delete_success'));
        router.push('/cron');
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  // Run job now
  const { run: runJobNow, loading: runLoading } = useRequest(
    async () => {
      if (!jobId) return;
      const [err] = await apiInterceptors(runCronJob(jobId, true));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('cron_run_success'));
        refreshJob();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  // Initialize form with job data
  useEffect(() => {
    if (jobData) {
      form.setFieldsValue({
        name: jobData.name,
        description: jobData.description,
        enabled: jobData.enabled,
        delete_after_run: jobData.delete_after_run,
        schedule: {
          kind: jobData.schedule.kind,
          at: jobData.schedule.at,
          every_ms: jobData.schedule.every_ms,
          anchor_ms: jobData.schedule.anchor_ms,
          expr: jobData.schedule.expr,
          tz: jobData.schedule.tz,
        },
        payload: {
          kind: jobData.payload.kind,
          message: jobData.payload.message,
          agent_id: jobData.payload.agent_id,
          tool_name: jobData.payload.tool_name,
          tool_args: jobData.payload.tool_args,
          text: jobData.payload.text,
          timeout_seconds: jobData.payload.timeout_seconds,
          session_mode: jobData.payload.session_mode || 'isolated',
          conv_session_id: jobData.payload.conv_session_id,
        },
      });
    }
  }, [jobData, form]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      await runUpdateJob(values);
    } catch (error) {
      // Form validation error
    }
  };

  const handleDelete = () => {
    modal.confirm({
      title: t('cron_confirm_delete'),
      onOk: () => runDeleteJob(),
      okText: t('Yes'),
      cancelText: t('No'),
    });
  };

  if (!jobId) {
    return (
      <div className="p-6">
        <Text type="secondary">Job ID is required</Text>
      </div>
    );
  }

  if (jobLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" />
      </div>
    );
  }

  if (!jobData) {
    return (
      <div className="p-6">
        <Text type="secondary">Job not found</Text>
      </div>
    );
  }

  return (
    <div className="p-6 min-h-screen overflow-auto">
      {/* Header - 固定在顶部 */}
      <div className="sticky top-0 z-10 bg-white dark:bg-gray-900 pb-4 mb-4 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              type='text'
              icon={<ArrowLeftOutlined />}
              onClick={() => router.push('/cron')}
            >
              {t('Back')}
            </Button>
            <span className="text-xl font-semibold">{t('cron_edit')}: {jobData.name}</span>
          </div>
          <Space>
            <Button
              icon={<PlayCircleOutlined />}
              loading={runLoading}
              onClick={() => runJobNow()}
            >
              {t('cron_run_now')}
            </Button>
            <Popconfirm
              title={t('cron_confirm_delete')}
              onConfirm={handleDelete}
              okText={t('Yes')}
              cancelText={t('No')}
            >
              <Button danger icon={<DeleteOutlined />} loading={deleteLoading}>
                {t('Delete')}
              </Button>
            </Popconfirm>
            <Button type="primary" icon={<SaveOutlined />} loading={updateLoading} onClick={handleSave}>
              {t('save')}
            </Button>
          </Space>
        </div>
      </div>

      {/* Job Status */}
      <Card className="mb-4" size="small">
        <Descriptions column={{ xs: 1, sm: 2, md: 4 }} size="small">
          <Descriptions.Item label={t('cron_status')}>
            <Tag color={jobData.enabled ? 'success' : 'default'}>
              {jobData.enabled ? t('cron_enabled') : t('cron_disabled')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('cron_last_run')}>
            {jobData.state?.last_run_at_ms
              ? moment(jobData.state.last_run_at_ms).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label={t('cron_next_run')}>
            {jobData.state?.next_run_at_ms
              ? moment(jobData.state.next_run_at_ms).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label={t('cron_consecutive_errors')}>
            <Tag color={(jobData.state?.consecutive_errors || 0) > 0 ? 'error' : 'success'}>
              {jobData.state?.consecutive_errors || 0}
            </Tag>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Edit Form - 可滚动区域 */}
      <div className="overflow-y-auto pb-8">
        <Card>
          <CronForm form={form} initialValues={jobData} />
        </Card>
      </div>
    </div>
  );
}