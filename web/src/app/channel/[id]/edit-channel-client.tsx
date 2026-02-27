'use client';

import { apiInterceptors, getChannel, updateChannel, deleteChannel, testChannel, enableChannel, disableChannel } from '@/client/api';
import { ChannelConfig } from '@/client/api/channel';
import ChannelForm from '../components/channel-form';
import {
  ApiOutlined,
  ArrowLeftOutlined,
  DeleteOutlined,
  SaveOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Card, Descriptions, Form, Popconfirm, Space, Switch, Tag, Typography } from 'antd';
import moment from 'moment';
import { useRouter, useParams } from 'next/navigation';
import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

export default function EditChannelClient() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams();
  const channelId = params?.id as string;
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();

  const {
    data: channelData,
    loading: channelLoading,
    refresh: refreshChannel,
  } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getChannel(channelId));
      if (err) {
        throw err;
      }
      return res?.data;
    },
    {
      ready: !!channelId,
    }
  );

  useEffect(() => {
    if (channelData) {
      form.setFieldsValue({
        name: channelData.name,
        channel_type: channelData.channel_type,
        enabled: channelData.enabled,
        config: channelData.config || {},
      });
    }
  }, [channelData, form]);

  const { run: runUpdateChannel, loading: updateLoading } = useRequest(
    async (data: ChannelConfig) => {
      const [err, res] = await apiInterceptors(updateChannel(channelId, data));
      if (err) {
        throw err;
      }
      return res?.data;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('channel_update_success'));
        refreshChannel();
      },
      onError: () => {
        message.error(t('channel_update_failed'));
      },
    }
  );

  const { run: runTestChannel, loading: testLoading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(testChannel(channelId));
      if (err) {
        throw err;
      }
      return res?.data;
    },
    {
      manual: true,
      onSuccess: (data) => {
        if (data?.success) {
          message.success(t('channel_test_success'));
        } else {
          message.error(data?.message || t('channel_test_failed'));
        }
        refreshChannel();
      },
      onError: () => {
        message.error(t('channel_test_failed'));
      },
    }
  );

  const { run: runEnableChannel, loading: enableLoading } = useRequest(
    async () => {
      const [err] = await apiInterceptors(enableChannel(channelId));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('channel_enable_success'));
        refreshChannel();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  const { run: runDisableChannel, loading: disableLoading } = useRequest(
    async () => {
      const [err] = await apiInterceptors(disableChannel(channelId));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('channel_disable_success'));
        refreshChannel();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  const { run: runDeleteChannel, loading: deleteLoading } = useRequest(
    async () => {
      const [err] = await apiInterceptors(deleteChannel(channelId));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('channel_delete_success'));
        router.push('/channel');
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  const handleToggleEnabled = async () => {
    if (channelData?.enabled) {
      await runDisableChannel();
    } else {
      await runEnableChannel();
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await runUpdateChannel(values);
    } catch (error) {
    }
  };

  const handleDelete = () => {
    modal.confirm({
      title: t('channel_delete'),
      content: t('channel_confirm_delete'),
      okText: t('Yes'),
      cancelText: t('No'),
      okButtonProps: { danger: true },
      onOk: () => runDeleteChannel(),
    });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected':
        return 'success';
      case 'disconnected':
        return 'default';
      case 'error':
        return 'error';
      default:
        return 'default';
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
            {t('channel_edit')}: {channelData?.name || ''}
          </Title>
        </div>
        <Space>
          <Popconfirm
            title={t('channel_confirm_delete')}
            onConfirm={handleDelete}
            okText={t('Yes')}
            cancelText={t('No')}
          >
            <Button danger icon={<DeleteOutlined />} loading={deleteLoading}>
              {t('Delete')}
            </Button>
          </Popconfirm>
          <Button onClick={() => router.push('/channel')}>{t('cancel')}</Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={updateLoading}
            onClick={handleSubmit}
          >
            {t('save')}
          </Button>
        </Space>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        <Card size="small" className="mb-4">
          <Descriptions column={{ xs: 1, sm: 2, md: 4 }} size="small">
            <Descriptions.Item label={t('channel_status')}>
              <Tag color={getStatusColor(channelData?.status || 'disconnected')}>
                {channelData?.status === 'connected' ? t('channel_connected') :
                 channelData?.status === 'error' ? t('channel_status_error') : t('channel_disconnected')}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('channel_enabled')}>
              <Switch
                checked={channelData?.enabled}
                onChange={handleToggleEnabled}
                loading={enableLoading || disableLoading}
                checkedChildren={t('Yes')}
                unCheckedChildren={t('No')}
              />
            </Descriptions.Item>
            <Descriptions.Item label={t('channel_last_connected')}>
              {channelData?.last_connected
                ? moment(channelData.last_connected).format('YYYY-MM-DD HH:mm:ss')
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('channel_last_error')}>
              <Text type="danger" ellipsis={{ tooltip: channelData?.last_error }}>
                {channelData?.last_error || '-'}
              </Text>
            </Descriptions.Item>
          </Descriptions>
          <div className="mt-4 flex gap-2">
            <Button
              icon={<ApiOutlined />}
              loading={testLoading}
              onClick={runTestChannel}
            >
              {t('channel_test')}
            </Button>
            <Button
              icon={<SyncOutlined />}
              onClick={refreshChannel}
            >
              {t('Refresh_status')}
            </Button>
          </div>
        </Card>

        <Card loading={channelLoading}>
          <ChannelForm
            form={form}
            initialValues={channelData}
          />
        </Card>
      </div>
    </div>
  );
}