'use client';

import { apiInterceptors, createChannel } from '@/client/api';
import { ChannelConfig } from '@/client/api/channel';
import ChannelForm from '../components/channel-form';
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Card, Form, Space, Typography } from 'antd';
import { useRouter } from 'next/navigation';
import React from 'react';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

export default function CreateChannelPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { message } = App.useApp();
  const [form] = Form.useForm();

  // Create channel
  const { run: runCreateChannel, loading: createLoading } = useRequest(
    async (data: ChannelConfig) => {
      const [err, res] = await apiInterceptors(createChannel(data));
      if (err) {
        throw err;
      }
      return res?.data;
    },
    {
      manual: true,
      onSuccess: (data) => {
        message.success(t('channel_create_success'));
        router.push('/channel');
      },
      onError: () => {
        message.error(t('channel_create_failed'));
      },
    }
  );

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await runCreateChannel(values);
    } catch (error) {
      // Form validation error
    }
  };

  return (
    <div className="flex flex-col h-full p-6 overflow-hidden">
      <div className="flex-shrink-0 mb-6 flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => router.push('/channel')}
          >
            {t('Back')}
          </Button>
          <Title level={3} className="mb-0">
            {t('channel_create')}
          </Title>
        </div>
        <Space>
          <Button onClick={() => router.push('/channel')}>{t('cancel')}</Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={createLoading}
            onClick={handleSubmit}
          >
            {t('save')}
          </Button>
        </Space>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        <Card>
          <ChannelForm form={form} />
        </Card>
      </div>
    </div>
  );
}