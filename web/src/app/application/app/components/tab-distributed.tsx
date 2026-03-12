'use client';

import { AppContext } from '@/contexts';
import {
  WorkerPoolConfig,
  MonitoringConfig,
  ExtConfig,
  LoadBalanceStrategy,
} from '@/types/app';
import {
  Card,
  Checkbox,
  Form,
  InputNumber,
  Select,
  Switch,
  Empty,
  Alert,
} from 'antd';
import {
  ClusterOutlined,
  MonitorOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useContext, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

const LOAD_BALANCE_OPTIONS: { value: LoadBalanceStrategy; label: string }[] = [
  { value: 'round_robin', label: 'Round Robin' },
  { value: 'least_loaded', label: 'Least Loaded' },
  { value: 'random', label: 'Random' },
  { value: 'weighted', label: 'Weighted' },
];

export default function TabDistributed() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp, fetchUpdateAppLoading } = useContext(AppContext);
  const [form] = Form.useForm();
  const isSaving = useRef(false);
  const lastAppCode = useRef<string | null>(null);

  useEffect(() => {
    if (isSaving.current) {
      return;
    }
    
    const currentAppCode = appInfo?.app_code;
    if (currentAppCode && currentAppCode !== lastAppCode.current) {
      lastAppCode.current = currentAppCode;
    }
    
    if (appInfo?.ext_config) {
      const extConfig = appInfo.ext_config as ExtConfig;
      form.setFieldsValue({
        worker_pool_enabled: extConfig.worker_pool?.enabled || false,
        min_workers: extConfig.worker_pool?.min_workers || 2,
        max_workers: extConfig.worker_pool?.max_workers || 10,
        max_tasks_per_worker: extConfig.worker_pool?.max_tasks_per_worker || 10,
        auto_scale: extConfig.worker_pool?.auto_scale ?? true,
        load_balance: extConfig.worker_pool?.load_balance || 'least_loaded',
        monitoring_enabled: extConfig.monitoring?.enabled || false,
        websocket_enabled: extConfig.monitoring?.websocket_enabled ?? true,
        max_history_events: extConfig.monitoring?.max_history_events || 1000,
      });
    } else {
      form.setFieldsValue({
        worker_pool_enabled: false,
        min_workers: 2,
        max_workers: 10,
        max_tasks_per_worker: 10,
        auto_scale: true,
        load_balance: 'least_loaded',
        monitoring_enabled: false,
        websocket_enabled: true,
        max_history_events: 1000,
      });
    }
  }, [appInfo, form]);

  useEffect(() => {
    if (!fetchUpdateAppLoading && isSaving.current) {
      setTimeout(() => {
        isSaving.current = false;
      }, 100);
    }
  }, [fetchUpdateAppLoading]);

  const buildExtConfig = (values: Record<string, any>): ExtConfig => {
    const workerPool: WorkerPoolConfig = {
      enabled: values.worker_pool_enabled || false,
      min_workers: values.min_workers || 2,
      max_workers: values.max_workers || 10,
      max_tasks_per_worker: values.max_tasks_per_worker || 10,
      auto_scale: values.auto_scale ?? true,
      load_balance: values.load_balance || 'least_loaded',
    };

    const monitoring: MonitoringConfig = {
      enabled: values.monitoring_enabled || false,
      websocket_enabled: values.websocket_enabled ?? true,
      max_history_events: values.max_history_events || 1000,
    };

    const existingExtConfig = (appInfo?.ext_config as ExtConfig) || {};

    return {
      ...existingExtConfig,
      worker_pool: workerPool,
      monitoring: monitoring,
    };
  };

  const saveConfig = (values: Record<string, any>) => {
    isSaving.current = true;
    const extConfig = buildExtConfig(values);
    fetchUpdateApp({ ...appInfo, ext_config: extConfig });
  };

  const workerPoolEnabled = Form.useWatch('worker_pool_enabled', form);
  const monitoringEnabled = Form.useWatch('monitoring_enabled', form);

  const handleValuesChange = (_changedValues: any, allValues: Record<string, any>) => {
    saveConfig(allValues);
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5 custom-scrollbar">
      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        message={t('distributed_info_title', 'Distributed Execution Settings')}
        description={t('distributed_info_desc', 'Configure worker pool and monitoring for parallel processing. Useful for large-scale tasks or multi-instance deployment.')}
        className="mb-5"
      />

      <Form form={form} layout="vertical" className="space-y-6" onValuesChange={handleValuesChange}>
        <Card
          className="shadow-sm border-gray-100/60"
          title={
            <div className="flex items-center gap-2 text-gray-700">
              <ClusterOutlined className="text-green-500" />
              <span>{t('distributed_worker_pool_title', 'Worker Pool')}</span>
            </div>
          }
          extra={
            <Form.Item name="worker_pool_enabled" valuePropName="checked" noStyle>
              <Switch checkedChildren="ON" unCheckedChildren="OFF" />
            </Form.Item>
          }
          size="small"
        >
          {workerPoolEnabled ? (
            <div className="grid grid-cols-2 gap-4">
              <Form.Item name="min_workers" label={t('distributed_min_workers', 'Min Workers')}>
                <InputNumber min={1} max={100} className="w-full" />
              </Form.Item>
              <Form.Item name="max_workers" label={t('distributed_max_workers', 'Max Workers')}>
                <InputNumber min={1} max={100} className="w-full" />
              </Form.Item>
              <Form.Item name="max_tasks_per_worker" label={t('distributed_max_tasks', 'Max Tasks per Worker')}>
                <InputNumber min={1} max={1000} className="w-full" />
              </Form.Item>
              <Form.Item name="load_balance" label={t('distributed_load_balance', 'Load Balance')}>
                <Select options={LOAD_BALANCE_OPTIONS} />
              </Form.Item>
              <Form.Item name="auto_scale" valuePropName="checked" className="col-span-2">
                <Checkbox>{t('distributed_auto_scale_desc', 'Auto-scaling')}</Checkbox>
              </Form.Item>
            </div>
          ) : (
            <Empty description={t('distributed_worker_pool_disabled', 'Worker pool disabled')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Card>

        <Card
          className="shadow-sm border-gray-100/60"
          title={
            <div className="flex items-center gap-2 text-gray-700">
              <MonitorOutlined className="text-purple-500" />
              <span>{t('distributed_monitoring_title', 'Monitoring')}</span>
            </div>
          }
          extra={
            <Form.Item name="monitoring_enabled" valuePropName="checked" noStyle>
              <Switch checkedChildren="ON" unCheckedChildren="OFF" />
            </Form.Item>
          }
          size="small"
        >
          {monitoringEnabled ? (
            <div className="grid grid-cols-2 gap-4">
              <Form.Item name="websocket_enabled" valuePropName="checked">
                <Checkbox>{t('distributed_websocket_desc', 'WebSocket real-time push')}</Checkbox>
              </Form.Item>
              <Form.Item name="max_history_events" label={t('distributed_max_history', 'Max History Events')}>
                <InputNumber min={100} max={10000} step={100} className="w-full" />
              </Form.Item>
            </div>
          ) : (
            <Empty description={t('distributed_monitoring_disabled', 'Monitoring disabled')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Card>
      </Form>
    </div>
  );
}