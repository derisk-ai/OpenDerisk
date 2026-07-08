'use client';

import { apiInterceptors } from '@/client/api';
import {
  listJobs,
  getJobStats,
  createJob,
  retryJob,
  cancelJob,
  deleteJob,
  getJobTypes,
  type Job,
  type JobStats,
  type JobCreate,
  type JobType,
  type JobTypeParam,
} from '@/client/api/job';
import {
  DeleteOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Statistic, Switch, Table, Tag, Typography } from 'antd';
import moment from 'moment';
import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  done: 'success',
  failed: 'error',
};

/**
 * Resolve a JSON-schema property to its effective type/enum, following $ref
 * into params_schema.$defs (pydantic v2 emits enums/constrained models as refs).
 */
function resolveParam(prop: JobTypeParam, $defs?: Record<string, any>): JobTypeParam {
  if (!prop) return { type: 'string' };
  // $ref like "#/$defs/ExtractMode"
  if ((prop as any).$ref && $defs) {
    const ref = (prop as any).$ref as string;
    const name = ref.split('/').pop();
    const def = $defs[name];
    if (def) return resolveParam(def, $defs);
  }
  // allOf with a single $ref (pydantic often wraps enums this way)
  if ((prop as any).allOf && $defs) {
    const inner = (prop as any).allOf[0];
    if (inner?.$ref) {
      const name = inner.$ref.split('/').pop();
      const def = $defs[name];
      if (def) return resolveParam(def, $defs);
    }
  }
  return prop;
}

/** Render one JSON-schema property as an antd form field. */
function ParamField({
  name,
  param,
  required,
}: {
  name: string;
  param: JobTypeParam;
  required: boolean;
}) {
  const t = param?.type || 'string';
  const label = name + (required ? ' *' : '');
  const placeholder = param?.description || name;

  if (param?.enum) {
    return (
      <Form.Item name={name} label={label} tooltip={param?.description} rules={required ? [{ required: true }] : []}>
        <Select
          allowClear={!required}
          placeholder={placeholder}
          options={param.enum.map((v: any) => ({ label: String(v), value: v }))}
        />
      </Form.Item>
    );
  }
  if (t === 'integer' || t === 'number') {
    return (
      <Form.Item name={name} label={label} tooltip={param?.description} rules={required ? [{ required: true }] : []}>
        <InputNumber style={{ width: '100%' }} placeholder={placeholder} />
      </Form.Item>
    );
  }
  if (t === 'boolean') {
    return (
      <Form.Item name={name} label={label} tooltip={param?.description} valuePropName="checked">
        <Switch />
      </Form.Item>
    );
  }
  // string / object / array — use text input (objects can be JSON)
  return (
    <Form.Item name={name} label={label} tooltip={param?.description} rules={required ? [{ required: true }] : []}>
      <Input placeholder={placeholder} />
    </Form.Item>
  );
}

export default function JobsPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [filters, setFilters] = useState<{ job_type?: string; status?: string; space_slug?: string }>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedType, setSelectedType] = useState<string | undefined>();
  const [form] = Form.useForm<any>();

  // load registered job types (for the create form)
  const { data: jobTypes } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getJobTypes());
    if (err) return [];
    return res || [];
  });

  const currentType: JobType | undefined = useMemo(
    () => jobTypes?.find(jt => jt.job_type === selectedType),
    [jobTypes, selectedType],
  );
  const paramsSchema = currentType?.params_schema;
  const requiredSet = new Set(paramsSchema?.required || []);

  // stats
  const { data: stats, loading: statsLoading, refresh: refreshStats } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getJobStats());
    if (err) return null;
    return res;
  });

  const {
    data: jobs,
    loading: jobsLoading,
    refresh: refreshJobs,
  } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(listJobs(filters));
      if (err) return { items: [], total: 0 };
      return res || { items: [], total: 0 };
    },
    { refreshDeps: [JSON.stringify(filters)] },
  );

  const runRefresh = () => { refreshJobs(); refreshStats(); };

  const { run: runRetry, loading: retryLoading } = useRequest(
    async (id: string) => { const [err] = await apiInterceptors(retryJob(id)); if (err) throw err; },
    { manual: true, onSuccess: () => { message.success('retried'); runRefresh(); }, onError: () => message.error('retry failed') },
  );
  const { run: runCancel, loading: cancelLoading } = useRequest(
    async (id: string) => { const [err] = await apiInterceptors(cancelJob(id)); if (err) throw err; },
    { manual: true, onSuccess: () => { message.success('cancelled'); runRefresh(); }, onError: () => message.error('cancel failed') },
  );
  const { run: runDelete, loading: deleteLoading } = useRequest(
    async (id: string) => { const [err] = await apiInterceptors(deleteJob(id)); if (err) throw err; },
    { manual: true, onSuccess: () => { message.success('deleted'); runRefresh(); }, onError: () => message.error('delete failed') },
  );
  const { run: runCreate, loading: createLoading } = useRequest(
    async (vals: any) => {
      if (!selectedType) throw new Error('select a job type');
      // split dynamic schema fields (payload) from the engine-level fields
      const { priority, max_attempts, run_after_seconds, not_before, required_worker, ...payload } = vals;
      const req: JobCreate = {
        job_type: selectedType,
        payload,
        priority,
        max_attempts,
        run_after_seconds,
        not_before,
        required_worker,
      };
      const [err] = await apiInterceptors(createJob(req));
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success('created');
        setCreateOpen(false);
        form.resetFields();
        setSelectedType(undefined);
        runRefresh();
      },
      onError: (e: any) => message.error(e?.message || 'create failed'),
    },
  );

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 180, ellipsis: true,
      render: (id: string) => <Text code className="text-xs">{id}</Text> },
    { title: 'Type', dataIndex: 'job_type', key: 'job_type', width: 160,
      render: (v: string) => <Tag>{v}</Tag> },
    { title: 'Space', dataIndex: 'space_slug', key: 'space_slug', width: 120, render: (v?: string) => v || '-' },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 120,
      render: (s: string, r: Job) => {
        const phase = r.result?.phase;
        const label = s === 'running' && phase ? phase : s;
        return <Tag color={STATUS_COLOR[s] || 'default'}>{label}</Tag>;
      } },
    { title: 'Priority', dataIndex: 'priority', key: 'priority', width: 70 },
    { title: 'Attempts', key: 'attempts', width: 90,
      render: (_: any, r: Job) => `${r.attempts}/${r.max_attempts}` },
    { title: 'Executor', dataIndex: 'executed_by', key: 'executed_by', width: 150, ellipsis: true,
      render: (v?: string) => v ? <Text code className="text-xs">{v}</Text> : '-' },
    { title: 'Scheduled', dataIndex: 'not_before', key: 'not_before', width: 160,
      render: (v?: string) => v ? moment(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
    { title: 'Affinity', dataIndex: 'required_worker', key: 'required_worker', width: 120,
      render: (v?: string[]) => v?.length ? v.map(tg => <Tag key={tg} color="purple">{tg}</Tag>) : '-' },
    { title: 'Created', dataIndex: 'gmt_created', key: 'gmt_created', width: 160,
      render: (v?: string) => v ? moment(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
    { title: 'Operation', key: 'op', width: 160, fixed: 'right' as const,
      render: (_: any, r: Job) => (
        <Space size="small">
          {r.status === 'failed' && (
            <Button size="small" icon={<PlayCircleOutlined />} loading={retryLoading} onClick={() => runRetry(r.id)}>retry</Button>
          )}
          {r.status === 'pending' && (
            <Button size="small" icon={<StopOutlined />} loading={cancelLoading} onClick={() => runCancel(r.id)}>cancel</Button>
          )}
          <Popconfirm title="Delete this job?" onConfirm={() => runDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} loading={deleteLoading} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-4">
      <Title level={3}>Jobs</Title>

      <Space className="mb-4" style={{ width: '100%' }} wrap>
        <Select
          placeholder="job type"
          allowClear
          style={{ width: 200 }}
          options={(jobTypes || []).map(jt => ({ label: jt.job_type, value: jt.job_type }))}
          onChange={v => setFilters(f => ({ ...f, job_type: v }))}
        />
        <Select
          placeholder="status"
          allowClear
          style={{ width: 140 }}
          options={['pending', 'running', 'done', 'failed'].map(s => ({ label: s, value: s }))}
          onChange={v => setFilters(f => ({ ...f, status: v }))}
        />
        <Input
          placeholder="space slug"
          allowClear
          style={{ width: 180 }}
          onChange={e => setFilters(f => ({ ...f, space_slug: e.target.value || undefined }))}
        />
        <Button icon={<ReloadOutlined />} onClick={runRefresh}>refresh</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setSelectedType(undefined); setCreateOpen(true); }}>new job</Button>
      </Space>

      <Space className="mb-4" size="large">
        <Statistic title="Total" value={stats?.total ?? 0} loading={statsLoading} />
        <Statistic title="Pending" value={stats?.by_status?.pending ?? 0} />
        <Statistic title="Running" value={stats?.by_status?.running ?? 0} />
        <Statistic title="Done" value={stats?.by_status?.done ?? 0} />
        <Statistic title="Failed" value={stats?.by_status?.failed ?? 0} />
      </Space>

      <Card>
        <Table
          rowKey="id"
          size="small"
          loading={jobsLoading}
          dataSource={jobs?.items || []}
          columns={columns}
          scroll={{ x: 1500 }}
          pagination={{ total: jobs?.total ?? 0, pageSize: 20, showSizeChanger: false }}
        />
      </Card>

      <Modal
        title="New Job"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={createLoading}
        onOk={() => form.validateFields().then(v => runCreate(v))}
        width={600}
      >
        <Form form={form} layout="vertical" initialValues={{ priority: 5, max_attempts: 3 }}>
          <Form.Item label="Job Type" required>
            <Select
              placeholder="select a registered job type"
              value={selectedType}
              onChange={v => { setSelectedType(v); form.resetFields(); }}
              options={(jobTypes || []).map(jt => ({
                label: jt.job_type + (jt.description ? ` — ${jt.description}` : ''),
                value: jt.job_type,
              }))}
            />
          </Form.Item>

          {currentType?.description && (
            <Text type="secondary" className="block mb-2">{currentType.description}</Text>
          )}

          {/* dynamic payload fields from params_schema */}
          {paramsSchema?.properties && Object.entries(paramsSchema.properties).map(([name, raw]) => {
            const param = resolveParam(raw, paramsSchema.$defs);
            return (
              <ParamField
                key={name}
                name={name}
                param={param}
                required={requiredSet.has(name)}
              />
            );
          })}

          {/* engine-level fields (not part of payload) */}
          {selectedType && (
            <>
              <Space>
                <Form.Item name="priority" label="Priority">
                  <InputNumber min={1} max={10} />
                </Form.Item>
                <Form.Item name="max_attempts" label="Max Attempts">
                  <InputNumber min={1} max={10} />
                </Form.Item>
              </Space>
              <Form.Item name="run_after_seconds" label="Run After (seconds)">
                <InputNumber min={0} placeholder="0 = immediately" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="not_before" label="Not Before (ISO time)">
                <Input placeholder="2026-07-10T10:00:00" />
              </Form.Item>
              <Form.Item name="required_worker" label="Affinity Tags">
                <Select mode="tags" placeholder="optional, e.g. gpu" tokenSeparators={[',']} />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
}