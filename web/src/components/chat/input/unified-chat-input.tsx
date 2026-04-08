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
  FolderAddOutlined,
  DatabaseOutlined,
  PlusOutlined,
  ThunderboltOutlined,
  LeftOutlined,
  BookOutlined,
  UploadOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import {
  Button,
  Input,
  Popover,
  Tooltip,
  Upload,
  Modal,
  Slider,
  Collapse,
  Spin,
  Select,
  App,
  Badge,
} from 'antd';
import { useRequest } from 'ahooks';
import classNames from 'classnames';
import { apiInterceptors, getModelList, clearChatHistory, stopChat, postChatModeParamsFileLoad, getResourceV2, getDbList, getSpaceList, getSkillList, getMCPList } from '@/client/api';
import { ChatContentContext, SelectedSkill } from '@/contexts';
import ModelIcon from '@/components/icons/model-icon';
import { IModelData } from '@/types/model';
import { IChatDialogueMessageSchema, UserChatContent } from '@/types/chat';
import { MEDIA_RESOURCE_TYPES } from '@/app/application/app/components/chat-layout-config';
import { parseResourceValue, transformFileUrl } from '@/utils';
import { useSearchParams } from 'next/navigation';
import { getFileIcon, formatFileSize } from '@/utils/fileUtils';
import { ConnectorsModal } from '@/components/chat/connectors-modal';

const { Panel } = Collapse;

interface ChatInLayoutItem {
  param_type: string;
  sub_type?: string;
  param_description?: string;
  param_default_value?: string | number;
  [key: string]: unknown;
}

interface UploadingFile {
  id: string;
  file: File;
  progress: number;
  status: 'uploading' | 'success' | 'error';
  error?: string;
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
  image_url?: { url: string; preview_url?: string; file_name?: string };
  file_url?: { url: string; preview_url?: string; file_name?: string };
  audio_url?: { url: string; preview_url?: string; file_name?: string };
  video_url?: { url: string; preview_url?: string; file_name?: string };
  file_name?: string;
  file_path?: string;
  url?: string;
  preview_url?: string;
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

// 数据源规范化 - 处理不同API返回格式
function normalizeDatasource(raw: any) {
  const params = raw.params || {};
  return {
    ...raw,
    db_type: raw.db_type || raw.type || '',
    db_name: raw.db_name || params.database || params.db_name || raw.name ||
             (params.path ? params.path.split('/').pop()?.replace(/\.\w+$/, '') : '') || '',
    db_host: raw.db_host || params.host || '',
    db_port: raw.db_port || params.port || 0,
    db_path: raw.db_path || params.path || '',
    comment: raw.comment || raw.description || '',
  };
}

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
  const { message } = App.useApp();
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
  const [isZhInput, setIsZhInput] = useState<boolean>(false);
  const submitCountRef = useRef(0);

  // 模型相关
  const [modelList, setModelList] = useState<IModelData[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [modelSearch, setModelSearch] = useState('');
  const [isModelOpen, setIsModelOpen] = useState(false);
  const [isParamsModalOpen, setIsParamsModalOpen] = useState(false);
  
  // 上传中的文件列表
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);

  // "+" 按钮相关
  const [isPlusMenuOpen, setIsPlusMenuOpen] = useState(false);
  const [plusMenuView, setPlusMenuView] = useState<'main' | 'datasource' | 'knowledge'>('main');
  const [dbList, setDbList] = useState<any[]>([]);
  const [dbLoading, setDbLoading] = useState(false);
  const [spaceList, setSpaceList] = useState<any[]>([]);
  const [spaceLoading, setSpaceLoading] = useState(false);
  const [selectedDataSources, setSelectedDataSources] = useState<any[]>([]);
  const [selectedKnowledgeBases, setSelectedKnowledgeBases] = useState<any[]>([]);
  const [dbSearch, setDbSearch] = useState('');
  const [kbSearch, setKbSearch] = useState('');
  const uploadRef = useRef<any>(null);

  // 闪电按钮相关 (Skills/MCP)
  const [isLightningOpen, setIsLightningOpen] = useState(false);
  const [lightningSearch, setLightningSearch] = useState('');
  const [skillList, setSkillList] = useState<any[]>([]);
  const [mcpList, setMcpList] = useState<any[]>([]);
  const [selectedMcps, setSelectedMcps] = useState<any[]>([]);
  const [isConnectorsModalOpen, setIsConnectorsModalOpen] = useState(false);

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

  // 获取技能列表
  useRequest(
    async () => {
      const [, data] = await apiInterceptors(getSkillList({ filter: '' }, { page: '1', page_size: '50' }));
      return data as any;
    },
    {
      onSuccess: (data: any) => {
        if (data?.items && Array.isArray(data.items)) {
          setSkillList(data.items);
        }
      },
    },
  );

  // 获取MCP列表
  useRequest(
    async () => {
      const [, data] = await apiInterceptors(getMCPList({ filter: '' }, { page: '1', page_size: '50' }));
      return data as any;
    },
    {
      onSuccess: (data: any) => {
        if (data?.items && Array.isArray(data.items)) {
          setMcpList(data.items);
        }
      },
    },
  );

  // 获取数据源列表（延迟加载）
  const fetchDbList = useCallback(async () => {
    if (dbList.length > 0) return;
    setDbLoading(true);
    try {
      const [, data] = await apiInterceptors(getDbList());
      if (data) setDbList((data as any[]).map(normalizeDatasource));
    } finally {
      setDbLoading(false);
    }
  }, [dbList.length]);

  // 获取知识库列表（延迟加载）
  const fetchSpaceList = useCallback(async () => {
    if (spaceList.length > 0) return;
    setSpaceLoading(true);
    try {
      const [, data] = await apiInterceptors(getSpaceList());
      if (data) setSpaceList(data);
    } finally {
      setSpaceLoading(false);
    }
  }, [spaceList.length]);

  const paramKey: string[] = useMemo(() => {
    return appInfo?.layout?.chat_in_layout?.map((i: ChatInLayoutItem) => i.param_type) || [];
  }, [appInfo?.layout?.chat_in_layout]);

  // 从应用配置加载默认绑定的 Skills/MCP
  const defaultBoundSkills = useMemo(() => {
    const tools = appInfo?.resource_tool || [];
    return tools
      .filter((item: any) => {
        const type = item.type || '';
        return type === 'skill' || type === 'skill(derisk)';
      })
      .map((item: any) => {
        try {
          const parsed = JSON.parse(item.value || '{}');
          return {
            skill_code: parsed.key || parsed.skillCode || parsed.skill_code || item.name,
            name: parsed.name || parsed.label || item.name,
            description: parsed.description || parsed.skill_description || '',
            icon: parsed.icon,
            author: parsed.author || parsed.skill_author,
            type: 'skill',
            _isDefault: true,
          };
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }, [appInfo?.resource_tool]);

  const defaultBoundMcps = useMemo(() => {
    const tools = appInfo?.resource_tool || [];
    return tools
      .filter((item: any) => {
        const type = item.type || '';
        return type === 'mcp(derisk)' || type === 'mcp';
      })
      .map((item: any) => {
        try {
          const parsed = JSON.parse(item.value || '{}');
          return {
            id: parsed.key || parsed.mcp_code || item.name,
            name: parsed.name || parsed.label || item.name,
            description: parsed.description || '',
            icon: parsed.icon,
            available: parsed.available,
            _isDefault: true,
          };
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }, [appInfo?.resource_tool]);

  const defaultBoundKnowledgeBases = useMemo(() => {
    const resourceKnowledge = appInfo?.resource_knowledge?.[0]?.value;
    if (!resourceKnowledge) return [];
    try {
      const parsed = JSON.parse(resourceKnowledge);
      return (parsed?.knowledges || []).map((k: any) => ({
        id: k.knowledge_id,
        name: k.knowledge_name || k.knowledge_id,
        _isDefault: true,
      }));
    } catch {
      return [];
    }
  }, [appInfo?.resource_knowledge]);

  const defaultBoundDatabases = useMemo(() => {
    const tools = appInfo?.resource_tool || [];
    return tools
      .filter((item: any) => item.type === 'datasource')
      .map((item: any) => {
        try {
          const parsed = JSON.parse(item.value || '{}');
          return {
            db_name: parsed.db_name,
            db_type: parsed.db_type,
            id: parsed.id,
            _isDefault: true,
          };
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }, [appInfo?.resource_tool]);

  // 初始化默认绑定 - 只在 appInfo 加载后执行一次
  const [defaultsInitialized, setDefaultsInitialized] = useState(false);
  useEffect(() => {
    if (defaultsInitialized) return;
    if (!appInfo?.app_code) return;

    let changed = false;
    if (defaultBoundSkills.length > 0 && (!selectedSkills || selectedSkills.length === 0)) {
      setSelectedSkills(defaultBoundSkills);
      changed = true;
    }
    if (defaultBoundMcps.length > 0 && selectedMcps.length === 0) {
      setSelectedMcps(defaultBoundMcps);
      changed = true;
    }
    if (defaultBoundKnowledgeBases.length > 0 && selectedKnowledgeBases.length === 0) {
      setSelectedKnowledgeBases(defaultBoundKnowledgeBases);
      changed = true;
    }
    if (defaultBoundDatabases.length > 0 && selectedDataSources.length === 0) {
      setSelectedDataSources(defaultBoundDatabases);
      changed = true;
    }
    if (changed || defaultBoundSkills.length === 0) {
      setDefaultsInitialized(true);
    }
  }, [appInfo?.app_code, defaultBoundSkills, defaultBoundMcps, defaultBoundKnowledgeBases, defaultBoundDatabases, defaultsInitialized]);

  // 合并默认绑定 + 动态选择的总数（用于 badge 显示）
  const allSelectedSkills = useMemo(() => {
    if (!selectedSkills || selectedSkills.length === 0) return defaultBoundSkills;
    return selectedSkills;
  }, [selectedSkills, defaultBoundSkills]);

  const allSelectedMcps = useMemo(() => {
    if (selectedMcps.length === 0) return defaultBoundMcps;
    return selectedMcps;
  }, [selectedMcps, defaultBoundMcps]);

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

  // 处理数据源选择
  const handleDataSourceSelect = useCallback((ds: any) => {
    const isSelected = selectedDataSources.some(s => s.id === ds.id);
    if (isSelected) {
      setSelectedDataSources(prev => prev.filter(s => s.id !== ds.id));
    } else {
      setSelectedDataSources(prev => [...prev, ds]);
    }
  }, [selectedDataSources]);

  // 处理知识库选择
  const handleKnowledgeBaseSelect = useCallback((kb: any) => {
    const isSelected = selectedKnowledgeBases.some(s => (s.id || s.name) === (kb.id || kb.name));
    if (isSelected) {
      setSelectedKnowledgeBases(prev => prev.filter(s => (s.id || s.name) !== (kb.id || kb.name)));
    } else {
      setSelectedKnowledgeBases(prev => [...prev, kb]);
    }
  }, [selectedKnowledgeBases]);

  // 处理闪电按钮中的 skill 切换
  const handleLightningSkillToggle = useCallback((skill: any) => {
    const isSelected = selectedSkills?.some((s: SelectedSkill) => s.skill_code === skill.skill_code);
    if (isSelected) {
      const newSkills = selectedSkills.filter((s: SelectedSkill) => s.skill_code !== skill.skill_code);
      setSelectedSkills(newSkills);
    } else {
      setSelectedSkills([...(selectedSkills || []), skill]);
    }
  }, [selectedSkills, setSelectedSkills]);

  // 处理闪电按钮中的 MCP 切换
  const handleLightningMcpToggle = useCallback((mcp: any) => {
    const mcpId = mcp.id || mcp.uuid || mcp.name;
    const isSelected = selectedMcps.some((m: any) => (m.id || m.uuid || m.name) === mcpId);
    if (isSelected) {
      setSelectedMcps(prev => prev.filter((m: any) => (m.id || m.uuid || m.name) !== mcpId));
    } else {
      setSelectedMcps(prev => [...prev, mcp]);
    }
  }, [selectedMcps]);

  // 闪电按钮 - 过滤后的列表
  const filteredSkillList = useMemo(() => {
    if (!lightningSearch) return skillList;
    const search = lightningSearch.toLowerCase();
    return skillList.filter((s: any) =>
      s.name?.toLowerCase().includes(search) || s.description?.toLowerCase().includes(search)
    );
  }, [skillList, lightningSearch]);

  const filteredMcpList = useMemo(() => {
    if (!lightningSearch) return mcpList;
    const search = lightningSearch.toLowerCase();
    return mcpList.filter((m: any) =>
      m.name?.toLowerCase().includes(search) || m.description?.toLowerCase().includes(search)
    );
  }, [mcpList, lightningSearch]);

  const lightningBadgeCount = (allSelectedSkills?.length || 0) + allSelectedMcps.length;

  // 闪电按钮弹出内容 - Skills/MCP 选择
  const lightningContent = useMemo(() => (
    <div className="w-80 flex flex-col max-h-[450px]">
      <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-700">
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('search_skills', '搜索技能...')}
          bordered={false}
          className="!bg-gray-50 dark:!bg-gray-800 rounded-lg"
          size="small"
          value={lightningSearch}
          onChange={(e) => setLightningSearch(e.target.value)}
          allowClear
        />
      </div>
      <div className="flex-1 overflow-y-auto py-1 px-2">
        {/* Skills 区域 */}
        {filteredSkillList.length > 0 && (
          <>
            <div className="px-2 py-1.5 text-xs text-gray-400 font-medium">{t('skills', '技能')}</div>
            {filteredSkillList.map((skill: any) => {
              const isSelected = selectedSkills?.some((s: SelectedSkill) => s.skill_code === skill.skill_code);
              return (
                <div
                  key={skill.skill_code}
                  className={classNames(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors mb-0.5',
                    isSelected
                      ? 'bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                  )}
                  onClick={() => handleLightningSkillToggle(skill)}
                >
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
                    {skill.icon ? (
                      <img src={skill.icon} className="w-5 h-5 rounded" alt={skill.name} />
                    ) : (
                      <ThunderboltOutlined className="text-white text-sm" />
                    )}
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">{skill.name}</span>
                      {skill.type && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 flex-shrink-0">{t('official', '官方')}</span>
                      )}
                    </div>
                    {skill.description && (
                      <div className="text-xs text-gray-400 truncate mt-0.5">{skill.description}</div>
                    )}
                  </div>
                  {isSelected && <CheckOutlined className="text-purple-500 text-sm flex-shrink-0" />}
                </div>
              );
            })}
          </>
        )}

        {/* MCP 区域 */}
        {filteredMcpList.length > 0 && (
          <>
            <div className="px-2 py-1.5 text-xs text-gray-400 font-medium mt-1">{t('mcp_servers', 'MCP 服务')}</div>
            {filteredMcpList.map((mcp: any) => {
              const mcpId = mcp.id || mcp.uuid || mcp.name;
              const isSelected = selectedMcps.some((m: any) => (m.id || m.uuid || m.name) === mcpId);
              return (
                <div
                  key={mcpId}
                  className={classNames(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors mb-0.5',
                    isSelected
                      ? 'bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                  )}
                  onClick={() => handleLightningMcpToggle(mcp)}
                >
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center flex-shrink-0">
                    {mcp.icon ? (
                      <img src={mcp.icon} className="w-5 h-5 rounded" alt={mcp.name} />
                    ) : (
                      <ApiOutlined className="text-white text-sm" />
                    )}
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">{mcp.name}</span>
                      {mcp.available && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400 flex-shrink-0">Active</span>
                      )}
                    </div>
                    {mcp.description && (
                      <div className="text-xs text-gray-400 truncate mt-0.5">{mcp.description}</div>
                    )}
                  </div>
                  {isSelected && <CheckOutlined className="text-purple-500 text-sm flex-shrink-0" />}
                </div>
              );
            })}
          </>
        )}

        {filteredSkillList.length === 0 && filteredMcpList.length === 0 && (
          <div className="text-center text-gray-400 text-xs py-8">{t('no_skills_found', '未找到相关技能')}</div>
        )}
      </div>
      <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100 dark:border-gray-700">
        <span className="text-xs text-gray-400">{skillList.length + mcpList.length} {t('skills_available', '个可用')}</span>
        <button
          className="text-xs text-indigo-500 hover:text-indigo-600 font-medium"
          onClick={() => { setIsLightningOpen(false); setIsConnectorsModalOpen(true); }}
        >
          {t('manage_skills', '管理技能')} →
        </button>
      </div>
    </div>
  ), [lightningSearch, filteredSkillList, filteredMcpList, selectedSkills, selectedMcps, skillList.length, mcpList.length, t, handleLightningSkillToggle, handleLightningMcpToggle]);

  // 处理多文件上传 - 保持与 parseResourceValue 兼容的格式
  const handleFileUpload = useCallback(async (file: File) => {
    // 生成唯一ID
    const uploadId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    
    // 立即添加到上传列表，显示卡片
    const uploadingFile: UploadingFile = {
      id: uploadId,
      file,
      progress: 0,
      status: 'uploading',
    };
    setUploadingFiles(prev => [...prev, uploadingFile]);
    
    const formData = new FormData();
    formData.append('doc_files', file);

    // 使用本地选择的模型，如果没有则使用 modelValue
    const currentModel = selectedModel || modelValue || '';

    try {
      const [err, res] = await apiInterceptors(
        postChatModeParamsFileLoad({
          convUid: chatId || '',
          chatMode: scene || 'chat_normal',
          data: formData,
          model: currentModel,
          temperatureValue,
          maxNewTokensValue,
          config: {
            timeout: 1000 * 60 * 60,
          },
        }),
      );
      
      if (err) {
        // 更新状态为错误，保留文件卡片
        setUploadingFiles(prev => 
          prev.map(f => 
            f.id === uploadId 
              ? { ...f, status: 'error', error: err?.message || t('upload_failed', '上传失败') }
              : f
          )
        );
        message.error(t('upload_failed', '上传失败'));
        console.error('Upload error:', err);
        return;
      }
      
      console.log('Upload response:', res);
      
      if (res) {
        // 移除上传中的文件
        setUploadingFiles(prev => prev.filter(f => f.id !== uploadId));
        
        // 获取当前资源列表
        const currentResources = resourceValue ? parseResourceValue(resourceValue) || [] : [];
        
        // 判断是图片还是文件
        const isImage = file.type.startsWith('image/');
        const isAudio = file.type.startsWith('audio/');
        const isVideo = file.type.startsWith('video/');
        
        // 处理返回的URL - 优先使用 preview_url
        // res 已经是 data.data，所以直接访问 preview_url
        let fileUrl = '';
        let previewUrl = '';
        
        // 格式1: res.preview_url (预览URL) 和 res.file_path (文件路径)
        if (res.preview_url) {
          previewUrl = res.preview_url;
          fileUrl = res.file_path || previewUrl;
        }
        // 格式2: res.file_path
        else if (res.file_path) {
          fileUrl = res.file_path;
          previewUrl = transformFileUrl(fileUrl);
        }
        // 格式3: res.url 或 res.file_url
        else if (res.url || res.file_url) {
          fileUrl = res.url || res.file_url;
          previewUrl = fileUrl;
        }
        // 格式4: res.path
        else if (res.path) {
          fileUrl = res.path;
          previewUrl = transformFileUrl(fileUrl);
        }
        // 格式5: 直接是字符串
        else if (typeof res === 'string') {
          fileUrl = res;
          previewUrl = res;
        }
        // 格式6: 数组
        else if (Array.isArray(res)) {
          const firstRes = res[0];
          previewUrl = firstRes?.preview_url || '';
          fileUrl = firstRes?.file_path || firstRes?.preview_url || previewUrl;
          if (!previewUrl && fileUrl) {
            previewUrl = transformFileUrl(fileUrl);
          }
        }
        
        console.log('File URL:', fileUrl, 'Preview URL:', previewUrl);
        
        let newResourceItem;
        if (isImage) {
          newResourceItem = {
            type: 'image_url',
            image_url: {
              url: fileUrl,
              preview_url: previewUrl || fileUrl,
              file_name: file.name,
            },
          };
        } else if (isAudio) {
          newResourceItem = {
            type: 'audio_url',
            audio_url: {
              url: fileUrl,
              preview_url: previewUrl || fileUrl,
              file_name: file.name,
            },
          };
        } else if (isVideo) {
          newResourceItem = {
            type: 'video_url',
            video_url: {
              url: fileUrl,
              preview_url: previewUrl || fileUrl,
              file_name: file.name,
            },
          };
        } else {
          newResourceItem = {
            type: 'file_url',
            file_url: {
              url: fileUrl,
              preview_url: previewUrl || fileUrl,
              file_name: file.name,
            },
          };
        }
        
        console.log('New resource item:', newResourceItem);
        
        // 添加到现有资源列表
        const updatedResources = [...currentResources, newResourceItem];
        
        const newChatInParams = [
          ...extendedChatInParams,
          {
            param_type: 'resource',
            param_value: JSON.stringify(updatedResources),
            sub_type: resourceConfig?.sub_type || 'common_file',
          },
        ];
        setChatInParams(newChatInParams);
        setResourceValue(updatedResources as Record<string, unknown>);
        
        message.success(t('upload_success', '上传成功'));
      }
    } catch (error: any) {
      console.error('Upload error:', error);
      // 更新状态为错误，保留文件卡片
      setUploadingFiles(prev => 
        prev.map(f => 
          f.id === uploadId 
            ? { ...f, status: 'error', error: error?.message || t('upload_failed', '上传失败') }
            : f
        )
      );
      message.error(t('upload_failed', '上传失败'));
    }
  }, [chatId, scene, selectedModel, modelValue, temperatureValue, maxNewTokensValue, resourceConfig, extendedChatInParams, setChatInParams, setResourceValue, resourceValue]);

  // "+" 按钮弹出菜单内容
  const plusMenuContent = useMemo(() => {
    // 过滤数据源
    const filteredDbList = dbSearch
      ? dbList.filter((ds: any) => ds.db_name?.toLowerCase().includes(dbSearch.toLowerCase()) || ds.comment?.toLowerCase().includes(dbSearch.toLowerCase()))
      : dbList;

    // 过滤知识库
    const filteredSpaceList = kbSearch
      ? spaceList.filter((kb: any) => kb.name?.toLowerCase().includes(kbSearch.toLowerCase()) || kb.desc?.toLowerCase().includes(kbSearch.toLowerCase()))
      : spaceList;

    if (plusMenuView === 'datasource') {
      return (
        <div className="w-72 flex flex-col max-h-[400px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 dark:border-gray-700">
            <button
              onClick={() => { setPlusMenuView('main'); setDbSearch(''); }}
              className="w-6 h-6 rounded flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500"
            >
              <LeftOutlined className="text-xs" />
            </button>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('select_datasource', '选择数据源')}</span>
          </div>
          <div className="px-3 py-2">
            <Input
              prefix={<SearchOutlined className="text-gray-400" />}
              placeholder={t('search_datasource', '搜索数据源...')}
              bordered={false}
              className="!bg-gray-50 dark:!bg-gray-800 rounded-lg"
              size="small"
              value={dbSearch}
              onChange={(e) => setDbSearch(e.target.value)}
            />
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {dbLoading ? (
              <div className="flex items-center justify-center py-8"><Spin size="small" /></div>
            ) : filteredDbList.length === 0 ? (
              <div className="text-center text-gray-400 text-xs py-8">{t('no_datasource', '暂无数据源')}</div>
            ) : (
              filteredDbList.map((ds: any) => {
                const isSelected = selectedDataSources.some(s => s.id === ds.id);
                return (
                  <div
                    key={ds.id}
                    className={classNames(
                      'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors mb-1',
                      isSelected ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                    )}
                    onClick={() => handleDataSourceSelect(ds)}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <DatabaseOutlined className={classNames('text-sm flex-shrink-0', isSelected ? 'text-green-500' : 'text-gray-400')} />
                      <div className="overflow-hidden">
                        <div className="text-sm text-gray-700 dark:text-gray-200 truncate">{ds.db_name}</div>
                        {ds.comment && <div className="text-xs text-gray-400 truncate">{ds.comment}</div>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500">{ds.db_type}</span>
                      {isSelected && <CheckOutlined className="text-green-500 text-xs" />}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      );
    }

    if (plusMenuView === 'knowledge') {
      return (
        <div className="w-72 flex flex-col max-h-[400px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 dark:border-gray-700">
            <button
              onClick={() => { setPlusMenuView('main'); setKbSearch(''); }}
              className="w-6 h-6 rounded flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500"
            >
              <LeftOutlined className="text-xs" />
            </button>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('select_knowledge_base', '选择知识库')}</span>
          </div>
          <div className="px-3 py-2">
            <Input
              prefix={<SearchOutlined className="text-gray-400" />}
              placeholder={t('search_knowledge_base', '搜索知识库...')}
              bordered={false}
              className="!bg-gray-50 dark:!bg-gray-800 rounded-lg"
              size="small"
              value={kbSearch}
              onChange={(e) => setKbSearch(e.target.value)}
            />
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {spaceLoading ? (
              <div className="flex items-center justify-center py-8"><Spin size="small" /></div>
            ) : filteredSpaceList.length === 0 ? (
              <div className="text-center text-gray-400 text-xs py-8">{t('no_knowledge_base', '暂无知识库')}</div>
            ) : (
              filteredSpaceList.map((kb: any) => {
                const isSelected = selectedKnowledgeBases.some(s => (s.id || s.name) === (kb.id || kb.name));
                return (
                  <div
                    key={kb.id || kb.name}
                    className={classNames(
                      'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors mb-1',
                      isSelected ? 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                    )}
                    onClick={() => handleKnowledgeBaseSelect(kb)}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <BookOutlined className={classNames('text-sm flex-shrink-0', isSelected ? 'text-amber-500' : 'text-gray-400')} />
                      <div className="overflow-hidden">
                        <div className="text-sm text-gray-700 dark:text-gray-200 truncate">{kb.name}</div>
                        {kb.desc && <div className="text-xs text-gray-400 truncate">{kb.desc}</div>}
                      </div>
                    </div>
                    {isSelected && <CheckOutlined className="text-amber-500 text-xs flex-shrink-0" />}
                  </div>
                );
              })
            )}
          </div>
        </div>
      );
    }

    // main view
    return (
      <div className="w-56 p-1">
        <Upload
          ref={uploadRef}
          name="file"
          accept={getAcceptTypes(resourceConfig?.sub_type || 'common_file')}
          showUploadList={false}
          beforeUpload={(file) => {
            handleFileUpload(file);
            setIsPlusMenuOpen(false);
            return false;
          }}
        >
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-gray-700 dark:text-gray-200 w-full">
            <UploadOutlined className="text-base text-gray-500" />
            <span className="text-sm">{t('upload_file', '上传文件')}</span>
          </div>
        </Upload>
        <div
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-gray-700 dark:text-gray-200"
          onClick={() => { setPlusMenuView('datasource'); fetchDbList(); }}
        >
          <DatabaseOutlined className="text-base text-gray-500" />
          <span className="text-sm">{t('select_datasource', '选择数据源')}</span>
        </div>
        <div
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-gray-700 dark:text-gray-200"
          onClick={() => { setPlusMenuView('knowledge'); fetchSpaceList(); }}
        >
          <BookOutlined className="text-base text-gray-500" />
          <span className="text-sm">{t('select_knowledge_base', '选择知识库')}</span>
        </div>
      </div>
    );
  }, [plusMenuView, dbList, spaceList, dbLoading, spaceLoading, selectedDataSources, selectedKnowledgeBases, dbSearch, kbSearch, resourceConfig, t, handleFileUpload, handleDataSourceSelect, handleKnowledgeBaseSelect, fetchDbList, fetchSpaceList]);

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

  // 资源文件显示 - 支持多文件，优化设计
  const ResourceItemsDisplay = () => {
    const resources = resourceValue ? parseResourceValue(resourceValue) || [] : [];
    
    // 如果没有资源且没有上传中的文件，不显示
    if (resources.length === 0 && uploadingFiles.length === 0) return null;

    const handleDelete = (index: number) => {
      const newResources = resources.filter((_: unknown, i: number) => i !== index);
      if (newResources.length === 0) {
        setResourceValue(null);
      } else {
        // 直接存储数组
        setResourceValue(newResources as Record<string, unknown>);
      }
      
      const chatInParamsResource = chatInParams.find((i: ChatInParamItem) => i.param_type === 'resource');
      if (chatInParamsResource && chatInParamsResource?.param_value) {
        const chatInParam = [
          ...extendedChatInParams,
          {
            param_type: 'resource',
            param_value: newResources.length > 0 ? JSON.stringify(newResources) : '',
            sub_type: resourceConfig?.sub_type,
          },
        ];
        setChatInParams(chatInParam);
      }
    };

    const handleDeleteUploading = (id: string) => {
      setUploadingFiles(prev => prev.filter(f => f.id !== id));
    };

    // 获取文件类型的颜色主题
    const getFileTypeTheme = (fileName: string) => {
      const ext = fileName.split('.').pop()?.toLowerCase() || '';
      const themes: Record<string, { bg: string; border: string; icon: string }> = {
        // 图片 - 紫色主题
        jpg: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
        jpeg: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
        png: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
        gif: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
        webp: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
        // PDF - 红色主题
        pdf: { bg: 'bg-red-50', border: 'border-red-200', icon: 'text-red-500' },
        // Word - 蓝色主题
        doc: { bg: 'bg-blue-50', border: 'border-blue-200', icon: 'text-blue-500' },
        docx: { bg: 'bg-blue-50', border: 'border-blue-200', icon: 'text-blue-500' },
        // Excel - 绿色主题
        xls: { bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-500' },
        xlsx: { bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-500' },
        csv: { bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-500' },
        // PPT - 橙色主题
        ppt: { bg: 'bg-orange-50', border: 'border-orange-200', icon: 'text-orange-500' },
        pptx: { bg: 'bg-orange-50', border: 'border-orange-200', icon: 'text-orange-500' },
        // 代码文件 - 青色主题
        js: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
        ts: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
        py: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
        java: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
        // Markdown - 灰色主题
        md: { bg: 'bg-gray-50', border: 'border-gray-200', icon: 'text-gray-500' },
        // 视频 - 粉色主题
        mp4: { bg: 'bg-pink-50', border: 'border-pink-200', icon: 'text-pink-500' },
        mov: { bg: 'bg-pink-50', border: 'border-pink-200', icon: 'text-pink-500' },
        // 音频 - 黄色主题
        mp3: { bg: 'bg-yellow-50', border: 'border-yellow-200', icon: 'text-yellow-600' },
        wav: { bg: 'bg-yellow-50', border: 'border-yellow-200', icon: 'text-yellow-600' },
        // 压缩包 - 靛蓝色主题
        zip: { bg: 'bg-indigo-50', border: 'border-indigo-200', icon: 'text-indigo-500' },
        rar: { bg: 'bg-indigo-50', border: 'border-indigo-200', icon: 'text-indigo-500' },
        '7z': { bg: 'bg-indigo-50', border: 'border-indigo-200', icon: 'text-indigo-500' },
      };
      return themes[ext] || { bg: 'bg-gray-50', border: 'border-gray-200', icon: 'text-gray-500' };
    };

    const totalCount = resources.length + uploadingFiles.length;

    return (
      <div className="px-4 pt-3 pb-2">
        {/* 多文件上传标题 - 当有多个文件时显示 */}
        {totalCount > 1 && (
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FolderAddOutlined className="text-indigo-600 text-xs" />
              </div>
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('uploaded_files', '已上传文件')} 
                <span className="ml-1 text-xs text-gray-500">({totalCount})</span>
              </span>
            </div>
            <button
              onClick={() => {
                setResourceValue(null);
                setUploadingFiles([]);
                const chatInParam = [
                  ...extendedChatInParams,
                  {
                    param_type: 'resource',
                    param_value: '',
                    sub_type: resourceConfig?.sub_type,
                  },
                ];
                setChatInParams(chatInParam);
              }}
              className="text-xs text-gray-500 hover:text-red-500 transition-colors flex items-center gap-1 px-2 py-1 rounded-full hover:bg-red-50"
            >
              <CloseOutlined className="text-xs" />
              {t('clear_all', '全部清除')}
            </button>
          </div>
        )}
        
        {/* 文件列表 - 统一使用大正方形卡片风格 */}
        <div className="flex flex-wrap gap-3">
          {/* 上传中的文件 */}
          {uploadingFiles.map((uploadingFile) => {
            const fileName = uploadingFile.file.name;
            const theme = getFileTypeTheme(fileName);
            const FileIcon = getFileIcon(fileName);
            const isImage = uploadingFile.file.type.startsWith('image/');
            const isError = uploadingFile.status === 'error';
            
            return (
              <div
                key={uploadingFile.id}
                className="relative group"
              >
                {/* 正方形卡片 */}
                <div className={`w-[60px] h-[60px] rounded-lg border-2 overflow-hidden bg-white dark:bg-gray-800 shadow-sm ${isError ? 'border-red-300' : theme.border} relative`}>
                  {isImage ? (
                    <img 
                      src={URL.createObjectURL(uploadingFile.file)} 
                      alt={fileName}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className={`w-full h-full flex items-center justify-center ${theme.bg}`}>
                      <FileIcon className={`${theme.icon} text-xl`} />
                    </div>
                  )}
                  
                  {/* 上传中遮罩 */}
                  {uploadingFile.status === 'uploading' && (
                    <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                      <LoadingOutlined className="text-white text-lg" spin />
                    </div>
                  )}
                  
                  {/* 错误遮罩 */}
                  {isError && (
                    <div className="absolute inset-0 bg-red-500/80 flex flex-col items-center justify-center cursor-pointer"
                      onClick={() => {
                        // 重试上传
                        setUploadingFiles(prev => prev.filter(f => f.id !== uploadingFile.id));
                        handleFileUpload(uploadingFile.file);
                      }}
                    >
                      <CloseOutlined className="text-white text-lg mb-1" />
                      <span className="text-white text-[10px]">{t('retry', '重试')}</span>
                    </div>
                  )}
                </div>
                {/* 文件名 */}
                <div className="mt-1 max-w-[60px]">
                  <p className={`text-xs truncate ${isError ? 'text-red-500' : 'text-gray-600 dark:text-gray-400'}`}>
                    {fileName}
                  </p>
                </div>
                {/* 删除按钮 */}
                <button
                  onClick={() => handleDeleteUploading(uploadingFile.id)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 shadow hover:bg-red-50 hover:border-red-300 hover:text-red-500"
                >
                  <CloseOutlined className="text-[10px]" />
                </button>
              </div>
            );
          })}
          
          {/* 已上传的文件 */}
          {resources.map((item: ParsedResourceItem, index: number) => {
            // 提取文件名和URL
            let fileName = 'File';
            let fileUrl = '';
            let previewUrl = '';
            let isImage = false;
            
            // 先判断类型
            if (item.type === 'image_url' && item.image_url) {
              fileName = item.image_url.file_name || 'Image';
              fileUrl = item.image_url.url || '';
              // 优先使用 preview_url，否则转换 file_url
              previewUrl = item.image_url.preview_url || transformFileUrl(fileUrl);
              isImage = true;
            } else if (item.type === 'file_url' && item.file_url) {
              fileName = item.file_url.file_name || 'File';
              fileUrl = item.file_url.url || '';
              previewUrl = item.file_url.preview_url || transformFileUrl(fileUrl);
            } else if (item.type === 'audio_url' && item.audio_url) {
              fileName = item.audio_url.file_name || 'Audio';
              fileUrl = item.audio_url.url || '';
              previewUrl = item.audio_url.preview_url || transformFileUrl(fileUrl);
            } else if (item.type === 'video_url' && item.video_url) {
              fileName = item.video_url.file_name || 'Video';
              fileUrl = item.video_url.url || '';
              previewUrl = item.video_url.preview_url || transformFileUrl(fileUrl);
            } else if (item.file_name) {
              // 兼容旧格式
              fileName = item.file_name;
              fileUrl = item.file_path || item.url || '';
              previewUrl = item.preview_url || transformFileUrl(fileUrl);
              isImage = /\.(jpg|jpeg|png|gif|bmp|webp|svg)$/i.test(fileName);
            }
            
            const theme = getFileTypeTheme(fileName);
            const FileIcon = getFileIcon(fileName);
            
            return (
              <div
                key={`file-${index}`}
                className="relative group"
              >
                {/* 正方形卡片 - 图片显示预览，文件显示大图标 */}
                <div className={`w-[60px] h-[60px] rounded-lg border-2 overflow-hidden bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-all duration-200 ${theme.border}`}>
                  {isImage && previewUrl ? (
                    <img 
                      src={previewUrl} 
                      alt={fileName}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        console.error('Image load error:', previewUrl);
                        const target = e.target as HTMLImageElement;
                        target.onerror = null;
                        target.style.display = 'none';
                        if (target.parentElement) {
                          target.parentElement.innerHTML = `<div class="w-full h-full flex items-center justify-center ${theme.bg}"><span class="text-xl">📷</span></div>`;
                        }
                      }}
                    />
                  ) : (
                    <div className={`w-full h-full flex items-center justify-center ${theme.bg}`}>
                      <FileIcon className={`${theme.icon} text-xl`} />
                    </div>
                  )}
                </div>
                {/* 文件名 */}
                <div className="mt-1 max-w-[60px]">
                  <p className="text-xs text-gray-600 dark:text-gray-400 truncate">
                    {fileName}
                  </p>
                </div>
                {/* 删除按钮 */}
                <button
                  onClick={() => handleDelete(index)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 shadow hover:bg-red-50 hover:border-red-300 hover:text-red-500"
                >
                  <CloseOutlined className="text-[10px]" />
                </button>
              </div>
            );
          })}
        </div>
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

  // 已选资源展示（数据源、知识库、MCP）
  const SelectedResourcesDisplay = () => {
    const hasResources = selectedDataSources.length > 0 || selectedKnowledgeBases.length > 0 || selectedMcps.length > 0;
    if (!hasResources) return null;

    return (
      <div className="flex flex-wrap gap-2 mb-3 px-4 pt-1">
        {/* 数据源标签 */}
        {selectedDataSources.map((ds: any) => (
          <div
            key={ds.id}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/20 text-sm"
          >
            <DatabaseOutlined className="text-green-500 text-xs" />
            <span className="text-gray-700 dark:text-gray-300 truncate max-w-[120px]">{ds.db_name}</span>
            <button
              onClick={() => setSelectedDataSources(prev => prev.filter(s => s.id !== ds.id))}
              className="ml-1 text-gray-400 hover:text-red-500 transition-colors"
            >
              <CloseOutlined className="text-xs" />
            </button>
          </div>
        ))}
        {/* 知识库标签 */}
        {selectedKnowledgeBases.map((kb: any) => (
          <div
            key={kb.id || kb.name}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/20 text-sm"
          >
            <BookOutlined className="text-amber-500 text-xs" />
            <span className="text-gray-700 dark:text-gray-300 truncate max-w-[120px]">{kb.name}</span>
            <button
              onClick={() => setSelectedKnowledgeBases(prev => prev.filter(s => (s.id || s.name) !== (kb.id || kb.name)))}
              className="ml-1 text-gray-400 hover:text-red-500 transition-colors"
            >
              <CloseOutlined className="text-xs" />
            </button>
          </div>
        ))}
        {/* MCP标签 */}
        {selectedMcps.map((mcp: any) => {
          const mcpId = mcp.id || mcp.uuid || mcp.name;
          return (
            <div
              key={mcpId}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-900/20 text-sm"
            >
              <ApiOutlined className="text-emerald-500 text-xs" />
              <span className="text-gray-700 dark:text-gray-300 truncate max-w-[120px]">{mcp.name}</span>
              <button
                onClick={() => setSelectedMcps(prev => prev.filter(m => (m.id || m.uuid || m.name) !== mcpId))}
                className="ml-1 text-gray-400 hover:text-red-500 transition-colors"
              >
                <CloseOutlined className="text-xs" />
              </button>
            </div>
          );
        })}
      </div>
    );
  };

  // 拖拽上传处理 - 支持多文件
  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      // 上传所有文件
      for (const file of files) {
        await handleFileUpload(file);
      }
    }
  }, [handleFileUpload]);

  // 粘贴上传处理 - 支持多文件
  const handlePaste = useCallback(async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;

    if (items) {
      const files: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) {
            files.push(file);
          }
        }
      }
      
      if (files.length > 0) {
        e.preventDefault();
        // 批量上传
        for (const file of files) {
          await handleFileUpload(file);
        }
      }
    }
  }, [handleFileUpload]);

  const onSubmit = async () => {
    // 检查是否有输入内容或上传的文件
    const resources = resourceValue ? parseResourceValue(resourceValue) || [] : [];
    const hasContent = userInput.trim() || resources.length > 0;
    
    if (!hasContent) return;

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
    
    if (MEDIA_RESOURCE_TYPES.includes(currentResourceConfig?.sub_type ?? '') || resources.length > 0) {
      const messages: (ParsedResourceItem | { type: string; text: string })[] = [...resources];
      if (userInput.trim()) {
        messages.push({ type: 'text', text: userInput });
      }
      newUserInput = { role: 'user', content: messages };
    } else {
      newUserInput = userInput;
    }

    // Inject dynamically selected datasources and knowledge bases into chat_in_params
    // Only pass non-default (dynamically added) resources; defaults are already in app config
    const dynamicResourceParams: ChatInParamItem[] = [];
    for (const ds of selectedDataSources) {
      if ((ds as any)._isDefault) continue;
      dynamicResourceParams.push({
        param_type: 'resource',
        param_value: JSON.stringify({ db_name: ds.db_name, db_type: ds.db_type, id: ds.id }),
        sub_type: 'database',
      });
    }
    for (const kb of selectedKnowledgeBases) {
      if ((kb as any)._isDefault) continue;
      dynamicResourceParams.push({
        param_type: 'resource',
        param_value: JSON.stringify({ name: kb.name, id: kb.id }),
        sub_type: 'knowledge',
      });
    }
    const currentChatInParams = [...chatInParams, ...dynamicResourceParams];

    setUserInput('');
    setResourceValue(null);
    setChatInParams(chatInParams.filter((i: ChatInParamItem) =>
      i.param_type !== 'resource' ||
      i.sub_type === 'skill(derisk)' ||
      i.sub_type === 'mcp(derisk)'
    ));

    await handleChat(newUserInput, {
      app_code: appInfo.app_code || '',
      ...(currentChatInParams?.length && { chat_in_params: currentChatInParams }),
    });

    if (submitCountRef.current === 1) {
      refreshDialogList && (await refreshDialogList());
    }
  };

  // 浮动操作按钮
  const handleStop = () => {
    if (!canAbort) return;
    const sessionId = context.currentConvSessionId || context.currentDialogue?.conv_uid || '';
    if (sessionId) {
      stopChat({ conv_session_id: sessionId });
    }
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
        ...(chatInParams?.length && { chat_in_params: chatInParams }),
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
    await apiInterceptors(clearChatHistory(context.currentDialogue?.conv_uid || '')).finally(async () => {
      await refreshHistory();
    });
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
              disabled={history.length === 0}
              className={classNames(
                'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                history.length > 0
                  ? 'hover:bg-orange-50 text-gray-600 hover:text-orange-500 cursor-pointer'
                  : 'text-gray-300 cursor-not-allowed'
              )}
            >
              <ClearOutlined className="text-lg" />
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

        {/* 已选资源预览 - 数据源、知识库、MCP */}
        <SelectedResourcesDisplay />

        {/* 已选资源预览 - 统一展示上传的文件 */}
        <ResourceItemsDisplay />

        {/* 文本输入区 */}
        <div className="p-4">
          <Input.TextArea
            placeholder={t('input_tips', '输入消息...')}
            className="!text-base !bg-transparent !border-0 !resize-none placeholder:!text-gray-400 !text-gray-800 dark:!text-gray-200 !shadow-none !p-0 !min-h-[60px]"
            autoSize={{ minRows: 2, maxRows: 8 }}
            value={userInput}
            onChange={(e) => {
              setUserInput(e.target.value);
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
                const resources = resourceValue ? parseResourceValue(resourceValue) || [] : [];
                const hasContent = userInput.trim() || resources.length > 0;
                if (!hasContent || replyLoading) return;
                onSubmit();
              }
            }}
          />
        </div>

        {/* 底部工具栏 */}
        <div className="flex items-center justify-between gap-2 px-3 pb-3 min-w-0">
          {/* 左侧工具区 */}
          <div className="flex items-center gap-2 min-w-0 flex-shrink overflow-visible">
            {/* "+" 按钮 - 文件上传/数据源/知识库 */}
            <Popover
              content={plusMenuContent}
              trigger="click"
              placement="topLeft"
              open={isPlusMenuOpen}
              onOpenChange={(open) => {
                setIsPlusMenuOpen(open);
                if (!open) { setPlusMenuView('main'); setDbSearch(''); setKbSearch(''); }
              }}
              arrow={false}
              overlayClassName="[&_.ant-popover-inner]:!p-0 [&_.ant-popover-inner]:!rounded-xl [&_.ant-popover-inner]:!shadow-xl"
            >
              <Badge count={selectedDataSources.length + selectedKnowledgeBases.length} size="small" offset={[-4, 4]} color="#16a34a">
                <button className="h-8 w-8 rounded-full flex items-center justify-center border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:text-indigo-500 hover:border-indigo-300 dark:hover:border-indigo-600 transition-all hover:bg-indigo-50 dark:hover:bg-indigo-900/20 flex-shrink-0">
                  <PlusOutlined className="text-sm" />
                </button>
              </Badge>
            </Popover>

            {/* 闪电按钮 - Skills/MCP 选择 */}
            <Popover
              content={lightningContent}
              trigger="click"
              placement="topLeft"
              open={isLightningOpen}
              onOpenChange={(open) => { setIsLightningOpen(open); if (!open) setLightningSearch(''); }}
              arrow={false}
              overlayClassName="[&_.ant-popover-inner]:!p-0 [&_.ant-popover-inner]:!rounded-xl [&_.ant-popover-inner]:!shadow-xl"
            >
              <Badge count={lightningBadgeCount} size="small" offset={[-4, 4]} color="#7c3aed">
                <button className="h-8 w-8 rounded-full flex items-center justify-center bg-purple-50 dark:bg-purple-900/30 border border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/50 hover:border-purple-400 transition-all flex-shrink-0">
                  <ThunderboltOutlined className="text-sm" />
                </button>
              </Badge>
            </Popover>

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
          </div>

          {/* 右侧：发送按钮 */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Button
              type="primary"
              shape="circle"
              className={classNames(
                'w-9 h-9 flex items-center justify-center transition-all !border-0 flex-shrink-0',
                (userInput.trim() || (resourceValue && parseResourceValue(resourceValue)?.length > 0))
                  ? 'bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-600 hover:to-indigo-700 shadow-md hover:shadow-lg'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
              )}
              onClick={onSubmit}
              disabled={(!userInput.trim() && !(resourceValue && parseResourceValue(resourceValue)?.length > 0)) || replyLoading}
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

      {/* Connectors 弹窗 - 管理技能/MCP */}
      <ConnectorsModal
        open={isConnectorsModalOpen}
        onCancel={() => setIsConnectorsModalOpen(false)}
        defaultTab="skill"
        selectedSkills={selectedSkills}
        onSkillsChange={setSelectedSkills}
        selectedMcps={selectedMcps}
        onMcpsChange={setSelectedMcps}
      />
    </div>
  );
};

export default UnifiedChatInput;
