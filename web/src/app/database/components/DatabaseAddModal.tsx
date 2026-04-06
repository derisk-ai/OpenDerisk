'use client';

import {
  apiInterceptors,
  postDbAdd,
  postDbTestConnect,
  uploadDbFile,
} from '@/client/api';
import { IChatDbSupportTypeSchema } from '@/types/db';
import { UploadOutlined } from '@ant-design/icons';
import { App, Button, Form, Input, Modal, Select, Space, Upload } from 'antd';
import type { UploadFile as AntUploadFile } from 'antd';
import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

interface DatabaseAddModalProps {
  open: boolean;
  supportTypes: IChatDbSupportTypeSchema[];
  onCancel: () => void;
  onSuccess: () => void;
}

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
      // Strip trailing "datasource" / "Datasource" suffix
      label = label.replace(/\s*[Dd]atasource$/i, '').trim();
      return { label, value: item.name || item.db_type };
    });
  }, [supportTypes]);

  const handleTypeChange = (value: string) => {
    setSelectedType(value);
    form.resetFields(['params']);
  };

  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields();
      setTestLoading(true);
      const submitData = {
        type: values.type,
        params: values.params || {},
        description: values.description,
      };
      const [err] = await apiInterceptors(postDbTestConnect(submitData as any));
      if (err) {
        message.error(t('test_connection_failed'));
      } else {
        message.success(t('test_connection_success'));
      }
    } catch {
      // validation failed
    } finally {
      setTestLoading(false);
    }
  };

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
        onSuccess();
      }
    } catch {
      // validation failed
    } finally {
      setLoading(false);
    }
  };

  // Detect if a parameter is a file/path type
  const isPathParam = (paramName: string, param: any) => {
    const name = (paramName || '').toLowerCase();
    const desc = (param.description || '').toLowerCase();
    return (
      name === 'path' ||
      name === 'file_path' ||
      name === 'db_path' ||
      name === 'filepath' ||
      name === 'database_path' ||
      name.endsWith('_path') ||
      desc.includes('file path') ||
      desc.includes('file_path')
    );
  };

  // Handle DB file upload for path-type params
  const handleDbFileUpload = async (file: File, paramName: string) => {
    setUploading(true);
    try {
      const [err, res] = await apiInterceptors(uploadDbFile(file));
      if (err || !res) {
        message.error(t('upload_failed') || 'Upload failed');
        return;
      }
      form.setFieldValue(['params', paramName], res.file_path);
      message.success(
        `${t('upload_success') || 'Uploaded'}: ${res.file_name}`,
      );
    } catch {
      message.error(t('upload_failed') || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const renderParamFields = () => {
    if (!currentTypeConfig) return null;
    const params = currentTypeConfig.parameters || currentTypeConfig.params;
    if (!params || !Array.isArray(params)) return null;

    return params.map((param: any) => {
      const paramName = param.param_name || param.name;
      const paramType = param.param_type || param.type || 'string';
      const isRequired = param.required !== false;
      const defaultValue = param.default_value;
      const isPassword =
        paramName === 'password' ||
        paramName === 'db_pwd' ||
        (param.tags && param.tags.includes('privacy'));
      const isPath = isPathParam(paramName, param);

      if (isPath) {
        return (
          <Form.Item
            key={paramName}
            label={param.label || paramName}
            required={isRequired}
          >
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item
                name={['params', paramName]}
                noStyle
                rules={
                  isRequired
                    ? [{ required: true, message: `${param.label || paramName} ${t('is_required') || 'is required'}` }]
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
                <Button
                  icon={<UploadOutlined />}
                  loading={uploading}
                  style={{ width: 110 }}
                >
                  {t('upload_file') || 'Upload'}
                </Button>
              </Upload>
            </Space.Compact>
          </Form.Item>
        );
      }

      return (
        <Form.Item
          key={paramName}
          name={['params', paramName]}
          label={param.label || paramName}
          rules={
            isRequired
              ? [{ required: true, message: `${param.label || paramName} ${t('is_required') || 'is required'}` }]
              : undefined
          }
          initialValue={defaultValue}
        >
          {isPassword ? (
            <Input.Password placeholder={param.description || paramName} />
          ) : paramType === 'int' || paramType === 'integer' ? (
            <Input type="number" placeholder={param.description || paramName} />
          ) : param.valid_values && Array.isArray(param.valid_values) ? (
            <Select
              options={param.valid_values.map((v: any) => ({
                label: String(v),
                value: v,
              }))}
              placeholder={param.description || paramName}
            />
          ) : (
            <Input placeholder={param.description || paramName} />
          )}
        </Form.Item>
      );
    });
  };

  return (
    <Modal
      title={t('add_database_title')}
      open={open}
      onCancel={() => {
        form.resetFields();
        setSelectedType('');
        onCancel();
      }}
      footer={
        <Space>
          <Button onClick={onCancel}>{t('cancel')}</Button>
          <Button onClick={handleTestConnection} loading={testLoading}>
            {t('test_connection')}
          </Button>
          <Button type="primary" onClick={handleSubmit} loading={loading}>
            {t('Add') || 'Add'}
          </Button>
        </Space>
      }
      width={600}
      destroyOnHidden
      className="db-modal"
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="type"
          label={t('database_type')}
          rules={[{ required: true, message: t('please_select_database_type') }]}
        >
          <Select
            options={typeOptions}
            placeholder={t('select_database_type')}
            onChange={handleTypeChange}
            showSearch
            filterOption={(input, option) =>
              (option?.label as string || '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>

        {renderParamFields()}

        <Form.Item name="description" label={t('description')}>
          <Input.TextArea
            rows={2}
            placeholder={t('optional_description')}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
