'use client';
import { getAppStrategy, getAppStrategyValues, promptTypeTarget, getChatLayout, getChatInputConfig, getChatInputConfigParams, getResourceV2, apiInterceptors, getUsableModels, getAgentList } from '@/client/api';
import { AppContext } from '@/contexts';
import { safeJsonParse } from '@/utils/json';
import { useRequest } from 'ahooks';
import { Checkbox, Form, Input, Select, Tag, Modal, Radio, Space, Typography, Card, Switch, Tooltip } from 'antd';
import { isString, uniqBy } from 'lodash';
import Image from 'next/image';
import { useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ChatLayoutConfig from './chat-layout-config';
import { EditOutlined, PictureOutlined, ThunderboltOutlined, RocketOutlined, CloudServerOutlined } from '@ant-design/icons';
import { SmartPluginIcon } from '@/components/icons/smart-plugin-icon';

const { Text, Paragraph } = Typography;

const iconOptions = [
  { value: 'smart-plugin', label: '智能插件', category: 'preset', color: 'from-indigo-500 to-purple-500', isSvg: true },
  { value: '/agents/agent1.jpg', label: '数据分析', category: 'preset', color: 'from-emerald-500 to-teal-500' },
  { value: '/agents/agent2.jpg', label: '代码助手', category: 'preset', color: 'from-violet-500 to-purple-500' },
  { value: '/agents/agent3.jpg', label: '文档处理', category: 'preset', color: 'from-orange-500 to-amber-500' },
  { value: '/agents/agent4.jpg', label: '安全审计', category: 'preset', color: 'from-rose-500 to-pink-500' },
  { value: '/agents/agent5.jpg', label: '系统运维', category: 'preset', color: 'from-cyan-500 to-blue-500' },
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
  const [selectedIcon, setSelectedIcon] = useState<string>(appInfo?.icon || 'smart-plugin');
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
      const teamContext = appInfo?.team_context;
      const parsedTeamContext = typeof teamContext === 'string' 
        ? safeJsonParse(teamContext, {}) 
        : (teamContext || {});
      
      const defaultV1Agent = 'BAIZE';
      const v1AgentValue = currentAgentVersion === 'v1' 
        ? (appInfo.agent || defaultV1Agent) 
        : undefined;
      
      form.setFieldsValue({
        app_name: appInfo.app_name,
        app_describe: appInfo.app_describe,
        agent: v1AgentValue,
        agent_version: currentAgentVersion,
        v2_agent_template: currentAgentVersion === 'v2' ? v2TemplateName : undefined,
        llm_strategy: appInfo?.llm_config?.llm_strategy,
        llm_strategy_value: appInfo?.llm_config?.llm_strategy_value || [],
        chat_layout: layout?.chat_layout?.name || '',
        chat_in_layout: chat_in_layout_list || [],
        reasoning_engine: engineItemValue?.key ?? engineItemValue?.name,
        use_sandbox: parsedTeamContext?.use_sandbox ?? false,
        ...chat_in_layout_obj,
      });
      
      setAgentVersion(currentAgentVersion);
      setSelectedIcon(appInfo.icon || 'smart-plugin');
      
      if (currentAgentVersion === 'v1' && !appInfo.agent) {
        fetchUpdateApp({ ...appInfo, agent: defaultV1Agent });
      }
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
        // 切换到 V1，设置默认的 V1 Agent 为 BAIZE
        const defaultV1Agent = 'BAIZE';
        form.setFieldValue('v2_agent_template', undefined);
        form.setFieldValue('agent', defaultV1Agent);
        const newTeamContext = {
          ...currentTeamContext,
          agent_version: fieldValue,
        };
        fetchUpdateApp({ ...appInfo, agent_version: fieldValue, team_context: newTeamContext, agent: defaultV1Agent });
      }
    } else if (fieldName === 'v2_agent_template') {
      const currentTeamContext = appInfo?.team_context || {};
      const newTeamContext = {
        ...currentTeamContext,
        agent_name: fieldValue,
      };
      const agentVersion = appInfo?.agent_version || currentTeamContext?.agent_version || 'v2';
      fetchUpdateApp({ ...appInfo, agent_version: agentVersion, team_context: newTeamContext });
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
    } else if (fieldName === 'use_sandbox') {
      // 确保 team_context 正确解析（可能是字符串或对象）
      const rawTeamContext = appInfo?.team_context;
      console.log('[SandboxToggle] rawTeamContext:', rawTeamContext, 'type:', typeof rawTeamContext);
      const currentTeamContext = typeof rawTeamContext === 'string' 
        ? safeJsonParse(rawTeamContext, {}) 
        : (rawTeamContext || {});
      console.log('[SandboxToggle] currentTeamContext:', currentTeamContext);
      const agentVersion = appInfo?.agent_version || currentTeamContext?.agent_version || 'v1';
      const newTeamContext = {
        ...currentTeamContext,
        agent_version: agentVersion,
        use_sandbox: fieldValue as boolean,
      };
      console.log('[SandboxToggle] newTeamContext:', newTeamContext);
      console.log('[SandboxToggle] Calling fetchUpdateApp with team_context');
      // 确保顶层 agent_version 也正确设置，后端需要根据这个字段决定如何解析 team_context
      fetchUpdateApp({ ...appInfo, agent_version: agentVersion, team_context: newTeamContext });
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
          <div className="bg-gradient-to-br from-slate-50/80 to-gray-50/40 rounded-2xl border border-gray-100/80 p-6 shadow-sm">
            <h3 className="text-[14px] font-semibold text-gray-800 mb-5 flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-md shadow-blue-500/20">
                <PictureOutlined className="text-white text-sm" />
              </div>
              <span>{t('baseinfo_basic_info')}</span>
            </h3>
            <div className="flex items-start gap-5">
              <div className="flex flex-col items-center gap-3">
                <div
                  className="relative group w-20 h-20 rounded-2xl border-2 border-gray-200/80 shadow-md hover:shadow-xl hover:border-blue-300/60 transition-all duration-300 cursor-pointer ring-4 ring-white flex items-center justify-center bg-gradient-to-br from-indigo-50 to-purple-50"
                  onClick={() => setIsIconModalOpen(true)}
                >
                  <div className="w-full h-full rounded-2xl overflow-hidden">
                    {selectedIcon === 'smart-plugin' ? (
                      <SmartPluginIcon size={72} className="relative z-10" />
                    ) : (
                      <Image src={selectedIcon} width={80} height={80} alt="agent icon" className="object-cover w-full h-full" unoptimized />
                    )}
                  </div>
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 backdrop-blur-[2px] bg-black/40 rounded-2xl">
                    <EditOutlined className="text-white text-xl drop-shadow-lg" />
                  </div>
                  {selectedIcon && (
                    <div className="absolute -top-1.5 -right-1.5 w-6 h-6 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full border-2 border-white flex items-center justify-center shadow-md z-20">
                      <span className="text-white text-[10px] font-bold">✓</span>
                    </div>
                  )}
                </div>
                <span className="text-xs text-gray-500 font-medium">
                  {iconOptions.find(i => i.value === selectedIcon)?.label || t('App_icon')}
                </span>
              </div>
              <div className="flex-1 space-y-4">
                <Form.Item name="app_name" label={<span className="text-gray-600 font-medium text-[13px]">{t('input_app_name')}</span>} required rules={[{ required: true, message: t('input_app_name') }]} className="mb-0">
                  <Input placeholder={t('input_app_name')} autoComplete="off" className="h-10 rounded-xl border-gray-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all" onBlur={() => onInputBlur('app_name')} />
                </Form.Item>
                <Form.Item name="app_describe" label={<span className="text-gray-600 font-medium text-[13px]">{t('Please_input_the_description')}</span>} required rules={[{ required: true, message: t('Please_input_the_description') }]} className="mb-0">
                  <Input.TextArea autoComplete="off" placeholder={t('Please_input_the_description')} autoSize={{ minRows: 3, maxRows: 5 }} className="resize-none rounded-xl border-gray-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all" onBlur={() => onInputBlur('app_describe')} />
                </Form.Item>
              </div>
            </div>

            {/* Sandbox Toggle - Moved to Basic Info */}
            <div className="mt-5 pt-5 border-t border-gray-100">
              <div className="flex items-center justify-between group">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500/10 to-purple-500/10 flex items-center justify-center">
                    <CloudServerOutlined className="text-violet-500 text-lg" />
                  </div>
                  <div>
                    <div className="text-[13px] font-medium text-gray-800">启用沙箱环境</div>
                    <div className="text-[11px] text-gray-500">Agent 将在隔离的沙箱环境中运行</div>
                  </div>
                </div>
                <Tooltip title="启用后，Agent 将在隔离的沙箱环境中执行代码和命令，提供更安全的运行环境" placement="left">
                  <div>
                    <Form.Item name="use_sandbox" valuePropName="checked" className="mb-0" noStyle>
                      <Switch
                        checkedChildren="已开启"
                        unCheckedChildren="已关闭"
                        className="scale-110"
                      />
                    </Form.Item>
                  </div>
                </Tooltip>
              </div>
            </div>
          </div>

          {/* Agent Config Section - Right Column */}
          <div className="bg-gradient-to-br from-violet-50/30 to-purple-50/20 rounded-2xl border border-violet-100/40 p-6 shadow-sm">
            <h3 className="text-[14px] font-semibold text-gray-800 mb-5 flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-md shadow-violet-500/20">
                <ThunderboltOutlined className="text-white text-sm" />
              </div>
              <span>{t('baseinfo_agent_config')}</span>
            </h3>
            <div className="space-y-4">
              {/* Agent Version Selector */}
              <Form.Item label={<span className="text-gray-600 font-medium text-[13px]">Agent Version</span>} name="agent_version" className="mb-0">
                <Radio.Group className="w-full">
                  <div className="grid grid-cols-2 gap-3">
                    <Radio.Button value="v1" className="h-auto py-3.5 px-4 rounded-xl border-2 border-gray-100 hover:border-blue-200 transition-all [&.ant-radio-button-wrapper-checked]:border-blue-500 [&.ant-radio-button-wrapper-checked]:bg-gradient-to-br [&.ant-radio-button-wrapper-checked]:from-blue-50 [&.ant-radio-button-wrapper-checked]:to-indigo-50">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-sm">
                          <ThunderboltOutlined className="text-lg text-white" />
                        </div>
                        <div className="flex-1">
                          <div className="font-semibold text-sm text-gray-800">V1 Classic</div>
                          <div className="text-xs text-gray-400">稳定 PDCA Agent</div>
                        </div>
                      </div>
                    </Radio.Button>
                    <Radio.Button value="v2" className="h-auto py-3.5 px-4 rounded-xl border-2 border-gray-100 hover:border-green-200 transition-all [&.ant-radio-button-wrapper-checked]:border-green-500 [&.ant-radio-button-wrapper-checked]:bg-gradient-to-br [&.ant-radio-button-wrapper-checked]:from-green-50 [&.ant-radio-button-wrapper-checked]:to-emerald-50">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center shadow-sm">
                          <RocketOutlined className="text-lg text-white" />
                        </div>
                        <div className="flex-1">
                          <div className="font-semibold text-sm text-gray-800">V2 Core</div>
                          <div className="text-xs text-gray-400">Canvas + 进度可视化</div>
                        </div>
                      </div>
                    </Radio.Button>
                  </div>
                </Radio.Group>
              </Form.Item>
              {/* Agent 模板选择器 - 根据版本动态切换 */}
              {currentAgentVersion === 'v2' ? (
                <Form.Item 
                  label={<span className="text-gray-600 font-medium text-[13px]">Agent 模板</span>}
                  name="v2_agent_template" 
                  key="v2_agent_template"
                  rules={[{ required: true, message: '请选择 V2 Agent 模板' }]} 
                  className="mb-0"
                >
                  <Select 
                    placeholder="选择 V2 Agent 模板" 
                    options={v2AgentOptions} 
                    className="w-full [&_.ant-select-selector]:!rounded-xl [&_.ant-select-selector]:border-gray-200 [&_.ant-select-selector]:focus-within:border-violet-400 [&_.ant-select-selector]:focus-within:ring-2 [&_.ant-select-selector]:focus-within:ring-violet-100"
                    loading={!v2AgentTemplates || v2AgentTemplates.length === 0}
                    optionRender={(option) => (
                      <div className="flex items-center gap-3 py-1">
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-100 to-purple-100 flex items-center justify-center text-lg">
                          {V2_AGENT_ICONS[option.value as string] || '🤖'}
                        </div>
                        <div className="flex-1">
                          <div className="font-medium text-gray-800">{option.data?.agent?.display_name || option.label}</div>
                          <div className="text-xs text-gray-500">{option.data?.agent?.description}</div>
                        </div>
                      </div>
                    )}
                  />
                </Form.Item>
              ) : (
                <Form.Item 
                  label={<span className="text-gray-600 font-medium text-[13px]">{t('baseinfo_select_agent_type')}</span>}
                  name="agent" 
                  key="v1_agent"
                  rules={[{ required: true, message: t('baseinfo_select_agent_type') }]} 
                  className="mb-0"
                >
                  <Select 
                    placeholder={t('baseinfo_select_agent_type')} 
                    options={targetOptions} 
                    allowClear 
                    className="w-full [&_.ant-select-selector]:!rounded-xl [&_.ant-select-selector]:border-gray-200 [&_.ant-select-selector]:focus-within:border-violet-400 [&_.ant-select-selector]:focus-within:ring-2 [&_.ant-select-selector]:focus-within:ring-violet-100" 
                  />
                </Form.Item>
              )}
              {is_reasoning_engine_agent && (
                <Form.Item name="reasoning_engine" label={<span className="text-gray-600 font-medium text-[13px]">{t('baseinfo_reasoning_engine')}</span>} rules={[{ required: true, message: t('baseinfo_select_reasoning_engine') }]} className="mb-0">
                  <Select options={reasoningEngineOptions} placeholder={t('baseinfo_select_reasoning_engine')} className="w-full [&_.ant-select-selector]:!rounded-xl [&_.ant-select-selector]:border-gray-200 [&_.ant-select-selector]:focus-within:border-violet-400 [&_.ant-select-selector]:focus-within:ring-2 [&_.ant-select-selector]:focus-within:ring-violet-100" />
                </Form.Item>
              )}
              <Form.Item label={<span className="text-gray-600 font-medium text-[13px]">{t('baseinfo_llm_strategy')}</span>} name="llm_strategy" rules={[{ required: true, message: t('baseinfo_select_llm_strategy') }]} className="mb-0">
                <Select options={strategyOptions} placeholder={t('baseinfo_select_llm_strategy')} className="w-full [&_.ant-select-selector]:!rounded-xl [&_.ant-select-selector]:border-gray-200 [&_.ant-select-selector]:focus-within:border-violet-400 [&_.ant-select-selector]:focus-within:ring-2 [&_.ant-select-selector]:focus-within:ring-violet-100" />
              </Form.Item>
              <Form.Item label={<span className="text-gray-600 font-medium text-[13px]">{t('baseinfo_llm_strategy_value')}</span>} name="llm_strategy_value" rules={[{ required: true, message: t('baseinfo_select_llm_model') }]} className="mb-0">
                <Select mode="multiple" allowClear options={llmOptions} placeholder={t('baseinfo_select_llm_model')} className="w-full [&_.ant-select-selector]:!rounded-xl [&_.ant-select-selector]:border-gray-200 [&_.ant-select-selector]:focus-within:border-violet-400 [&_.ant-select-selector]:focus-within:ring-2 [&_.ant-select-selector]:focus-within:ring-violet-100" maxTagCount="responsive"
                  maxTagPlaceholder={(omittedValues) => (<Tag className="rounded-lg text-[10px] font-medium">+{omittedValues.length} ...</Tag>)} />
              </Form.Item>
            </div>
          </div>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-gray-200/60 to-transparent my-8" />

        {/* Layout Section */}
        <div className="bg-gradient-to-br from-emerald-50/30 to-green-50/20 rounded-2xl border border-emerald-100/40 p-6 shadow-sm">
          <h3 className="text-[14px] font-semibold text-gray-800 mb-5 flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-emerald-500 to-green-600 flex items-center justify-center shadow-md shadow-emerald-500/20">
              <PictureOutlined className="text-white text-sm" />
            </div>
            <span>{t('baseinfo_layout')}</span>
          </h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Form.Item label={<span className="text-gray-600 font-medium text-[13px]">{t('baseinfo_layout_type')}</span>} name="chat_layout" rules={[{ required: true, message: t('baseinfo_select_layout_type') }]} className="mb-0">
              <Select options={layoutDataOptions} placeholder={t('baseinfo_select_layout_type')} className="w-full [&_.ant-select-selector]:!rounded-xl [&_.ant-select-selector]:border-gray-200 [&_.ant-select-selector]:focus-within:border-emerald-400 [&_.ant-select-selector]:focus-within:ring-2 [&_.ant-select-selector]:focus-within:ring-emerald-100" />
            </Form.Item>
            <Form.Item label={<span className="text-gray-600 font-medium text-[13px]">{t('baseinfo_chat_config')}</span>} name="chat_in_layout" className="mb-0">
              <Checkbox.Group options={chatConfigOptions} className="flex flex-wrap gap-2" />
            </Form.Item>
            {selectedChatConfigs && selectedChatConfigs.length > 0 && (
              <div className="col-span-2 bg-white/70 p-4 rounded-xl border border-emerald-100/50 mt-2">
                <ChatLayoutConfig form={form} selectedChatConfigs={selectedChatConfigs} chatConfigOptions={chatConfigOptions} onInputBlur={onInputBlur} resourceOptions={resourceOptions} modelOptions={modelOptions} />
              </div>
            )}
          </div>
        </div>
      </Form>

      {/* Icon Selection Modal */}
      <Modal
        title={
          <div className="flex items-center gap-3 pb-2 border-b border-gray-100">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
              <PictureOutlined className="text-white text-lg" />
            </div>
            <div>
              <div className="font-semibold text-gray-800 text-base">{t('App_icon')}</div>
              <div className="text-xs text-gray-400">选择一个代表您应用特性的图标</div>
            </div>
          </div>
        }
        open={isIconModalOpen}
        onCancel={() => setIsIconModalOpen(false)}
        footer={null}
        width={520}
        centered
        className="[&_.ant-modal-content]:rounded-2xl [&_.ant-modal-content]:shadow-2xl [&_.ant-modal-header]:border-b-0 [&_.ant-modal-header]:pb-0 [&_.ant-modal-body]:pt-2"
      >
        <div className="py-4">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3 px-1">预设图标</div>
          <div className="grid grid-cols-3 gap-4">
            {iconOptions.map(icon => (
              <div
                key={icon.value}
                onClick={() => handleIconSelect(icon.value)}
                className={`
                  group cursor-pointer relative rounded-2xl p-4 transition-all duration-300
                  ${selectedIcon === icon.value
                    ? 'bg-gradient-to-br from-blue-50 to-indigo-50 border-2 border-blue-400 shadow-lg shadow-blue-500/15 scale-[1.02]'
                    : 'bg-gray-50/80 border-2 border-transparent hover:border-gray-200 hover:bg-white hover:shadow-lg hover:shadow-gray-200/50 hover:scale-[1.02]'
                  }
                `}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className={`
                    relative w-16 h-16 rounded-2xl overflow-hidden shadow-md transition-all duration-300 flex items-center justify-center
                    ${selectedIcon === icon.value ? 'ring-4 ring-blue-200/50' : 'group-hover:shadow-lg'}
                  `}>
                    <div className={`absolute inset-0 bg-gradient-to-br ${icon.color} opacity-10`} />
                    {icon.isSvg ? (
                      <SmartPluginIcon size={56} className="relative z-10" />
                    ) : (
                      <Image
                        src={icon.value}
                        width={64}
                        height={64}
                        alt={icon.label}
                        className="object-cover w-full h-full relative z-10"
                        unoptimized
                      />
                    )}
                    {selectedIcon === icon.value && (
                      <div className="absolute inset-0 bg-blue-500/10 flex items-center justify-center z-20">
                        <div className="w-7 h-7 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center shadow-lg">
                          <span className="text-white text-xs font-bold">✓</span>
                        </div>
                      </div>
                    )}
                  </div>
                  <span className={`
                    text-xs font-medium text-center transition-colors duration-200
                    ${selectedIcon === icon.value ? 'text-blue-600' : 'text-gray-600 group-hover:text-gray-800'}
                  `}>
                    {icon.label}
                  </span>
                </div>
                {selectedIcon === icon.value && (
                  <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full border-2 border-white flex items-center justify-center shadow-md">
                    <span className="text-white text-[8px] font-bold">✓</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </Modal>
    </div>
  );
}
