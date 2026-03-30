'use client';
import { apiInterceptors, getAppList, getAppInfo, getModelList, newDialogue, postChatModeParamsFileLoad, getSkillList, getToolList, getMCPList } from '@/client/api';
import { STORAGE_INIT_MESSAGE_KET } from '@/utils/constants/storage';
import { transformFileUrl } from '@/utils';
import { getFileIcon, formatFileSize } from '@/utils/fileUtils';
import {
  ArrowUpOutlined,
  BulbOutlined,
  CodeOutlined,
  DesktopOutlined,
  DownOutlined,
  FileTextOutlined,
  FundProjectionScreenOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ToolOutlined,
  ApiOutlined,
  SearchOutlined,
  CheckOutlined,
  SettingOutlined,
  RightOutlined,
  HeartOutlined,
  CloudServerOutlined,
  SwapOutlined,
  DatabaseOutlined,
  AlertOutlined,
  DollarOutlined,
  GlobalOutlined,
  DashboardOutlined,
  RobotOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
  CloseOutlined,
  FolderAddOutlined
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import {
  Badge,
  Dropdown,
  Input,
  MenuProps,
  Popover,
  Typography,
  Upload,
  UploadProps,
  List,
  Space,
  Collapse,
  theme
} from 'antd';
import ModelIcon from '@/components/icons/model-icon';
import cls from 'classnames';
import { useRouter } from 'next/navigation';
import { useEffect, useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ConnectorsModal } from '@/components/chat/connectors-modal';
import { InteractionHandler } from '@/components/interaction';
import { IApp } from '@/types/app';
import { IModelData } from '@/types/model';

const { Title, Text } = Typography;
const { Panel } = Collapse;

// 文件类型颜色主题
const getFileTypeTheme = (fileName: string) => {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  const themes: Record<string, { bg: string; border: string; icon: string }> = {
    jpg: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
    jpeg: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
    png: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
    gif: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
    webp: { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
    pdf: { bg: 'bg-red-50', border: 'border-red-200', icon: 'text-red-500' },
    doc: { bg: 'bg-blue-50', border: 'border-blue-200', icon: 'text-blue-500' },
    docx: { bg: 'bg-blue-50', border: 'border-blue-200', icon: 'text-blue-500' },
    xls: { bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-500' },
    xlsx: { bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-500' },
    csv: { bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-500' },
    ppt: { bg: 'bg-orange-50', border: 'border-orange-200', icon: 'text-orange-500' },
    pptx: { bg: 'bg-orange-50', border: 'border-orange-200', icon: 'text-orange-500' },
    js: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
    ts: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
    py: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
    java: { bg: 'bg-cyan-50', border: 'border-cyan-200', icon: 'text-cyan-500' },
    md: { bg: 'bg-gray-50', border: 'border-gray-200', icon: 'text-gray-500' },
    mp4: { bg: 'bg-pink-50', border: 'border-pink-200', icon: 'text-pink-500' },
    mov: { bg: 'bg-pink-50', border: 'border-pink-200', icon: 'text-pink-500' },
    mp3: { bg: 'bg-yellow-50', border: 'border-yellow-200', icon: 'text-yellow-600' },
    wav: { bg: 'bg-yellow-50', border: 'border-yellow-200', icon: 'text-yellow-600' },
    zip: { bg: 'bg-indigo-50', border: 'border-indigo-200', icon: 'text-indigo-500' },
    rar: { bg: 'bg-indigo-50', border: 'border-indigo-200', icon: 'text-indigo-500' },
    '7z': { bg: 'bg-indigo-50', border: 'border-indigo-200', icon: 'text-indigo-500' },
  };
  return themes[ext] || { bg: 'bg-gray-50', border: 'border-gray-200', icon: 'text-gray-500' };
};

// 已上传资源显示组件
const UploadedResourcePreview = ({ resource, onRemove }: { resource: any; onRemove: () => void }) => {
  const theme = getFileTypeTheme(resource.file_name || resource.image_url?.file_name || resource.file_url?.file_name || '');
  const FileIcon = getFileIcon(resource.file_name || resource.image_url?.file_name || resource.file_url?.file_name || '');
  
  let fileName = 'File';
  let previewUrl = '';
  let isImage = false;
  
  if (resource.type === 'image_url' && resource.image_url) {
    fileName = resource.image_url.file_name || 'Image';
    previewUrl = resource.image_url.preview_url || resource.image_url.url;
    isImage = true;
  } else if (resource.type === 'file_url' && resource.file_url) {
    fileName = resource.file_url.file_name || 'File';
    previewUrl = resource.file_url.preview_url || resource.file_url.url;
  } else if (resource.type === 'audio_url' && resource.audio_url) {
    fileName = resource.audio_url.file_name || 'Audio';
    previewUrl = resource.audio_url.preview_url || resource.audio_url.url;
  } else if (resource.type === 'video_url' && resource.video_url) {
    fileName = resource.video_url.file_name || 'Video';
    previewUrl = resource.video_url.preview_url || resource.video_url.url;
  }
  
  return (
    <div className="relative group">
      <div className={`w-[60px] h-[60px] rounded-lg border-2 overflow-hidden bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-all duration-200 ${theme.border}`}>
        {isImage && previewUrl ? (
          <img src={previewUrl} alt={fileName} className="w-full h-full object-cover" />
        ) : (
          <div className={`w-full h-full flex items-center justify-center ${theme.bg}`}>
            <FileIcon className={`${theme.icon} text-xl`} />
          </div>
        )}
      </div>
      <div className="mt-1 max-w-[60px]">
        <p className="text-xs text-gray-600 dark:text-gray-400 truncate">{fileName}</p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 shadow hover:bg-red-50 hover:border-red-300 hover:text-red-500"
      >
        <CloseOutlined className="text-[10px]" />
      </button>
    </div>
  );
};

// 上传中文件显示组件
const UploadingFilePreview = ({ uploadingFile, onRetry, onRemove }: { uploadingFile: { id: string; file: File; status: string }; onRetry: () => void; onRemove: () => void }) => {
  const theme = getFileTypeTheme(uploadingFile.file.name);
  const FileIcon = getFileIcon(uploadingFile.file.name, uploadingFile.file.type);
  const isImage = uploadingFile.file.type.startsWith('image/');
  const isError = uploadingFile.status === 'error';
  
  return (
    <div className="relative group">
      <div className={`w-[60px] h-[60px] rounded-lg border-2 overflow-hidden bg-white dark:bg-gray-800 shadow-sm ${isError ? 'border-red-300' : theme.border} relative`}>
        {isImage ? (
          <img src={URL.createObjectURL(uploadingFile.file)} alt={uploadingFile.file.name} className="w-full h-full object-cover" />
        ) : (
          <div className={`w-full h-full flex items-center justify-center ${theme.bg}`}>
            <FileIcon className={`${theme.icon} text-xl`} />
          </div>
        )}
        {uploadingFile.status === 'uploading' && (
          <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {isError && (
          <div className="absolute inset-0 bg-red-500/80 flex flex-col items-center justify-center cursor-pointer" onClick={onRetry}>
            <CloseOutlined className="text-white text-lg mb-1" />
            <span className="text-white text-[10px]">重试</span>
          </div>
        )}
      </div>
      <div className="mt-1 max-w-[60px]">
        <p className={`text-xs truncate ${isError ? 'text-red-500' : 'text-gray-600 dark:text-gray-400'}`}>
          {uploadingFile.file.name}
        </p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 shadow hover:bg-red-50 hover:border-red-300 hover:text-red-500"
      >
        <CloseOutlined className="text-[10px]" />
      </button>
    </div>
  );
};

// 文件列表显示组件
const FileListDisplay = ({ 
  uploadingFiles, 
  uploadedResources, 
  onRemoveUploading, 
  onRemoveResource, 
  onRetryUploading,
  onClearAll 
}: { 
  uploadingFiles: { id: string; file: File; status: string }[];
  uploadedResources: any[];
  onRemoveUploading: (id: string) => void;
  onRemoveResource: (index: number) => void;
  onRetryUploading: (id: string) => void;
  onClearAll: () => void;
}) => {
  const totalCount = uploadingFiles.length + uploadedResources.length;
  if (totalCount === 0) return null;

  return (
    <div className="pb-3">
      {totalCount > 1 && (
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-indigo-100 flex items-center justify-center">
              <FolderAddOutlined className="text-indigo-600 text-xs" />
            </div>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              已上传文件
              <span className="ml-1 text-xs text-gray-500">({totalCount})</span>
            </span>
          </div>
          <button
            onClick={onClearAll}
            className="text-xs text-gray-500 hover:text-red-500 transition-colors flex items-center gap-1 px-2 py-1 rounded-full hover:bg-red-50"
          >
            <CloseOutlined className="text-xs" />
            全部清除
          </button>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        {uploadingFiles.map((uf) => (
          <UploadingFilePreview 
            key={uf.id} 
            uploadingFile={uf} 
            onRetry={() => onRetryUploading(uf.id)}
            onRemove={() => onRemoveUploading(uf.id)} 
          />
        ))}
        {uploadedResources.map((resource, index) => (
          <UploadedResourcePreview 
            key={`resource-${index}`} 
            resource={resource} 
            onRemove={() => onRemoveResource(index)} 
          />
        ))}
      </div>
    </div>
  );
};

export default function HomeChat() {
  const router = useRouter();
  const { t } = useTranslation();
  const [userInput, setUserInput] = useState<string>('');
  const [isFocus, setIsFocus] = useState<boolean>(false);
  const [uploadingFiles, setUploadingFiles] = useState<{ id: string; file: File; status: 'uploading' | 'success' | 'error' }[]>([]);
  const [uploadedResources, setUploadedResources] = useState<any[]>([]);
  const [pendingConvUid, setPendingConvUid] = useState<string>('');
  const [isConnectorsModalOpen, setIsConnectorsModalOpen] = useState(false);
  const [connectorsModalTab, setConnectorsModalTab] = useState<'mcp' | 'local' | 'skill'>('skill');
  const [selectedSkills, setSelectedSkills] = useState<any[]>([]);
  const [selectedMcps, setSelectedMcps] = useState<any[]>([]);
  const [selectedApp, setSelectedApp] = useState<IApp | null>(null);
  const [appList, setAppList] = useState<IApp[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [modelList, setModelList] = useState<IModelData[]>([]);
  const [modelSearch, setModelSearch] = useState('');
  const [isModelOpen, setIsModelOpen] = useState(false);
  const [selectedConnectors, setSelectedConnectors] = useState<any[]>([]);
  const { token } = theme.useToken();
const [appDetail, setAppDetail] = useState<IApp | null>(null);
  const [recommendedSkills, setRecommendedSkills] = useState<any[]>([]);
  const [recommendedTools, setRecommendedTools] = useState<any[]>([]);
const [recommendedMcps, setRecommendedMcps] = useState<any[]>([]);

  // Compact skill chip - same size as + button
  const SkillChip = ({ skill, onRemove }: { skill: any; onRemove: () => void }) => {
    const [showDelete, setShowDelete] = useState(false);
    
    return (
      <Popover
        content={
          <div className="w-[200px] p-2">
            <div className="font-medium text-sm mb-1 truncate">{skill.name}</div>
            {skill.description && (
              <div className="text-xs text-gray-500 mb-2 line-clamp-2">{skill.description}</div>
            )}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[10px] text-gray-400">
                {skill.author && <span>{skill.author}</span>}
                {skill.version && <span>v{skill.version}</span>}
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove();
                }}
                className="text-xs text-red-400 hover:text-red-500"
              >
                移除
              </button>
            </div>
          </div>
        }
        placement="top"
        trigger="hover"
        mouseEnterDelay={0.2}
      >
        <div
          className={cls(
            "h-7 w-7 rounded-full flex items-center justify-center cursor-pointer transition-all duration-200",
            "border shadow-sm flex-shrink-0",
            showDelete
              ? "bg-red-500 border-red-600 shadow-red-200"
              : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-blue-100"
          )}
          onMouseEnter={() => setShowDelete(true)}
          onMouseLeave={() => setShowDelete(false)}
          onClick={(e) => {
            e.stopPropagation();
            if (showDelete) onRemove();
          }}
        >
          {showDelete ? (
            <svg className="w-3.5 h-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          ) : skill.icon ? (
            <img src={skill.icon} alt={skill.name} className="w-4 h-4 rounded-full object-cover" />
          ) : (
            <div className="w-4 h-4 rounded-full bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center">
              <span className="text-white text-[9px] font-bold">
                {skill.name?.charAt(0)?.toUpperCase() || 'S'}
              </span>
            </div>
          )}
        </div>
      </Popover>
    );
  };

  // Compact MCP chip - same size as + button
  const McpChip = ({ mcp, onRemove }: { mcp: any; onRemove: () => void }) => {
    const [showDelete, setShowDelete] = useState(false);
    const mcpId = mcp.id || mcp.uuid || mcp.name;
    
    return (
      <Popover
        content={
          <div className="w-[200px] p-2">
            <div className="font-medium text-sm mb-1 truncate">{mcp.name}</div>
            {mcp.description && (
              <div className="text-xs text-gray-500 mb-2 line-clamp-2">{mcp.description}</div>
            )}
            <div className="flex items-center justify-end">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove();
                }}
                className="text-xs text-red-400 hover:text-red-500"
              >
                移除
              </button>
            </div>
          </div>
        }
        placement="top"
        trigger="hover"
        mouseEnterDelay={0.2}
      >
        <div
          className={cls(
            "h-7 w-7 rounded-full flex items-center justify-center cursor-pointer transition-all duration-200",
            "border shadow-sm flex-shrink-0",
            showDelete
              ? "bg-red-500 border-red-600 shadow-red-200"
              : "bg-white dark:bg-gray-800 border-green-400 dark:border-green-600 hover:border-green-500 dark:hover:border-green-500 hover:shadow-green-100"
          )}
          onMouseEnter={() => setShowDelete(true)}
          onMouseLeave={() => setShowDelete(false)}
          onClick={(e) => {
            e.stopPropagation();
            if (showDelete) onRemove();
          }}
        >
          {showDelete ? (
            <svg className="w-3.5 h-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          ) : mcp.icon ? (
            <img src={mcp.icon} alt={mcp.name} className="w-4 h-4 rounded-full object-cover" />
          ) : (
            <div className="w-4 h-4 rounded-full bg-gradient-to-br from-green-400 to-emerald-500 flex items-center justify-center">
              <ApiOutlined className="text-white text-[9px]" />
            </div>
          )}
        </div>
      </Popover>
    );
  };

  // Selected skills container - horizontal chips
  const SelectedSkillsBar = () => {
    if (selectedSkills.length === 0) return null;
    
    return (
      <div className="flex items-center gap-1.5">
        {selectedSkills.slice(0, 3).map((skill) => (
          <SkillChip
            key={skill.skill_code}
            skill={skill}
            onRemove={() => handleSkillRemove(skill.skill_code)}
          />
        ))}
        {selectedSkills.length > 3 && (
          <Popover
            content={
              <div className="w-[200px] max-h-[200px] overflow-y-auto">
                <div className="text-xs text-gray-500 mb-2">已选择 {selectedSkills.length} 个技能</div>
                {selectedSkills.slice(3).map((skill) => (
                  <div key={skill.skill_code} className="flex items-center justify-between py-1">
                    <span className="text-sm text-gray-700 dark:text-gray-200 truncate">{skill.name}</span>
                    <button
                      onClick={() => handleSkillRemove(skill.skill_code)}
                      className="text-xs text-red-400 hover:text-red-500"
                    >
                      移除
                    </button>
                  </div>
                ))}
              </div>
            }
            placement="top"
            trigger="hover"
          >
            <div className="h-7 w-7 rounded-full bg-gray-100 dark:bg-gray-700 border border-dashed border-gray-300 dark:border-gray-500 flex items-center justify-center cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">
              <span className="text-[10px] text-gray-500 dark:text-gray-400 font-medium">+{selectedSkills.length - 3}</span>
            </div>
          </Popover>
        )}
      </div>
    );
  };

  // Selected MCPs container - horizontal chips
  const SelectedMcpsBar = () => {
    if (selectedMcps.length === 0) return null;
    
    return (
      <div className="flex items-center gap-1.5">
        {selectedMcps.slice(0, 3).map((mcp: any) => {
          const mcpId = mcp.id || mcp.uuid || mcp.name;
          return (
            <McpChip
              key={mcpId}
              mcp={mcp}
              onRemove={() => setSelectedMcps(selectedMcps.filter((m: any) => (m.id || m.uuid || m.name) !== mcpId))}
            />
          );
        })}
        {selectedMcps.length > 3 && (
          <Popover
            content={
              <div className="w-[200px] max-h-[200px] overflow-y-auto">
                <div className="text-xs text-gray-500 mb-2">已选择 {selectedMcps.length} 个MCP服务</div>
                {selectedMcps.slice(3).map((mcp: any) => {
                  const mcpId = mcp.id || mcp.uuid || mcp.name;
                  return (
                    <div key={mcpId} className="flex items-center justify-between py-1">
                      <span className="text-sm text-gray-700 dark:text-gray-200 truncate">{mcp.name}</span>
                      <button
                        onClick={() => setSelectedMcps(selectedMcps.filter((m: any) => (m.id || m.uuid || m.name) !== mcpId))}
                        className="text-xs text-red-400 hover:text-red-500"
                      >
                        移除
                      </button>
                    </div>
                  );
                })}
              </div>
            }
            placement="top"
            trigger="hover"
          >
            <div className="h-7 w-7 rounded-full bg-gray-100 dark:bg-gray-700 border border-dashed border-gray-300 dark:border-gray-500 flex items-center justify-center cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">
              <span className="text-[10px] text-gray-500 dark:text-gray-400 font-medium">+{selectedMcps.length - 3}</span>
            </div>
          </Popover>
        )}
      </div>
    );
  };

  // Filter LLM models only and group by provider
  const groupedModels = useMemo(() => {
    const groups: Record<string, string[]> = {};
    const otherModels: string[] = [];

    const filtered = modelList.filter(model =>
      model.worker_type === 'llm' &&
      model.model_name.toLowerCase().includes(modelSearch.toLowerCase())
    );

    filtered.forEach(modelData => {
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

    Object.keys(groups).forEach(provider => {
      groups[provider].sort((a, b) => {
        if (a === selectedModel) return -1;
        if (b === selectedModel) return 1;
        return 0;
      });
    });

    otherModels.sort((a, b) => {
      if (a === selectedModel) return -1;
      if (b === selectedModel) return 1;
      return 0;
    });

    return { groups, otherModels };
  }, [modelList, modelSearch, selectedModel]);

  const collapseDefaultActiveKey = useMemo(() => 
    ['AgentLLM', ...Object.keys(groupedModels.groups)],
    [groupedModels.groups]
  );

  const modelContent = useMemo(() => (
    <div className="w-80 flex flex-col h-[400px]">
      <div className="p-3 border-b border-gray-100 dark:border-gray-700 flex items-center gap-2 flex-shrink-0">
        <Input 
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('search_model', 'Search Model')} 
          bordered={false}
          className="!bg-gray-50 dark:!bg-gray-800 rounded-md flex-1"
          value={modelSearch}
          onChange={e => setModelSearch(e.target.value)}
        />
        <button className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
          <PlusOutlined className="text-sm" />
        </button>
        <button className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
          <SettingOutlined className="text-sm" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {Object.entries(groupedModels.groups).length > 0 && (
          <Collapse
            ghost
            defaultActiveKey={collapseDefaultActiveKey}
            expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} className="text-xs text-gray-400" />}
            className="[&_.ant-collapse-header]:!p-2 [&_.ant-collapse-content-box]:!p-0"
          >
            {Object.entries(groupedModels.groups).map(([provider, models]) => (
              <Panel header={<span className="text-xs font-medium text-gray-500">{provider}</span>} key={provider}>
                {models.map(model => (
                  <div 
                    key={model}
                    className={cls(
                      "flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors mb-1",
                      selectedModel === model ? "bg-gray-50 dark:bg-gray-800" : ""
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
                    {selectedModel === model && <CheckOutlined className="text-blue-500 flex-shrink-0" />}
                  </div>
                ))}
              </Panel>
            ))}
          </Collapse>
        )}
        
        {groupedModels.otherModels.length > 0 && (
          <div className="mt-2">
            <div className="px-2 py-1 text-xs font-medium text-gray-500">{t('other_models', 'Other Models')}</div>
            {groupedModels.otherModels.map(model => (
              <div 
                key={model}
                className={cls(
                  "flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors mb-1",
                  selectedModel === model ? "bg-gray-50 dark:bg-gray-800" : ""
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
                {selectedModel === model && <CheckOutlined className="text-blue-500 flex-shrink-0" />}
              </div>
            ))}
          </div>
        )}

        {Object.keys(groupedModels.groups).length === 0 && groupedModels.otherModels.length === 0 && (
          <div className="px-3 py-8 text-center text-gray-400 text-xs">
            {t('no_models_found', 'No models found')}
          </div>
        )}
      </div>
    </div>
  ), [groupedModels, selectedModel, modelSearch, t]);

  // 从 URL 参数中获取 app_code
  // Use useEffect to access URL search params safely on client side
  useEffect(() => {
    // Basic way to get query params without using useSearchParams which might cause hydration issues
    const urlParams = new URLSearchParams(window.location.search);
    const appCode = urlParams.get('app_code');
    
    if (appCode && appList.length > 0) {
      const app = appList.find(a => a.app_code === appCode);
      if (app) {
        setSelectedApp(app);
      }
    }
  }, [appList]);

  const { run: fetchAppList } = useRequest(
    async () => {
      const [_, data] = await apiInterceptors(
        getAppList({
          page: 1,
          page_size: 100,
          published: true,
        }),
      );
      return data;
    },
    {
      onSuccess: (data) => {
        if (data?.app_list) {
          setAppList(data.app_list);
          const defaultApp =
            data.app_list.find((app) => app.app_code === 'chat_normal') || data.app_list[0];
          setSelectedApp(defaultApp);
        }
      },
    },
  );

  // Get recommended skills
  useRequest(
    async () => {
      const [_, data] = await apiInterceptors(getSkillList({ filter: '' }, { page: '1', page_size: '5' }));
      return data as any;
    },
    {
      onSuccess: (data: any) => {
        if (data?.items && Array.isArray(data.items)) {
          setRecommendedSkills(data.items.slice(0, 2));
        }
      },
    },
  );

  // Get recommended tools
  useRequest(
    async () => {
      const [_, data] = await apiInterceptors(getToolList('local'));
      return data as any;
    },
    {
      onSuccess: (data: any) => {
        if (Array.isArray(data) && data.length > 0) {
          setRecommendedTools(data.slice(0, 2));
        }
      },
    },
  );

  // Get recommended MCP servers
  useRequest(
    async () => {
      const [_, data] = await apiInterceptors(getMCPList({ filter: '' }, { page: '1', page_size: '5' }));
      return data as any;
    },
    {
      onSuccess: (data: any) => {
        if (data?.items && Array.isArray(data.items)) {
          setRecommendedMcps(data.items.slice(0, 2));
        }
      },
    },
  );

  // Get default model from app configuration
  const getDefaultModelFromApp = (app: IApp | null, llmModels: IModelData[]): string => {
    if (!app) return '';

    // Try to get model from app's llm_config
    const appConfigModel = app.llm_config?.llm_strategy_value?.[0];
    if (appConfigModel) {
      // Check if the configured model exists in available LLM models
      const modelExists = llmModels.some(m => m.model_name === appConfigModel && m.worker_type === 'llm');
      if (modelExists) return appConfigModel;
    }

    // Try to get model from app details
    const detailWithModel = app.details?.find(d => d.llm_strategy_value);
    if (detailWithModel?.llm_strategy_value) {
      const modelExists = llmModels.some(m => m.model_name === detailWithModel.llm_strategy_value && m.worker_type === 'llm');
      if (modelExists) return detailWithModel.llm_strategy_value;
    }

    // Try to get model from app layout configuration (model_value)
    const modelLayoutItem = app.layout?.chat_in_layout?.find(item => item.param_type === 'model');
    if (modelLayoutItem?.param_default_value) {
      const modelExists = llmModels.some(m => m.model_name === modelLayoutItem.param_default_value && m.worker_type === 'llm');
      if (modelExists) return modelLayoutItem.param_default_value;
    }

    return '';
  };

  useRequest(
    async () => {
      const [_, data] = await apiInterceptors(getModelList());
      return data || [];
    },
    {
      onSuccess: (models) => {
        if (models && models.length > 0) {
          // Filter only LLM models
          const llmModels = models.filter((m: IModelData) => m.worker_type === 'llm');
          setModelList(llmModels);

          // Default selection logic: prioritize app's configured model
          const appDefaultModel = getDefaultModelFromApp(appDetail, llmModels);
          if (appDefaultModel) {
            setSelectedModel(appDefaultModel);
          } else {
            // Fallback to gpt models or first available
            const modelNames = llmModels.map((m: IModelData) => m.model_name);
            const fallbackModel = modelNames.find((m: string) => m.includes('gpt-3.5') || m.includes('gpt-4')) || modelNames[0];
            setSelectedModel(fallbackModel);
          }
        }
      },
    },
  );

  // Fetch app detail when selectedApp changes
  useEffect(() => {
    if (selectedApp?.app_code) {
      const fetchAppDetail = async () => {
        const [_, data] = await apiInterceptors(getAppInfo({ app_code: selectedApp.app_code }));
        if (data) {
          setAppDetail(data);

          // Update default model based on app's configuration
          if (modelList.length > 0) {
            const llmModels = modelList.filter(m => m.worker_type === 'llm');
            const appDefaultModel = getDefaultModelFromApp(data, llmModels);
            if (appDefaultModel) {
              setSelectedModel(appDefaultModel);
            }
          }
        }
      };
      fetchAppDetail();
    }
}, [selectedApp?.app_code]);

  // Handle file upload - upload immediately after selection (same as unified-chat-input.tsx)
  const handleFileUpload = useCallback(async (file: File) => {
    const uploadId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    
    setUploadingFiles(prev => [...prev, { id: uploadId, file, status: 'uploading' }]);
    
    const appCode = selectedApp?.app_code || 'chat_normal';
    const currentModel = selectedModel || '';
    
    let convUid = pendingConvUid;
    
    if (!convUid) {
      const [, dialogueRes] = await apiInterceptors(
        newDialogue({ app_code: appCode, model: currentModel }),
      );
      if (dialogueRes) {
        convUid = dialogueRes.conv_uid;
        setPendingConvUid(convUid);
      }
    }
    
    if (!convUid) {
      setUploadingFiles(prev => prev.map(f => f.id === uploadId ? { ...f, status: 'error' } : f));
      return;
    }
    
    const formData = new FormData();
    formData.append('doc_files', file);
    
    const [uploadErr, uploadRes] = await apiInterceptors(
      postChatModeParamsFileLoad({
        convUid: convUid,
        chatMode: appCode,
        data: formData,
        model: currentModel,
        config: { timeout: 1000 * 60 * 60 },
      }),
    );
    
    if (uploadErr || !uploadRes) {
      console.error('File upload error:', uploadErr);
      setUploadingFiles(prev => prev.map(f => f.id === uploadId ? { ...f, status: 'error' } : f));
      return;
    }
    
    const isImage = file.type.startsWith('image/');
    const isAudio = file.type.startsWith('audio/');
    const isVideo = file.type.startsWith('video/');
    
    let fileUrl = '';
    let previewUrl = '';
    
    if (uploadRes.preview_url) {
      previewUrl = uploadRes.preview_url;
      fileUrl = uploadRes.file_path || previewUrl;
    } else if (uploadRes.file_path) {
      fileUrl = uploadRes.file_path;
      previewUrl = transformFileUrl(fileUrl);
    } else if (uploadRes.url || uploadRes.file_url) {
      fileUrl = uploadRes.url || uploadRes.file_url;
      previewUrl = fileUrl;
    } else if (uploadRes.path) {
      fileUrl = uploadRes.path;
      previewUrl = transformFileUrl(fileUrl);
    } else if (typeof uploadRes === 'string') {
      fileUrl = uploadRes;
      previewUrl = uploadRes;
    } else if (Array.isArray(uploadRes)) {
      const firstRes = uploadRes[0];
      previewUrl = firstRes?.preview_url || '';
      fileUrl = firstRes?.file_path || firstRes?.preview_url || previewUrl;
      if (!previewUrl && fileUrl) previewUrl = transformFileUrl(fileUrl);
    }
    
    let newResourceItem;
    if (isImage) {
      newResourceItem = { type: 'image_url', image_url: { url: fileUrl, preview_url: previewUrl || fileUrl, file_name: file.name } };
    } else if (isAudio) {
      newResourceItem = { type: 'audio_url', audio_url: { url: fileUrl, preview_url: previewUrl || fileUrl, file_name: file.name } };
    } else if (isVideo) {
      newResourceItem = { type: 'video_url', video_url: { url: fileUrl, preview_url: previewUrl || fileUrl, file_name: file.name } };
    } else {
      newResourceItem = { type: 'file_url', file_url: { url: fileUrl, preview_url: previewUrl || fileUrl, file_name: file.name } };
    }
    
    setUploadingFiles(prev => prev.filter(f => f.id !== uploadId));
    setUploadedResources(prev => [...prev, newResourceItem]);
  }, [pendingConvUid, selectedApp, selectedModel]);

  const onSubmit = async () => {
    if (!userInput.trim() && uploadedResources.length === 0 && uploadingFiles.length === 0) return;
    
    if (uploadingFiles.some(f => f.status === 'uploading')) {
      return;
    }
    
    const appCode = selectedApp?.app_code || 'chat_normal';
    let convUid = pendingConvUid;
    
    if (!convUid) {
      const [, res] = await apiInterceptors(
        newDialogue({ app_code: appCode, model: selectedModel }),
      );
      if (res) {
        convUid = res.conv_uid;
        setPendingConvUid(convUid);
      }
    }
    
    if (convUid) {
      localStorage.setItem(
        STORAGE_INIT_MESSAGE_KET,
        JSON.stringify({
          id: convUid,
          message: userInput,
          resources: uploadedResources.length > 0 ? uploadedResources : undefined,
          model: selectedModel, 
          skills: selectedSkills.length > 0 ? selectedSkills : undefined,
          mcps: selectedMcps.length > 0 ? selectedMcps : undefined,
        }),
      );
      router.push(`/chat/?app_code=${appCode}&conv_uid=${convUid}`);
    }
    setUserInput('');
    setUploadingFiles([]);
    setUploadedResources([]);
    setPendingConvUid('');
    setSelectedSkills([]);
    setSelectedMcps([]);
  };

  const uploadProps: UploadProps = {
    showUploadList: false,
    beforeUpload: (file) => {
      handleFileUpload(file);
      return false;
    },
  };

  const QuickActionButton = ({ 
    icon, 
    text, 
    bgColor = 'bg-gray-100',
    iconColor = 'text-gray-600',
    isOutline = false,
    onClick
  }: { 
    icon: React.ReactNode; 
    text: string;
    bgColor?: string;
    iconColor?: string;
    isOutline?: boolean;
    onClick?: () => void;
  }) => (
    <div className="flex flex-col items-center gap-2 cursor-pointer group" onClick={onClick}>
      <div className={cls(
        "w-14 h-14 rounded-full flex items-center justify-center transition-all duration-200 group-hover:scale-110 group-hover:shadow-lg",
        isOutline 
          ? "bg-white dark:bg-[#232734] border-2 border-dashed border-gray-300 dark:border-gray-600" 
          : bgColor
      )}>
        <span className={cls("text-xl", iconColor)}>{icon}</span>
      </div>
      <span className="text-xs text-gray-600 dark:text-gray-400 text-center max-w-[80px] leading-tight group-hover:text-gray-900 dark:group-hover:text-gray-200 transition-colors">
        {text}
      </span>
    </div>
  );

  const openConnectorsModal = (tab: 'mcp' | 'local' | 'skill') => {
    setConnectorsModalTab(tab);
    setIsConnectorsModalOpen(true);
  };

  const handleSkillsChange = useCallback((skills: any[]) => {
    setSelectedSkills(skills);
  }, []);

  const handleSkillRemove = useCallback((skillCode: string) => {
    setSelectedSkills(prev => prev.filter(s => s.skill_code !== skillCode));
  }, []);

  const appMenuProps: MenuProps = useMemo(() => ({
    items: appList.map((app) => ({
      key: app.app_code,
      label: (
        <div className="flex items-center gap-2" onClick={() => setSelectedApp(app)}>
          <span className="text-base">
            {app.icon ? <img src={app.icon} className="w-4 h-4" /> : '🤖'}
          </span>
          <span>{app.app_name}</span>
        </div>
      ),
    })),
  }), [appList]);

  const plusMenuContent = useMemo(() => (
    <div className="flex flex-col gap-1 w-52 p-1">
      {recommendedSkills.length > 0 && (
        <>
          <div className="px-3 py-2 text-xs text-gray-400 font-medium">推荐技能</div>
          {recommendedSkills.slice(0, 1).map((skill) => {
            const isSelected = selectedSkills.some(s => s.skill_code === skill.skill_code);
            return (
              <div
                key={skill.skill_code}
                className={cls(
                  "flex items-center justify-between gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors",
                  isSelected
                    ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300"
                    : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200"
                )}
                onClick={() => {
                  if (isSelected) {
                    handleSkillsChange(selectedSkills.filter(s => s.skill_code !== skill.skill_code));
                  } else {
                    handleSkillsChange([...selectedSkills, skill]);
                  }
                }}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  {skill.icon ? (
                    <img src={skill.icon} className="w-4 h-4 flex-shrink-0" />
                  ) : (
                    <span className={cls("text-sm font-semibold w-4 h-4 flex items-center justify-center flex-shrink-0", isSelected ? "text-blue-500" : "")}>{skill.name ? skill.name.charAt(0).toUpperCase() : 'S'}</span>
                  )}
                  <span className="text-sm truncate">{skill.name}</span>
                </div>
                {isSelected && <CheckOutlined className="text-blue-500 text-sm flex-shrink-0" />}
              </div>
            );
          })}
        </>
      )}

      {recommendedMcps.length > 0 && (
        <>
          <div className="px-3 py-2 text-xs text-gray-400 font-medium mt-1">推荐MCP服务</div>
          {recommendedMcps.slice(0, 1).map((mcp) => {
            const mcpId = mcp.id || mcp.uuid || mcp.name;
            const isSelected = selectedMcps.some((m: any) => (m.id || m.uuid || m.name) === mcpId);
            return (
              <div
                key={mcpId}
                className={cls(
                  "flex items-center justify-between gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors",
                  isSelected
                    ? "bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300"
                    : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200"
                )}
                onClick={() => {
                  if (isSelected) {
                    setSelectedMcps(selectedMcps.filter((m: any) => (m.id || m.uuid || m.name) !== mcpId));
                  } else {
                    setSelectedMcps([...selectedMcps, mcp]);
                  }
                }}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  {mcp.icon ? (
                    <img src={mcp.icon} className="w-4 h-4 flex-shrink-0" />
                  ) : (
                    <ApiOutlined className={cls("text-sm flex-shrink-0", isSelected ? "text-green-500" : "")} />
                  )}
                  <span className="text-sm truncate">{mcp.name}</span>
                </div>
                {isSelected && <CheckOutlined className="text-green-500 text-sm flex-shrink-0" />}
              </div>
            );
          })}
        </>
      )}

      {recommendedTools.length > 0 && (
        <>
          <div className="px-3 py-2 text-xs text-gray-400 font-medium mt-1">推荐工具</div>
          {recommendedTools.slice(0, 1).map((tool) => (
            <div
              key={tool.tool_id}
              className="flex items-center gap-3 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg cursor-pointer transition-colors text-gray-700 dark:text-gray-200"
              onClick={() => {
                openConnectorsModal('local');
              }}
            >
              <ToolOutlined className="text-lg" />
              <span className="text-sm truncate">{tool.tool_name}</span>
            </div>
          ))}
        </>
      )}

      <div className="h-[1px] bg-gray-100 dark:bg-gray-800 my-1 mx-2" />

      <div
        className="flex items-center gap-3 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg cursor-pointer transition-colors text-gray-700 dark:text-gray-200"
        onClick={() => openConnectorsModal('skill')}
      >
        <ApiOutlined className="text-lg" />
        <span className="text-sm">更多</span>
      </div>
    </div>
  ), [recommendedSkills, recommendedMcps, recommendedTools, selectedSkills, selectedMcps, handleSkillsChange]);

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    let hasFile = false;

    if (items) {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) {
            handleFileUpload(file);
            hasFile = true;
          }
        }
      }
    }

    if (hasFile) {
      e.preventDefault();
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsFocus(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      files.forEach(file => handleFileUpload(file));
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#FAFAFA] dark:bg-[#111] overflow-y-auto relative">
      <div className="flex justify-end items-center px-8 py-5 w-full absolute top-0 left-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white dark:bg-[#232734] flex items-center justify-center shadow-sm border border-gray-200/60 dark:border-gray-700/60 cursor-pointer hover:shadow-md hover:border-gray-300 dark:hover:border-gray-600 transition-all">
            <Badge dot offset={[-2, 2]}>
              <span className="text-lg">🔔</span>
            </Badge>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col items-center w-full max-w-5xl mx-auto px-4 pt-[12vh]">
        {/* Title */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-medium text-gray-900 dark:text-gray-100 tracking-tight mb-3">
            <span className="mr-2">🚀</span>
            You Command, We
            <span className="text-orange-500 ml-2">Defend.</span>
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-base">
            OpenDeRisk—AI原生风险智能系统，为每个应用系统提供一个7*24H的AI系统数字管家
          </p>
        </div>

        {/* Input Box Area */}
        <div
          className={cls(
            'w-full max-w-4xl bg-white dark:bg-[#232734] rounded-[24px] shadow-sm hover:shadow-md transition-all duration-300 border',
            isFocus
              ? 'border-blue-500/50 shadow-lg ring-4 ring-blue-500/5'
              : 'border-gray-200 dark:border-gray-800',
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
          <div className="p-4">
            {/* Selected Files Preview Area (Top of Input) */}
            <FileListDisplay
              uploadingFiles={uploadingFiles}
              uploadedResources={uploadedResources}
              onRemoveUploading={(id) => setUploadingFiles(prev => prev.filter(f => f.id !== id))}
              onRemoveResource={(index) => setUploadedResources(prev => prev.filter((_, i) => i !== index))}
              onRetryUploading={(id) => {
                const uf = uploadingFiles.find(f => f.id === id);
                if (uf) {
                  setUploadingFiles(prev => prev.filter(f => f.id !== id));
                  handleFileUpload(uf.file);
                }
              }}
              onClearAll={() => {
                setUploadingFiles([]);
                setUploadedResources([]);
              }}
            />

            <Input.TextArea
              placeholder="分配一个任务或提问任何问题"
              className="!text-lg !bg-transparent !border-0 !resize-none placeholder:!text-gray-400 !text-gray-800 dark:!text-gray-200 !shadow-none !p-2 mb-4"
              autoSize={{ minRows: 2, maxRows: 20 }}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onFocus={() => setIsFocus(true)}
              onBlur={() => setIsFocus(false)}
              onPaste={handlePaste}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  onSubmit();
                }
              }}
            />

              <div className="flex items-center justify-between px-2 pb-1">
                <div className="flex items-center gap-2">
                  {/* + Button for Skills/Tools */}
                  <Popover
                    content={plusMenuContent}
                    trigger="click"
                    placement="topLeft"
                    overlayClassName="!p-0"
                  >
                    <button className="h-7 w-7 rounded-full flex items-center justify-center border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-blue-500 hover:border-blue-300 dark:hover:border-blue-600 transition-all hover:bg-blue-50 dark:hover:bg-blue-900/20">
                      <PlusOutlined className="text-sm" />
                    </button>
                  </Popover>

                  {/* Selected Skills Display */}
                  <SelectedSkillsBar />

                  {/* Selected MCPs Display */}
                  <SelectedMcpsBar />

                  {/* Agent Selector */}
                  <Dropdown menu={appMenuProps} trigger={['click']} placement="bottomLeft">
                    <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800/50 px-3 py-1.5 rounded-full border border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                      <span className="text-base">
                        {selectedApp?.icon ? (
                          <img src={selectedApp.icon} className="w-4 h-4" />
                        ) : (
                          '🤖'
                        )}
                      </span>
                      <span className="text-sm text-gray-700 dark:text-gray-300 font-medium max-w-[100px] truncate">
                        {selectedApp?.app_name || t('select_app', 'Select App')}
                      </span>
                      <DownOutlined className="text-xs text-gray-400" />
                    </div>
                  </Dropdown>

                  {/* Spacer */}
                  <div className="w-4" />

                  {/* Model Selector */}
                  <Popover
                    content={modelContent}
                    trigger="click"
                    placement="topLeft"
                    open={isModelOpen}
                    onOpenChange={setIsModelOpen}
                    arrow={false}
                    overlayClassName="[&_.ant-popover-inner]:!p-0 [&_.ant-popover-inner]:!rounded-lg [&_.ant-popover-inner]:!shadow-lg"
                    zIndex={1000}
                  >
                    <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800/50 px-3 py-1.5 rounded-full border border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors group">
                      <ModelIcon model={selectedModel} width={18} height={18} />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-200 max-w-[120px] truncate group-hover:text-blue-500 transition-colors">
                        {selectedModel || t('select_model', 'Select Model')}
                      </span>
                      <DownOutlined className="text-xs text-gray-400 group-hover:text-blue-500 transition-colors" />
                    </div>
                  </Popover>
              </div>

              <div className="flex items-center gap-3">
                {/* File Upload Icon Button */}
                <Upload {...uploadProps} showUploadList={false}>
                  <button className="h-7 w-7 rounded-full flex items-center justify-center border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-all hover:bg-gray-100 dark:hover:bg-gray-800">
                    <PaperClipOutlined className="text-sm" />
                  </button>
                </Upload>

                <button
                  className={cls(
                    'h-8 w-8 rounded-full flex items-center justify-center transition-all',
                    userInput.trim() || uploadedResources.length > 0 || uploadingFiles.length > 0
                      ? 'bg-gradient-to-r from-blue-500 to-indigo-500 hover:from-blue-600 hover:to-indigo-600 text-white shadow-md hover:shadow-lg'
                      : 'bg-gray-100 text-gray-400 border-none dark:bg-gray-800 dark:text-gray-600',
                  )}
                  onClick={onSubmit}
                  disabled={!userInput.trim() && uploadedResources.length === 0 && uploadingFiles.length === 0}
                >
                  <ArrowUpOutlined className="text-sm" />
                </button>
              </div>
            </div>

            {/* Selected Files List (Removed old list) */}
          </div>
        </div>

        {/* Quick Actions - SRE Domain Scenarios */}
        <div className="flex flex-wrap justify-center gap-10 mt-10 max-w-4xl">
          <QuickActionButton 
            icon={<HeartOutlined />} 
            text="AI应用健康" 
            bgColor="bg-gradient-to-br from-blue-400 to-blue-500"
            iconColor="text-white"
          />
          <QuickActionButton 
            icon={<CodeOutlined />} 
            text="AI代码风险" 
            bgColor="bg-gradient-to-br from-orange-400 to-amber-500"
            iconColor="text-white"
          />
          <QuickActionButton 
            icon={<CloudServerOutlined />} 
            text="AI基础设施" 
            bgColor="bg-gradient-to-br from-red-400 to-red-500"
            iconColor="text-white"
          />
          <QuickActionButton 
            icon={<SwapOutlined />} 
            text="AI变更风险" 
            bgColor="bg-gradient-to-br from-emerald-400 to-green-500"
            iconColor="text-white"
          />
          <QuickActionButton 
            icon={<DatabaseOutlined />} 
            text="AI存储容量" 
            bgColor="bg-gradient-to-br from-teal-400 to-cyan-500"
            iconColor="text-white"
          />
          <QuickActionButton 
            icon={<AlertOutlined />} 
            text="AI应急风险" 
            bgColor="bg-gradient-to-br from-orange-500 to-red-500"
            iconColor="text-white"
          />
          <QuickActionButton 
            icon={<GlobalOutlined />} 
            text="AI环境风险" 
            bgColor="bg-gradient-to-br from-slate-400 to-gray-500"
            iconColor="text-white"
          />
          <QuickActionButton 
            icon={<RobotOutlined />} 
            text="自定义智能体" 
            isOutline={true}
            iconColor="text-gray-400 dark:text-gray-500"
            onClick={() => router.push('/application/app')}
          />
        </div>
      </div>

      <ConnectorsModal
        open={isConnectorsModalOpen}
        onCancel={() => setIsConnectorsModalOpen(false)}
        defaultTab={connectorsModalTab}
        selectedSkills={selectedSkills}
        onSkillsChange={handleSkillsChange}
        selectedMcps={selectedMcps}
        onMcpsChange={setSelectedMcps}
      />

      <InteractionHandler />
    </div>
  );
}
