'use client';

import { apiInterceptors, getCronJobs, getCronStatus, deleteCronJob, runCronJob } from '@/client/api';
import { CronJob } from '@/client/api/cron';
import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Card, Space, Switch, Table, Tag, Typography, Popconfirm, Tooltip, Empty } from 'antd';
import moment from 'moment';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

export default function CronPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { message } = App.useApp();
  const [includeDisabled, setIncludeDisabled] = useState(false);

  // Fetch status
  const { data: statusData, loading: statusLoading, refresh: refreshStatus } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getCronStatus());
    if (err) {
      return null;
    }
    return res;
  });

  // Fetch jobs
  const {
    data: jobsData,
    loading: jobsLoading,
    refresh: refreshJobs,
  } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getCronJobs(includeDisabled));
      if (err) {
        return [];
      }
      return res || [];
    },
    {
      refreshDeps: [includeDisabled],
    }
  );

  // Delete job
  const { run: runDeleteJob, loading: deleteLoading } = useRequest(
    async (jobId: string) => {
      const [err] = await apiInterceptors(deleteCronJob(jobId));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('cron_delete_success'));
        refreshJobs();
        refreshStatus();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  // Run job now
  const { run: runJobNow, loading: runLoading } = useRequest(
    async (jobId: string) => {
      const [err] = await apiInterceptors(runCronJob(jobId, true));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('cron_run_success'));
        refreshJobs();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  const columns = [
    {
      title: t('cron_name'),
      dataIndex: 'name',
      key: 'name',
      width: 150,
      render: (name: string, record: CronJob) => (
        <Link href={`/cron/edit?id=${record.id}`} className="text-blue-500 hover:text-blue-700">
          {name}
        </Link>
      ),
    },
    {
      title: t('cron_description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc: string) => desc || '-',
    },
    {
      title: t('cron_created_at'),
      dataIndex: 'gmt_created',
      key: 'created_at',
      width: 160,
      render: (created: string) => created ? moment(created).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: t('cron_schedule_type'),
      dataIndex: ['schedule', 'kind'],
      key: 'schedule_kind',
      width: 100,
      render: (kind: string) => {
        const kindMap: Record<string, { label: string; color: string }> = {
          cron: { label: t('cron_cron_expr'), color: 'blue' },
          every: { label: t('cron_interval'), color: 'green' },
          at: { label: t('cron_once'), color: 'orange' },
        };
        const item = kindMap[kind] || { label: kind, color: 'default' };
        return <Tag color={item.color}>{item.label}</Tag>;
      },
    },
    {
      title: t('cron_schedule'),
      key: 'schedule',
      width: 150,
      render: (_: any, record: CronJob) => {
        const { schedule } = record;
        if (schedule.kind === 'cron') {
          return <Text code>{schedule.expr}</Text>;
        } else if (schedule.kind === 'every') {
          const seconds = Math.floor((schedule.every_ms || 0) / 1000);
          if (seconds < 60) return `${seconds}s`;
          if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
          return `${Math.floor(seconds / 3600)}h`;
        } else if (schedule.kind === 'at') {
          return moment(schedule.at).format('YYYY-MM-DD HH:mm:ss');
        }
        return '-';
      },
    },
    {
      title: t('cron_status'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'success' : 'default'}>{enabled ? t('cron_enabled') : t('cron_disabled')}</Tag>
      ),
    },
    {
      title: t('cron_last_run'),
      dataIndex: ['state', 'last_run_at_ms'],
      key: 'last_run',
      width: 160,
      render: (ms: number) => (ms ? moment(ms).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: t('cron_next_run'),
      dataIndex: ['state', 'next_run_at_ms'],
      key: 'next_run',
      width: 160,
      render: (ms: number) => (ms ? moment(ms).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: t('Operation'),
      key: 'action',
      width: 120,
      render: (_: any, record: CronJob) => (
        <Space size="small">
          <Tooltip title={t('Edit')}>
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => router.push(`/cron/edit?id=${record.id}`)}
            />
          </Tooltip>
          <Tooltip title={t('cron_run_now')}>
            <Button
              type="text"
              icon={<PlayCircleOutlined />}
              loading={runLoading}
              onClick={() => runJobNow(record.id)}
            />
          </Tooltip>
          <Popconfirm
            title={t('cron_confirm_delete')}
            onConfirm={() => runDeleteJob(record.id)}
            okText={t('Yes')}
            cancelText={t('No')}
          >
            <Tooltip title={t('Delete')}>
              <Button type="text" danger icon={<DeleteOutlined />} loading={deleteLoading} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-6 [&_table]:table">
      <div className="mb-6">
        <Title level={3}>{t('cron_page_title')}</Title>
      </div>

      {/* Status Card */}
      <Card className="mb-6" loading={statusLoading}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div>
              <Text type="secondary">{t('cron_scheduler_status')}</Text>
              <div className="mt-1">
                <Tag color={statusData?.running ? 'processing' : 'default'}>
                  {statusData?.running ? t('cron_running') : t('cron_stopped')}
                </Tag>
              </div>
            </div>
            <div>
              <Text type="secondary">{t('cron_total_jobs')}</Text>
              <div className="mt-1 text-xl font-semibold">{statusData?.jobs || 0}</div>
            </div>
            <div>
              <Text type="secondary">{t('cron_enabled_jobs')}</Text>
              <div className="mt-1 text-xl font-semibold text-green-600">{statusData?.enabled_jobs || 0}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Text type="secondary">{t('cron_show_disabled')}</Text>
            <Switch checked={includeDisabled} onChange={setIncludeDisabled} />
          </div>
        </div>
      </Card>

      {/* Jobs Table */}
      <Card
        title={
          <div className="flex items-center justify-between">
            <span>{t('cron_page_title')}</span>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => { refreshJobs(); refreshStatus(); }}>
                {t('Refresh_status')}
              </Button>
              <Link href="/cron/create">
                <Button type="primary" icon={<PlusOutlined />}>
                  {t('cron_create')}
                </Button>
              </Link>
            </Space>
          </div>
        }
      >
        <Table
          columns={columns}
          dataSource={jobsData}
          rowKey="id"
          loading={jobsLoading}
          pagination={{ pageSize: 10 }}
          locale={{
            emptyText: (
              <Empty
                description={t('cron_no_jobs')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
        />
      </Card>
    </div>
  );
}