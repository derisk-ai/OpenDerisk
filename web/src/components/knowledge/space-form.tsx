import { addSpace, apiInterceptors } from '@/client/api';
import { IStorage, StepChangeParams } from '@/types/knowledge';
import { Button, Form, Input, Select, Spin } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

type FieldType = {
  spaceName: string;
  owner: string;
  description: string;
  storage: string;
  field: string;
  embeddingModel?: string;
};

type IProps = {
  handleStepChange: (params: StepChangeParams) => void;
  spaceConfig: IStorage | null;
  embeddingModels?: Array<{ name: string; provider?: string }>;
};

export default function SpaceForm(props: IProps) {
  const { t } = useTranslation();
  const { handleStepChange, spaceConfig, embeddingModels } = props;
  const [spinning, setSpinning] = useState<boolean>(false);
  const [storage, setStorage] = useState<string>();

  const [form] = Form.useForm();

  useEffect(() => {
    form.setFieldValue('storage', spaceConfig?.[0].name);
    setStorage(spaceConfig?.[0].name);
  }, [spaceConfig]);

  const handleStorageChange = (data: string) => {
    setStorage(data);
  };

  const handleFinish = async (fieldsValue: FieldType) => {
    const { spaceName, owner, description, storage, field, embeddingModel } = fieldsValue;
    setSpinning(true);
    const vector_type = storage;
    const domain_type = field;

    // Build context for Memory storage type
    let context: string | undefined;
    if (vector_type === 'Memory' && embeddingModel) {
      context = JSON.stringify({ embedding_model: embeddingModel });
    }

    const [_, data, res] = await apiInterceptors(
      addSpace({
        name: spaceName,
        vector_type: vector_type,
        owner,
        desc: description,
        domain_type: domain_type,
        context,
      }),
    );
    setSpinning(false);
    const is_financial = domain_type === 'FinancialReport';
    const is_memory = vector_type === 'Memory';
    localStorage.setItem('cur_space_id', JSON.stringify(data));
    res?.success &&
      handleStepChange({
        label: is_memory ? 'finish' : 'forward',
        spaceName,
        pace: is_financial ? 2 : 1,
        docType: is_financial ? 'DOCUMENT' : '',
      });
  };

  return (
    <Spin spinning={spinning}>
      <Form
        form={form}
        size='large'
        className='mt-4'
        layout='vertical'
        name='basic'
        initialValues={{ remember: true }}
        autoComplete='off'
        onFinish={handleFinish}
      >
        <Form.Item<FieldType>
          label={t('Knowledge_Space_Name')}
          name='spaceName'
          rules={[
            { required: true, message: t('Please_input_the_name') },
            () => ({
              validator(_, value) {
                if (/[^一-龥0-9a-zA-Z_-]/.test(value)) {
                  return Promise.reject(new Error(t('the_name_can_only_contain')));
                }
                return Promise.resolve();
              },
            }),
          ]}
        >
          <Input className='h-12' placeholder={t('Please_input_the_name')} />
        </Form.Item>
        <Form.Item<FieldType>
          label={t('Storage')}
          name='storage'
          rules={[{ required: true, message: t('Please_select_the_storage') }]}
        >
          <Select className='mb-5 h-12' placeholder={t('Please_select_the_storage')} onChange={handleStorageChange}>
            {spaceConfig?.map((item: any) => {
              return (
                <Select.Option key={item.name} value={item.name}>
                  {item.desc}
                </Select.Option>
              );
            })}
          </Select>
        </Form.Item>
        {storage === 'Memory' && embeddingModels && embeddingModels.length > 0 && (
          <Form.Item<FieldType>
            label={t('Embedding_Model')}
            name='embeddingModel'
            rules={[{ required: true, message: t('Please_select_the_embedding_model') }]}
          >
            <Select className='mb-5 h-12' placeholder={t('Please_select_the_embedding_model')}>
              {embeddingModels.map((item) => (
                <Select.Option key={item.name} value={item.name}>
                  {item.name}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        )}
        <Form.Item<FieldType>
          label={t('Domain')}
          name='field'
          rules={[{ required: true, message: t('Please_select_the_domain_type') }]}
        >
          <Select className='mb-5 h-12' placeholder={t('Please_select_the_domain_type')}>
            {spaceConfig
              ?.find((item: any) => item.name === storage)
              ?.domain_types.map((item: any) => {
                return (
                  <Select.Option key={item.name} value={item.name}>
                    {item.desc}
                  </Select.Option>
                );
              })}
          </Select>
        </Form.Item>
        <Form.Item<FieldType>
          label={t('Description')}
          name='description'
          rules={[{ required: true, message: t('Please_input_the_description') }]}
        >
          <Input className='h-12' placeholder={t('Please_input_the_description')} />
        </Form.Item>
        <Form.Item>
          <Button type='primary' htmlType='submit'>
            {t('Next')}
          </Button>
        </Form.Item>
      </Form>
    </Spin>
  );
}
