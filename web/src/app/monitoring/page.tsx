'use client';

import {
  getDashboardData,
  getMonitoringStats,
  resolveAlert,
  createMonitoringWebSocket,
  DashboardEvent,
  MonitoringStats,
  TaskProgress,
  WorkerProgress,
  HealthAlert,
} from '@/client/api/monitoring';
import { apiInterceptors } from '@/client/api';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
  DashboardOutlined,
  TeamOutlined,
  RobotOutlined,
  AlertOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Badge, Button, Card, Col, Progress, Row, Spin, Statistic, Table, Tag, Typography, Empty, List, Tooltip, Space } from 'antd';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import moment from 'moment';

const { Title, Text } = Typography;

// Status color mapping
const TASK_STATUS_COLORS: Record<string, string> = {
  created: 'processing',
  running: 'warning',
  completed: 'success',
  failed: 'error',
};

const WORKER_STATUS_COLORS: Record<string, string> = {
  idle: 'default',
  busy: 'processing',
  stopping: 'warning',
  stopped: 'default',
  error: 'error',
};

const ALERT_SEVERITY_COLORS: Record<string, string> = {
  info: 'processing',
  warning: 'warning',
  error: 'error',
  critical: 'magenta',
};

const ALERT_SEVERITY_ICONS: Record<string, React.ReactNode> = {
  info: <InfoCircleOutlined />,
  warning: <WarningOutlined />,
  error: <ExclamationCircleOutlined />,
  critical: <CloseCircleOutlined />,
};

export default function MonitoringPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [events, setEvents] = useState<DashboardEvent[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const eventsListRef = useRef<HTMLDivElement>(null);

  // Fetch dashboard data
  const {
    data: dashboardData,
    loading: dashboardLoading,
    refresh: refreshDashboard,
  } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getDashboardData());
      if (err) {
        throw err;
      }
      return res;
    },
    {
      pollingInterval: 5000, // Auto refresh every 5 seconds
    }
  );

  // Resolve alert
  const { run: runResolveAlert, loading: resolveLoading } = useRequest(
    async (alertId: string) => {
      const [err] = await apiInterceptors(resolveAlert(alertId));
      if (err) {
        throw err;
      }
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('monitoring_alert_resolved', 'Alert resolved'));
        refreshDashboard();
      },
      onError: () => {
        message.error(t('Error_Message'));
      },
    }
  );

  // WebSocket connection
  useEffect(() => {
    const connectWebSocket = () => {
      const ws = createMonitoringWebSocket(
        (event) => {
          setEvents((prev) => [event, ...prev].slice(0, 100)); // Keep last 100 events
          refreshDashboard();
        },
        () => {
          setWsConnected(false);
          // Reconnect after 3 seconds
          setTimeout(() => {
            wsRef.current = connectWebSocket();
          }, 3000);
        }
      );

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onclose = () => {
        setWsConnected(false);
      };

      return ws;
    };

    wsRef.current = connectWebSocket();

    return () => {
      wsRef.current?.close();
    };
  }, []);

  // Auto scroll to bottom of events list
  useEffect(() => {
    if (eventsListRef.current) {
      eventsListRef.current.scrollTop = 0;
    }
  }, [events]);

  const stats = dashboardData?.stats;
  const tasks = dashboardData?.tasks || [];
  const workers = dashboardData?.workers || [];
  const alerts = dashboardData?.alerts || [];

  // Task columns
  const taskColumns = [
    {
      title: t('monitoring_task_id', 'Task ID'),
      dataIndex: 'task_id',
      key: 'task_id',
      width: 180,
      render: (id: string) => <Text code copyable={{ text: id }}>{id.slice(0, 12)}...</Text>,
    },
    {
      title: t('monitoring_task_goal', 'Goal'),
      dataIndex: 'goal',
      key: 'goal',
      ellipsis: true,
      render: (goal: string) => goal || '-',
    },
    {
      title: t('monitoring_task_status', 'Status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={TASK_STATUS_COLORS[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: t('monitoring_task_progress', 'Progress'),
      key: 'progress',
      width: 200,
      render: (_: any, record: TaskProgress) => (
        <div className="flex items-center gap-2">
          <Progress
            percent={Math.round(record.progress_percent)}
            size="small"
            status={record.status === 'failed' ? 'exception' : record.status === 'completed' ? 'success' : 'active'}
            style={{ width: 100 }}
          />
          <Text type="secondary" className="text-xs">
            {record.current_step}/{record.total_steps}
          </Text>
        </div>
      ),
    },
    {
      title: t('monitoring_task_created', 'Created'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time: string) => (time ? moment(time).format('MM-DD HH:mm:ss') : '-'),
    },
  ];

  // Worker columns
  const workerColumns = [
    {
      title: t('monitoring_worker_id', 'Worker ID'),
      dataIndex: 'worker_id',
      key: 'worker_id',
      width: 150,
      render: (id: string) => <Text code>{id}</Text>,
    },
    {
      title: t('monitoring_worker_pid', 'PID'),
      dataIndex: 'pid',
      key: 'pid',
      width: 80,
      render: (pid: number | null) => pid || '-',
    },
    {
      title: t('monitoring_worker_status', 'Status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={WORKER_STATUS_COLORS[status] || 'default'}>
          <Badge status={status === 'busy' ? 'processing' : status === 'idle' ? 'success' : 'default'} />
          {status}
        </Tag>
      ),
    },
    {
      title: t('monitoring_worker_tasks', 'Tasks'),
      key: 'tasks',
      width: 150,
      render: (_: any, record: WorkerProgress) => (
        <Text type="secondary">
          {record.completed_tasks}/{record.total_tasks}
          {record.current_tasks > 0 && (
            <Tag color="processing" className="ml-1">{record.current_tasks} running</Tag>
          )}
        </Text>
      ),
    },
    {
      title: t('monitoring_worker_resources', 'Resources'),
      key: 'resources',
      width: 150,
      render: (_: any, record: WorkerProgress) => (
        <div className="text-xs">
          <div>CPU: {record.cpu_percent?.toFixed(1)}%</div>
          <div>MEM: {record.memory_mb?.toFixed(0)}MB</div>
        </div>
      ),
    },
    {
      title: t('monitoring_worker_heartbeat', 'Last Heartbeat'),
      dataIndex: 'last_heartbeat',
      key: 'last_heartbeat',
      width: 160,
      render: (time: string) => (time ? moment(time).fromNow() : '-'),
    },
  ];

  return (
    <div className="p-6 min-h-screen bg-gray-50/50">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <DashboardOutlined className="text-2xl text-blue-500" />
          <Title level={3} className="m-0">{t('monitoring_page_title', 'Monitoring Dashboard')}</Title>
        </div>
        <Space>
          <Badge 
            status={wsConnected ? 'success' : 'error'} 
            text={wsConnected ? t('monitoring_ws_connected', 'WebSocket Connected') : t('monitoring_ws_disconnected', 'Disconnected')} 
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refreshDashboard()}
            loading={dashboardLoading}
          >
            {t('Refresh_status')}
          </Button>
        </Space>
      </div>

      {/* Stats Cards */}
      <Row gutter={[16, 16]} className="mb-6">
        <Col xs={24} sm={12} lg={6}>
          <Card className="shadow-sm hover:shadow-md transition-shadow">
            <Statistic
              title={
                <div className="flex items-center gap-2">
                  <ThunderboltOutlined className="text-blue-500" />
                  <span>{t('monitoring_active_tasks', 'Active Tasks')}</span>
                </div>
              }
              value={stats?.tasks?.active || 0}
              suffix={`/ ${stats?.tasks?.total_created || 0}`}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="shadow-sm hover:shadow-md transition-shadow">
            <Statistic
              title={
                <div className="flex items-center gap-2">
                  <TeamOutlined className="text-green-500" />
                  <span>{t('monitoring_active_workers', 'Active Workers')}</span>
                </div>
              }
              value={stats?.workers?.active || 0}
              suffix={`/ ${stats?.workers?.total || 0}`}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="shadow-sm hover:shadow-md transition-shadow">
            <Statistic
              title={
                <div className="flex items-center gap-2">
                  <RobotOutlined className="text-purple-500" />
                  <span>{t('monitoring_running_subagents', 'Running Subagents')}</span>
                </div>
              }
              value={stats?.subagents?.running || 0}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="shadow-sm hover:shadow-md transition-shadow">
            <Statistic
              title={
                <div className="flex items-center gap-2">
                  <AlertOutlined className="text-red-500" />
                  <span>{t('monitoring_unresolved_alerts', 'Unresolved Alerts')}</span>
                </div>
              }
              value={stats?.alerts?.unresolved || 0}
              valueStyle={{ color: stats?.alerts?.unresolved ? '#ff4d4f' : '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Main Content */}
      <Row gutter={[16, 16]}>
        {/* Tasks Table */}
        <Col xs={24} lg={14}>
          <Card
            className="shadow-sm"
            title={
              <div className="flex items-center gap-2">
                <ThunderboltOutlined className="text-blue-500" />
                <span>{t('monitoring_tasks_title', 'Tasks')}</span>
                <Tag color="blue">{tasks.length}</Tag>
              </div>
            }
          >
            <Table
              columns={taskColumns}
              dataSource={tasks}
              rowKey="task_id"
              loading={dashboardLoading}
              size="small"
              pagination={{ pageSize: 5, size: 'small' }}
              scroll={{ x: 800 }}
              locale={{
                emptyText: (
                  <Empty
                    description={t('monitoring_no_tasks', 'No tasks')}
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  />
                ),
              }}
            />
          </Card>
        </Col>

        {/* Workers Table */}
        <Col xs={24} lg={10}>
          <Card
            className="shadow-sm"
            title={
              <div className="flex items-center gap-2">
                <TeamOutlined className="text-green-500" />
                <span>{t('monitoring_workers_title', 'Workers')}</span>
                <Tag color="green">{workers.length}</Tag>
              </div>
            }
          >
            <Table
              columns={workerColumns}
              dataSource={workers}
              rowKey="worker_id"
              loading={dashboardLoading}
              size="small"
              pagination={{ pageSize: 5, size: 'small' }}
              scroll={{ x: 700 }}
              locale={{
                emptyText: (
                  <Empty
                    description={t('monitoring_no_workers', 'No workers')}
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  />
                ),
              }}
            />
          </Card>
        </Col>

        {/* Alerts Panel */}
        <Col xs={24} lg={12}>
          <Card
            className="shadow-sm"
            title={
              <div className="flex items-center gap-2">
                <AlertOutlined className="text-red-500" />
                <span>{t('monitoring_alerts_title', 'Alerts')}</span>
                {stats?.alerts?.unresolved ? (
                  <Tag color="error">{stats.alerts.unresolved} unresolved</Tag>
                ) : null}
              </div>
            }
          >
            {alerts.length > 0 ? (
              <List
                dataSource={alerts}
                renderItem={(alert) => (
                  <List.Item
                    actions={[
                      <Button
                        key="resolve"
                        type="link"
                        size="small"
                        onClick={() => runResolveAlert(alert.alert_id)}
                        loading={resolveLoading}
                      >
                        <CheckCircleOutlined /> {t('monitoring_resolve', 'Resolve')}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={ALERT_SEVERITY_ICONS[alert.severity]}
                      title={
                        <div className="flex items-center gap-2">
                          <Tag color={ALERT_SEVERITY_COLORS[alert.severity]}>{alert.severity}</Tag>
                          <span>{alert.alert_type}</span>
                        </div>
                      }
                      description={
                        <div>
                          <Text>{alert.message}</Text>
                          <br />
                          <Text type="secondary" className="text-xs">
                            {moment(alert.timestamp).format('YYYY-MM-DD HH:mm:ss')}
                          </Text>
                        </div>
                      }
                    />
                  </List.Item>
                )}
                style={{ maxHeight: 300, overflow: 'auto' }}
              />
            ) : (
              <Empty
                description={t('monitoring_no_alerts', 'No active alerts')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
          </Card>
        </Col>

        {/* Real-time Events */}
        <Col xs={24} lg={12}>
          <Card
            className="shadow-sm"
            title={
              <div className="flex items-center gap-2">
                <SyncOutlined spin={wsConnected} className="text-blue-500" />
                <span>{t('monitoring_events_title', 'Real-time Events')}</span>
                <Badge count={events.length} style={{ backgroundColor: '#1890ff' }} />
              </div>
            }
          >
            <div
              ref={eventsListRef}
              style={{ maxHeight: 300, overflow: 'auto' }}
              className="space-y-1"
            >
              {events.length > 0 ? (
                events.slice(0, 50).map((event, idx) => (
                  <div
                    key={`${event.timestamp}-${idx}`}
                    className="flex items-center gap-2 py-1 px-2 rounded hover:bg-gray-50 text-xs"
                  >
                    <Tag color="blue" className="m-0 text-xs">{event.event_type}</Tag>
                    {event.task_id && (
                      <Tooltip title={event.task_id}>
                        <Text code className="text-xs">{event.task_id.slice(0, 8)}...</Text>
                      </Tooltip>
                    )}
                    <Text type="secondary" className="text-xs ml-auto">
                      {moment(event.timestamp).format('HH:mm:ss')}
                    </Text>
                  </div>
                ))
              ) : (
                <Empty
                  description={t('monitoring_no_events', 'Waiting for events...')}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}