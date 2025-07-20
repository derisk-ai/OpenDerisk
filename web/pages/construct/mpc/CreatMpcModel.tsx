import { addMCP, apiInterceptors,EditMCP } from '@/client/api';
import { PlusOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Button,Select, Form, Input, Modal, message } from 'antd';
import React, { useState ,useEffect} from 'react';
import { useTranslation } from 'react-i18next';
import CustomUpload from './CustomUpload';
interface CreatMpcModelProps {
  onSuccess?: () => void;
  setFormData?: () => void;
  formData?:any;

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
  mcp_code?: any;
  stdio_cmd?: string;
};

const CreatMpcModel: React.FC<CreatMpcModelProps> = (props: CreatMpcModelProps) => {
  const { onSuccess,setFormData ,formData} = props;
  const { t } = useTranslation();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modleTitle, setModleTitle] = useState(t('create_MCP'));
  const [form] = Form.useForm();

  useEffect(() => {
    if (formData.name) {
      form.setFieldsValue(formData);
      setModleTitle(t('edit_MCP'));
      setIsModalOpen(true);
    }
  }, [formData]);


  const { loading, run: runAddMCP } = useRequest(
    async (params): Promise<any> => {
      if (modleTitle === t('edit_MCP')) {
        params.mcp_code = formData.mcp_code;
        return await apiInterceptors(EditMCP(params));
      }else{
        return await apiInterceptors(addMCP(params));
      }
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          if (modleTitle === t('edit_MCP')) {
            message.success(t('Edit_Success'));
          }else{
            message.success(t('Add_Success'))
          }
          form?.resetFields();
          setIsModalOpen(false);
          onSuccess?.();
        }
      },
      throttleWait: 300,
    },
  );

  const showModal = () => {
    setModleTitle(t('create_MCP'));
    setIsModalOpen(true);
  };

  const handleOk = () => {
    form?.validateFields().then(async values => {
      const useInfo = localStorage.getItem('__db_gpt_uinfo_key');
      values.author = JSON.parse(useInfo as string).nick_name;
      
      runAddMCP(values);
    });
  };

  const handleCancel = () => {
    setIsModalOpen(false);
   
    setFormData({});
    form?.resetFields();
  };

  return (
    <>
      <Button className='border-none text-white bg-button-gradient' icon={<PlusOutlined />} onClick={showModal}>
        {t('create_MCP')}
      </Button>
      <Modal
        title={modleTitle}
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
            rules={[{ message: 'Please input your description!' }]}
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

          <Form.Item<FieldType> label="Mcp Url" name='sse_url'
             rules={[{ required: true, message: 'Please input Mcp Url!' }]}>
            <Input />
       
          </Form.Item>
          <Form.Item<FieldType> label="Token" name='token'
            >
            <Input />
          </Form.Item>

          <Form.Item<FieldType> label={t('mcp_email')} name='email'
            >
            <Input />
          </Form.Item>

          {/* <Form.Item<FieldType> label={t('mcp_version')} name='version'>
            <Input />
          </Form.Item> */}

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

export default CreatMpcModel;
