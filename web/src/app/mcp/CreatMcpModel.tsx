import { addMCP, updateMCP, apiInterceptors } from '@/client/api';
import { PlusOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Button, Col, Form, Input, Modal, Row, Select, message } from 'antd';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import CustomUpload from './CustomUpload';

interface CreatMcpModelProps {
  formData: any;
  setFormData: (data: any) => void;
  onSuccess?: () => void;
}

type FieldType = {
  name?: string;
  description?: string;
  type?: string;
  sse_url?: string;
  sse_headers?: string;
  token?: string;
  email?: string;
  version?: string;
  author?: string;
  icon?: any;
  stdio_cmd?: string;
  mcp_code?: string;
};

const CreatMcpModel: React.FC<CreatMcpModelProps> = (props: CreatMcpModelProps) => {
  const { onSuccess, formData } = props;
  const { t } = useTranslation();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [mcpType, setMcpType] = useState<string>('http');

  const isEditing = !!formData?.mcp_code;

  const { loading, run: runAddMCP } = useRequest(
    async (params): Promise<any> => {
      const apiCall = isEditing ? updateMCP : addMCP;
      return await apiInterceptors(apiCall(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          message.success(isEditing ? t('update_success') : t('create_success'));
          form?.resetFields();
          setMcpType('http');
          setIsModalOpen(false);
          props.setFormData({});
          onSuccess?.();
        } else {
          message.error(res?.message || (isEditing ? t('update_failed') : t('create_failed')));
        }
      },
      onError: (error) => {
        message.error(isEditing ? t('update_failed') : t('create_failed'));
        console.error(isEditing ? 'Update MCP error:' : 'Create MCP error:', error);
      },
      throttleWait: 300,
    },
  );

  const showModal = () => {
    setIsModalOpen(true);
  };

  const handleOk = () => {
    form?.validateFields().then(async values => {
      // Parse sse_headers from JSON string to dict before submit
      if (values.sse_headers && typeof values.sse_headers === 'string') {
        try {
          values.sse_headers = JSON.parse(values.sse_headers);
        } catch {
          message.error(t('mcp_headers_invalid_json'));
          return;
        }
      }
      // If editing, include mcp_code from formData
      const submitData = formData?.mcp_code ? { ...values, mcp_code: formData.mcp_code } : values;
      runAddMCP(submitData);
    });
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    form?.resetFields();
    setMcpType('http');
    props.setFormData({});
  };

  // Populate form when editing
  useEffect(() => {
    if (Object.keys(formData || {}).length > 0 && isModalOpen) {
      const displayData = { ...formData };
      // Convert sse_headers dict to JSON string for display in textarea
      if (displayData.sse_headers && typeof displayData.sse_headers === 'object') {
        displayData.sse_headers = JSON.stringify(displayData.sse_headers, null, 2);
      }
      form?.setFieldsValue(displayData);
      setMcpType(displayData?.type || 'http');
    }
  }, [formData, form, isModalOpen]);

  // Open modal when formData is set
  useEffect(() => {
    if (Object.keys(formData || {}).length > 0) {
      setIsModalOpen(true);
    }
  }, [formData]);

  return (
    <>
      <Button
        className='border-none text-white bg-button-gradient'
        icon={<PlusOutlined />}
        onClick={showModal}
      >
        {t('create_mcp')}
      </Button>
      <Modal
        title={formData?.mcp_code ? t('edit_mcp') : t('create_mcp')}
        open={isModalOpen}
        onOk={handleOk}
        onCancel={handleCancel}
        confirmLoading={loading}
        okButtonProps={{ className: 'bg-button-gradient' }}
        width={720}
        centered
        className="mcp-modal"
        destroyOnClose
      >
        <Form
          initialValues={{ type: 'http' }}
          autoComplete='off'
          form={form}
          layout='vertical'
          requiredMark={false}
        >
          {/* -- Basic Info Section -- */}
          <div className="mcp-modal-section-title">{t('mcp_section_basic')}</div>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item<FieldType>
                label={t('mcp_name')}
                name='name'
                rules={[{ required: true, message: t('mcp_name_required') }]}
              >
                <Input placeholder={t('mcp_name_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item<FieldType>
                label={t('mcp_type')}
                name='type'
                rules={[{ required: true, message: t('mcp_type_required') }]}
              >
                <Select
                  onChange={(value) => setMcpType(value)}
                  placeholder={t('mcp_type_placeholder')}
                >
                  <Select.Option value="http">HTTP / SSE</Select.Option>
                  <Select.Option value="stdio">STDIO</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Form.Item<FieldType>
            label={t('mcp_description')}
            name='description'
            rules={[{ required: true, message: t('mcp_description_required') }]}
          >
            <Input.TextArea rows={2} placeholder={t('mcp_description_placeholder')} />
          </Form.Item>

          {/* -- Connection Section -- */}
          <div className="mcp-modal-section-title">{t('mcp_section_connection')}</div>

          {mcpType === 'http' && (
            <>
              <Row gutter={16}>
                <Col span={14}>
                  <Form.Item<FieldType>
                    label={t('mcp_sse_url')}
                    name='sse_url'
                    rules={[{ required: true, message: t('mcp_sse_url_required') }]}
                  >
                    <Input placeholder={t('mcp_sse_url_placeholder')} />
                  </Form.Item>
                </Col>
                <Col span={10}>
                  <Form.Item<FieldType>
                    label={t('mcp_token')}
                    name='token'
                  >
                    <Input.Password placeholder={t('mcp_token_placeholder')} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item<FieldType>
                label={t('mcp_headers')}
                name='sse_headers'
                rules={[
                  {
                    validator: (_, value) => {
                      if (!value || value.trim() === '') return Promise.resolve();
                      try {
                        const parsed = JSON.parse(value);
                        if (typeof parsed !== 'object' || Array.isArray(parsed)) {
                          return Promise.reject(t('mcp_headers_must_be_object'));
                        }
                        return Promise.resolve();
                      } catch {
                        return Promise.reject(t('mcp_headers_invalid_json'));
                      }
                    },
                  },
                ]}
                extra={t('mcp_headers_extra')}
              >
                <Input.TextArea
                  rows={3}
                  placeholder={t('mcp_headers_placeholder')}
                  style={{ fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace", fontSize: 12 }}
                />
              </Form.Item>
            </>
          )}

          {mcpType === 'stdio' && (
            <Form.Item<FieldType>
              label={t('mcp_stdio_cmd')}
              name='stdio_cmd'
              rules={[{ required: true, message: t('mcp_stdio_cmd_required') }]}
            >
              <Input.TextArea
                rows={3}
                placeholder={t('mcp_stdio_cmd_placeholder')}
                style={{ fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace", fontSize: 12 }}
              />
            </Form.Item>
          )}

          {/* -- Metadata Section -- */}
          <div className="mcp-modal-section-title">{t('mcp_section_metadata')}</div>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item<FieldType> label={t('mcp_author')} name='author'>
                <Input placeholder={t('mcp_author_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item<FieldType> label={t('mcp_email')} name='email'>
                <Input placeholder={t('mcp_email_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item<FieldType> label={t('mcp_version')} name='version'>
                <Input placeholder={t('mcp_version_placeholder')} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item<FieldType>
            label={t('mcp_icon')}
            name='icon'
            getValueFromEvent={e => {
              form.setFieldsValue({
                icon: e,
              });
            }}
          >
            <CustomUpload />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default CreatMcpModel;