'use client';

import { ChannelConfig } from '@/client/api/channel';
import { Form, Input, Select, Switch, Card, Typography, Divider } from 'antd';
import Image from 'next/image';
import React from 'react';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

interface ChannelFormProps {
  form: any;
  initialValues?: Partial<ChannelConfig>;
  onValuesChange?: (changedValues: any, allValues: any) => void;
}

// Channel type icons
const channelTypeIcons: Record<string, React.ReactNode> = {
  dingtalk: <Image src="/icons/channel/dingtalk.svg" alt="DingTalk" width={20} height={20} className="inline-block mr-2" />,
  feishu: <Image src="/icons/channel/feishu.svg" alt="Feishu" width={20} height={20} className="inline-block mr-2" />,
  wechat: <span className="mr-2">💬</span>,
  qq: <span className="mr-2">🐧</span>,
};

export default function ChannelForm({ form, initialValues, onValuesChange }: ChannelFormProps) {
  const { t } = useTranslation();
  const channelType = Form.useWatch('channel_type', form);

  // Render platform-specific config fields
  const renderPlatformConfig = () => {
    if (!channelType) return null;

    if (channelType === 'dingtalk') {
      return (
        <Card size="small" title={t('channel_dingtalk_config')} className="mb-4">
          <Form.Item
            name={['config', 'app_id']}
            label={t('channel_app_id')}
            rules={[{ required: true, message: t('Please_Input') }]}
          >
            <Input placeholder="DingTalk AppKey" />
          </Form.Item>
          <Form.Item
            name={['config', 'app_secret']}
            label={t('channel_app_secret')}
            rules={[{ required: true, message: t('Please_Input') }]}
          >
            <Input.Password placeholder="DingTalk AppSecret" />
          </Form.Item>
          <Form.Item name={['config', 'webhook_url']} label={t('channel_webhook_url')}>
            <Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
          </Form.Item>
          <Form.Item name={['config', 'token']} label={t('channel_token')}>
            <Input placeholder="Token for signature validation" />
          </Form.Item>
          <Form.Item name={['config', 'aes_key']} label={t('channel_aes_key')}>
            <Input.Password placeholder="AES key for encryption" />
          </Form.Item>
          <Form.Item name={['config', 'agent_id']} label={t('channel_agent_id')}>
            <Input placeholder="DingTalk Agent ID" />
          </Form.Item>
        </Card>
      );
    }

    if (channelType === 'feishu') {
      return (
        <Card size="small" title={t('channel_feishu_config')} className="mb-4">
          <Form.Item
            name={['config', 'app_id']}
            label={t('channel_app_id')}
            rules={[{ required: true, message: t('Please_Input') }]}
          >
            <Input placeholder="Feishu App ID" />
          </Form.Item>
          <Form.Item
            name={['config', 'app_secret']}
            label={t('channel_app_secret')}
            rules={[{ required: true, message: t('Please_Input') }]}
          >
            <Input.Password placeholder="Feishu App Secret" />
          </Form.Item>
          <Form.Item name={['config', 'encrypt_key']} label={t('channel_encrypt_key')}>
            <Input.Password placeholder="Encrypt key for message encryption" />
          </Form.Item>
          <Form.Item name={['config', 'verification_token']} label={t('channel_verification_token')}>
            <Input placeholder="Verification token for events" />
          </Form.Item>
          <Form.Item name={['config', 'domain']} label={t('channel_domain')}>
            <Select placeholder="Select domain">
              <Select.Option value="feishu">Feishu (China)</Select.Option>
              <Select.Option value="lark">Lark (International)</Select.Option>
            </Select>
          </Form.Item>
        </Card>
      );
    }

    if (channelType === 'wechat') {
      return (
        <Card size="small" title="WeChat Configuration" className="mb-4">
          <Form.Item
            name={['config', 'app_id']}
            label={t('channel_app_id')}
            rules={[{ required: true, message: t('Please_Input') }]}
          >
            <Input placeholder="WeChat App ID" />
          </Form.Item>
          <Form.Item
            name={['config', 'app_secret']}
            label={t('channel_app_secret')}
            rules={[{ required: true, message: t('Please_Input') }]}
          >
            <Input.Password placeholder="WeChat App Secret" />
          </Form.Item>
          <Form.Item name={['config', 'token']} label={t('channel_token')}>
            <Input placeholder="Token for signature validation" />
          </Form.Item>
          <Form.Item name={['config', 'encoding_aes_key']} label="Encoding AES Key">
            <Input.Password placeholder="Encoding AES Key" />
          </Form.Item>
        </Card>
      );
    }

    if (channelType === 'qq') {
      return (
        <Card size="small" title="QQ Configuration" className="mb-4">
          <Form.Item name={['config', 'app_id']} label={t('channel_app_id')}>
            <Input placeholder="QQ App ID" />
          </Form.Item>
          <Form.Item name={['config', 'app_secret']} label={t('channel_app_secret')}>
            <Input.Password placeholder="QQ App Secret" />
          </Form.Item>
          <Form.Item name={['config', 'token']} label={t('channel_token')}>
            <Input placeholder="Token" />
          </Form.Item>
        </Card>
      );
    }

    return null;
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{
        enabled: true,
        channel_type: 'dingtalk',
        config: {},
        ...initialValues,
      }}
      onValuesChange={onValuesChange}
    >
      {/* Basic Info */}
      <Card size="small" title={t('channel_basic_info')} className="mb-4">
        <Form.Item
          name="name"
          label={t('channel_name')}
          rules={[{ required: true, message: t('Please_Input') }]}
        >
          <Input placeholder={t('channel_name_placeholder')} />
        </Form.Item>
        <Form.Item
          name="channel_type"
          label={t('channel_type')}
          rules={[{ required: true, message: t('please_select') }]}
        >
          <Select placeholder={t('channel_type_placeholder')}>
            <Select.Option value="dingtalk">
              {channelTypeIcons.dingtalk} {t('channel_dingtalk')}
            </Select.Option>
            <Select.Option value="feishu">
              {channelTypeIcons.feishu} {t('channel_feishu')}
            </Select.Option>
            <Select.Option value="wechat" disabled>
              {channelTypeIcons.wechat} WeChat ({t('channel_coming_soon')})
            </Select.Option>
            <Select.Option value="qq" disabled>
              {channelTypeIcons.qq} QQ ({t('channel_coming_soon')})
            </Select.Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="enabled"
          label={t('channel_enabled')}
          valuePropName="checked"
        >
          <Switch checkedChildren={t('Yes')} unCheckedChildren={t('No')} />
        </Form.Item>
      </Card>

      {/* Platform-specific config */}
      {renderPlatformConfig()}
    </Form>
  );
}