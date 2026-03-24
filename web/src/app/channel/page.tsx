'use client';

import { apiInterceptors, getChannels, deleteChannel, testChannel, startChannel, stopChannel } from '@/client/api';
import { ChannelResponse } from '@/client/api/channel';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  ApiTwoTone,
  PlayCircleOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Card, Space, Switch, Table, Tag, Typography, Popconfirm, Tooltip, Empty } from 'antd';
import moment from 'moment';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

// Channel type icons
const channelTypeIcons: Record<string, React.ReactNode> = {
  dingtalk: <Image src="/icons/channel/dingtalk.svg" alt="DingTalk" width={20} height={20} className="inline-block mr-2" />,
  feishu: <Image src="/icons/channel/feishu.svg" alt="Feishu" width={20} height={20} className="inline-block mr-2" />,
  wechat: <span className="text-lg mr-2">💬</span>,
  qq: <span className="text-lg mr-2">🐧</span>,
};

// Channel status colors
const statusColors: Record<string, string> = {
  connected: 'success',
  disconnected: 'default',
  error: 'error',
};

export default function ChannelPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { message } = App.useApp();
  const [includeDisabled, setIncludeDisabled] = useState(false);
  const [testingChannelId, setTestingChannelId] = useState<string | null>(null);
  const [deletingChannelId, setDeletingChannelId] = useState<string | null>(null);
  const [operatingChannelId, setOperatingChannelId] = useState<string | null>(null);

  // Fetch channels
  const {
    data: channelsData,
    loading: channelsLoading,
    refresh: refreshChannels,
  } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getChannels(includeDisabled));
      if (err) {
        return [];
      }
      return res || [];
    },
    {
      refreshDeps: [includeDisabled],
    }
  );

  // Delete channel
  const { run: runDeleteChannel } = useRequest(
    async (channelId: string) => {
      setDeletingChannelId(channelId);
      const [err] = await apiInterceptors(deleteChannel(channelId));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onFinally: () => {
        setDeletingChannelId(null);
      },
      onSuccess: () => {
        message.success(t('channel_delete_success'));
        refreshChannels();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  // Test connection
  const { run: runTestChannel } = useRequest(
    async (channelId: string) => {
      setTestingChannelId(channelId);
      const [err, res] = await apiInterceptors(testChannel(channelId));
      if (err) {
        throw err;
      }
      return res;
    },
    {
      manual: true,
      onFinally: () => {
        setTestingChannelId(null);
      },
      onSuccess: (data) => {
        if (data?.success) {
          message.success(t('channel_test_success'));
        } else {
          message.error(data?.message || t('channel_test_failed'));
        }
        refreshChannels();
      },
      onError: () => {
        message.error(t('channel_test_failed'));
      },
    }
  );

  // Start channel
  const { run: runStartChannel } = useRequest(
    async (channelId: string) => {
      setOperatingChannelId(channelId);
      const [err, res] = await apiInterceptors(startChannel(channelId));
      if (err) {
        throw err;
      }
      return res;
    },
    {
      manual: true,
      onFinally: () => {
        setOperatingChannelId(null);
      },
      onSuccess: (data) => {
        if (data?.started) {
          message.success(t('channel_start_success'));
        } else {
          message.error(t('channel_start_failed'));
        }
        refreshChannels();
      },
      onError: () => {
        message.error(t('channel_start_failed'));
      },
    }
  );

  // Stop channel
  const { run: runStopChannel } = useRequest(
    async (channelId: string) => {
      setOperatingChannelId(channelId);
      const [err, res] = await apiInterceptors(stopChannel(channelId));
      if (err) {
        throw err;
      }
      return res;
    },
    {
      manual: true,
      onFinally: () => {
        setOperatingChannelId(null);
      },
      onSuccess: (data) => {
        if (data?.stopped) {
          message.success(t('channel_stop_success'));
        } else {
          message.error(t('channel_stop_failed'));
        }
        refreshChannels();
      },
      onError: () => {
        message.error(t('channel_stop_failed'));
      },
    }
  );

  const columns = [
    {
      title: t('channel_name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: ChannelResponse) => (
        <Link href={`/channel/edit?id=${record.id}`} className="text-blue-500 hover:text-blue-700 flex items-center gap-2">
          {channelTypeIcons[record.channel_type]}
          {name}
        </Link>
      ),
    },
    {
      title: t('channel_type'),
      dataIndex: 'channel_type',
      key: 'channel_type',
      render: (type: string) => {
        const typeMap: Record<string, string> = {
          dingtalk: t('channel_dingtalk'),
          feishu: t('channel_feishu'),
          wechat: 'WeChat',
          qq: 'QQ',
        };
        return <Tag color="blue">{typeMap[type] || type}</Tag>;
      },
    },
    {
      title: t('channel_status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: Record<string, string> = {
          connected: t('channel_connected'),
          disconnected: t('channel_disconnected'),
          error: t('channel_status_error'),
        };
        return (
          <Tag color={statusColors[status]} icon={status === 'connected' ? <CheckCircleOutlined /> : status === 'error' ? <CloseCircleOutlined /> : undefined}>
            {statusMap[status] || status}
          </Tag>
        );
      },
    },
    {
      title: t('channel_enabled'),
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'success' : 'default'}>{enabled ? t('channel_enabled') : t('channel_disabled')}</Tag>
      ),
    },
    {
      title: t('channel_last_connected'),
      dataIndex: 'last_connected',
      key: 'last_connected',
      render: (time: string) => (time ? moment(time).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: t('channel_last_error'),
      dataIndex: 'last_error',
      key: 'last_error',
      ellipsis: true,
      render: (error: string) => error || '-',
    },
    {
      title: t('Operation'),
      key: 'action',
      render: (_: any, record: ChannelResponse) => (
        <Space size="small">
          {record.status === 'connected' ? (
            <Popconfirm
              title={t('channel_confirm_stop')}
              onConfirm={() => runStopChannel(record.id)}
              okText={t('Yes')}
              cancelText={t('No')}
            >
              <Tooltip title={t('channel_stop')}>
                <Button
                  type="text"
                  icon={<PauseCircleOutlined />}
                  loading={operatingChannelId === record.id}
                />
              </Tooltip>
            </Popconfirm>
          ) : (
            <Tooltip title={t('channel_start')}>
              <Button
                type="text"
                icon={<PlayCircleOutlined />}
                loading={operatingChannelId === record.id}
                onClick={() => runStartChannel(record.id)}
              />
            </Tooltip>
          )}
          <Tooltip title={t('Edit')}>
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => router.push(`/channel/edit?id=${record.id}`)}
            />
          </Tooltip>
          <Tooltip title={t('channel_test')}>
            <Button
              type="text"
              icon={<ApiOutlined />}
              loading={testingChannelId === record.id}
              onClick={() => runTestChannel(record.id)}
            />
          </Tooltip>
          <Popconfirm
            title={t('channel_confirm_delete')}
            onConfirm={() => runDeleteChannel(record.id)}
            okText={t('Yes')}
            cancelText={t('No')}
          >
            <Tooltip title={t('Delete')}>
              <Button type="text" danger icon={<DeleteOutlined />} loading={deletingChannelId === record.id} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-6 [&_table]:table">
      <div className="mb-6">
        <Title level={3}>{t('channel_page_title')}</Title>
      </div>

      {/* Channels Table */}
      <Card
        title={
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <ApiTwoTone twoToneColor="#1890ff" />
              {t('channel_page_title')}
            </span>
            <Space>
              <div className="flex items-center gap-2">
                <Text type="secondary">{t('channel_show_disabled')}</Text>
                <Switch checked={includeDisabled} onChange={setIncludeDisabled} />
              </div>
              <Button icon={<ReloadOutlined />} onClick={refreshChannels}>
                {t('Refresh_status')}
              </Button>
              <Link href="/channel/create">
                <Button type="primary" icon={<PlusOutlined />}>
                  {t('channel_create')}
                </Button>
              </Link>
            </Space>
          </div>
        }
      >
        <Table
          columns={columns}
          dataSource={channelsData}
          rowKey="id"
          loading={channelsLoading}
          pagination={{ pageSize: 10 }}
          locale={{
            emptyText: (
              <Empty
                description={t('channel_no_channels')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
        />
      </Card>
    </div>
  );
}