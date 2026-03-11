'use client';
import { getAppStrategy, getAppStrategyValues, promptTypeTarget, getChatLayout, getChatInputConfig, getChatInputConfigParams, getResourceV2, apiInterceptors, getUsableModels, getAgentList } from '@/client/api';
import { AppContext } from '@/contexts';
import { safeJsonParse } from '@/utils/json';
import { useRequest } from 'ahooks';
import { Checkbox, Form, Input, Select, Tag, Modal, Radio, Space, Typography, Card } from 'antd';
import { isString, uniqBy } from 'lodash';
import Image from 'next/image';
import { useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ChatLayoutConfig from './chat-layout-config';
import { EditOutlined, PictureOutlined, ThunderboltOutlined, RocketOutlined } from '@ant-design/icons';

const { Text, Paragraph } = Typography;

const iconOptions = [
  { value: '/icons/colorful-plugin.png', label: 'agent0' },
  { value: '/agents/agent1.jpg', label: 'agent1' },
  { value: '/agents/agent2.jpg', label: 'agent2' },
  { value: '/agents/agent3.jpg', label: 'agent3' },
  { value: '/agents/agent4.jpg', label: 'agent4' },
  { value: '/agents/agent5.jpg', label: 'agent5' },
];

const layoutConfigChangeList = [
  'chat_in_layout',
  'resource_sub_type',
  'model_sub_type',
  'temperature_sub_type',
  'max_new_tokens_sub_type',
  'resource_value',
  'model_value',
];

const layoutConfigValueChangeList = [
  'temperature_value',
  'max_new_tokens_value',
];

const V2_AGENT_ICONS: Record<string, string> = {
  react_reasoning: '🧠',
  coding: '💻',
  simple_chat: '💬',
};

export default function TabOverview() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [form] = Form.useForm();
  const [selectedIcon, setSelectedIcon] = useState<string>(appInfo?.icon || '/agents/agent1.jpg');
  const [isIconModalOpen, setIsIconModalOpen] = useState(false);
  const [resourceOptions, setResourceOptions] = useState<any[]>([]);
  const [agentVersion, setAgentVersion] = useState<string>(appInfo?.agent_version || 'v1');

  // Initialize form values from appInfo
  useEffect(() => {
    if (appInfo) {
      const { layout } = appInfo || {};
      const engineItem = appInfo?.resources?.find((item: any) => item.type === 'reasoning_engine');
      const engineItemValue = isString(engineItem?.value) ? safeJsonParse(engineItem?.value, {}) : engineItem?.value;

      const chat_in_layout_list = layout?.chat_in_layout?.map((item: any) => item.param_type) || [];
      let chat_in_layout_obj: any = {};
      chat_in_layout_list.forEach((type: string) => {
        const item = layout?.chat_in_layout?.find((i: any) => i.param_type === type);
        if (!item) return;
        if (type === 'resource') {
          chat_in_layout_obj = { ...chat_in_layout_obj, resource_sub_type: item.sub_type, resource_value: item.param_default_value };
        } else if (type === 'model') {
          chat_in_layout_obj = { ...chat_in_layout_obj, model_sub_type: item.sub_type, model_value: item.param_default_value };
        } else if (type === 'temperature') {
          chat_in_layout_obj = { ...chat_in_layout_obj, temperature_sub_type: item.sub_type, temperature_value: item.param_default_value };
        } else if (type === 'max_new_tokens') {
          chat_in_layout_obj = { ...chat_in_layout_obj, max_new_tokens_sub_type: item.sub_type, max_new_tokens_value: item.param_default_value };
        }
      });

      const currentAgentVersion = appInfo.agent_version || 'v1';
      const v2TemplateName = appInfo?.team_context?.agent_name || 'simple_chat';
      
      form.setFieldsValue({
        app_name: appInfo.app_name,
        app_describe: appInfo.app_describe,
        agent: currentAgentVersion === 'v1' ? appInfo.agent : undefined,
        agent_version: currentAgentVersion,
        v2_agent_template: currentAgentVersion === 'v2' ? v2TemplateName : undefined,
        llm_strategy: appInfo?.llm_config?.llm_strategy,
        llm_strategy_value: appInfo?.llm_config?.llm_strategy_value || [],
        chat_layout: layout?.chat_layout?.name || '',
        chat_in_layout: chat_in_layout_list || [],
        reasoning_engine: engineItemValue?.key ?? engineItemValue?.name,
        ...chat_in_layout_obj,
      });
      
      setAgentVersion(currentAgentVersion);
      setSelectedIcon(appInfo.icon || '/agents/agent1.jpg');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appInfo]);

  // Fetch data
  const { data: strategyData } = useRequest(async () => await getAppStrategy());
  const { data: llmData, run: getAppLLmList } = useRequest(
    async (type: string) => await getAppStrategyValues(type),
    { manual: true },
  );
  const { data: targetData } = useRequest(async () => await promptTypeTarget('Agent'));
  const { data: layoutData } = useRequest(async () => await getChatLayout());
  const { data: reasoningEngineData } = useRequest(async () => await getResourceV2({ type: 'reasoning_engine' }));
  const { data: chatConfigData } = useRequest(async () => await getChatInputConfig());
  const { run: chatInputConfigParams } = useRequest(
    async (data: any) => await getChatInputConfigParams([data]),
    {
      manual: true,
      onSuccess: data => {
        const resourceData = data?.data?.data[0]?.param_type_options;
        if (!resourceData) return;
        setResourceOptions(resourceData.map((item: any) => ({ ...item, label: item.label, value: item.key || item.value })));
      },
    },
  );
  const { data: modelList = [] } = useRequest(async () => {
    const [, res] = await apiInterceptors(getUsableModels());
    return res ?? [];
  });
  
  // 获取 V2 Agent 模板列表
  const { data: v2AgentTemplates, run: fetchV2Agents } = useRequest(
    async () => {
      const res = await getAgentList('v2');
      // API 直接返回 { version, agents }，不需要 .data
      return res?.data?.agents || res?.agents || [];
    },
    { manual: true },
  );
  
  // 当 agent_version 变化时获取对应的 Agent 列表
  useEffect(() => {
    if (agentVersion === 'v2') {
      fetchV2Agents();
    }
  }, [agentVersion, fetchV2Agents]);

  useEffect(() => {
    getAppLLmList(appInfo?.llm_config?.llm_strategy || 'priority');
  }, [appInfo?.llm_config?.llm_strategy]);

  useEffect(() => {
    const resource = appInfo?.layout?.chat_in_layout?.find((i: any) => i.param_type === 'resource');
    if (resource) chatInputConfigParams(resource);
  }, [appInfo?.layout?.chat_in_layout]);

  // Memoized options
  const strategyOptions = useMemo(() => strategyData?.data?.data?.map((o: any) => ({ ...o, value: o.value, label: o.name_cn })), [strategyData]);
  const llmOptions = useMemo(() => llmData?.data?.data?.map((o: any) => ({ value: o, label: o })), [llmData]);
  const targetOptions = useMemo(() => targetData?.data?.data?.map((o: any) => ({
    ...o, value: o.name, label: (<div className="flex justify-between items-center"><span>{o.name}</span><span className="text-gray-400 text-xs">{o.desc}</span></div>),
  })), [targetData]);
  const layoutDataOptions = useMemo(() => layoutData?.data?.data?.map((o: any) => ({ ...o, value: o.name, label: `${o.description}[${o.name}]` })), [layoutData]);
  const reasoningEngineOptions = useMemo(() =>
    reasoningEngineData?.data?.data?.flatMap((item: any) =>
      item.valid_values?.map((o: any) => ({ item: o, value: o.key, label: o.label, selected: true })) || [],
    ), [reasoningEngineData]);
  const chatConfigOptions = useMemo(() => chatConfigData?.data?.data?.map((o: any) => ({ ...o, value: o.param_type, label: o.param_description })), [chatConfigData]);
  const modelOptions = useMemo(() => modelList.map((item: string) => ({ value: item, label: item })), [modelList]);
  const selectedChatConfigs = Form.useWatch('chat_in_layout', form);

  const is_reasoning_engine_agent = useMemo(() => appInfo?.is_reasoning_engine_agent, [appInfo]);
  
  // V2 Agent 模板选项
  const v2AgentOptions = useMemo(() => 
    v2AgentTemplates?.map((agent: any) => ({
      value: agent.name,
      label: agent.display_name,
      agent,
    })) || [],
  [v2AgentTemplates]);
  
  // 当前选中的 Agent 版本
  const currentAgentVersion = Form.useWatch('agent_version', form);

  // Layout config change handler
  const layoutConfigChange = () => {
    const changeFieldValue = form.getFieldValue('chat_in_layout') || [];
    const curConfig = changeFieldValue
      .map((item: string) => {
        const { label, value, sub_types, ...rest } = chatConfigOptions?.find((md: any) => item === md.param_type) || {};
        if (item === 'resource') return { ...rest, param_default_value: form.getFieldValue('resource_value') || null, sub_type: form.getFieldValue('resource_sub_type') || null };
        if (item === 'model') return { ...rest, param_default_value: form.getFieldValue('model_value') || null, sub_type: form.getFieldValue('model_sub_type') || null };
        if (item === 'temperature') return { ...rest, param_default_value: Number(form.getFieldValue('temperature_value') || rest.param_default_value || null), sub_type: form.getFieldValue('temperature_sub_type') || null };
        if (item === 'max_new_tokens') return { ...rest, param_default_value: Number(form.getFieldValue('max_new_tokens_value') || rest.param_default_value), sub_type: form.getFieldValue('max_new_tokens_sub_type') || null };
        return chatConfigOptions?.find((md: any) => item.includes(md.param_type)) || {};
      })
      .filter((obj: any) => Object.keys(obj).length > 0);
    fetchUpdateApp({ ...appInfo, layout: { ...appInfo.layout, chat_in_layout: curConfig } });
  };

  const onInputBlur = (name: string) => {
    if (layoutConfigValueChangeList.includes(name)) {
      layoutConfigChange();
    } else {
      if (appInfo[name] !== form.getFieldValue(name)) {
        fetchUpdateApp({ ...appInfo, [name]: form.getFieldValue(name) });
      }
    }
  };

  const onValuesChange = (changedValues: any) => {
    const [fieldName] = Object.keys(changedValues ?? {});
    const [fieldValue] = Object.values(changedValues ?? {});

    if (fieldName === 'agent') {
      fetchUpdateApp({ ...appInfo, agent: fieldValue });
    } else if (fieldName === 'agent_version') {
      setAgentVersion(fieldValue);
      // 切换版本时更新 team_context 和清除旧字段
      const currentTeamContext = appInfo?.team_context || {};
      if (fieldValue === 'v2') {
        // 切换到 V2，设置默认的 V2 模板
        const v2TemplateName = 'simple_chat';
        form.setFieldValue('v2_agent_template', v2TemplateName);
        form.setFieldValue('agent', undefined); // 清除 V1 的 agent 值
        const newTeamContext = {
          ...currentTeamContext,
          agent_version: fieldValue,
          agent_name: v2TemplateName,
        };
        fetchUpdateApp({ ...appInfo, agent_version: fieldValue, team_context: newTeamContext, agent: undefined });
      } else {
        // 切换到 V1
        form.setFieldValue('v2_agent_template', undefined);
        const newTeamContext = {
          ...currentTeamContext,
          agent_version: fieldValue,
        };
        fetchUpdateApp({ ...appInfo, agent_version: fieldValue, team_context: newTeamContext });
      }
    } else if (fieldName === 'v2_agent_template') {
      // V2 Agent 模板选择
      const currentTeamContext = appInfo?.team_context || {};
      const newTeamContext = {
        ...currentTeamContext,
        agent_name: fieldValue,
      };
      fetchUpdateApp({ ...appInfo, team_context: newTeamContext });
    } else if (fieldName === 'llm_strategy') {
      fetchUpdateApp({ ...appInfo, llm_config: { llm_strategy: fieldValue as string, llm_strategy_value: appInfo.llm_config?.llm_strategy_value || [] } });
    } else if (fieldName === 'llm_strategy_value') {
      fetchUpdateApp({ ...appInfo, llm_config: { llm_strategy: form.getFieldValue('llm_strategy'), llm_strategy_value: fieldValue as string[] } });
    } else if (fieldName === 'chat_layout') {
      const currentChatLayout = layoutDataOptions?.find((item: any) => item.value === fieldValue);
      fetchUpdateApp({ ...appInfo, layout: { ...appInfo.layout, chat_layout: currentChatLayout } });
    } else if (fieldName === 'reasoning_engine') {
      const currentEngine = reasoningEngineOptions?.find((item: any) => item.value === fieldValue);
      if (currentEngine) {
        fetchUpdateApp({ ...appInfo, resources: uniqBy([{ type: 'reasoning_engine', value: currentEngine.item }, ...(appInfo.resources ?? [])], 'type') });
      }
    } else if (layoutConfigChangeList.includes(fieldName)) {
      layoutConfigChange();
    }
  };

  const handleIconSelect = (iconValue: string) => {
    setSelectedIcon(iconValue);
    setIsIconModalOpen(false);
    fetchUpdateApp({ ...appInfo, icon: iconValue });
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5 custom-scrollbar">
      <Form form={form} layout="vertical" onValuesChange={onValuesChange}
        className="[&_.ant-form-item-label>label]:text-gray-500 [&_.ant-form-item-label>label]:text-xs [&_.ant-form-item-label>label]:font-medium [&_.ant-form-item-label>label]:uppercase [&_.ant-form-item-label>label]:tracking-wider">

        {/* Two-column grid: Basic Info (left) + Agent Config (right) */}
        <div className="grid grid-cols-2 gap-6">
          {/* Basic Info Section - Left Column */}
          <div className="bg-gray-50/30 rounded-xl border border-gray-100/60 p-5">
            <h3 className="text-[13px] font-semibold text-gray-700 mb-4 flex items-center gap-2">
              <div className="w-1 h-4 rounded-full bg-gradient-to-b from-blue-500 to-indigo-500" />
              {t('baseinfo_basic_info')}
            </h3>
            <div className="flex items-start gap-4">
              <div className="flex flex-col items-center gap-2">
                <div
                  className="relative group w-16 h-16 rounded-2xl border border-gray-200/60 overflow-hidden shadow-sm hover:shadow-lg hover:border-blue-200/60 transition-all duration-300 cursor-pointer ring-2 ring-white"
                  onClick={() => setIsIconModalOpen(true)}
                >
                  <Image src={selectedIcon} width={64} height={64} alt="agent icon" className="object-cover w-full h-full" unoptimized />
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 backdrop-blur-[2px]" style={{ backgroundColor: 'rgba(0,0,0,0.35)' }}>
                    <EditOutlined className="text-white text-lg drop-shadow-sm" />
                  </div>
                </div>
                <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wider">{t('App_icon')}</span>
              </div>
              <div className="flex-1 space-y-4">
                <Form.Item name="app_name" label={t('input_app_name')} required rules={[{ required: true, message: t('input_app_name') }]} className="mb-0">
                  <Input placeholder={t('input_app_name')} autoComplete="off" className="h-9 rounded-lg" onBlur={() => onInputBlur('app_name')} />
                </Form.Item>
                <Form.Item name="app_describe" label={t('Please_input_the_description')} required rules={[{ required: true, message: t('Please_input_the_description') }]} className="mb-0">
                  <Input.TextArea autoComplete="off" placeholder={t('Please_input_the_description')} autoSize={{ minRows: 3, maxRows: 5 }} className="resize-none rounded-lg" onBlur={() => onInputBlur('app_describe')} />
                </Form.Item>
              </div>
            </div>
          </div>

          {/* Agent Config Section - Right Column */}
          <div className="bg-gray-50/30 rounded-xl border border-gray-100/60 p-5">
            <h3 className="text-[13px] font-semibold text-gray-700 mb-4 flex items-center gap-2">
              <div className="w-1 h-4 rounded-full bg-gradient-to-b from-violet-500 to-purple-500" />
              {t('baseinfo_agent_config')}
            </h3>
            <div className="space-y-4">
              {/* Agent Version 选择器 - 放在上面 */}
              <Form.Item label="Agent Version" name="agent_version" className="mb-0">
                <Radio.Group className="w-full">
                  <div className="grid grid-cols-2 gap-3">
                    <Radio.Button value="v1" className="h-auto py-3 px-4 rounded-xl border-2 [&.ant-radio-button-wrapper-checked]:border-blue-500 [&.ant-radio-button-wrapper-checked]:bg-blue-50/60">
                      <div className="flex items-center gap-2">
                        <ThunderboltOutlined className="text-lg text-blue-500" />
                        <div>
                          <div className="font-semibold text-sm">V1 Classic</div>
                          <div className="text-xs text-gray-400">Stable PDCA Agent</div>
                        </div>
                      </div>
                    </Radio.Button>
                    <Radio.Button value="v2" className="h-auto py-3 px-4 rounded-xl border-2 [&.ant-radio-button-wrapper-checked]:border-green-500 [&.ant-radio-button-wrapper-checked]:bg-green-50/60">
                      <div className="flex items-center gap-2">
                        <RocketOutlined className="text-lg text-green-500" />
                        <div>
                          <div className="font-semibold text-sm">V2 Core_v2</div>
                          <div className="text-xs text-gray-400">Canvas + Progress</div>
                        </div>
                      </div>
                    </Radio.Button>
                  </div>
                </Radio.Group>
              </Form.Item>
              {/* Agent 模板选择器 - 根据版本动态切换 */}
              {currentAgentVersion === 'v2' ? (
                <Form.Item 
                  label="Agent Template" 
                  name="v2_agent_template" 
                  key="v2_agent_template"
                  rules={[{ required: true, message: 'Please select a V2 Agent template' }]} 
                  className="mb-0"
                >
                  <Select 
                    placeholder="Select V2 Agent Template" 
                    options={v2AgentOptions} 
                    className="w-full [&_.ant-select-selector]:!rounded-lg"
                    loading={!v2AgentTemplates || v2AgentTemplates.length === 0}
                    optionRender={(option) => (
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{V2_AGENT_ICONS[option.value as string] || '🤖'}</span>
                        <div>
                          <div className="font-medium">{option.data?.agent?.display_name || option.label}</div>
                          <div className="text-xs text-gray-400">{option.data?.agent?.description}</div>
                        </div>
                      </div>
                    )}
                  />
                </Form.Item>
              ) : (
                <Form.Item 
                  label={t('baseinfo_select_agent_type')} 
                  name="agent" 
                  key="v1_agent"
                  rules={[{ required: true, message: t('baseinfo_select_agent_type') }]} 
                  className="mb-0"
                >
                  <Select 
                    placeholder={t('baseinfo_select_agent_type')} 
                    options={targetOptions} 
                    allowClear 
                    className="w-full [&_.ant-select-selector]:!rounded-lg" 
                  />
                </Form.Item>
              )}
              {is_reasoning_engine_agent && (
                <Form.Item name="reasoning_engine" label={t('baseinfo_reasoning_engine')} rules={[{ required: true, message: t('baseinfo_select_reasoning_engine') }]} className="mb-0">
                  <Select options={reasoningEngineOptions} placeholder={t('baseinfo_select_reasoning_engine')} className="w-full [&_.ant-select-selector]:!rounded-lg" />
                </Form.Item>
              )}
              <Form.Item label={t('baseinfo_llm_strategy')} name="llm_strategy" rules={[{ required: true, message: t('baseinfo_select_llm_strategy') }]} className="mb-0">
                <Select options={strategyOptions} placeholder={t('baseinfo_select_llm_strategy')} className="w-full [&_.ant-select-selector]:!rounded-lg" />
              </Form.Item>
              <Form.Item label={t('baseinfo_llm_strategy_value')} name="llm_strategy_value" rules={[{ required: true, message: t('baseinfo_select_llm_model') }]} className="mb-0">
                <Select mode="multiple" allowClear options={llmOptions} placeholder={t('baseinfo_select_llm_model')} className="w-full [&_.ant-select-selector]:!rounded-lg" maxTagCount="responsive"
                  maxTagPlaceholder={(omittedValues) => (<Tag className="rounded-md text-[10px] font-medium">+{omittedValues.length} ...</Tag>)} />
              </Form.Item>
            </div>
          </div>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-gray-200/60 to-transparent my-6" />

        {/* Layout Section — full width below */}
        <div className="bg-gray-50/30 rounded-xl border border-gray-100/60 p-5">
          <h3 className="text-[13px] font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-gradient-to-b from-emerald-500 to-green-500" />
            {t('baseinfo_layout')}
          </h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Form.Item label={t('baseinfo_layout_type')} name="chat_layout" rules={[{ required: true, message: t('baseinfo_select_layout_type') }]} className="mb-0">
              <Select options={layoutDataOptions} placeholder={t('baseinfo_select_layout_type')} className="w-full [&_.ant-select-selector]:!rounded-lg" />
            </Form.Item>
            <Form.Item label={t('baseinfo_chat_config')} name="chat_in_layout" className="mb-0">
              <Checkbox.Group options={chatConfigOptions} className="flex flex-wrap gap-2" />
            </Form.Item>
            {selectedChatConfigs && selectedChatConfigs.length > 0 && (
              <div className="col-span-2 bg-white/60 p-3.5 rounded-xl border border-gray-100/60 mt-1">
                <ChatLayoutConfig form={form} selectedChatConfigs={selectedChatConfigs} chatConfigOptions={chatConfigOptions} onInputBlur={onInputBlur} resourceOptions={resourceOptions} modelOptions={modelOptions} />
              </div>
            )}
          </div>
        </div>
      </Form>

      {/* Icon Selection Modal */}
      <Modal
        title={<div className="flex items-center gap-2.5"><div className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-100 to-indigo-50 flex items-center justify-center"><PictureOutlined className="text-blue-500 text-xs" /></div><span className="font-semibold text-gray-700">{t('App_icon')}</span></div>}
        open={isIconModalOpen}
        onCancel={() => setIsIconModalOpen(false)}
        footer={null}
        width={420}
        centered
        className="[&_.ant-modal-content]:rounded-2xl [&_.ant-modal-content]:shadow-2xl [&_.ant-modal-header]:border-b-0 [&_.ant-modal-header]:pb-0"
      >
        <div className="grid grid-cols-4 gap-3 p-5">
          {iconOptions.map(icon => (
            <div key={icon.value} className={`cursor-pointer rounded-2xl border-2 transition-all duration-300 p-1.5 relative group hover:scale-105 ${selectedIcon === icon.value ? 'border-blue-500 bg-blue-50/60 shadow-md shadow-blue-500/10' : 'border-transparent hover:border-gray-200/80 hover:bg-gray-50/60 hover:shadow-sm'}`} onClick={() => handleIconSelect(icon.value)}>
              <Image src={icon.value} width={60} height={60} alt={icon.label} className="rounded-xl mx-auto shadow-sm" />
              {selectedIcon === icon.value && (
                <div className="absolute -top-1 -right-1 w-5 h-5 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full border-2 border-white flex items-center justify-center shadow-sm">
                  <span className="text-white text-[8px] font-bold">✓</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
