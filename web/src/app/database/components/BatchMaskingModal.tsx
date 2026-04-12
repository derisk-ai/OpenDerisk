'use client';

import { apiInterceptors, batchAddMaskingConfig } from '@/client/api';
import {
  BatchMaskingConfigResponse,
  SENSITIVE_TYPE_OPTIONS,
  MASKING_MODE_OPTIONS,
} from '@/types/db';
import { SafetyCertificateOutlined, CheckCircleOutlined, WarningOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Form,
  Input,
  Select,
  Switch,
  Modal,
  Space,
  Divider,
  List,
  Typography,
  Spin,
} from 'antd';
import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

interface BatchMaskingModalProps {
  open: boolean;
  datasourceId: number;
  onCancel: () => void;
  onSuccess: () => void;
}

export default function BatchMaskingModal({
  open,
  datasourceId,
  onCancel,
  onSuccess,
}: BatchMaskingModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BatchMaskingConfigResponse | null>(null);

  // Reset form and result when modal opens
  React.useEffect(() => {
    if (open) {
      form.resetFields();
      setResult(null);
    }
  }, [open, form]);

  const handleApply = useCallback(async () => {
    try {
      const values = await form.validateFields();

      // Parse column names - support comma or space separated
      const columnNames = values.column_names
        .split(/[,\s]+/)
        .map((name: string) => name.trim())
        .filter((name: string) => name.length > 0);

      if (columnNames.length === 0) {
        message.error('Please enter at least one column name');
        return;
      }

      setLoading(true);
      const [err, res] = await apiInterceptors(
        batchAddMaskingConfig(datasourceId, {
          column_names: columnNames,
          sensitive_type: values.sensitive_type,
          masking_mode: values.masking_mode || 'mask',
          ignore_case: values.ignore_case ?? true,
        }),
      );

      if (err) {
        message.error('Failed to apply batch masking config');
        setLoading(false);
        return;
      }

      setResult(res);
      setLoading(false);
    } catch {
      message.error('Please check your input');
      setLoading(false);
    }
  }, [datasourceId, form, message]);

  const handleClose = useCallback(() => {
    if (result && result.total_configs_added > 0) {
      onSuccess();
    }
    onCancel();
  }, [result, onSuccess, onCancel]);

  return (
    <Modal
      title={
        <Space>
          <SafetyCertificateOutlined />
          {t('Batch Masking Configuration')}
        </Space>
      }
      open={open}
      onCancel={handleClose}
      footer={null}
      width={520}
      destroyOnClose
    >
      {!result ? (
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            sensitive_type: 'phone',
            masking_mode: 'mask',
            ignore_case: true,
          }}
        >
          <Form.Item
            name="column_names"
            label={t('Column Names')}
            rules={[{ required: true, message: t('Please enter column names') }]}
            extra={t('Enter column names to mask. Multiple names can be separated by comma or space (e.g., "phone, mobile, email")')}
          >
            <Input.TextArea
              rows={2}
              placeholder="phone, mobile, email, telephone..."
            />
          </Form.Item>

          <Form.Item
            name="sensitive_type"
            label={t('Sensitive Type')}
            rules={[{ required: true, message: t('Please select a sensitive type') }]}
          >
            <Select options={SENSITIVE_TYPE_OPTIONS.map((item) => ({
              value: item.value,
              label: `${item.label} (${item.labelEn})`,
            }))} />
          </Form.Item>

          <Form.Item
            name="masking_mode"
            label={t('Masking Mode')}
          >
            <Select options={MASKING_MODE_OPTIONS.map((item) => ({
              value: item.value,
              label: `${item.label} (${item.labelEn})`,
            }))} />
          </Form.Item>

          <Form.Item
            name="ignore_case"
            label={t('Ignore Case')}
            extra={t('Match column names case-insensitively (recommended)')}
          >
            <Switch defaultChecked />
          </Form.Item>

          <Divider />

          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={handleClose}>{t('Cancel')}</Button>
            <Button type="primary" loading={loading} onClick={handleApply}>
              {t('Apply')}
            </Button>
          </Space>
        </Form>
      ) : (
        <div>
          {/* Result Summary */}
          <div style={{ marginBottom: 16 }}>
            {result.total_configs_added > 0 ? (
              <Space style={{ color: '#52c41a' }}>
                <CheckCircleOutlined />
                <Typography.Text strong style={{ color: '#52c41a' }}>
                  {t('Successfully added {{count}} masking configurations', { count: result.total_configs_added })}
                </Typography.Text>
              </Space>
            ) : (
              <Space style={{ color: '#faad14' }}>
                <WarningOutlined />
                <Typography.Text style={{ color: '#faad14' }}>
                  {t('No matching columns found')}
                </Typography.Text>
              </Space>
            )}
          </div>

          <Typography.Paragraph>
            <ul style={{ paddingLeft: 20, margin: 0 }}>
              <li>{t('Scanned {{count}} tables', { count: result.total_tables_scanned })}</li>
              <li>{t('Matched {{count}} columns', { count: result.total_columns_matched })}</li>
              <li>{t('Added {{count}} configurations', { count: result.total_configs_added })}</li>
            </ul>
          </Typography.Paragraph>

          {/* Matched Columns List */}
          {result.matched_columns.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Typography.Text strong>{t('Matched columns:')}</Typography.Text>
              <List
                size="small"
                dataSource={result.matched_columns}
                renderItem={(item) => (
                  <List.Item>
                    <Typography.Text>
                      <code>{item.table}.{item.column}</code>
                    </Typography.Text>
                  </List.Item>
                )}
                style={{ maxHeight: 200, overflow: 'auto' }}
              />
            </div>
          )}

          {/* Errors */}
          {result.errors.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Typography.Text type="danger">{t('Errors:')}</Typography.Text>
              <List
                size="small"
                dataSource={result.errors}
                renderItem={(item) => (
                  <List.Item>
                    <Typography.Text type="danger">{item}</Typography.Text>
                  </List.Item>
                )}
              />
            </div>
          )}

          <Divider />

          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={handleClose}>{t('Close')}</Button>
          </Space>
        </div>
      )}
    </Modal>
  );
}