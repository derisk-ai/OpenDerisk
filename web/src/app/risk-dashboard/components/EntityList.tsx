'use client';

import React from 'react';
import { Card, Table, Tag, Button, Space, Tooltip, Popconfirm, Empty, Typography } from 'antd';
import {
  EyeOutlined,
  PlayCircleOutlined,
  BellOutlined,
  BellFilled,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import moment from 'moment';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { Entity, riskLevelMap, RiskLevel } from '../mock/data';

const { Text } = Typography;

interface EntityListProps {
  entities: Entity[];
  loading?: boolean;
  showActions?: boolean;
  onCheck?: (entityId: string) => void;
  onSubscribe?: (entityId: string) => void;
  onDelete?: (entityId: string) => void;
}

export default function EntityList({
  entities,
  loading,
  showActions = true,
  onCheck,
  onSubscribe,
  onDelete,
}: EntityListProps) {
  const { t } = useTranslation();

  const getRiskLevelTag = (level?: RiskLevel) => {
    if (!level) return <Tag>-</Tag>;
    const info = riskLevelMap[level];
    return (
      <Tag color={info.color} style={{ borderRadius: 4 }}>
        {info.icon} {info.text}
      </Tag>
    );
  };

  const columns = [
    {
      title: t('risk_entity_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string, record: Entity) => (
        <Link
          href={`/risk-dashboard/entities?id=${record.id}`}
          className="text-blue-500 hover:text-blue-700 font-medium"
        >
          {name}
        </Link>
      ),
    },
    {
      title: t('risk_entity_type'),
      dataIndex: 'typeName',
      key: 'typeName',
      width: 100,
      render: (typeName: string) => <Tag>{typeName}</Tag>,
    },
    {
      title: t('risk_level'),
      dataIndex: 'riskLevel',
      key: 'riskLevel',
      width: 100,
      render: (level: RiskLevel) => getRiskLevelTag(level),
    },
    {
      title: t('risk_last_check'),
      dataIndex: 'lastCheckAt',
      key: 'lastCheckAt',
      width: 160,
      render: (time: string) =>
        time ? moment(time).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: t('risk_summary'),
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
      render: (summary: string) => (
        <Text ellipsis={{ tooltip: summary }} style={{ maxWidth: 200 }}>
          {summary || '-'}
        </Text>
      ),
    },
    {
      title: t('Operation'),
      key: 'action',
      width: 150,
      render: (_: any, record: Entity) => (
        <Space size="small">
          <Tooltip title={t('risk_view_detail')}>
            <Link href={`/risk-dashboard/entities?id=${record.id}`}>
              <Button type="text" icon={<EyeOutlined />} />
            </Link>
          </Tooltip>
          {onCheck && (
            <Tooltip title={t('risk_check_now')}>
              <Button
                type="text"
                icon={<PlayCircleOutlined />}
                onClick={() => onCheck(record.id)}
              />
            </Tooltip>
          )}
          {onSubscribe && (
            <Tooltip title={record.subscribed ? t('risk_unsubscribe') : t('risk_subscribe')}>
              <Button
                type="text"
                icon={record.subscribed ? <BellFilled style={{ color: '#1890ff' }} /> : <BellOutlined />}
                onClick={() => onSubscribe(record.id)}
              />
            </Tooltip>
          )}
          {onDelete && (
            <Popconfirm
              title={t('risk_confirm_delete_entity')}
              onConfirm={() => onDelete(record.id)}
              okText={t('Yes')}
              cancelText={t('No')}
            >
              <Tooltip title={t('Delete')}>
                <Button type="text" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card loading={loading}>
      <Table
        columns={columns}
        dataSource={entities}
        rowKey="id"
        pagination={{ pageSize: 10 }}
        locale={{
          emptyText: (
            <Empty
              description={t('risk_no_entities')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ),
        }}
      />
    </Card>
  );
}