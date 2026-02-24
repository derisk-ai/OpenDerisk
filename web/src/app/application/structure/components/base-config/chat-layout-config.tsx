import { Col, Form, FormInstance, Input, Row, Select } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';

export const MEDIA_RESOURCE_TYPES = [
  'image_file',
  'video_file',
  'excel_file',
  'text_file',
  'common_file'
];

function ChatLayoutConfig({
  form,
  selectedChatConfigs,
  chatConfigOptions,
  onInputBlur,
  resourceOptions,
  modelOptions,
}: {
  form: FormInstance;
  selectedChatConfigs: string[];
  chatConfigOptions: any[];
  onInputBlur: (fieldName: string) => void;
  resourceOptions: any[];
  modelOptions?: any[];
}) {
  const { t } = useTranslation();

  if (!selectedChatConfigs || selectedChatConfigs.length === 0) {
    return null;
  }

  const labelStyle = {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap'
  };

  const renderConfigItem = (item: any) => {
    if (!item) return null;

    switch (item.param_type) {
      case 'model':
        return (
          <Row gutter={12} key={item.param_type} className="mb-2">
            <Col span={12} key={`${item.param_type}-col1`}>
              <Form.Item
                label={<span style={labelStyle} title={item.param_description}>{item.param_description}</span>}
                name={`${item.param_type}_sub_type`}
                labelCol={{ span: 24 }}
                className="mb-0"
              >
                <Select
                  className='w-full'
                  options={item.sub_types?.map((sub: string) => ({ value: sub, label: sub })) || []}
                  disabled={!item.sub_types}
                  placeholder={t('chat_layout_config_select_param', { desc: item.param_description })}
                  onBlur={() => onInputBlur(`${item.param_type}_value`)}
                />
              </Form.Item>
            </Col>
            <Col span={12} key={`${item.param_type}-col2`}>
              <Form.Item name={`${item.param_type}_value`} initialValue={item.param_default_value} label=" " labelCol={{ span: 24 }} className="mb-0">
                <Select
                  options={modelOptions} 
                  placeholder={t('chat_layout_config_input_param', { desc: item.param_description })}
                  className='w-full'
                />
              </Form.Item>
            </Col>
          </Row>
        );

      case 'temperature':
      case 'max_new_tokens':
        return (
          <Row gutter={12} key={item.param_type} className="mb-2">
            <Col span={12} key={`${item.param_type}-col1`}>
              <Form.Item
                label={<span style={labelStyle} title={item.param_description}>{item.param_description}</span>}
                name={`${item.param_type}_sub_type`}
                labelCol={{ span: 24 }}
                className="mb-0"
              >
                 <Select
                  className='w-full'
                  options={item.sub_types?.map((sub: string) => ({ value: sub, label: sub })) || []}
                  disabled={!item.sub_types}
                  placeholder={t('chat_layout_config_select_param', { desc: item.param_description })}
                />
              </Form.Item>
            </Col>
            <Col span={12} key={`${item.param_type}-col2`}>
              <Form.Item name={`${item.param_type}_value`} initialValue={item.param_default_value} label=" " labelCol={{ span: 24 }} className="mb-0">
                <Input 
                  type='number' 
                  step={item.param_type === 'temperature' ? '0.01' : '1'} 
                  placeholder={t('chat_layout_config_input_param', { desc: item.param_description })}
                  className='w-full' 
                  onBlur={() => onInputBlur(`${item.param_type}_value`)}
                />
              </Form.Item>
            </Col>
          </Row>
        );

      case 'resource':
        return (
          <Row gutter={12} key={item.param_type} className="mb-2">
            <Col span={12} key={`${item.param_type}-col1`}>
              <Form.Item
                label={<span style={labelStyle} title={item.param_description}>{item.param_description}</span>}
                name={`${item.param_type}_sub_type`}
                labelCol={{ span: 24 }}
                className="mb-0"
              >
                <Select
                  className='w-full'
                  options={
                    item.sub_types ? item.sub_types.map((sub: string) => ({ value: sub, label: sub })) || [] : []
                  }
                  placeholder={t('chat_layout_config_select_param', { desc: item.param_description })}
                />
              </Form.Item>
            </Col>
            <Col span={12} key={`${item.param_type}-col2`}>
              <Form.Item name={`${item.param_type}_value`} label=" " labelCol={{ span: 24 }} className="mb-0">
                <Select
                  options={resourceOptions}
                  className='w-full'
                  placeholder={t('chat_layout_config_input_resource')}
                  disabled={MEDIA_RESOURCE_TYPES.includes(form.getFieldValue(`${item.param_type}_sub_type`)) }
                />
              </Form.Item>
            </Col>
          </Row>
        );

      default:
        return null;
    }
  };

  return (
    <>
      {selectedChatConfigs?.map((selectedType: string) => {
        const item = chatConfigOptions?.find((md: any) => md.param_type === selectedType);
        return renderConfigItem(item);
      })}
    </>
  );
}

export default React.memo(ChatLayoutConfig); // 使用 React.memo 优化性能
