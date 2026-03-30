'use client';

import React from 'react';
import { Card, Table, Tag, Typography, Empty, Timeline } from 'antd';
import { useTranslation } from 'react-i18next';
import moment from 'moment';
import Link from 'next/link';
import { CheckRecord, riskLevelMap, RiskLevel } from '../mock/data';

const { Text, Paragraph } = Typography;

interface CheckHistoryProps {
  records: CheckRecord[];
  loading?: boolean;
  mode?: 'table' | 'timeline';
}

export default function CheckHistory({ records, loading, mode = 'table' }: CheckHistoryProps) {
  const { t } = useTranslation();

  const getRiskLevelTag = (level: RiskLevel) => {
    const info = riskLevelMap[level];
    return (
      <Tag color={info.color} style={{ borderRadius: 4 }}>
        {info.icon} {info.text}
      </Tag>
    );
  };

  if (mode === 'timeline') {
    return (
      <Card title={t('risk_check_history')} loading={loading}>
        {records.length === 0 ? (
          <Empty
            description={t('risk_no_check_history')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Timeline
            items={records.map((record) => ({
              color: riskLevelMap[record.riskLevel].color,
              children: (
                <div className="pb-4">
                  <div className="flex items-center gap-2 mb-1">
                    <Text strong>{moment(record.checkedAt).format('MM-DD HH:mm')}</Text>
                    {getRiskLevelTag(record.riskLevel)}
                    {record.convId && (
                      <Link
                        href={`/chat/?conv_uid=${record.convId}`}
                        className="text-xs text-blue-500 hover:text-blue-700"
                      >
                        {t('risk_view_conversation')}
                      </Link>
                    )}
                  </div>
                  <Text type="secondary">{record.summary}</Text>
                  {record.suggestions && record.suggestions.length > 0 && (
                    <div className="mt-2">
                      <Text type="secondary" className="text-xs">
                        {t('risk_suggestions')}:
                      </Text>
                      <ul className="text-xs text-gray-500 mt-1 pl-4">
                        {record.suggestions.map((s, idx) => (
                          <li key={idx}>
                            {s.action}
                            {s.auto && <Tag color="blue" className="ml-1">{t('risk_auto')}</Tag>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        )}
      </Card>
    );
  }

  const columns = [
    {
      title: t('risk_check_time'),
      dataIndex: 'checkedAt',
      key: 'checkedAt',
      width: 160,
      render: (time: string) =>
        time ? moment(time).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: t('risk_level'),
      dataIndex: 'riskLevel',
      key: 'riskLevel',
      width: 100,
      render: (level: RiskLevel) => getRiskLevelTag(level),
    },
    {
      title: t('risk_summary'),
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
      render: (summary: string) => (
        <Text ellipsis={{ tooltip: summary }}>{summary || '-'}</Text>
      ),
    },
    {
      title: t('risk_conversation'),
      dataIndex: 'convId',
      key: 'convId',
      width: 120,
      render: (convId: string) =>
        convId ? (
          <Link
            href={`/chat/?conv_uid=${convId}`}
            className="text-blue-500 hover:text-blue-700"
          >
            {t('risk_view')}
          </Link>
        ) : (
          '-'
        ),
    },
  ];

  return (
    <Card title={t('risk_check_history')} loading={loading}>
      <Table
        columns={columns}
        dataSource={records}
        rowKey="id"
        pagination={false}
        size="small"
        locale={{
          emptyText: (
            <Empty
              description={t('risk_no_check_history')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ),
        }}
      />
    </Card>
  );
}