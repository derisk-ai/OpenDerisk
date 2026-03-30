'use client';

import React, { useState } from 'react';
import {
  Card,
  Button,
  Typography,
  Space,
  Table,
  Tag,
  Popconfirm,
  App,
  Modal,
  Form,
  Select,
  Empty,
} from 'antd';
import {
  ArrowLeftOutlined,
  PlusOutlined,
  ReloadOutlined,
  DeleteOutlined,
  BellOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import moment from 'moment';
import { mockSubscriptions, mockEntities, riskLevelMap, RiskLevel } from '../mock/data';

const { Title } = Typography;

export default function SubscriptionsPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [addModalOpen, setAddModalOpen] = useState(false);

  // Mock data loading
  const {
    data: subscriptions,
    loading,
    refresh,
  } = useRequest(async () => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    return mockSubscriptions;
  });

  const handleDelete = (subscriptionId: string) => {
    message.success(t('risk_unsubscribe_success'));
    refresh();
  };

  const handleAdd = async (values: any) => {
    message.success(t('risk_subscribe_success'));
    setAddModalOpen(false);
    form.resetFields();
    refresh();
  };

  const getNotifyLevelText = (level: string) => {
    const map: Record<string, string> = {
      all: t('risk_notify_all'),
      yellow_plus: t('risk_notify_yellow_plus'),
      red_only: t('risk_notify_red_only'),
    };
    return map[level] || level;
  };

  const getRiskLevelTag = (level?: RiskLevel) => {
    if (!level) return <Tag>-</Tag>;
    const info = riskLevelMap[level];
    return (
      <Tag color={info.color}>
        {info.icon} {info.text}
      </Tag>
    );
  };

  const columns = [
    {
      title: t('risk_entity_name'),
      dataIndex: 'entityName',
      key: 'entityName',
      render: (name: string, record: any) => (
        <Link
          href={`/risk-dashboard/entities/${record.entityId}`}
          className="text-blue-500 hover:text-blue-700"
        >
          {name}
        </Link>
      ),
    },
    {
      title: t('risk_entity_type'),
      dataIndex: 'entityTypeName',
      key: 'entityTypeName',
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: t('risk_level'),
      dataIndex: 'riskLevel',
      key: 'riskLevel',
      render: (level: RiskLevel) => getRiskLevelTag(level),
    },
    {
      title: t('risk_notify_level'),
      dataIndex: 'notifyLevel',
      key: 'notifyLevel',
      render: (level: string) => <Tag color="blue">{getNotifyLevelText(level)}</Tag>,
    },
    {
      title: t('risk_notify_channels'),
      dataIndex: 'notifyChannels',
      key: 'notifyChannels',
      render: (channels: string[]) => (
        <Space>
          {channels?.map((c) => (
            <Tag key={c}>{c}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: t('creation_time'),
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (time: string) =>
        time ? moment(time).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: t('Operation'),
      key: 'action',
      width: 100,
      render: (_: any, record: any) => (
        <Popconfirm
          title={t('risk_confirm_unsubscribe')}
          onConfirm={() => handleDelete(record.id)}
          okText={t('Yes')}
          cancelText={t('No')}
        >
          <Button type="text" danger icon={<DeleteOutlined />}>
            {t('risk_unsubscribe')}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link href="/risk-dashboard">
            <Button icon={<ArrowLeftOutlined />}>{t('Back')}</Button>
          </Link>
          <Title level={3} className="mb-0">
            {t('risk_subscriptions_title')}
          </Title>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => refresh()}>
            {t('Refresh_status')}
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setAddModalOpen(true)}
          >
            {t('risk_add_subscription')}
          </Button>
        </Space>
      </div>

      {/* Subscription List */}
      <Card>
        <Table
          columns={columns}
          dataSource={subscriptions || []}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{
            emptyText: (
              <Empty
                description={t('risk_no_subscriptions')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
        />
      </Card>

      {/* Add Modal */}
      <Modal
        title={t('risk_add_subscription')}
        open={addModalOpen}
        onCancel={() => {
          setAddModalOpen(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item
            name="entityId"
            label={t('risk_select_entity')}
            rules={[{ required: true, message: t('risk_select_entity_placeholder') }]}
          >
            <Select
              showSearch
              placeholder={t('risk_select_entity_placeholder')}
              optionFilterProp="label"
              options={mockEntities.map((e) => ({
                label: `${e.name} (${e.typeName})`,
                value: e.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="notifyLevel"
            label={t('risk_notify_level')}
            rules={[{ required: true }]}
            initialValue="yellow_plus"
          >
            <Select
              options={[
                { label: t('risk_notify_all'), value: 'all' },
                { label: t('risk_notify_yellow_plus'), value: 'yellow_plus' },
                { label: t('risk_notify_red_only'), value: 'red_only' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="notifyChannels"
            label={t('risk_notify_channels')}
            initialValue={['dingtalk']}
          >
            <Select
              mode="multiple"
              options={[
                { label: '钉钉', value: 'dingtalk' },
                { label: '邮件', value: 'email' },
                { label: '短信', value: 'sms' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}