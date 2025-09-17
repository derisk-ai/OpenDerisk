import { getAppStrategy, getAppStrategyValues, promptTypeTarget } from '@/client/api';
import { AppContext } from '@/contexts';
import { useRequest } from 'ahooks';
import { Checkbox, Col, Collapse, Form, Input, Modal, Select } from 'antd';
import Image from 'next/image';
import { useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ChatLayoutConfig from './chat-layout-config';

// 可选图标列表
const iconOptions = [
  { value: '/icons/colorful-plugin.png', label: 'agent0' },
  { value: '/agents/agent1.jpg', label: 'agent1' },
  { value: '/agents/agent2.jpg', label: 'agent2' },
  { value: '/agents/agent3.jpg', label: 'agent3' },
  { value: '/agents/agent4.jpg', label: 'agent4' },
  { value: '/agents/agent5.jpg', label: 'agent5' },
];

function BaseInfoItem(props: any) {
  const { handleChangedIcon, onInputBlur } = props;
  const { t, i18n } = useTranslation();
  const { appInfo } = useContext(AppContext);
  const [selectedIcon, setSelectedIcon] = useState<string>(appInfo?.icon || '/agents/agent1.jpg');
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleIconSelect = (iconValue: string) => {
    setSelectedIcon(iconValue);
    setIsModalOpen(false);
    handleChangedIcon(iconValue);
  };

  useEffect(() => {
    if (appInfo?.icon) {
      setSelectedIcon(appInfo.icon);
    }
  }, [appInfo]);

  return (
    <div className='flex gap-6'>
      {/* 左侧：App Icon 选择 */}
      <div className='flex flex-col items-center gap-2'>
        <div
          className='cursor-pointer rounded-md border-2 border-dashed border-gray-300 hover:border-[#0c75fc] p-2 transition-all duration-200'
          onClick={() => setIsModalOpen(true)}
        >
          <Image src={selectedIcon} width={48} height={48} alt='app icon' className='rounded-md' />
        </div>
      </div>

      {/* 右侧：表单字段 */}
      <div className='flex-1 [&_.ant-form-item]:mb-4'>
        <Form.Item name='app_name' required rules={[{ required: true, message: t('input_app_name') }]}>
          <Input
            placeholder={t('input_app_name')}
            autoComplete='off'
            className='h-10'
            onBlur={() => onInputBlur('app_name')}
          />
        </Form.Item>

        <Form.Item
          name='app_describe'
          required
          rules={[{ required: true, message: t('Please_input_the_description') }]}
        >
          <Input.TextArea
            autoComplete='off'
            placeholder={t('Please_input_the_description')}
            autoSize={{ minRows: 3 }}
            onBlur={() => onInputBlur('app_describe')}
          />
        </Form.Item>
      </div>

      {/* Modal 浮层选择图标 */}
      <Modal title={t('App_icon')} open={isModalOpen} onCancel={() => setIsModalOpen(false)} footer={null} width={500}>
        <div className='grid grid-cols-6 gap-4 p-2'>
          {iconOptions.map(icon => (
            <div
              key={icon.value}
              className={`cursor-pointer rounded-md border-2 transition-all duration-200 hover:border-[#0c75fc] p-2 text-center ${
                selectedIcon === icon.value ? 'border-[#0c75fc] bg-[#f5faff]' : 'border-gray-200 hover:bg-gray-50'
              }`}
              onClick={() => handleIconSelect(icon.value)}
            >
              <Image src={icon.value} width={48} height={48} alt={icon.label} className='rounded-md mx-auto mb-2' />
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}

function ModalConfig(props: any) {
  const { form, reasoningEngineOptions } = props;
  const { t } = useTranslation();
  const { appInfo } = useContext(AppContext);
  // const agentType = Form.useWatch('agent', form);

  const { data: strategyData, run: getAppLLm } = useRequest(async () => await getAppStrategy(), {
    manual: true,
  });

  const { data: llmData, run: getAppLLmList } = useRequest(async (type: string) => await getAppStrategyValues(type), {
    manual: true,
  });

  // 获取target选项
  const { data: targetData } = useRequest(async () => await promptTypeTarget('Agent'));

  const targetOptions = useMemo(() => {
    return targetData?.data?.data?.map((option: any) => {
      return {
        ...option,
        value: option.name,
        label: `${option.name} (${option.desc})`,
      };
    });
  }, [targetData]);

  useEffect(() => {
    getAppLLm();
    getAppLLmList(appInfo.llm_strategy || 'priority');
  }, [appInfo.llm_strategy]);

  const strategyOptions = useMemo(() => {
    return strategyData?.data?.data?.map((option: any) => {
      return {
        ...option,
        value: option.value,
        label: option.name_cn,
      };
    });
  }, [strategyData]);

  const llmOptions = useMemo(() => {
    return llmData?.data?.data?.map((option: any) => {
      return {
        ...option,
        value: option,
        label: option,
      };
    });
  }, [llmData]);

  const is_reasoning_engine_agent = useMemo(() => {
    return appInfo?.is_reasoning_engine_agent;
  }, [appInfo]);

  return (
    <div className='flex flex-col gap-1 [&_.ant-form-item]:mb-4'>
      <Form.Item label={t('baseinfo_select_agent_type')} name='agent' rules={[{ required: true, message: t('baseinfo_select_agent_type') }]}>
        <Select placeholder={t('baseinfo_select_agent_type')} options={targetOptions} allowClear className='h-10' />
      </Form.Item>

      {is_reasoning_engine_agent && (
        <Form.Item name={'reasoning_engine'} label={t('baseinfo_reasoning_engine')} rules={[{ required: true, message: t('baseinfo_select_reasoning_engine') }]}>
          <Select options={reasoningEngineOptions} placeholder={t('baseinfo_select_reasoning_engine')} className='h-10' />
        </Form.Item>
      )}

      <Form.Item label={t('baseinfo_llm_strategy')} name='llm_strategy' rules={[{ required: true, message: t('baseinfo_select_llm_strategy') }]}>
        <Select options={strategyOptions} placeholder={t('baseinfo_select_llm_strategy')} className='h-10' />
      </Form.Item>

      <Form.Item label={t('baseinfo_llm_strategy_value')} name='llm_strategy_value' rules={[{ required: true, message: t('baseinfo_select_llm_model') }]}>
        <Select
          mode='multiple'
          allowClear
          options={llmOptions}
          placeholder={t('baseinfo_select_llm_model')}
          className='min-h-10'
        />
      </Form.Item>
    </div>
  );
}

function LayoutConfig(props: any) {
  const { form, layoutDataOptions, chatConfigOptions, onInputBlur, resourceOptions, modelOptions } = props;
  const { t } = useTranslation();
  // Use useWatch to reactively get selectedChatConfigs
  const selectedChatConfigs = Form.useWatch('chat_in_layout', form);
  
  return (
    <div className='flex flex-col gap-1 [&_.ant-form-item]:mb-4'>
      <Form.Item label={t('baseinfo_layout_type')} name='chat_layout' rules={[{ required: true, message: t('baseinfo_select_layout_type') }]}>
        <Select options={layoutDataOptions} placeholder={t('baseinfo_select_layout_type')} className='h-10' />
      </Form.Item>

      <Form.Item
        label={t('baseinfo_chat_config')}
        name='chat_in_layout'
        rules={[{ required: false, message: t('baseinfo_select_chat_config') }]}
      >
        <Checkbox.Group options={chatConfigOptions} className='flex flex-wrap gap-2'></Checkbox.Group>
      </Form.Item>
      <ChatLayoutConfig
        form={form}
        selectedChatConfigs={selectedChatConfigs}
        chatConfigOptions={chatConfigOptions}
        onInputBlur={onInputBlur}
        resourceOptions={resourceOptions}
        modelOptions={modelOptions}
      />
    </div>
  );
}

function BaseInfo(props: any) {
  const {
    form,
    activeKey,
    setActiveKey,
    setIsCollapsed,
    layoutDataOptions,
    reasoningEngineOptions,
    handleChangedIcon,
    onInputBlur,
    chatConfigOptions,
    resourceOptions,
    modelOptions
  } = props;

  const { t } = useTranslation();

  const allItems = [
    {
      label: t('baseinfo_basic_info'),
      children: <BaseInfoItem form={form} handleChangedIcon={handleChangedIcon} onInputBlur={onInputBlur} />,
    },
    {
      label: t('baseinfo_agent_config'),
      children: <ModalConfig form={form} reasoningEngineOptions={reasoningEngineOptions} />,
    },
    {
      label: t('baseinfo_layout'),
      children: (
        <LayoutConfig
          form={form}
          layoutDataOptions={layoutDataOptions}
          chatConfigOptions={chatConfigOptions}
          onInputBlur={onInputBlur}
          resourceOptions={resourceOptions}
          modelOptions={modelOptions}
        />
      ),
    },
  ];

  return (
    <div className='[&_.ant-collapse-header-text]:font-bold'>
      <Collapse
        items={allItems}
        bordered={false}
        activeKey={activeKey}
        onChange={key => {
          setActiveKey(key as string[]);
          setIsCollapsed(key.length === 0);
        }}
        collapsible='header'
      />
    </div>
  );
}

export default BaseInfo;
