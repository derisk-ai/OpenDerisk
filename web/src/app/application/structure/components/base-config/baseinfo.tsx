import { getAppStrategy, getAppStrategyValues, promptTypeTarget } from '@/client/api';
import { AppContext } from '@/contexts';
import { useRequest } from 'ahooks';
import { Checkbox, Form, Input, Modal, Select, Tag } from 'antd';
import Image from 'next/image';
import { useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ChatLayoutConfig from './chat-layout-config';
import { EditOutlined, PictureOutlined, AppstoreOutlined, RobotOutlined, LayoutOutlined, DownOutlined } from '@ant-design/icons';

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
  const { t } = useTranslation();
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
    <div className='flex flex-col gap-4'>
      <div className='flex items-start gap-4'>
        {/* App Icon Selection */}
        <div className='flex flex-col items-center gap-2'>
           <div 
             className="relative group w-16 h-16 rounded-xl border border-gray-200 overflow-hidden shadow-sm hover:shadow-md transition-all duration-200 cursor-pointer"
             onClick={() => setIsModalOpen(true)}
           >
              <Image 
                src={selectedIcon} 
                width={64} 
                height={64} 
                alt='app icon' 
                className='object-cover w-full h-full'
                unoptimized 
              />
              <div 
                className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
              >
                <EditOutlined className="text-white text-lg" />
              </div>
           </div>
           <span className="text-xs text-gray-500">{t('App_icon')}</span>
        </div>

        {/* Form Fields */}
        <div className='flex-1 space-y-4'>
          <Form.Item 
            name='app_name' 
            label={t('input_app_name')}
            required 
            rules={[{ required: true, message: t('input_app_name') }]}
            className="mb-0"
          >
            <Input
              placeholder={t('input_app_name')}
              autoComplete='off'
              className='h-9'
              onBlur={() => onInputBlur('app_name')}
            />
          </Form.Item>

          <Form.Item
            name='app_describe'
            label={t('Please_input_the_description')}
            required
            rules={[{ required: true, message: t('Please_input_the_description') }]}
            className="mb-0"
          >
            <Input.TextArea
              autoComplete='off'
              placeholder={t('Please_input_the_description')}
              autoSize={{ minRows: 3, maxRows: 5 }}
              className="resize-none"
              onBlur={() => onInputBlur('app_describe')}
            />
          </Form.Item>
        </div>
      </div>

      {/* Icon Selection Modal */}
      <Modal 
        title={<div className="flex items-center gap-2"><PictureOutlined /> {t('App_icon')}</div>} 
        open={isModalOpen} 
        onCancel={() => setIsModalOpen(false)} 
        footer={null} 
        width={420}
        centered
      >
        <div className='grid grid-cols-4 gap-4 p-4'>
          {iconOptions.map(icon => (
            <div
              key={icon.value}
              className={`cursor-pointer rounded-xl border-2 transition-all duration-200 p-1 relative group ${
                selectedIcon === icon.value ? 'border-blue-500 bg-blue-50' : 'border-transparent hover:border-gray-200 hover:bg-gray-50'
              }`}
              onClick={() => handleIconSelect(icon.value)}
            >
              <Image src={icon.value} width={60} height={60} alt={icon.label} className='rounded-lg mx-auto shadow-sm' />
               {selectedIcon === icon.value && (
                <div className="absolute top-0 right-0 w-3 h-3 bg-blue-500 rounded-full border-2 border-white translate-x-1/3 -translate-y-1/3"></div>
              )}
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
        label: (
          <div className="flex justify-between items-center">
            <span>{option.name}</span>
            <span className="text-gray-400 text-xs">{option.desc}</span>
          </div>
        ),
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
    <div className='flex flex-col gap-4'>
      <Form.Item 
        label={t('baseinfo_select_agent_type')} 
        name='agent' 
        rules={[{ required: true, message: t('baseinfo_select_agent_type') }]}
        className="mb-0"
      >
        <Select 
          placeholder={t('baseinfo_select_agent_type')} 
          options={targetOptions} 
          allowClear 
          className='w-full' 
        />
      </Form.Item>

      {is_reasoning_engine_agent && (
        <Form.Item 
          name={'reasoning_engine'} 
          label={t('baseinfo_reasoning_engine')} 
          rules={[{ required: true, message: t('baseinfo_select_reasoning_engine') }]}
          className="mb-0"
        >
          <Select options={reasoningEngineOptions} placeholder={t('baseinfo_select_reasoning_engine')} className='w-full' />
        </Form.Item>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Form.Item 
          label={t('baseinfo_llm_strategy')} 
          name='llm_strategy' 
          rules={[{ required: true, message: t('baseinfo_select_llm_strategy') }]}
          className="mb-0"
        >
          <Select options={strategyOptions} placeholder={t('baseinfo_select_llm_strategy')} className='w-full' />
        </Form.Item>
        
         <Form.Item 
          label={t('baseinfo_llm_strategy_value')} 
          name='llm_strategy_value' 
          rules={[{ required: true, message: t('baseinfo_select_llm_model') }]}
          className="mb-0"
        >
          <Select
            mode='multiple'
            allowClear
            options={llmOptions}
            placeholder={t('baseinfo_select_llm_model')}
            className='w-full'
            maxTagCount='responsive'
            style={{ width: '100%' }}
            maxTagPlaceholder={(omittedValues) => (
                <Tag>+{omittedValues.length} ...</Tag>
            )}
          />
        </Form.Item>
      </div>
    </div>
  );
}

function LayoutConfig(props: any) {
  const { form, layoutDataOptions, chatConfigOptions, onInputBlur, resourceOptions, modelOptions } = props;
  const { t } = useTranslation();
  // Use useWatch to reactively get selectedChatConfigs
  const selectedChatConfigs = Form.useWatch('chat_in_layout', form);
  
  return (
    <div className='flex flex-col gap-4'>
      <Form.Item 
        label={t('baseinfo_layout_type')} 
        name='chat_layout' 
        rules={[{ required: true, message: t('baseinfo_select_layout_type') }]}
        className="mb-0"
      >
        <Select options={layoutDataOptions} placeholder={t('baseinfo_select_layout_type')} className='w-full' />
      </Form.Item>

      <Form.Item
        label={t('baseinfo_chat_config')}
        name='chat_in_layout'
        rules={[{ required: false, message: t('baseinfo_select_chat_config') }]}
        className="mb-0"
      >
        <Checkbox.Group options={chatConfigOptions} className='flex flex-wrap gap-2'></Checkbox.Group>
      </Form.Item>
      
      {selectedChatConfigs && selectedChatConfigs.length > 0 && (
         <div className="bg-gray-50 p-3 rounded-lg border border-gray-100 mt-2">
            <ChatLayoutConfig
              form={form}
              selectedChatConfigs={selectedChatConfigs}
              chatConfigOptions={chatConfigOptions}
              onInputBlur={onInputBlur}
              resourceOptions={resourceOptions}
              modelOptions={modelOptions}
            />
         </div>
      )}
    </div>
  );
}

function Section({ 
  title, 
  icon, 
  children, 
  defaultExpanded = true,
  iconColor = 'text-gray-500'
}: { 
  title: string; 
  icon: React.ReactNode; 
  children: React.ReactNode;
  defaultExpanded?: boolean;
  iconColor?: string;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  
  return (
    <div className="mb-4">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between py-2 px-1 text-left hover:bg-gray-50 rounded-lg transition-colors group"
      >
        <div className="flex items-center gap-2">
          <span className={iconColor}>{icon}</span>
          <span className="font-medium text-gray-700 text-sm">{title}</span>
        </div>
        <DownOutlined 
          className={`text-xs text-gray-400 transition-transform duration-200 ${expanded ? '' : '-rotate-90'}`} 
        />
      </button>
      
      <div 
        className={`overflow-hidden transition-all duration-200 ease-in-out ${
          expanded ? 'max-h-[1000px] opacity-100 mt-3' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="pl-1">
          {children}
        </div>
      </div>
    </div>
  );
}

function BaseInfo(props: any) {
  const {
    form,
    layoutDataOptions,
    reasoningEngineOptions,
    handleChangedIcon,
    onInputBlur,
    chatConfigOptions,
    resourceOptions,
    modelOptions
  } = props;

  const { t } = useTranslation();

  return (
    <div className='space-y-2'>
      <Section 
        title={t('baseinfo_basic_info')} 
        icon={<AppstoreOutlined />}
        iconColor="text-blue-500"
        defaultExpanded={true}
      >
        <BaseInfoItem form={form} handleChangedIcon={handleChangedIcon} onInputBlur={onInputBlur} />
      </Section>

      <Section 
        title={t('baseinfo_agent_config')} 
        icon={<RobotOutlined />}
        iconColor="text-purple-500"
        defaultExpanded={true}
      >
        <ModalConfig form={form} reasoningEngineOptions={reasoningEngineOptions} />
      </Section>

      <Section 
        title={t('baseinfo_layout')} 
        icon={<LayoutOutlined />}
        iconColor="text-green-500"
        defaultExpanded={true}
      >
        <LayoutConfig
          form={form}
          layoutDataOptions={layoutDataOptions}
          chatConfigOptions={chatConfigOptions}
          onInputBlur={onInputBlur}
          resourceOptions={resourceOptions}
          modelOptions={modelOptions}
        />
      </Section>
    </div>
  );
}

export default BaseInfo;
