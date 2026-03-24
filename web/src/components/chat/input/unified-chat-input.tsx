'use client';

import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  ArrowUpOutlined, 
  PaperClipOutlined,
  DownOutlined,
  PauseCircleOutlined,
  RedoOutlined,
  ClearOutlined,
  CloseOutlined,
  SlidersOutlined,
  SearchOutlined,
  CheckOutlined,
  LoadingOutlined,
  FileOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  DatabaseOutlined
} from '@ant-design/icons';
import { 
  Button, 
  Input, 
  Popover, 
  Tooltip,
  Upload,
  UploadProps,
  Modal,
  Slider,
  Collapse,
  Spin,
  Select,
  message,
} from 'antd';
import { useRequest } from 'ahooks';
import classNames from 'classnames';
import { apiInterceptors, getModelList, clearChatHistory, stopChat, postChatModeParamsFileLoad, getResourceV2 } from '@/client/api';
import { ChatContentContext, SelectedSkill } from '@/contexts';
import ModelIcon from '@/components/icons/model-icon';
import { IModelData } from '@/types/model';
import { IChatDialogueMessageSchema, UserChatContent } from '@/types/chat';
import { MEDIA_RESOURCE_TYPES } from '@/app/application/app/components/chat-layout-config';
import { parseResourceValue, transformFileUrl } from '@/utils';
import { useSearchParams } from 'next/navigation';

const { Panel } = Collapse;

interface ChatInLayoutItem {
  param_type: string;
  sub_type?: string;
  param_description?: string;
  param_default_value?: string | number;
  [key: string]: unknown;
}

interface ChatInParamItem {
  param_type: string;
  param_value: string;
  sub_type: string;
}

interface ResourceOptionItem {
  label: string;
  value: string;
  key?: string;
  [key: string]: unknown;
}

interface ParsedResourceItem {
  type: string;
  image_url?: { url: string; file_name?: string };
  file_url?: { url: string; file_name?: string };
}

const getAcceptTypes = (type: string) => {
  switch (type) {
    case 'excel_file':
      return '.csv,.xlsx,.xls';
    case 'text_file':
      return '.txt,.doc,.docx,.pdf,.md';
    case 'image_file':
      return '.jpg,.jpeg,.png,.gif,.bmp,.webp';
    case 'audio_file':
      return '.mp3,.wav,.ogg,.aac';
    case 'video_file':
      return '.mp4,.wav,.mov';
    case 'common_file':
      return '';
    default:
      return '';
  }
};

// 模型参数配置弹窗
interface ModelParamsModalProps {
  open: boolean;
  onClose: () => void;
  temperature: number;
  onTemperatureChange: (val: number) => void;
  maxTokens: number;
  onMaxTokensChange: (val: number) => void;
}

const ModelParamsModal: React.FC<ModelParamsModalProps> = ({
  open,
  onClose,
  temperature,
  onTemperatureChange,
  maxTokens,
  onMaxTokensChange,
}) => {
  const { t } = useTranslation();
  const [tempTemp, setTempTemp] = useState(temperature);
  const [tempTokens, setTempTokens] = useState(maxTokens);

  useEffect(() => {
    setTempTemp(temperature);
    setTempTokens(maxTokens);
  }, [temperature, maxTokens, open]);

  const handleOk = () => {
    onTemperatureChange(tempTemp);
    onMaxTokensChange(tempTokens);
    onClose();
  };

  return (
    <Modal
      title={
        <div className="flex items-center gap-2 text-base font-medium">
          <SlidersOutlined className="text-indigo-500" />
          <span>{t('model_params', '模型参数')}</span>
        </div>
      }
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      okText={t('confirm', '确认')}
      cancelText={t('cancel', '取消')}
      width={420}
      className="[&_.ant-modal-content]:rounded-xl"
    >
      <div className="space-y-6 py-4">
        <div>
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('temperature', 'Temperature')}
            </span>
            <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded text-gray-700 dark:text-gray-300">
              {tempTemp.toFixed(1)}
            </span>
          </div>
          <Slider
            min={0}
            max={2}
            step={0.1}
            value={tempTemp}
            onChange={setTempTemp}
            trackStyle={{ backgroundColor: '#6366f1' }}
            handleStyle={{ borderColor: '#6366f1' }}
          />
          <p className="text-xs text-gray-500 mt-2">
            {t('temperature_desc', '控制输出的随机性，值越高输出越创造性')}
          </p>
        </div>

        <div>
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('max_tokens', 'Max Tokens')}
            </span>
            <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded text-gray-700 dark:text-gray-300">
              {tempTokens}
            </span>
          </div>
          <Slider
            min={256}
            max={8192}
            step={256}
            value={tempTokens}
            onChange={setTempTokens}
            trackStyle={{ backgroundColor: '#6366f1' }}
            handleStyle={{ borderColor: '#6366f1' }}
          />
          <p className="text-xs text-gray-500 mt-2">
            {t('max_tokens_desc', '控制生成文本的最大长度')}
          </p>
        </div>
      </div>
    </Modal>
  );
};

// 主组件
interface UnifiedChatInputProps {
  ctrl: AbortController;
  showFloatingActions?: boolean;
}

const UnifiedChatInput: React.FC<UnifiedChatInputProps> = ({
  ctrl,
  showFloatingActions = true,
}) => {
  const { t } = useTranslation();
  const context = React.useContext(ChatContentContext);
  const {
    scrollRef,
    replyLoading,
    handleChat,
    appInfo,
    resourceValue,
    setResourceValue,
    refreshDialogList,
    chatInParams,
    setChatInParams,
    history,
    canAbort,
    setCanAbort,
    setReplyLoading,
    temperatureValue,
    setTemperatureValue,
    maxNewTokensValue,
    setMaxNewTokensValue,
    refreshHistory,
    modelValue,
    selectedSkills,
    setSelectedSkills,
  } = context;

  const [userInput, setUserInput] = useState<string>('');
  const [isFocus, setIsFocus] = useState<boolean>(false);
  const [fileList, setFileList] = useState<File[]>([]);
  const [isZhInput, setIsZhInput] = useState<boolean>(false);
  const submitCountRef = useRef(0);
  const [clsLoading, setClsLoading] = useState<boolean>(false);
  const [autoGeneratedFileIndex, setAutoGeneratedFileIndex] = useState<number | null>(null);
  const isAutoConverting = useRef(false);
  
  const MAX_TEXT_LENGTH = 1000;

  // 模型相关
  const [modelList, setModelList] = useState<IModelData[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [modelSearch, setModelSearch] = useState('');
  const [isModelOpen, setIsModelOpen] = useState(false);
  const [isParamsModalOpen, setIsParamsModalOpen] = useState(false);
  
  // 动态资源选择相关
  const [resourceOptions, setResourceOptions] = useState<{ label: string; value: string; [key: string]: unknown }[]>([]);
  const searchParams = useSearchParams();
  const scene = searchParams?.get('scene') ?? '';
  const chatId = (searchParams?.get('conv_uid') || searchParams?.get('chatId')) ?? '';

  // 获取模型列表
  useRequest(
    async () => {
      const [, data] = await apiInterceptors(getModelList());
      return data || [];
    },
    {
      onSuccess: (models) => {
        if (models && models.length > 0) {
          const llmModels = models.filter((m: IModelData) => m.worker_type === 'llm');
          setModelList(llmModels);
          
          // 优先使用 modelValue（从页面 URL 传入），否则从 appInfo.llm_config 取第一个
          const defaultModel = modelValue || appInfo?.llm_config?.llm_strategy_value?.[0];
          
          if (defaultModel && llmModels.some((m: IModelData) => m.model_name === defaultModel)) {
            setSelectedModel(defaultModel);
          } else {
            const fallback = llmModels.find((m: IModelData) => 
              m.model_name.includes('gpt-4') || m.model_name.includes('gpt-3.5')
            )?.model_name || llmModels[0]?.model_name;
            setSelectedModel(fallback);
          }
        }
      },
    }
  );

  const paramKey: string[] = useMemo(() => {
    return appInfo?.layout?.chat_in_layout?.map((i: ChatInLayoutItem) => i.param_type) || [];
  }, [appInfo?.layout?.chat_in_layout]);

  // 获取resource配置
  const resourceConfig = useMemo(
    () => appInfo?.layout?.chat_in_layout?.find((i: ChatInLayoutItem) => i.param_type === 'resource'),
    [appInfo?.layout?.chat_in_layout]
  );

  // 判断是否需要显示资源选择器（非媒体类型资源需要选择）
  const shouldShowResourceSelect = useMemo(() => {
    return (
      paramKey.includes('resource') &&
      resourceConfig &&
      !MEDIA_RESOURCE_TYPES.includes(resourceConfig?.sub_type ?? '')
    );
  }, [paramKey, resourceConfig]);

  // 判断是否需要显示文件上传按钮
  // 所有 agent 默认支持普通文件上传，不再需要配置资源类型
  const shouldShowFileUpload = true;

  // 获取资源选项 - 使用 getResourceV2 直接获取资源列表
  const { run: fetchResourceOptions, loading: fetchResourceLoading } = useRequest(
    async (subType: string) => {
      const res = await getResourceV2({ type: subType });
      return res;
    },
    {
      manual: true,
      onSuccess: (response) => {
        // getResourceV2 直接返回 axios 响应，结构是 response.data.data
        const resourceData = response?.data?.data as unknown as { valid_values?: { key: string; label: string }[] }[];
        if (!resourceData) return;
        // 从 valid_values 中提取选项，并去重
        const options = resourceData.flatMap((item) => 
          item.valid_values?.map((opt) => ({
            label: opt.label,
            value: opt.key,
            key: opt.key,
          })) || []
        );
        // 根据 value 去重
        const uniqueOptions = options.filter((item, index, self) => 
          index === self.findIndex(t => t.value === item.value)
        );
        setResourceOptions(uniqueOptions);
      },
    }
  );

  // 当资源配置变化时获取资源选项
  useEffect(() => {
    if (resourceConfig?.sub_type && paramKey.includes('resource') && !MEDIA_RESOURCE_TYPES.includes(resourceConfig.sub_type)) {
      fetchResourceOptions(resourceConfig.sub_type);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceConfig?.sub_type]);

  // 过滤非resource类型的chatInParams
  const extendedChatInParams = useMemo(() => {
    return chatInParams?.filter((i: ChatInParamItem) => i.param_type !== 'resource') || [];
  }, [chatInParams]);

  // 处理资源选择变化
  const handleResourceSelectChange = useCallback((val: string) => {
    if (!val || !resourceConfig) return;
    
    const resourceItem = resourceOptions.find((item: ResourceOptionItem) => item.value === val);
    setResourceValue(resourceItem as Record<string, unknown>);
    
    const newChatInParams = [
      ...extendedChatInParams,
      {
        param_type: 'resource',
        param_value: JSON.stringify(resourceItem),
        sub_type: resourceConfig.sub_type,
      },
    ];
    setChatInParams(newChatInParams);
  }, [resourceConfig, resourceOptions, extendedChatInParams, setResourceValue, setChatInParams]);

  // 处理文件上传
  const handleFileUpload = useCallback(async (file: File) => {
    const formData = new FormData();
    formData.append('doc_files', file);

    const [, res] = await apiInterceptors(
      postChatModeParamsFileLoad({
        convUid: chatId || '',
        chatMode: scene || 'chat_normal',
        data: formData,
        model: modelValue,
        temperatureValue,
        maxNewTokensValue,
        config: {
          timeout: 1000 * 60 * 60,
        },
      }),
    );
    
    if (res && resourceConfig) {
      const newChatInParams = [
        ...extendedChatInParams,
        {
          param_type: 'resource',
          param_value: JSON.stringify(res),
          sub_type: resourceConfig.sub_type,
        },
      ];
      setChatInParams(newChatInParams);
      setResourceValue(res);
    }
  }, [chatId, scene, modelValue, temperatureValue, maxNewTokensValue, resourceConfig, extendedChatInParams, setChatInParams, setResourceValue]);

  const groupedModels = useMemo(() => {
    const groups: Record<string, string[]> = {};
    const otherModels: string[] = [];

    const filtered = modelList.filter(
      (model) =>
        model.worker_type === 'llm' &&
        model.model_name.toLowerCase().includes(modelSearch.toLowerCase())
    );

    filtered.forEach((modelData) => {
      let provider = 'Other';
      if (modelData.host && modelData.host.startsWith('proxy@')) {
        provider = modelData.host.replace('proxy@', '');
        provider = provider.charAt(0).toUpperCase() + provider.slice(1);
      } else if (modelData.host && modelData.host !== '127.0.0.1' && modelData.host !== 'localhost') {
        provider = modelData.host;
      }

      if (provider && provider !== 'Other') {
        if (!groups[provider]) {
          groups[provider] = [];
        }
        groups[provider].push(modelData.model_name);
      } else {
        otherModels.push(modelData.model_name);
      }
    });

    return { groups, otherModels };
  }, [modelList, modelSearch]);

  const modelContent = (
    <div className="w-80 flex flex-col h-[400px]">
      <div className="p-3 border-b border-gray-100 dark:border-gray-700 flex items-center gap-2 flex-shrink-0">
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('search_model', '搜索模型')}
          bordered={false}
          className="!bg-gray-50 dark:!bg-gray-800 rounded-lg flex-1"
          value={modelSearch}
          onChange={(e) => setModelSearch(e.target.value)}
        />
      </div>
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {Object.entries(groupedModels.groups).length > 0 && (
          <Collapse
            ghost
            defaultActiveKey={['AgentLLM', ...Object.keys(groupedModels.groups)]}
            expandIcon={({ isActive }) => (
              <DownOutlined rotate={isActive ? 180 : 0} className="text-xs text-gray-400" />
            )}
            className="[&_.ant-collapse-header]:!p-2 [&_.ant-collapse-content-box]:!p-0"
          >
            {Object.entries(groupedModels.groups).map(([provider, models]) => (
              <Panel header={<span className="text-xs font-medium text-gray-500">{provider}</span>} key={provider}>
                {models.map((model) => (
                  <div
                    key={model}
                    className={classNames(
                      'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors mb-1',
                      selectedModel === model ? 'bg-indigo-50 dark:bg-indigo-900/20' : ''
                    )}
                    onClick={() => {
                      setSelectedModel(model);
                      setIsModelOpen(false);
                      const filteredParams = chatInParams?.filter((i: ChatInParamItem) => i.param_type !== 'model') || [];
                      const modelConfig = appInfo?.layout?.chat_in_layout?.find(
                        (i: ChatInLayoutItem) => i.param_type === 'model'
                      );
                      setChatInParams([
                        ...filteredParams,
                        {
                          param_type: 'model',
                          param_value: model,
                          sub_type: modelConfig?.sub_type,
                        },
                      ]);
                    }}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <ModelIcon model={model} width={16} height={16} />
                      <span className="text-sm text-gray-700 dark:text-gray-200 truncate">{model}</span>
                    </div>
                    {selectedModel === model && <CheckOutlined className="text-indigo-500 flex-shrink-0" />}
                  </div>
                ))}
              </Panel>
            ))}
          </Collapse>
        )}

        {groupedModels.otherModels.length > 0 && (
          <div className="mt-2">
            <div className="px-2 py-1 text-xs font-medium text-gray-500">
              {t('other_models', '其他模型')}
            </div>
            {groupedModels.otherModels.map((model) => (
              <div
                key={model}
                className={classNames(
                  'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors mb-1',
                  selectedModel === model ? 'bg-indigo-50 dark:bg-indigo-900/20' : ''
                )}
                onClick={() => {
                  setSelectedModel(model);
                  setIsModelOpen(false);
                }}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <ModelIcon model={model} width={16} height={16} />
                  <span className="text-sm text-gray-700 dark:text-gray-200 truncate">{model}</span>
                </div>
                {selectedModel === model && <CheckOutlined className="text-indigo-500 flex-shrink-0" />}
              </div>
            ))}
          </div>
        )}

        {Object.keys(groupedModels.groups).length === 0 && groupedModels.otherModels.length === 0 && (
          <div className="px-3 py-8 text-center text-gray-400 text-xs">
            {t('no_models_found', '未找到模型')}
          </div>
        )}
      </div>
    </div>
  );

  // 资源文件显示
  const ResourceItemsDisplay = () => {
    const resources = resourceValue ? parseResourceValue(resourceValue) || [] : [];
    if (resources.length === 0) return null;

    const handleDelete = () => {
      setResourceValue({} as Record<string, unknown>);
      const chatInParamsResource = chatInParams.find((i: ChatInParamItem) => i.param_type === 'resource');
      if (chatInParamsResource && chatInParamsResource?.param_value) {
        const chatInParam = [
          ...extendedChatInParams,
          {
            param_type: 'resource',
            param_value: '',
            sub_type: resourceConfig?.sub_type,
          },
        ];
        setChatInParams(chatInParam);
      }
    };

    return (
      <div className="flex flex-wrap gap-2 mb-3">
        {resources.map((item: ParsedResourceItem, index: number) => {
          if (item.type === 'image_url' && item.image_url?.url) {
            const previewUrl = transformFileUrl(item.image_url.url);
            return (
              <div
                key={`img-${index}`}
                className="relative group flex-shrink-0"
              >
                <div className="w-16 h-16 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-gray-50 dark:bg-gray-800">
                  <img src={previewUrl} alt={item.image_url.file_name || 'Preview'} className="w-full h-full object-cover" />
                </div>
                <button
                  onClick={handleDelete}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-gray-500 hover:bg-red-500 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
                >
                  <CloseOutlined className="text-white text-xs" />
                </button>
              </div>
            );
          } else if (item.type === 'file_url' && item.file_url?.url) {
            return (
              <div
                key={`file-${index}`}
                className="relative group flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm"
              >
                <FileOutlined className="text-gray-400" />
                <span className="text-gray-700 dark:text-gray-300 truncate max-w-[120px]">
                  {item.file_url.file_name}
                </span>
                <button
                  onClick={handleDelete}
                  className="ml-1 text-gray-400 hover:text-red-500 transition-colors"
                >
                  <CloseOutlined className="text-xs" />
                </button>
              </div>
            );
          }
          return null;
        })}
      </div>
    );
  };

  // Selected Skills Display
  const SelectedSkillsDisplay = () => {
    if (!selectedSkills || selectedSkills.length === 0) return null;

    const handleRemoveSkill = (skillCode: string) => {
      const newSkills = selectedSkills.filter(s => s.skill_code !== skillCode);
      setSelectedSkills(newSkills);
      
      // Update chatInParams to remove the skill
      const newChatInParams = chatInParams.filter(
        (p: ChatInParamItem) => !(p.param_type === 'resource' && p.sub_type === 'skill(derisk)' && 
          (() => {
            try {
              const skillData = JSON.parse(p.param_value);
              return skillData.skill_code === skillCode;
            } catch {
              return false;
            }
          })())
      );
      setChatInParams(newChatInParams);
    };

    return (
      <div className="flex flex-wrap gap-2 mb-3 px-4 pt-3">
        {selectedSkills.map((skill) => (
          <div
            key={skill.skill_code}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/20 text-sm"
          >
            {skill.icon ? (
              <img src={skill.icon} className="w-4 h-4 rounded" alt={skill.name} />
            ) : (
              <div className="w-4 h-4 rounded bg-blue-500 flex items-center justify-center text-white text-xs font-medium">
                {skill.name?.charAt(0)?.toUpperCase() || 'S'}
              </div>
            )}
            <span className="text-gray-700 dark:text-gray-300 truncate max-w-[120px]">
              {skill.name}
            </span>
            <button
              onClick={() => handleRemoveSkill(skill.skill_code)}
              className="ml-1 text-gray-400 hover:text-red-500 transition-colors"
            >
              <CloseOutlined className="text-xs" />
            </button>
          </div>
        ))}
      </div>
    );
  };

  // 文件预览组件
  const FilePreview = ({ file, onRemove, isAutoGenerated }: { file: File; onRemove: () => void; isAutoGenerated?: boolean }) => {
    const [preview, setPreview] = useState<string>('');

    useEffect(() => {
      if (file.type.startsWith('image/')) {
        const url = URL.createObjectURL(file);
        setPreview(url);
        return () => URL.revokeObjectURL(url);
      }
    }, [file]);

    const isMarkdown = file.name.endsWith('.md') || file.type === 'text/markdown';

    return (
      <div className="relative group flex-shrink-0">
        {file.type.startsWith('image/') ? (
          <div className="w-12 h-12 rounded-lg border border-gray-100 dark:border-gray-700 overflow-hidden bg-white dark:bg-[#1F1F1F]">
            <img src={preview} alt={file.name} className="w-full h-full object-cover" />
          </div>
        ) : isMarkdown ? (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/20">
            <div className="w-8 h-10 rounded bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col items-center justify-center relative overflow-hidden">
              <div className="absolute top-0 right-0 w-3 h-3 bg-blue-500" style={{ clipPath: 'polygon(100% 0, 0 0, 100% 100%)' }}></div>
              <FileTextOutlined className="text-blue-500 text-lg" />
              <span className="text-[8px] text-blue-600 dark:text-blue-400 font-medium mt-0.5">MD</span>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate max-w-[120px]">
                {isAutoGenerated ? '输入内容' : file.name}
              </span>
              <span className="text-[10px] text-gray-400">
                {(file.size / 1024).toFixed(1)} KB
              </span>
            </div>
            <button
              className="ml-1 p-1 rounded-full hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-400 hover:text-red-500 transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
            >
              <CloseOutlined className="text-xs" />
            </button>
          </div>
        ) : (
          <div className="w-12 h-12 rounded-lg border border-gray-100 dark:border-gray-700 overflow-hidden bg-white dark:bg-[#1F1F1F] flex items-center justify-center bg-gray-50 dark:bg-gray-800">
            <FileTextOutlined className="text-gray-400 text-xl" />
          </div>
        )}
        {!isMarkdown && (
          <div
            className="absolute -top-1 -right-1 w-5 h-5 bg-black/50 hover:bg-red-500 rounded-full flex items-center justify-center cursor-pointer transition-all opacity-0 group-hover:opacity-100 backdrop-blur-sm"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
          >
            <CloseOutlined className="text-white text-xs" />
          </div>
        )}
      </div>
    );
  };

  // 超长文本自动转换为 Markdown 文件
  const convertTextToFile = useCallback((text: string): File | null => {
    if (!text.trim()) return null;

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const name = `input-${timestamp}.md`;

    const header = `# 对话输入内容

生成时间: ${new Date().toLocaleString()}
字符数: ${text.length}

---

`;
    const content = header + text;
    const blob = new Blob([content], { type: 'text/markdown' });
    return new File([blob], name, { type: 'text/markdown' });
  }, []);

  // 检查并自动转换超长文本
  const checkAndAutoConvertText = useCallback((text: string) => {
    if (text.length <= MAX_TEXT_LENGTH) return;
    if (autoGeneratedFileIndex !== null) return;
    if (isAutoConverting.current) return;

    isAutoConverting.current = true;

    const file = convertTextToFile(text);
    if (file) {
      const currentIndex = fileList.length;
      setFileList(prev => [...prev, file]);
      setAutoGeneratedFileIndex(currentIndex);
      setUserInput('');
    }

    setTimeout(() => {
      isAutoConverting.current = false;
    }, 100);
  }, [MAX_TEXT_LENGTH, autoGeneratedFileIndex, fileList.length, convertTextToFile]);

  // 拖拽上传处理
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsFocus(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      setFileList(prev => [...prev, ...files]);
    }
  }, []);

  // 粘贴上传处理
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    let hasFile = false;

    if (items) {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) {
            setFileList(prev => [...prev, file]);
            hasFile = true;
          }
        }
      }
    }

    if (hasFile) {
      e.preventDefault();
    }
  }, []);

  const onSubmit = async () => {
    if (!userInput.trim() && fileList.length === 0) return;

    if (shouldShowResourceSelect) {
      const resourceParam = chatInParams.find((i: ChatInParamItem) => i.param_type === 'resource');
      const hasResourceValue = resourceParam?.param_value && resourceParam.param_value.trim() !== '';
      if (!hasResourceValue) {
        message.warning(t('please_select_resource', '请先选择资源'));
        return;
      }
    }

    submitCountRef.current++;
    setTimeout(() => {
      scrollRef.current?.scrollTo({
        top: scrollRef.current?.scrollHeight,
        behavior: 'smooth',
      });
    }, 0);

    let newUserInput: UserChatContent;
    const currentResourceConfig = chatInParams.find((i: ChatInParamItem) => i.param_type === 'resource');
    
    if (MEDIA_RESOURCE_TYPES.includes(currentResourceConfig?.sub_type ?? '')) {
      const resources = parseResourceValue(resourceValue);
      const messages: (ParsedResourceItem | { type: string; text: string })[] = [...(resources || [])];
      if (userInput.trim()) {
        messages.push({ type: 'text', text: userInput });
      }
      newUserInput = { role: 'user', content: messages };
    } else {
      newUserInput = userInput;
    }

    setUserInput('');
    setFileList([]);

    await handleChat(newUserInput, {
      app_code: appInfo.app_code || '',
      ...(paramKey.length && { chat_in_params: chatInParams }),
    });

    if (submitCountRef.current === 1) {
      refreshDialogList && (await refreshDialogList());
    }
  };

  // 浮动操作按钮
  const handleStop = () => {
    if (!canAbort) return;
    stopChat({ conv_session_id: context.currentDialogue?.conv_uid || '' });
    ctrl && ctrl.abort();
    setTimeout(() => {
      setCanAbort(false);
      setReplyLoading(false);
    }, 100);
  };

  const handleRetry = () => {
    const lastHuman = history.filter((i: IChatDialogueMessageSchema) => i.role === 'human')?.slice(-1)?.[0];
    if (lastHuman) {
      handleChat(lastHuman.context || '', {
        app_code: appInfo.app_code,
        ...(paramKey.length && { chat_in_params: chatInParams }),
      });
      setTimeout(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current?.scrollHeight,
          behavior: 'smooth',
        });
      }, 0);
    }
  };

  const handleClear = async () => {
    if (clsLoading) return;
    setClsLoading(true);
    await apiInterceptors(clearChatHistory(context.currentDialogue?.conv_uid || '')).finally(async () => {
      await refreshHistory();
      setClsLoading(false);
    });
  };

  const uploadProps: UploadProps = {
    onRemove: (file) => {
      const index = fileList.indexOf(file as any);
      const newFileList = fileList.slice();
      newFileList.splice(index, 1);
      setFileList(newFileList);
    },
    beforeUpload: (file) => {
      setFileList([...fileList, file]);
      return false;
    },
    fileList: fileList as any,
  };

  return (
    <div className="w-full relative">
      {/* 浮动操作按钮 - 右上角 */}
      {showFloatingActions && history.length > 0 && (
        <div className="absolute -top-14 right-0 flex items-center gap-1 bg-white dark:bg-gray-800 rounded-full shadow-lg border border-gray-100 dark:border-gray-700 px-2 py-1 z-20">
          <Tooltip title={t('stop_replying', '暂停生成')} placement="top">
            <button
              onClick={handleStop}
              disabled={!canAbort}
              className={classNames(
                'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                canAbort
                  ? 'hover:bg-red-50 text-gray-600 hover:text-red-500 cursor-pointer'
                  : 'text-gray-300 cursor-not-allowed'
              )}
            >
              <PauseCircleOutlined className="text-lg" />
            </button>
          </Tooltip>

          <Tooltip title={t('answer_again', '重新生成')} placement="top">
            <button
              onClick={handleRetry}
              disabled={replyLoading || history.length === 0}
              className={classNames(
                'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                !replyLoading && history.length > 0
                  ? 'hover:bg-indigo-50 text-gray-600 hover:text-indigo-500 cursor-pointer'
                  : 'text-gray-300 cursor-not-allowed'
              )}
            >
              <RedoOutlined className="text-lg" />
            </button>
          </Tooltip>

          <Tooltip title={t('erase_memory', '清空对话')} placement="top">
            <button
              onClick={handleClear}
              disabled={clsLoading || history.length === 0}
              className={classNames(
                'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                !clsLoading && history.length > 0
                  ? 'hover:bg-orange-50 text-gray-600 hover:text-orange-500 cursor-pointer'
                  : 'text-gray-300 cursor-not-allowed'
              )}
            >
              {clsLoading ? (
                <Spin indicator={<LoadingOutlined style={{ fontSize: 16 }} spin />} />
              ) : (
                <ClearOutlined className="text-lg" />
              )}
            </button>
          </Tooltip>
        </div>
      )}

      {/* 主输入框 - 首页样式 */}
      <div
        className={classNames(
          'w-full bg-white dark:bg-[#232734] rounded-2xl shadow-sm border transition-all duration-300',
          isFocus
            ? 'border-indigo-500/50 shadow-lg ring-4 ring-indigo-500/5'
            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setIsFocus(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsFocus(false);
        }}
        onDrop={handleDrop}
      >
        {/* 已选技能预览 */}
        <SelectedSkillsDisplay />
        
        {/* 已选资源预览 */}
        <ResourceItemsDisplay />
        
        {/* 已选文件预览 */}
        {fileList.length > 0 && (
          <div className="flex gap-2 px-4 pt-3 overflow-x-auto scrollbar-hide">
            {fileList.map((file, index) => (
              <FilePreview
                key={index + file.name}
                file={file}
                isAutoGenerated={index === autoGeneratedFileIndex}
                onRemove={() => {
                  const newFileList = [...fileList];
                  newFileList.splice(index, 1);
                  setFileList(newFileList);
                  if (index === autoGeneratedFileIndex) {
                    setAutoGeneratedFileIndex(null);
                  }
                }}
              />
            ))}
          </div>
        )}

        {/* 文本输入区 */}
        <div className="p-4">
          <Input.TextArea
            placeholder={t('input_tips', '输入消息...')}
            className="!text-base !bg-transparent !border-0 !resize-none placeholder:!text-gray-400 !text-gray-800 dark:!text-gray-200 !shadow-none !p-0 !min-h-[60px]"
            autoSize={{ minRows: 2, maxRows: 8 }}
            value={userInput}
            onChange={(e) => {
              const text = e.target.value;
              setUserInput(text);
              checkAndAutoConvertText(text);
            }}
            onFocus={() => setIsFocus(true)}
            onBlur={() => setIsFocus(false)}
            onCompositionStart={() => setIsZhInput(true)}
            onCompositionEnd={() => setIsZhInput(false)}
            onPaste={handlePaste}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                if (e.shiftKey) return;
                if (isZhInput) return;
                e.preventDefault();
                if (!userInput.trim() || replyLoading) return;
                onSubmit();
              }
            }}
          />
        </div>

        {/* 底部工具栏 - 首页样式：左侧资源选择/模型选择，右侧文件上传和发送 */}
        <div className="flex items-center justify-between gap-2 px-3 pb-3 min-w-0">
          {/* 左侧工具区 - 可收缩 */}
          <div className="flex items-center gap-1.5 min-w-0 flex-shrink overflow-hidden">
            {/* 动态资源选择器 - 根据chat_in_layout配置渲染 */}
            {shouldShowResourceSelect && (
              <Select
                className="min-w-[80px] max-w-[130px] h-9 flex-shrink [&_.ant-select-selector]:!pr-6 [&_.ant-select-selection-item]:!max-w-[70px] [&_.ant-select-selection-item]:!truncate"
                placeholder={resourceConfig?.param_description || t('select_resource', '选择资源')}
                value={(resourceValue?.value || resourceValue?.key) as string | undefined}
                onChange={handleResourceSelectChange}
                loading={fetchResourceLoading}
                options={resourceOptions}
                suffixIcon={<DatabaseOutlined className="text-gray-400 text-xs" />}
                variant="borderless"
                style={{ 
                  backgroundColor: 'rgb(249 250 251 / 1)',
                  borderRadius: '9999px',
                }}
                popupMatchSelectWidth={false}
              />
            )}

            {/* 媒体类型文件上传按钮 */}
            {shouldShowFileUpload && (
              <Upload
                name="file"
                accept={getAcceptTypes(resourceConfig?.sub_type || '')}
                showUploadList={false}
                beforeUpload={(file) => {
                  handleFileUpload(file);
                  return false;
                }}
              >
                <Tooltip title={resourceConfig?.param_description || t('upload_file', '上传文件')}>
                  <button className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-all flex-shrink-0">
                    <FolderAddOutlined className="text-sm" />
                  </button>
                </Tooltip>
              </Upload>
            )}

            {/* 分隔线 - 仅当有资源配置时显示 */}
            {(shouldShowResourceSelect || shouldShowFileUpload) && (
              <div className="w-px h-4 bg-gray-200 dark:bg-gray-700 flex-shrink-0" />
            )}

            {/* 模型选择器 */}
            <Popover
              content={modelContent}
              trigger="click"
              placement="topLeft"
              open={isModelOpen}
              onOpenChange={setIsModelOpen}
              arrow={false}
              overlayClassName="[&_.ant-popover-inner]:!p-0 [&_.ant-popover-inner]:!rounded-xl [&_.ant-popover-inner]:!shadow-xl"
            >
              <div className="flex items-center gap-1.5 bg-gray-50 dark:bg-gray-800 px-2 py-1 rounded-full border border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 transition-all group flex-shrink-0">
                <ModelIcon model={selectedModel} width={14} height={14} />
                <span className="text-xs text-gray-700 dark:text-gray-300 max-w-[80px] truncate group-hover:text-indigo-500 transition-colors">
                  {selectedModel || t('select_model', '选择模型')}
                </span>
                <DownOutlined className="text-[10px] text-gray-400 group-hover:text-indigo-500 transition-colors" />
              </div>
            </Popover>

            {/* 模型参数配置按钮 */}
            <Tooltip title={t('model_params', '模型参数')}>
              <button
                onClick={() => setIsParamsModalOpen(true)}
                className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-indigo-500 transition-all flex-shrink-0"
              >
                <SlidersOutlined className="text-sm" />
              </button>
            </Tooltip>
          </div>

          {/* 右侧：文件上传和发送按钮 - 固定不收缩 */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {/* 文件上传 - 首页位置（右侧） */}
            <Upload {...uploadProps} showUploadList={false}>
              <button className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-all">
                <PaperClipOutlined className="text-sm" />
              </button>
            </Upload>

            {/* 发送按钮 */}
            <Button
              type="primary"
              shape="circle"
              className={classNames(
                'w-9 h-9 flex items-center justify-center transition-all !border-0 flex-shrink-0',
                userInput.trim() || fileList.length > 0
                  ? 'bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-600 hover:to-indigo-700 shadow-md hover:shadow-lg'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
              )}
              onClick={onSubmit}
              disabled={(!userInput.trim() && fileList.length === 0) || replyLoading}
            >
              {replyLoading ? (
                <Spin indicator={<LoadingOutlined className="text-white text-sm" spin />} />
              ) : (
                <ArrowUpOutlined className="text-white text-base" />
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* 模型参数配置弹窗 */}
      <ModelParamsModal
        open={isParamsModalOpen}
        onClose={() => setIsParamsModalOpen(false)}
        temperature={temperatureValue}
        onTemperatureChange={setTemperatureValue}
        maxTokens={maxNewTokensValue}
        onMaxTokensChange={setMaxNewTokensValue}
      />
    </div>
  );
};

export default UnifiedChatInput;
