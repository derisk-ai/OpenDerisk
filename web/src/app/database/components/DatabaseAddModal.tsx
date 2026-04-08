'use client';

import {
  apiInterceptors,
  postDbAdd,
  postDbTestConnect,
  uploadDbFile,
} from '@/client/api';
import { IChatDbSupportTypeSchema } from '@/types/db';
import {
  UploadOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  SettingOutlined,
} from '@ant-design/icons';
import {
  App,
  Alert,
  Button,
  Collapse,
  Modal,
  Form,
  Input,
  Select,
  Space,
  Upload,
  Row,
  Col,
} from 'antd';
import React, { useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

interface DatabaseAddModalProps {
  open: boolean;
  supportTypes: IChatDbSupportTypeSchema[];
  onCancel: () => void;
  onSuccess: () => void;
}

/** Fields that most users need to fill in */
const BASIC_FIELDS = new Set([
  'host', 'port', 'user', 'password', 'database',
  'path', 'file_path', 'db_path', 'filepath', 'database_path',
  'service_name', 'sid',
]);

/** Fields that should be hidden from the form (auto-managed) */
const HIDDEN_FIELDS = new Set(['driver']);

/** Fields that render as a two-column row together */
const TWO_COL_PAIRS: Record<string, string> = {
  host: 'port',
  user: 'password',
  service_name: 'sid',
};

export default function DatabaseAddModal({
  open,
  supportTypes,
  onCancel,
  onSuccess,
}: DatabaseAddModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('');
  const [uploading, setUploading] = useState(false);

  // Test connection result state
  const [testResult, setTestResult] = useState<{
    status: 'success' | 'error' | null;
    message?: string;
  }>({ status: null });

  const currentTypeConfig = useMemo(() => {
    if (!Array.isArray(supportTypes)) return undefined;
    return supportTypes.find(
      (item) => item.name === selectedType || item.db_type === selectedType,
    );
  }, [supportTypes, selectedType]);

  const typeOptions = useMemo(() => {
    if (!Array.isArray(supportTypes)) return [];
    return supportTypes.map((item) => {
      let label = item.label || item.name || item.db_type;
      label = label.replace(/\s*[Dd]atasource$/i, '').trim();
      return { label, value: item.name || item.db_type };
    });
  }, [supportTypes]);

  // Split params into basic + advanced groups
  const { basicParams, advancedParams } = useMemo(() => {
    if (!currentTypeConfig) return { basicParams: [], advancedParams: [] };
    const params = currentTypeConfig.parameters || currentTypeConfig.params;
    if (!params || !Array.isArray(params)) return { basicParams: [], advancedParams: [] };

    const basic: any[] = [];
    const advanced: any[] = [];
    for (const param of params) {
      const name = param.param_name || param.name;
      if (HIDDEN_FIELDS.has(name)) continue;
      if (BASIC_FIELDS.has(name)) {
        basic.push(param);
      } else {
        advanced.push(param);
      }
    }
    return { basicParams: basic, advancedParams: advanced };
  }, [currentTypeConfig]);

  const handleTypeChange = (value: string) => {
    setSelectedType(value);
    setTestResult({ status: null });
    form.resetFields(['params']);
  };

  const handleTestConnection = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setTestLoading(true);
      setTestResult({ status: null });

      const submitData = {
        type: values.type,
        params: values.params || {},
        description: values.description,
      };
      const [err, , res] = await apiInterceptors(
        postDbTestConnect(submitData as any),
      );
      if (err || !res?.success) {
        const errMsg =
          res?.err_msg || err?.message || t('test_connection_failed');
        setTestResult({ status: 'error', message: errMsg });
      } else {
        setTestResult({ status: 'success', message: t('test_connection_success') });
      }
    } catch {
      // form validation failed
    } finally {
      setTestLoading(false);
    }
  }, [form, t]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      const submitData = {
        type: values.type,
        params: values.params || {},
        description: values.description,
      };
      const [err] = await apiInterceptors(postDbAdd(submitData as any));
      if (err) {
        message.error(t('add_database_failed'));
      } else {
        message.success(t('add_database_success'));
        form.resetFields();
        setSelectedType('');
        setTestResult({ status: null });
        onSuccess();
      }
    } catch {
      // validation failed
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    form.resetFields();
    setSelectedType('');
    setTestResult({ status: null });
    onCancel();
  };

  // Detect if a parameter is a file/path type
  const isPathParam = (paramName: string, param: any) => {
    const name = (paramName || '').toLowerCase();
    const desc = (param.description || '').toLowerCase();
    return (
      name === 'path' || name === 'file_path' || name === 'db_path' ||
      name === 'filepath' || name === 'database_path' || name.endsWith('_path') ||
      desc.includes('file path') || desc.includes('file_path')
    );
  };

  const handleDbFileUpload = async (file: File, paramName: string) => {
    setUploading(true);
    try {
      const [err, res] = await apiInterceptors(uploadDbFile(file));
      if (err || !res) {
        message.error(t('upload_failed') || 'Upload failed');
        return;
      }
      form.setFieldValue(['params', paramName], res.file_path);
      message.success(`${t('upload_success') || 'Uploaded'}: ${res.file_name}`);
    } catch {
      message.error(t('upload_failed') || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  /** Render a single form field */
  const renderField = (param: any, compact?: boolean) => {
    const paramName = param.param_name || param.name;
    const paramType = param.param_type || param.type || 'string';
    const isRequired = param.required !== false;
    const defaultValue = param.default_value;
    const isPassword =
      paramName === 'password' || paramName === 'db_pwd' ||
      (param.tags && param.tags.includes('privacy'));
    const isPath = isPathParam(paramName, param);

    const label = param.label || paramName;

    if (isPath) {
      return (
        <Form.Item key={paramName} label={label} required={isRequired}>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item
              name={['params', paramName]}
              noStyle
              rules={
                isRequired
                  ? [{ required: true, message: `${label} ${t('is_required') || 'is required'}` }]
                  : undefined
              }
              initialValue={defaultValue}
            >
              <Input
                placeholder={t('input_path_or_upload') || 'Enter server path or upload file'}
                style={{ width: 'calc(100% - 110px)' }}
              />
            </Form.Item>
            <Upload
              accept=".db,.sqlite,.sqlite3,.duckdb,.mdb,.accdb"
              showUploadList={false}
              beforeUpload={(file) => {
                handleDbFileUpload(file as unknown as File, paramName);
                return false;
              }}
            >
              <Button icon={<UploadOutlined />} loading={uploading} style={{ width: 110 }}>
                {t('upload_file') || 'Upload'}
              </Button>
            </Upload>
          </Space.Compact>
        </Form.Item>
      );
    }

    const inputNode = isPassword ? (
      <Input.Password placeholder={param.description || paramName} />
    ) : paramType === 'int' || paramType === 'integer' ? (
      <Input type="number" placeholder={param.description || paramName} />
    ) : param.valid_values && Array.isArray(param.valid_values) ? (
      <Select
        options={param.valid_values.map((v: any) => ({ label: String(v), value: v }))}
        placeholder={param.description || paramName}
      />
    ) : (
      <Input placeholder={param.description || paramName} />
    );

    return (
      <Form.Item
        key={paramName}
        name={['params', paramName]}
        label={label}
        rules={
          isRequired
            ? [{ required: true, message: `${label} ${t('is_required') || 'is required'}` }]
            : undefined
        }
        initialValue={defaultValue}
      >
        {inputNode}
      </Form.Item>
    );
  };

  /** Render basic fields with two-column layout for paired fields */
  const renderBasicFields = () => {
    if (!basicParams.length) return null;

    const rendered = new Set<string>();
    const elements: React.ReactNode[] = [];

    for (const param of basicParams) {
      const name = param.param_name || param.name;
      if (rendered.has(name)) continue;

      // Check if this field has a pair partner
      const partnerName = TWO_COL_PAIRS[name];
      const partnerParam = partnerName
        ? basicParams.find((p: any) => (p.param_name || p.name) === partnerName)
        : null;

      if (partnerParam) {
        rendered.add(name);
        rendered.add(partnerName);
        elements.push(
          <Row gutter={16} key={`pair-${name}`}>
            <Col span={12}>{renderField(param, true)}</Col>
            <Col span={12}>{renderField(partnerParam, true)}</Col>
          </Row>,
        );
      } else {
        rendered.add(name);
        elements.push(renderField(param));
      }
    }

    return elements;
  };

  /** Render advanced fields inside a collapsible section */
  const renderAdvancedFields = () => {
    if (!advancedParams.length) return null;
    return (
      <Collapse
        ghost
        size="small"
        style={{ marginTop: 4, marginBottom: 8 }}
        items={[
          {
            key: 'advanced',
            label: (
              <span style={{ fontSize: 13, color: 'var(--ant-color-text-secondary)' }}>
                <SettingOutlined style={{ marginRight: 6 }} />
                {t('advanced_settings') || 'Advanced Settings'}
                <span style={{ marginLeft: 6, fontSize: 12, opacity: 0.6 }}>
                  ({advancedParams.length})
                </span>
              </span>
            ),
            children: (
              <div style={{ paddingTop: 8 }}>
                <Row gutter={16}>
                  {advancedParams.map((param: any) => (
                    <Col span={12} key={param.param_name || param.name}>
                      {renderField(param, true)}
                    </Col>
                  ))}
                </Row>
              </div>
            ),
          },
        ]}
      />
    );
  };

  return (
    <Modal
      title={t('add_database_title') || 'Add Database'}
      open={open}
      onCancel={handleClose}
      width={600}
      destroyOnClose
      className="db-modal"
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Button
            onClick={handleTestConnection}
            loading={testLoading}
            icon={
              testResult.status === 'success' ? (
                <CheckCircleFilled style={{ color: '#52c41a' }} />
              ) : testResult.status === 'error' ? (
                <CloseCircleFilled style={{ color: '#ff4d4f' }} />
              ) : undefined
            }
          >
            {t('test_connection') || 'Test Connection'}
          </Button>
          <Space>
            <Button onClick={handleClose}>{t('cancel') || 'Cancel'}</Button>
            <Button type="primary" onClick={handleSubmit} loading={loading}>
              {t('Add') || 'Add'}
            </Button>
          </Space>
        </div>
      }
    >
      <Form form={form} layout="vertical" size="middle">
        {/* Database Type Selector */}
        <Form.Item
          name="type"
          label={t('database_type') || 'Database Type'}
          rules={[{ required: true, message: t('please_select_database_type') || 'Please select' }]}
        >
          <Select
            options={typeOptions}
            placeholder={t('select_database_type') || 'Select database type'}
            onChange={handleTypeChange}
            showSearch
            filterOption={(input, option) =>
              ((option?.label as string) || '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>

        {/* Basic Connection Fields */}
        {renderBasicFields()}

        {/* Advanced Settings (collapsed by default) */}
        {renderAdvancedFields()}

        {/* Description */}
        <Form.Item name="description" label={t('description') || 'Description'}>
          <Input.TextArea rows={2} placeholder={t('optional_description') || 'Optional description'} />
        </Form.Item>
      </Form>

      {/* Test Connection Result */}
      {testResult.status === 'success' && (
        <Alert
          type="success"
          showIcon
          message={testResult.message}
          style={{ marginTop: 8 }}
        />
      )}
      {testResult.status === 'error' && (
        <Alert
          type="error"
          showIcon
          message={t('test_connection_failed') || 'Connection test failed'}
          description={
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 160, overflow: 'auto' }}>
              {testResult.message}
            </div>
          }
          style={{ marginTop: 8 }}
        />
      )}
    </Modal>
  );
}
