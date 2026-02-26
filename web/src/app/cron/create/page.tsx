'use client';

import { apiInterceptors, createCronJob } from '@/client/api';
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Card, Space, Form } from 'antd';
import { useRouter } from 'next/navigation';
import React from 'react';
import { useTranslation } from 'react-i18next';
import CronForm from '../components/cron-form';

export default function CreateCronPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { message } = App.useApp();
  const [form] = Form.useForm();

  // Create job
  const { run: runCreateJob, loading: createLoading } = useRequest(
    async (values: any) => {
      // Parse tool_args if it's a string
      if (values.payload?.tool_args && typeof values.payload.tool_args === 'string') {
        try {
          values.payload.tool_args = JSON.parse(values.payload.tool_args);
        } catch {
          // Keep as is if not valid JSON
        }
      }
      console.log('Creating cron job with values:', values);
      const [err, res] = await apiInterceptors(createCronJob(values));
      console.log('API response:', { err, res });
      if (err) {
        throw err;
      }
      return res;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('cron_save_success'));
        router.push('/cron');
      },
      onError: (err: any) => {
        console.error('Create job error:', err);
        message.error(t('Error_Message') + ': ' + (err?.message || 'Unknown error'));
      },
    }
  );

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      console.log('Form values:', values);
      await runCreateJob(values);
    } catch (error: any) {
      console.error('Validation or API error:', error);
      // Check if it's a form validation error
      if (error?.errorFields) {
        message.warning(t('form_required'));
      } else {
        message.error(t('Error_Message'));
      }
    }
  };

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
            <span className="text-xl font-semibold">{t('cron_create')}</span>
          </div>
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={createLoading} onClick={handleSave}>
              {t('save')}
            </Button>
          </Space>
        </div>
      </div>

      {/* Form - 可滚动区域 */}
      <div className="overflow-y-auto pb-8">
        <CronForm form={form} />
      </div>
    </div>
  );
}