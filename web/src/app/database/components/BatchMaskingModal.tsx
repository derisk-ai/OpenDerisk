'use client';

import { apiInterceptors, batchAddMaskingConfig } from '@/client/api';
import {
  BatchMaskingConfigResponse,
  SENSITIVE_TYPE_OPTIONS,
  MASKING_MODE_OPTIONS,
} from '@/types/db';
import { SafetyCertificateOutlined, CheckCircleOutlined, WarningOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
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
  Card,
} from 'antd';
import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

interface MaskingRule {
  column_names: string;
  sensitive_type: string;
  masking_mode: string;
}

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
  const [results, setResults] = useState<BatchMaskingConfigResponse[]>([]);
  const [ignoreCase, setIgnoreCase] = useState(true);

  // Reset form and results when modal opens
  React.useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({
        rules: [{ column_names: '', sensitive_type: 'phone', masking_mode: 'mask' }],
      });
      setResults([]);
      setIgnoreCase(true);
    }
  }, [open, form]);

  const handleApply = useCallback(async () => {
    try {
      const values = await form.validateFields();
      const rules: MaskingRule[] = values.rules || [];

      // Validate each rule has column names
      const validRules = rules.filter((rule: MaskingRule) => {
        const names = rule.column_names
          .split(/[,\s]+/)
          .map((name: string) => name.trim())
          .filter((name: string) => name.length > 0);
        return names.length > 0;
      });

      if (validRules.length === 0) {
        message.error('Please enter at least one rule with column names');
        return;
      }

      setLoading(true);
      const allResults: BatchMaskingConfigResponse[] = [];

      // Process each rule sequentially
      for (const rule of validRules) {
        const columnNames = rule.column_names
          .split(/[,\s]+/)
          .map((name: string) => name.trim())
          .filter((name: string) => name.length > 0);

        const [err, res] = await apiInterceptors(
          batchAddMaskingConfig(datasourceId, {
            column_names: columnNames,
            sensitive_type: rule.sensitive_type,
            masking_mode: rule.masking_mode || 'mask',
            ignore_case: ignoreCase,
          }),
        );

        if (!err && res) {
          allResults.push(res);
        }
      }

      setResults(allResults);
      setLoading(false);

      const totalAdded = allResults.reduce((sum, r) => sum + r.total_configs_added, 0);
      if (totalAdded > 0) {
        message.success(`Successfully added ${totalAdded} masking configurations`);
      }
    } catch {
      message.error('Please check your input');
      setLoading(false);
    }
  }, [datasourceId, form, message, ignoreCase]);

  const handleClose = useCallback(() => {
    const totalAdded = results.reduce((sum, r) => sum + r.total_configs_added, 0);
    if (totalAdded > 0) {
      onSuccess();
    }
    onCancel();
  }, [results, onSuccess, onCancel]);

  // Calculate totals from all results
  const totals = results.reduce(
    (acc, r) => ({
      tables: acc.tables + r.total_tables_scanned,
      columns: acc.columns + r.total_columns_matched,
      configs: acc.configs + r.total_configs_added,
    }),
    { tables: 0, columns: 0, configs: 0 }
  );

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
      width={650}
      destroyOnClose
    >
      {results.length === 0 ? (
        <Form form={form} layout="vertical">
          <Form.List name="rules" initialValue={[{ column_names: '', sensitive_type: 'phone', masking_mode: 'mask' }]}>
            {(fields, { add, remove }) => (
              <>
                <Typography.Text type="secondary" style={{ marginBottom: 8 }}>
                  {t('Add multiple masking rules. Each rule applies a sensitive type to matching columns.')}
                </Typography.Text>

                {fields.map(({ key, name, ...restField }) => (
                  <Card
                    key={key}
                    size="small"
                    style={{ marginBottom: 12 }}
                    title={
                      <Space>
                        <Typography.Text strong>Rule {name + 1}</Typography.Text>
                        {fields.length > 1 && (
                          <Button
                            type="text"
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            onClick={() => remove(name)}
                          />
                        )}
                      </Space>
                    }
                  >
                    <Form.Item
                      {...restField}
                      name={[name, 'column_names']}
                      label={t('Column Names')}
                      rules={[{ required: true, message: t('Please enter column names') }]}
                      extra={t('Separate multiple names with comma or space')}
                    >
                      <Input.TextArea
                        rows={1}
                        placeholder="phone, mobile, telephone..."
                        autoSize={{ minRows: 1, maxRows: 2 }}
                      />
                    </Form.Item>

                    <Space style={{ width: '100%' }} size="middle">
                      <Form.Item
                        {...restField}
                        name={[name, 'sensitive_type']}
                        label={t('Sensitive Type')}
                        rules={[{ required: true, message: t('Please select') }]}
                        style={{ flex: 1, minWidth: 180 }}
                      >
                        <Select
                          options={SENSITIVE_TYPE_OPTIONS.map((item) => ({
                            value: item.value,
                            label: `${item.label} (${item.labelEn})`,
                          }))}
                        />
                      </Form.Item>

                      <Form.Item
                        {...restField}
                        name={[name, 'masking_mode']}
                        label={t('Masking Mode')}
                        style={{ flex: 1, minWidth: 150 }}
                      >
                        <Select
                          options={MASKING_MODE_OPTIONS.map((item) => ({
                            value: item.value,
                            label: `${item.label} (${item.labelEn})`,
                          }))}
                        />
                      </Form.Item>
                    </Space>
                  </Card>
                ))}

                <Button
                  type="dashed"
                  onClick={() => add({ column_names: '', sensitive_type: 'phone', masking_mode: 'mask' })}
                  icon={<PlusOutlined />}
                  style={{ width: '100%', marginBottom: 16 }}
                >
                  {t('Add Rule')}
                </Button>
              </>
            )}
          </Form.List>

          <Form.Item
            label={t('Ignore Case')}
            extra={t('Match column names case-insensitively (applies to all rules)')}
          >
            <Switch checked={ignoreCase} onChange={setIgnoreCase} />
          </Form.Item>

          <Divider />

          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={handleClose}>{t('Cancel')}</Button>
            <Button type="primary" loading={loading} onClick={handleApply}>
              {t('Apply All Rules')}
            </Button>
          </Space>
        </Form>
      ) : (
        <div>
          {/* Combined Result Summary */}
          <div style={{ marginBottom: 16 }}>
            {totals.configs > 0 ? (
              <Space style={{ color: '#52c41a' }}>
                <CheckCircleOutlined />
                <Typography.Text strong style={{ color: '#52c41a' }}>
                  {t('Successfully added {{count}} masking configurations', { count: totals.configs })}
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
              <li>{t('Scanned {{count}} tables', { count: totals.tables })}</li>
              <li>{t('Matched {{count}} columns', { count: totals.columns })}</li>
              <li>{t('Added {{count}} configurations', { count: totals.configs })}</li>
            </ul>
          </Typography.Paragraph>

          {/* Per-rule results */}
          {results.length > 1 && (
            <div style={{ marginTop: 16 }}>
              <Typography.Text strong>{t('Results by rule:')}</Typography.Text>
              <List
                size="small"
                dataSource={results}
                renderItem={(item, idx) => (
                  <List.Item>
                    <Typography.Text>
                      Rule {idx + 1}: {item.total_configs_added} configs added ({item.total_columns_matched} columns matched)
                    </Typography.Text>
                  </List.Item>
                )}
              />
            </div>
          )}

          {/* All Matched Columns */}
          {results.some(r => r.matched_columns.length > 0) && (
            <div style={{ marginTop: 16 }}>
              <Typography.Text strong>{t('All matched columns:')}</Typography.Text>
              <List
                size="small"
                dataSource={results.flatMap(r => r.matched_columns)}
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
          {results.some(r => r.errors.length > 0) && (
            <div style={{ marginTop: 16 }}>
              <Typography.Text type="danger">{t('Errors:')}</Typography.Text>
              <List
                size="small"
                dataSource={results.flatMap(r => r.errors)}
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