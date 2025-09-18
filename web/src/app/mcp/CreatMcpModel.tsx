import { addMCP, apiInterceptors } from '@/client/api';
import { PlusOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Button, Form, Input, Modal, message, Select} from 'antd';
import React, { useState } from 'react';
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
  token?: string;
  email?: string;
  version?: string;
  author?: string;
  icon?: any;
  stdio_cmd?: string;
};

const CreatMcpModel: React.FC<CreatMcpModelProps> = (props: CreatMcpModelProps) => {
  const { onSuccess } = props;
  const { t } = useTranslation();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  const { loading, run: runAddMCP } = useRequest(
    async (params): Promise<any> => {
      return await apiInterceptors(addMCP(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          message.success('创建成功');
          form?.resetFields();
          setIsModalOpen(false);
          onSuccess?.();
        }
      },
      throttleWait: 300,
    },
  );

  const showModal = () => {
    setIsModalOpen(true);
  };

  const handleOk = () => {
    form?.validateFields().then(async values => {
      runAddMCP(values);
    });
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    form?.resetFields();
  };

  return (
    <>
      <Button className='border-none text-white bg-button-gradient' icon={<PlusOutlined />} onClick={showModal}>
        {t('create_mcp')}
      </Button>
      <Modal
        title={t('create_mcp')}
        closable={{ 'aria-label': 'Custom Close Button' }}
        open={isModalOpen}
        onOk={handleOk}
        onCancel={handleCancel}
        confirmLoading={loading}
      >
        <Form initialValues={{ remember: true }} autoComplete='off' layout='vertical' form={form}>
          <Form.Item<FieldType>
            label={t('mcp_name')}
            name='name'
            rules={[{ required: true, message: 'Please input your name!' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item<FieldType>
            label={t('mcp_description')}
            name='description'
            rules={[{ required: true, message: 'Please input your description!' }]}
          >
            <Input.TextArea />
          </Form.Item>

          <Form.Item<FieldType>
            label={t('mcp_type')}
            name='type'
            rules={[{ required: true, message: 'Please input your type!' }]}
          >
            <Select>
              <Select.Option value="http">http</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item<FieldType> 
            label={t('mcp_url')}
            name='sse_url'
            rules={[{ required: true, message: 'Please input Mcp Url!' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item<FieldType> 
            label={t('mcp_token')}
            name='token'
          >  
            <Input />
          </Form.Item>

          <Form.Item<FieldType> label={t('mcp_author')} name='author'>
            <Input />
          </Form.Item>

          <Form.Item<FieldType> label={t('mcp_email')} name='email'>
            <Input />
          </Form.Item>

          <Form.Item<FieldType> label={t('mcp_version')} name='version'>
            <Input />
          </Form.Item>

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

          <Form.Item<FieldType> label={t('mcp_stdio_cmd')} name='stdio_cmd'>
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default CreatMcpModel;
