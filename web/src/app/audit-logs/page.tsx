'use client';

import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequest } from 'ahooks';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Typography,
  Input,
  Select,
  DatePicker,
  Row,
  Col,
  Statistic,
  Progress,
  Tooltip,
  Empty,
  Descriptions,
  Modal,
  Badge,
  Divider,
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  SafetyOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  ToolOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import moment from 'moment';
import type { AuthorizationAuditLog, AuthorizationAuditStats, ToolUsageStats, AuditLogQueryParams } from '@/client/api/authorization/audit';
import { listAuditLogs, getAuditStats, getToolUsageStats } from '@/client/api/authorization/audit';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

// Risk level color mapping
const RISK_LEVEL_COLORS: Record<string, string> = {
  safe: 'success',
  low: 'blue',
  medium: 'warning',
  high: 'orange',
  critical: 'error',
};

// Decision color mapping
const DECISION_COLORS: Record<string, string> = {
  granted: 'success',
  denied: 'error',
  cached: 'processing',
  need_confirmation: 'warning',
};

// Decision icon mapping
const DECISION_ICONS: Record<string, React.ReactNode> = {
  granted: <CheckCircleOutlined />,
  denied: <CloseCircleOutlined />,
  cached: <ThunderboltOutlined />,
  need_confirmation: <QuestionCircleOutlined />,
};

export default function AuditLogsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useState<AuditLogQueryParams>({
    page: 1,
    page_size: 20,
  });
  const [detailLog, setDetailLog] = useState<AuthorizationAuditLog | null>(null);

  // Fetch audit logs
  const { data: logsData, loading: logsLoading, refresh: refreshLogs } = useRequest(
    async () => {
      const res = await listAuditLogs(searchParams);
      if (res.data?.success && res.data.data) {
        return res.data.data;
      }
      return { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
    },
    { refreshDeps: [searchParams] }
  );

  // Fetch statistics
  const { data: statsData, loading: statsLoading, refresh: refreshStats } = useRequest(
    async () => {
      const params: any = {};
      if (searchParams.start_time) params.start_time = searchParams.start_time;
      if (searchParams.end_time) params.end_time = searchParams.end_time;
      
      const res = await getAuditStats(params);
      if (res.data?.success && res.data.data) {
        return res.data.data;
      }
      return null;
    },
    { refreshDeps: [searchParams.start_time, searchParams.end_time] }
  );

  // Fetch tool usage stats
  const { data: toolStatsData, loading: toolStatsLoading } = useRequest(
    async () => {
      const params: any = {};
      if (searchParams.start_time) params.start_time = searchParams.start_time;
      if (searchParams.end_time) params.end_time = searchParams.end_time;
      
      const res = await getToolUsageStats(params);
      if (res.data?.success && res.data.data) {
        return res.data.data;
      }
      return [];
    },
    { refreshDeps: [searchParams.start_time, searchParams.end_time] }
  );

  // Handle search
  const handleSearch = () => {
    setSearchParams({ ...searchParams, page: 1 });
  };

  // Handle reset
  const handleReset = () => {
    setSearchParams({
      page: 1,
      page_size: 20,
    });
  };

  // Handle page change
  const handlePageChange = (page: number, pageSize: number) => {
    setSearchParams({ ...searchParams, page, page_size: pageSize });
  };

  // Handle date range change
  const handleDateRangeChange = (dates: any) => {
    if (dates) {
      setSearchParams({
        ...searchParams,
        start_time: dates[0].toISOString(),
        end_time: dates[1].toISOString(),
        page: 1,
      });
    } else {
      const newParams = { ...searchParams };
      delete newParams.start_time;
      delete newParams.end_time;
      setSearchParams({ ...newParams, page: 1 });
    }
  };

  // Table columns
  const columns = [
    {
      title: t('audit_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time: string) => time ? moment(time).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: t('audit_tool'),
      dataIndex: 'tool_name',
      key: 'tool_name',
      width: 120,
      render: (name: string) => (
        <Space>
          <ToolOutlined className="text-gray-400" />
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: t('audit_decision'),
      dataIndex: 'decision',
      key: 'decision',
      width: 100,
      render: (decision: string) => (
        <Tag color={DECISION_COLORS[decision] || 'default'} icon={DECISION_ICONS[decision]}>
          {t(`audit_decision_${decision}`)}
        </Tag>
      ),
    },
    {
      title: t('audit_risk_level'),
      dataIndex: 'risk_level',
      key: 'risk_level',
      width: 100,
      render: (level: string, record: AuthorizationAuditLog) => (
        <Tooltip title={t(`audit_risk_score`) + `: ${record.risk_score || 0}`}>
          <Badge 
            status={RISK_LEVEL_COLORS[level] === 'error' ? 'error' : RISK_LEVEL_COLORS[level] === 'warning' ? 'warning' : 'success'} 
            text={t(`audit_risk_${level}`)}
          />
        </Tooltip>
      ),
    },
    {
      title: t('audit_agent'),
      dataIndex: 'agent_name',
      key: 'agent_name',
      width: 120,
      render: (name: string) => name || '-',
    },
    {
      title: t('audit_session'),
      dataIndex: 'session_id',
      key: 'session_id',
      width: 180,
      ellipsis: true,
      render: (id: string) => (
        <Tooltip title={id}>
          <Text code className="text-xs">{id ? `${id.slice(0, 16)}...` : '-'}</Text>
        </Tooltip>
      ),
    },
    {
      title: t('audit_cached'),
      dataIndex: 'cached',
      key: 'cached',
      width: 80,
      render: (cached: boolean) => cached ? <Tag color="blue">{t('audit_yes')}</Tag> : <Tag>{t('audit_no')}</Tag>,
    },
    {
      title: t('audit_duration'),
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      render: (ms: number) => ms ? `${ms.toFixed(1)}ms` : '-',
    },
    {
      title: t('Operation'),
      key: 'action',
      width: 80,
      render: (_: any, record: AuthorizationAuditLog) => (
        <Button
          type="link"
          size="small"
          onClick={() => setDetailLog(record)}
        >
          {t('audit_detail')}
        </Button>
      ),
    },
  ];

  // Calculate grant rate
  const grantRate = useMemo(() => {
    if (!statsData || statsData.total_count === 0) return 0;
    return ((statsData.granted_count + statsData.cached_count) / statsData.total_count * 100).toFixed(1);
  }, [statsData]);

  return (
    <div className="p-6">
      <div className="mb-6">
        <Title level={3}>{t('audit_logs_title')}</Title>
        <Text type="secondary">{t('audit_logs_description')}</Text>
      </div>

      {/* Statistics Cards */}
      <Row gutter={16} className="mb-6">
        <Col span={4}>
          <Card loading={statsLoading}>
            <Statistic
              title={t('audit_total_checks')}
              value={statsData?.total_count || 0}
              prefix={<SafetyOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={statsLoading}>
            <Statistic
              title={t('audit_granted')}
              value={statsData?.granted_count || 0}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={statsLoading}>
            <Statistic
              title={t('audit_denied')}
              value={statsData?.denied_count || 0}
              valueStyle={{ color: '#ff4d4f' }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={statsLoading}>
            <Statistic
              title={t('audit_cached')}
              value={statsData?.cached_count || 0}
              valueStyle={{ color: '#1890ff' }}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={statsLoading}>
            <Statistic
              title={t('audit_high_risk')}
              value={(statsData?.high_risk_count || 0) + (statsData?.critical_risk_count || 0)}
              valueStyle={{ color: '#fa8c16' }}
              prefix={<ExclamationCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={statsLoading}>
            <Statistic
              title={t('audit_grant_rate')}
              value={grantRate}
              suffix="%"
              valueStyle={{ color: parseFloat(grantRate as string) > 90 ? '#52c41a' : '#1890ff' }}
            />
            <Progress 
              percent={parseFloat(grantRate as string)} 
              showInfo={false} 
              strokeColor={{
                '0%': '#108ee9',
                '100%': '#87d068',
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* Tool Usage Stats */}
      <Card title={t('audit_tool_usage')} className="mb-6" loading={toolStatsLoading}>
        <div className="flex flex-wrap gap-4">
          {toolStatsData?.slice(0, 10).map((stat: ToolUsageStats) => (
            <div key={stat.tool_name} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg">
              <ToolOutlined className="text-gray-500" />
              <Text strong>{stat.tool_name}</Text>
              <Divider type="vertical" />
              <Text type="secondary">{t('audit_total')}: {stat.total}</Text>
              <Tag color="green">{stat.granted}</Tag>
              <Tag color="red">{stat.denied}</Tag>
            </div>
          ))}
          {(!toolStatsData || toolStatsData.length === 0) && (
            <Empty description={t('audit_no_data')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </div>
      </Card>

      {/* Filters */}
      <Card className="mb-4">
        <Row gutter={16}>
          <Col span={6}>
            <Input
              placeholder={t('audit_search_session')}
              prefix={<SearchOutlined />}
              value={searchParams.session_id || ''}
              onChange={(e) => setSearchParams({ ...searchParams, session_id: e.target.value || undefined })}
              allowClear
            />
          </Col>
          <Col span={4}>
            <Input
              placeholder={t('audit_search_tool')}
              value={searchParams.tool_name || ''}
              onChange={(e) => setSearchParams({ ...searchParams, tool_name: e.target.value || undefined })}
              allowClear
            />
          </Col>
          <Col span={4}>
            <Select
              placeholder={t('audit_filter_decision')}
              value={searchParams.decision}
              onChange={(v) => setSearchParams({ ...searchParams, decision: v || undefined })}
              allowClear
              style={{ width: '100%' }}
            >
              <Option value="granted">{t('audit_decision_granted')}</Option>
              <Option value="denied">{t('audit_decision_denied')}</Option>
              <Option value="cached">{t('audit_decision_cached')}</Option>
              <Option value="need_confirmation">{t('audit_decision_need_confirmation')}</Option>
            </Select>
          </Col>
          <Col span={4}>
            <Select
              placeholder={t('audit_filter_risk')}
              value={searchParams.risk_level}
              onChange={(v) => setSearchParams({ ...searchParams, risk_level: v || undefined })}
              allowClear
              style={{ width: '100%' }}
            >
              <Option value="safe">{t('audit_risk_safe')}</Option>
              <Option value="low">{t('audit_risk_low')}</Option>
              <Option value="medium">{t('audit_risk_medium')}</Option>
              <Option value="high">{t('audit_risk_high')}</Option>
              <Option value="critical">{t('audit_risk_critical')}</Option>
            </Select>
          </Col>
          <Col span={6}>
            <RangePicker
              showTime
              onChange={handleDateRangeChange}
              style={{ width: '100%' }}
            />
          </Col>
        </Row>
        <Row gutter={16} className="mt-4">
          <Col span={24}>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
                {t('Search')}
              </Button>
              <Button onClick={handleReset}>
                {t('Reset')}
              </Button>
              <Button icon={<ReloadOutlined />} onClick={() => { refreshLogs(); refreshStats(); }}>
                {t('Refresh')}
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Logs Table */}
      <Card>
        <Table
          columns={columns}
          dataSource={logsData?.items || []}
          rowKey="id"
          loading={logsLoading}
          pagination={{
            current: logsData?.page || 1,
            pageSize: logsData?.page_size || 20,
            total: logsData?.total || 0,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => t('audit_total_records', { total }),
            onChange: handlePageChange,
          }}
          locale={{
            emptyText: <Empty description={t('audit_no_logs')} />,
          }}
          scroll={{ x: 1200 }}
        />
      </Card>

      {/* Detail Modal */}
      <Modal
        title={
          <Space>
            <SafetyOutlined />
            {t('audit_detail_title')}
          </Space>
        }
        open={!!detailLog}
        onCancel={() => setDetailLog(null)}
        footer={null}
        width={700}
      >
        {detailLog && (
          <div>
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label={t('audit_tool')} span={1}>
                <Text strong>{detailLog.tool_name}</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_decision')} span={1}>
                <Tag color={DECISION_COLORS[detailLog.decision]} icon={DECISION_ICONS[detailLog.decision]}>
                  {t(`audit_decision_${detailLog.decision}`)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_risk_level')} span={1}>
                <Badge 
                  status={RISK_LEVEL_COLORS[detailLog.risk_level] === 'error' ? 'error' : RISK_LEVEL_COLORS[detailLog.risk_level] === 'warning' ? 'warning' : 'success'} 
                  text={t(`audit_risk_${detailLog.risk_level}`)}
                />
                <Text type="secondary" className="ml-2">({t('audit_score')}: {detailLog.risk_score})</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_cached')} span={1}>
                {detailLog.cached ? <Tag color="blue">{t('audit_yes')}</Tag> : <Tag>{t('audit_no')}</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_session')} span={2}>
                <Text code>{detailLog.session_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_agent')} span={1}>
                {detailLog.agent_name || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_user')} span={1}>
                {detailLog.user_id || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_time')} span={2}>
                {moment(detailLog.created_at).format('YYYY-MM-DD HH:mm:ss')}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_duration')} span={1}>
                {detailLog.duration_ms ? `${detailLog.duration_ms.toFixed(2)}ms` : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit_action')} span={1}>
                <Tag>{detailLog.action}</Tag>
              </Descriptions.Item>
            </Descriptions>

            {detailLog.risk_factors && detailLog.risk_factors.length > 0 && (
              <div className="mt-4">
                <Text strong>{t('audit_risk_factors')}</Text>
                <div className="mt-2 flex flex-wrap gap-2">
                  {detailLog.risk_factors.map((factor, idx) => (
                    <Tag key={idx} color="orange">{factor}</Tag>
                  ))}
                </div>
              </div>
            )}

            {detailLog.arguments && Object.keys(detailLog.arguments).length > 0 && (
              <div className="mt-4">
                <Text strong>{t('audit_arguments')}</Text>
                <pre className="mt-2 p-3 bg-gray-50 rounded text-xs overflow-auto max-h-40">
                  {JSON.stringify(detailLog.arguments, null, 2)}
                </pre>
              </div>
            )}

            {detailLog.reason && (
              <div className="mt-4">
                <Text strong>{t('audit_reason')}</Text>
                <Paragraph className="mt-2 p-3 bg-gray-50 rounded">
                  {detailLog.reason}
                </Paragraph>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}