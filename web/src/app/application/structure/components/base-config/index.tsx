'use client';
import { getChatInputConfig, getChatLayout, getResourceV2, getChatInputConfigParams, apiInterceptors, getUsableModels } from '@/client/api';
import { AppContext } from '@/contexts';
import { safeJsonParse } from '@/utils/json';
import { DeleteOutlined, NodeCollapseOutlined, SettingOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Form, FormProps, Spin } from 'antd';
import { isString, uniqBy } from 'lodash';
import { useContext, useEffect, useMemo, useState } from 'react';
import AgentModal from './agent-modal';
import BaseInfo from './baseinfo';
import KnowledgeSelectModal from './knowledge-modal';
import ToolsModal from './tools-modal';

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
]

function AppConfig() {
  const { appInfo, fetchUpdateApp, fetchUpdateAppLoading } =
    useContext(AppContext);
  const [form] = Form.useForm();
  const modal = App.useApp().modal;
  const [showKnowledgeModal, setShowKnowledgeModal] = useState(false);
  const [showToolsModal, setShowToolsModal] = useState(false);
  const [showAgentModal, setShowAgentModal] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeKey, setActiveKey] = useState<string[]>(['0', '1', '2']);
  const [selectedKnowledgeList, setSelectedKnowledgeList] = useState<any[]>([]);
  const [resourceOptions, setResourceOptions] = useState<any[]>([]);

  useEffect(() => {
    // 初始化应用信息
    if (appInfo) {
      const { resource_knowledge, resources, layout } = appInfo || {};
      const engineItem = resources?.find((item: any) => item.type === 'reasoning_engine');
      const engineItemValue = isString(engineItem?.value) ? safeJsonParse(engineItem?.value, {}) : engineItem?.value;
      const resource_knowledge_value = JSON.parse(resource_knowledge?.[0]?.value || '{}');
      const knowledgeList = resource_knowledge_value?.knowledges?.map((item: any) => {
        return {
          ...item,
          value: item.knowledge_id,
          name: item.label || item.knowledge_name,
        };
      });

      const toolsList = (appInfo?.resource_tool?.filter((item: any) => item.type === 'tool') || []).map((item: any) => {
        const { value } = item || {};
        const key = JSON.parse(value || '{}')?.key;
        return key;
      });

      const agentsList = (
        appInfo?.resource_agent?.map((item: any) => {
          const { value } = item || {};
          return JSON.parse(value || '{}')?.key;
        }) || []
      ).filter((item: any) => item);

      setSelectedKnowledgeList(knowledgeList);

      const chat_in_layout_list = appInfo?.layout?.chat_in_layout?.map((item: any) => item.param_type) || [];
      let chat_in_layout_obj = {};
      chat_in_layout_list.forEach((type: any) => {
        const item = appInfo?.layout?.chat_in_layout.find((i: any) => i.param_type === type);
        if(type === 'resource') {
          chat_in_layout_obj = {
            ...chat_in_layout_obj,
            resource_sub_type: item.sub_type,
            resource_value: item.param_default_value,
          };
        } else if(type === 'model') {
          chat_in_layout_obj = {
            ...chat_in_layout_obj,
            model_sub_type: item.sub_type,
            model_value: item.param_default_value,
          };
        } else if(type === 'temperature') {
          chat_in_layout_obj = {
            ...chat_in_layout_obj,
            temperature_sub_type: item.sub_type,
            temperature_value: item.param_default_value,
          };
        } else if(type === 'max_new_tokens') {  
          chat_in_layout_obj = {
            ...chat_in_layout_obj,
            max_new_tokens_sub_type: item.sub_type,
            max_new_tokens_value: item.param_default_value,
          };
        } else {
          chat_in_layout_obj = {
            ...chat_in_layout_obj,
            [item]: {
              sub_type: item.sub_type,
              value: item.param_default_value,
            },
          };
        }
      });

      form.setFieldsValue({
        app_name: appInfo.app_name,
        app_icon: appInfo.icon,
        app_describe: appInfo.app_describe,
        llm_strategy: appInfo?.llm_config?.llm_strategy,
        llm_strategy_value: appInfo?.llm_config?.llm_strategy_value || [],
        knowledge: knowledgeList?.map((item: { value: any }) => item.value),
        tools: toolsList,
        chat_layout: appInfo?.layout?.chat_layout?.name || '',
        chat_in_layout: chat_in_layout_list || [],
        agents: agentsList,
        agent: appInfo.agent,
        reasoning_engine: engineItemValue?.key ?? engineItemValue?.name,
        ...chat_in_layout_obj,
      });
    }
  }, [appInfo, form]);

  // 需要使用 layoutDataOptions 提至外层
  const { data: layoutData, run: fetchChatLayout } = useRequest(async () => await getChatLayout(), {
    manual: true,
  });

  const { data: reasoningEngineData } = useRequest(async () => await getResourceV2({ type: 'reasoning_engine' }));

  const { data: chatConfigData, run: fetchChatInputConfig } = useRequest(async () => await getChatInputConfig(), {
    manual: true,
  });

  const { run: chatInputConfigParams, loading } = useRequest(async data => await getChatInputConfigParams([data]), {
    manual: true,
    onSuccess: data => {
      const resourceData = data?.data?.data[0]?.param_type_options;
      if (!resourceData) return;
      setResourceOptions(resourceData.map((item: any) => ({
        ...item,
        label: item.label,
        value: item.key || item.value,
      })));
    },
  });

  const { data: modelList = [] } = useRequest(async () => {
    const [, res] = await apiInterceptors(getUsableModels());
    return res ?? [];
  });

 useEffect(() => {
    const resource = appInfo?.layout?.chat_in_layout?.find((i: { param_type: string; }) => i.param_type === 'resource');
    if (resource) {
      chatInputConfigParams(resource);
    }
  }, [appInfo.layout?.chat_in_layout]);

  useEffect(() => {
    fetchChatLayout();
    fetchChatInputConfig();
  }, []);

  const layoutDataOptions = useMemo(() => {
    return layoutData?.data?.data?.map((option: any) => {
      return {
        ...option,
        value: option.name,
        label: `${option.description}[${option.name}]`,
      };
    });
  }, [layoutData]);

  const reasoningEngineOptions = useMemo(
    () =>
      reasoningEngineData?.data?.data?.flatMap(
        (item: any) =>
          item.valid_values?.map((option: any) => ({
            item: option,
            value: option.key,
            label: option.label,
            selected: true,
          })) || [],
      ),
    [reasoningEngineData],
  );

  const chatConfigOptions = useMemo(() => {
    return chatConfigData?.data?.data?.map((option: any) => {
      return {
        ...option,
        value: option.param_type,
        label: option.param_description
      };
    });
  }, [chatConfigData]);

  const modelOptions = useMemo(() => {
    return modelList.map(item => ({
      value: item,
      label: item,
    }));
  }, [modelList]);

  const handleToggleAll = () => {
    if (isCollapsed) {
      setActiveKey(['0', '1', '2']);
      setIsCollapsed(false);
    } else {
      setActiveKey([]);
      setIsCollapsed(true);
    }
  };

  const layoutConfigChange = () => {
    const changeFieldValue = form.getFieldValue('chat_in_layout') || [];
    const curConfig = changeFieldValue
      .map((item: string) => {
      const { label, value, sub_types, ...rest } = chatConfigOptions?.find((md: { param_type: string }) =>
        item === md.param_type,
      ) || {};
      if (item === 'resource') {
        const cur_sub_type = form.getFieldValue('resource_sub_type') || null;
        const cur_resource_value = form.getFieldValue('resource_value') || null;
        return {
        ...rest,
        param_default_value: cur_resource_value || null,
        sub_type: cur_sub_type,
        };
      } else if (item === 'model') {
        const cur_sub_type = form.getFieldValue('model_sub_type') || null;
        const cur_model_value = form.getFieldValue('model_value') || null;
        return {
        ...rest,
        param_default_value: cur_model_value || null,
        sub_type: cur_sub_type,
        };
      } else if (item === 'temperature') {
        const cur_sub_type = form.getFieldValue('temperature_sub_type') || null;
        const cur_temperature_value = form.getFieldValue('temperature_value') || rest.param_default_value || null;
        return {
        ...rest,
        param_default_value: Number(cur_temperature_value) || null,
        sub_type: cur_sub_type,
        };
      } else if (item === 'max_new_tokens') {
        const cur_sub_type = form.getFieldValue('max_new_tokens_sub_type') || null;
        const cur_max_new_tokens_value = form.getFieldValue('max_new_tokens_value') || rest.param_default_value || null;
        return {
        ...rest,
        param_default_value: Number(cur_max_new_tokens_value),
        sub_type: cur_sub_type,
        };
      } else {
        return chatConfigOptions.find((md: { param_type: string }) => item.includes(md.param_type)) || {};
      }
      }).filter((obj: {}) => Object.keys(obj).length > 0);
    fetchUpdateApp({
      ...appInfo,
      layout: {
        ...appInfo.layout,
        chat_in_layout: curConfig,
      },
    });
  };
  
  const onInputBlur = (name: string) => {
     if (layoutConfigValueChangeList.includes(name)) {
         layoutConfigChange();
      } else {
        if(appInfo[name] !== form.getFieldValue(name)) {
          fetchUpdateApp({
            ...appInfo,
            [name]: form.getFieldValue(name),
          }); 
        }
      }
  };

  const onValuesChange: FormProps['onValuesChange'] = changedValues => {
    const [fieldName] = Object.keys(changedValues ?? {});
    const [fieldValue] = Object.values(changedValues ?? {});

    if (fieldName === 'icon') {
      fetchUpdateApp({
        ...appInfo,
        icon: fieldValue,
      });
    } else if (fieldName === 'agent') {
      fetchUpdateApp({
        ...appInfo,
        agent: fieldValue,
      });
    } else if (fieldName === 'llm_strategy') {
      fetchUpdateApp({
        ...appInfo,
        llm_config: {
          llm_strategy: fieldValue,
          llm_strategy_value: appInfo.llm_config?.llm_strategy_value || [],
        },
      });
    } else if (fieldName === 'llm_strategy_value') {
      fetchUpdateApp({
        ...appInfo,
        llm_config: {
          llm_strategy: form.getFieldValue('llm_strategy'),
          llm_strategy_value: fieldValue,
        },
      });
    } else if (fieldName === 'chat_layout') {
      const currentChatLayout = layoutDataOptions.find((item: any) => item.value === fieldValue);
      fetchUpdateApp({
        ...appInfo,
        layout: {
          ...appInfo.layout,
          chat_layout: currentChatLayout,
        },
      });
    } else if (fieldName === 'reasoning_engine') {
      const currentEngine = reasoningEngineOptions?.find((item: any) => item.value === fieldValue);
      if (currentEngine) {
        fetchUpdateApp({
          ...appInfo,
          resources: uniqBy(
            [
              {
                type: 'reasoning_engine',
                value: currentEngine.item,
              },
              ...(appInfo.resources ?? []),
            ],
            'type',
          ),
        });
      }
    } else if (layoutConfigChangeList.includes(fieldName)) {
      layoutConfigChange();
    } else {
      return null; 
    }
  };

  const onKnowledgeChange = (lists: any) => {
    fetchUpdateApp({
      ...appInfo,
      resource_knowledge: lists,
    });
    setShowKnowledgeModal(false);
  };

  const onToolsChange = (tools: any) => {
    fetchUpdateApp({
      ...appInfo,
      resource_tool: tools,
    });
    setShowToolsModal(false);
  };

  const onAgentChange = (agents: any) => {
    fetchUpdateApp({
      ...appInfo,
      resource_agent: agents,
    });
    setShowAgentModal(false);
  };

  const onChangedIcon = (icon: string) => {
    fetchUpdateApp({
      ...appInfo,
      icon,
    });
  };

  const deleteKnowledge = (knowledgeId: string) => {
    const appInfo_resource_knowledge_item = appInfo?.resource_knowledge[0]?.value;
    const updatedList = selectedKnowledgeList.filter(item => item.value !== knowledgeId);
    modal.confirm({
      title: '确认删除',
      content: '您确定要删除该知识吗？',
      onOk: () => {
        const _resource_knowledge = [
          {
            ...appInfo.resource_knowledge[0],
            value: JSON.stringify({
              ...JSON.parse(appInfo_resource_knowledge_item || '{}'),
              knowledges: updatedList.map(item => ({
                knowledge_id: item.value,
                knowledge_name: item.name,
              })),
            }),
          },
        ];
        fetchUpdateApp({
          ...appInfo,
          resource_knowledge: _resource_knowledge,
        });
        setSelectedKnowledgeList(updatedList);
      },
    });
  };

  const deleteTool = (tool: { type: string; value: any; name: any }) => {
    const name =
      tool.type === 'tool' ? JSON.parse(tool.value || '{}')?.name || JSON.parse(tool.value || '{}')?.label : tool.name;
    modal.confirm({
      title: '确认删除',
      content: `您确定要删除${name}该工具吗？`,
      onOk: () => {
        if (tool.type === 'tool') {
          // 删除 value.name 匹配的 tool
          const toolKey = JSON.parse(tool.value || '{}')?.name || JSON.parse(tool.value || '{}')?.label;
          const updatedTools = appInfo.resource_tool.filter((item: any) => {
            if (item.type !== 'tool') return true;
            const key = JSON.parse(item.value || '{}')?.key;
            return key !== toolKey;
          });
          fetchUpdateApp({
            ...appInfo,
            resource_tool: updatedTools,
          });
        } else if (tool.type === 'tool(mcp(sse))') {
          // 删除 name 匹配的 tool
          const updatedTools = appInfo.resource_tool.filter((item: any) => {
            if (item.type !== 'tool(mcp(sse))') return true;
            return item.name !== tool.name;
          });
          fetchUpdateApp({
            ...appInfo,
            resource_tool: updatedTools,
          });
        }
      },
    });
  };

  const deleteAgent = (agent: { type: string; value: any; name: any }) => {
    const name = JSON.parse(agent.value || '{}')?.name || JSON.parse(agent.value || '{}')?.label;
    modal.confirm({
      title: '确认删除',
      content: `您确定要删除${name}该Agent吗？`,
      onOk: () => {
        const agentKey = JSON.parse(agent.value || '{}')?.key;
        const updatedAgents = appInfo.resource_agent.filter((item: any) => {
          const key = JSON.parse(item.value || '{}')?.key;
          return key !== agentKey;
        });
        fetchUpdateApp({
          ...appInfo,
          resource_agent: updatedAgents,
        });
      },
    });
  };

  return (
    <div className='flex-1 border-r-1 p-4 border-r-[#D9D9D9] h-full overflow-y-auto'>
      <Spin spinning={fetchUpdateAppLoading} 
        wrapperClassName="h-full w-full max-h-full" 
      >
        {/* 基础配置 */}
        <div className='p-4 flex pt-1 flex-row items-center text-[18px]'>
          <div className='flex flex-row items-center flex-1'>
            <SettingOutlined className='pr-2' />
            <h2 className='font-semibold'>配置</h2>
          </div>
          <div className='flex items-center gap-1 cursor-pointer transition-colors ml-auto' onClick={handleToggleAll}>
            <img src={isCollapsed ? '/icons/collapsed.svg' : '/icons/uncollapsed.svg'} alt='toggle' className='w-5 h-5'/>
          </div>
        </div>
        <div className='overflow-y-auto flex-1'>
          <Form form={form} onValuesChange={onValuesChange}>
            <BaseInfo
              form={form}
              activeKey={activeKey}
              setActiveKey={setActiveKey}
              setIsCollapsed={setIsCollapsed}
              layoutDataOptions={layoutDataOptions}
              reasoningEngineOptions={reasoningEngineOptions}
              chatConfigOptions={chatConfigOptions}
              handleChangedIcon={onChangedIcon}
              onInputBlur={onInputBlur}
              resourceOptions={resourceOptions}
              modelOptions={modelOptions}
            />
          </Form>

          {/* 知识配置 */}
          <div>
            <div className='p-4 flex flex-row items-center text-[18px] justify-between'>
              <div className='flex flex-row items-center'>
                <img
                  src='/icons/knowledge.svg'
                  alt='知识图标'
                  style={{ width: 18, height: 18, marginRight: 8 }}
                />
                <h2 className='font-semibold'>知识</h2>
              </div>
              <div className='flex flex-row items-center text-[14px] text-[#0c75fc] cursor-pointer'>
                <span className='cursor-pointer flex items-center' onClick={() => setShowKnowledgeModal(true)}>
                  <span className='text-[16px] mr-1'>+</span>
                  <span>关联知识</span>
                </span>
              </div>
            </div>
            {/* 使用 knowledge_pack 特殊处理 */}
            {appInfo?.resource_knowledge?.length > 0 ? (
              <div>
                {selectedKnowledgeList?.map((item: any) => {
                  return (
                    <div
                      key={item.name + item.id}
                      className='flex items-center justify-between py-2 border-gray-200 bg-[#F2F2F2] mb-1'
                    >
                      <div className='px-4 flex-row display flex flex-1 items-center justify-between'>
                        <div className='flex-1'>{item.name}</div>
                        <DeleteOutlined onClick={() => deleteKnowledge(item.value)} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              ''
            )}
          </div>

          {/* 技能配置 */}
          <div>
            <div className='p-4 flex flex-row items-center text-[18px] justify-between'>
              <div className='flex flex-row items-center'>
                <img
                  src='/icons/skill.svg'
                  alt='技能图标'
                  style={{ width: 18, height: 18, marginRight: 8 }}
                />
                <h2 className='font-semibold'>技能</h2>
              </div>
              <div className='flex flex-row items-center text-[14px] text-[#0c75fc] cursor-pointer'>
                <span className='cursor-pointer flex items-center' onClick={() => setShowToolsModal(true)}>
                  <span className='text-[16px] mr-1'>+</span>
                  <span>关联技能</span>
                </span>
              </div>
            </div>
            {appInfo?.resource_tool?.length > 0 ? (
              <div>
                {appInfo?.resource_tool?.map((item: any) => {
                  const { value } = item || {};
                  const name =
                    item.type === 'tool'
                      ? JSON.parse(value || '{}')?.name || JSON.parse(value || '{}')?.label || item.name
                      : item.name;
                  return (
                    <div
                      key={name + item.id}
                      className='flex items-center justify-between py-2 border-gray-200 bg-[#F2F2F2] mb-1'
                    >
                      <div className='px-4 flex-row display flex flex-1 items-center justify-between'>
                        <div className='flex-1'>{name}</div>
                        <DeleteOutlined onClick={() => deleteTool(item)} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              ''
            )}
          </div>

          {/* Agent 配置 */}
          <div>
            <div className='p-4 flex flex-row items-center text-[18px] justify-between'>
              <div className='flex flex-row items-center'>
                <img
                  src='/icons/agent.svg'
                  alt='Agent图标'
                  style={{ width: 18, height: 18, marginRight: 8 }}
                />
                <h2 className='font-semibold  text-[16px]'>Agent</h2>
              </div>
              <div className='flex flex-row items-center text-[14px] text-[#0c75fc] cursor-pointer'>
                <span
                  className='cursor-pointer flex items-center justify-center'
                  onClick={() => setShowAgentModal(true)}
                >
                  <span className='text-[16px] mr-1'>+</span>
                  <span>关联Agent</span>
                </span>
              </div>
            </div>
            {appInfo?.resource_agent?.length > 0 ? (
              <div>
                {appInfo?.resource_agent?.map((item: any) => {
                  const { value } = item || {};
                  const name = JSON.parse(value || '{}')?.name || JSON.parse(value || '{}')?.label;
                  return (
                    <div
                      key={name + item.key}
                      className='flex items-center justify-between py-2 border-gray-200 bg-[#F2F2F2] mb-1'
                    >
                      <div className='px-4 flex-row display flex flex-1 items-center justify-between'>
                        <div className='flex-1'>{name}</div>
                        <DeleteOutlined onClick={() => deleteAgent(item)} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              ''
            )}
          </div>

          {/* 知识选择 Modal */}
          {showKnowledgeModal && (
            <KnowledgeSelectModal
              form={form}
              visible={showKnowledgeModal}
              onKnowledgeChange={onKnowledgeChange}
              onCancel={() => setShowKnowledgeModal(false)}
            />
          )}
          {/* 技能选择 Modal */}
          {showToolsModal && (
            <ToolsModal
              form={form}
              visible={showToolsModal}
              onCancel={() => setShowToolsModal(false)}
              onToolsChange={onToolsChange}
            />
          )}
          {showAgentModal && (
            <AgentModal
              visible={showAgentModal}
              onCancel={() => setShowAgentModal(false)}
              onAgentChange={onAgentChange}
              form={form}
            />
          )}
        </div>
      </Spin>
    </div>
  );
}

export default AppConfig;
