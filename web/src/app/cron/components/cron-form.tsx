'use client';

import { CronJobCreate } from '@/client/api/cron';
import { Input, Select, InputNumber, Switch, Form, Card, Divider } from 'antd';
import { useTranslation } from 'react-i18next';

const { TextArea } = Input;

interface CronFormProps {
  form: any;
  initialValues?: Partial<CronJobCreate>;
}

export default function CronForm({ form, initialValues }: CronFormProps) {
  const { t } = useTranslation();

  const scheduleKind = Form.useWatch(['schedule', 'kind'], form);
  const sessionMode = Form.useWatch(['payload', 'session_mode'], form);

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{
        enabled: true,
        ...initialValues,
        schedule: {
          kind: 'cron',
          tz: 'Asia/Shanghai',
          ...initialValues?.schedule,
        },
        payload: {
          kind: 'agentTurn',
          session_mode: 'isolated',
          ...initialValues?.payload,
        },
      }}
    >
      {/* 基础信息 */}
      <Card title={t('baseinfo_basic_info')} className="mb-4" size="small">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Form.Item
            name="name"
            label={t('cron_name')}
            rules={[{ required: true, message: t('Please_Input') + t('cron_name') }]}
          >
            <Input placeholder={t('Please_Input') + t('cron_name')} />
          </Form.Item>
          <Form.Item name="enabled" label={t('cron_status')} valuePropName="checked">
            <Switch checkedChildren={t('cron_enabled')} unCheckedChildren={t('cron_disabled')} />
          </Form.Item>
        </div>
        <Form.Item name="description" label={t('cron_description')}>
          <TextArea rows={2} placeholder={t('Please_Input') + t('cron_description')} />
        </Form.Item>
        <Form.Item name="delete_after_run" label={t('cron_delete_after_run')} valuePropName="checked">
          <Switch />
        </Form.Item>
      </Card>

      {/* 调度配置 */}
      <Card title={t('cron_schedule')} className="mb-4" size="small">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Form.Item
            name={['schedule', 'kind']}
            label={t('cron_schedule_type')}
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="cron">{t('cron_cron_expr')}</Select.Option>
              <Select.Option value="every">{t('cron_interval')}</Select.Option>
              <Select.Option value="at">{t('cron_once')}</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name={['schedule', 'tz']} label={t('cron_timezone')}>
            <Select showSearch allowClear>
              <Select.Option value="Asia/Shanghai">Asia/Shanghai (UTC+8)</Select.Option>
              <Select.Option value="UTC">UTC</Select.Option>
              <Select.Option value="America/New_York">America/New_York (EST)</Select.Option>
              <Select.Option value="Europe/London">Europe/London (GMT)</Select.Option>
              <Select.Option value="Asia/Tokyo">Asia/Tokyo (JST)</Select.Option>
            </Select>
          </Form.Item>
        </div>

        {scheduleKind === 'cron' && (
          <Form.Item
            name={['schedule', 'expr']}
            label={t('cron_cron_expression')}
            rules={[{ required: true, message: t('Please_Input') + t('cron_cron_expression') }]}
            extra="格式: 秒 分 时 日 月 周 (例如: 0 0 * * * 表示每小时执行)"
          >
            <Input placeholder="0 0 * * *" />
          </Form.Item>
        )}

        {scheduleKind === 'every' && (
          <Form.Item
            name={['schedule', 'every_ms']}
            label={t('cron_interval_ms')}
            rules={[{ required: true, message: t('Please_Input') + t('cron_interval_ms') }]}
            extra="例如: 60000 表示 1 分钟, 3600000 表示 1 小时"
          >
            <InputNumber min={1000} step={1000} style={{ width: '100%' }} />
          </Form.Item>
        )}

        {scheduleKind === 'at' && (
          <Form.Item
            name={['schedule', 'at']}
            label={t('cron_run_at')}
            rules={[{ required: true, message: t('Please_Input') + t('cron_run_at') }]}
            extra="ISO 格式: 2024-01-01T00:00:00"
          >
            <Input placeholder="2024-01-01T00:00:00" />
          </Form.Item>
        )}
      </Card>

      {/* 任务负载 */}
      <Card title={t('cron_payload')} size="small">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Form.Item
            name={['payload', 'kind']}
            label={t('cron_payload_type')}
            rules={[{ required: true }]}
            extra="选择定时任务要执行的操作类型"
          >
            <Select>
              <Select.Option value="agentTurn">{t('cron_agent_turn')}</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name={['payload', 'timeout_seconds']} label={t('cron_timeout')} extra="任务执行超时时间(秒)">
            <InputNumber min={1} max={3600} style={{ width: '100%' }} placeholder="默认600秒" />
          </Form.Item>
        </div>

        <Divider style={{ margin: '12px 0' }} />

        {/* Agent 调用 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Form.Item
            name={['payload', 'agent_id']}
            label={t('cron_agent_id')}
            rules={[{ required: true, message: t('Please_Input') + t('cron_agent_id') }]}
            extra="要调用的 Agent ID"
          >
            <Input placeholder={t('Please_Input') + t('cron_agent_id')} />
          </Form.Item>
          <Form.Item
            name={['payload', 'session_mode']}
            label={t('cron_session_mode')}
            extra={t('cron_session_mode_desc')}
          >
            <Select>
              <Select.Option value="isolated">{t('cron_session_isolated')}</Select.Option>
              <Select.Option value="shared">{t('cron_session_shared')}</Select.Option>
            </Select>
          </Form.Item>
        </div>
        {sessionMode === 'shared' && (
          <Form.Item
            name={['payload', 'conv_session_id']}
            label={t('cron_session_id')}
            extra={t('cron_session_id_desc')}
          >
            <Input placeholder={t('Please_Input') + t('cron_session_id')} />
          </Form.Item>
        )}
        <Form.Item
          name={['payload', 'message']}
          label={t('cron_message')}
          rules={[{ required: true, message: t('Please_Input') + t('cron_message') }]}
          extra="发送给 Agent 的消息内容"
        >
          <TextArea rows={3} placeholder={t('Please_Input') + t('cron_message')} />
        </Form.Item>
      </Card>
    </Form>
  );
}