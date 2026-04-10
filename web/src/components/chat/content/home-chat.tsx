'use client';
import { apiInterceptors, getAppList, getAppInfo, getModelList, newDialogue, postChatModeParamsFileLoad, getSkillList, getToolList, getMCPList, getDbList, getSpaceList } from '@/client/api';
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
  FolderAddOutlined,
  BookOutlined,
  UploadOutlined,
  LeftOutlined,
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
  Spin,
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

// 首页场景图标名称 → 组件映射
const HOME_SCENE_ICON_MAP: Record<string, React.ComponentType<any>> = {
  HeartOutlined,
  CodeOutlined,
  CloudServerOutlined,
  SwapOutlined,
  DatabaseOutlined,
  AlertOutlined,
  GlobalOutlined,
  SafetyOutlined,
  DashboardOutlined,
  ThunderboltOutlined,
  RobotOutlined,
};

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

  // "+" 按钮相关
  const [isPlusMenuOpen, setIsPlusMenuOpen] = useState(false);
  const [plusMenuView, setPlusMenuView] = useState<'main' | 'datasource' | 'knowledge'>('main');
  const [dbList, setDbList] = useState<any[]>([]);
  const [dbLoading, setDbLoading] = useState(false);
  const [spaceListData, setSpaceListData] = useState<any[]>([]);
  const [spaceLoading, setSpaceLoading] = useState(false);
  const [selectedDataSources, setSelectedDataSources] = useState<any[]>([]);
  const [selectedKnowledgeBases, setSelectedKnowledgeBases] = useState<any[]>([]);
  const [dbSearch, setDbSearch] = useState('');
  const [kbSearch, setKbSearch] = useState('');

  // 闪电按钮相关
  const [isLightningOpen, setIsLightningOpen] = useState(false);
  const [lightningSearch, setLightningSearch] = useState('');

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

  // 获取完整技能列表（用于闪电按钮）
  const [fullSkillList, setFullSkillList] = useState<any[]>([]);
  const [fullMcpList, setFullMcpList] = useState<any[]>([]);

  useRequest(
    async () => {
      const [, data] = await apiInterceptors(getSkillList({ filter: '' }, { page: '1', page_size: '50' }));
      return data as any;
    },
    {
      onSuccess: (data: any) => {
        if (data?.items && Array.isArray(data.items)) {
          setFullSkillList(data.items);
        }
      },
    },
  );

  useRequest(
    async () => {
      const [, data] = await apiInterceptors(getMCPList({ filter: '' }, { page: '1', page_size: '50' }));
      return data as any;
    },
    {
      onSuccess: (data: any) => {
        if (data?.items && Array.isArray(data.items)) {
          setFullMcpList(data.items);
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
      if (data) setDbList(data.map(normalizeDatasource));
    } finally {
      setDbLoading(false);
    }
  }, [dbList.length]);

  // 获取知识库列表（延迟加载）
  const fetchSpaceListData = useCallback(async () => {
    if (spaceListData.length > 0) return;
    setSpaceLoading(true);
    try {
      const [, data] = await apiInterceptors(getSpaceList());
      if (data) setSpaceListData(data);
    } finally {
      setSpaceLoading(false);
    }
  }, [spaceListData.length]);

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

  // 闪电按钮 - Skill 切换
  const handleLightningSkillToggle = useCallback((skill: any) => {
    const isSelected = selectedSkills.some((s: any) => s.skill_code === skill.skill_code);
    if (isSelected) {
      setSelectedSkills(prev => prev.filter((s: any) => s.skill_code !== skill.skill_code));
    } else {
      setSelectedSkills(prev => [...prev, skill]);
    }
  }, [selectedSkills]);

  // 闪电按钮 - MCP 切换
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
  const filteredLightningSkills = useMemo(() => {
    if (!lightningSearch) return fullSkillList;
    const search = lightningSearch.toLowerCase();
    return fullSkillList.filter((s: any) =>
      s.name?.toLowerCase().includes(search) || s.description?.toLowerCase().includes(search)
    );
  }, [fullSkillList, lightningSearch]);

  const filteredLightningMcps = useMemo(() => {
    if (!lightningSearch) return fullMcpList;
    const search = lightningSearch.toLowerCase();
    return fullMcpList.filter((m: any) =>
      m.name?.toLowerCase().includes(search) || m.description?.toLowerCase().includes(search)
    );
  }, [fullMcpList, lightningSearch]);

  // 默认绑定 - 从应用配置中提取
  const defaultBoundSkills = useMemo(() => {
    const tools = appDetail?.resource_tool || [];
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
        } catch { return null; }
      }).filter(Boolean);
  }, [appDetail?.resource_tool]);

  const defaultBoundMcps = useMemo(() => {
    const tools = appDetail?.resource_tool || [];
    return tools
      .filter((item: any) => {
        const type = item.type || '';
        return type === 'mcp' || type === 'mcp(derisk)';
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
            type: 'mcp',
            _isDefault: true,
          };
        } catch { return null; }
      }).filter(Boolean);
  }, [appDetail?.resource_tool]);

  const defaultBoundKnowledgeBases = useMemo(() => {
    const knowledgeResources = appDetail?.resource_knowledge || [];
    const kbs: any[] = [];
    knowledgeResources.forEach((item: any) => {
      try {
        const parsed = JSON.parse(item.value || '{}');
        if (parsed.knowledges && Array.isArray(parsed.knowledges)) {
          parsed.knowledges.forEach((kb: any) => {
            kbs.push({
              id: kb.knowledge_id,
              name: kb.knowledge_name || kb.name,
              _isDefault: true,
            });
          });
        }
      } catch { /* ignore */ }
    });
    return kbs;
  }, [appDetail?.resource_knowledge]);

  // 初始化默认绑定
  const [defaultsInitialized, setDefaultsInitialized] = useState(false);
  useEffect(() => {
    if (!appDetail || defaultsInitialized) return;
    if (defaultBoundSkills.length > 0) {
      setSelectedSkills(prev => {
        const existingCodes = new Set(prev.map((s: any) => s.skill_code));
        const newDefaults = defaultBoundSkills.filter((s: any) => !existingCodes.has(s.skill_code));
        return newDefaults.length > 0 ? [...prev, ...newDefaults] : prev;
      });
    }
    if (defaultBoundMcps.length > 0) {
      setSelectedMcps(prev => {
        const existingIds = new Set(prev.map((m: any) => m.id || m.uuid || m.name));
        const newDefaults = defaultBoundMcps.filter((m: any) => !existingIds.has(m.id || m.uuid || m.name));
        return newDefaults.length > 0 ? [...prev, ...newDefaults] : prev;
      });
    }
    if (defaultBoundKnowledgeBases.length > 0) {
      setSelectedKnowledgeBases(prev => {
        const existingIds = new Set(prev.map((kb: any) => kb.id || kb.name));
        const newDefaults = defaultBoundKnowledgeBases.filter((kb: any) => !existingIds.has(kb.id || kb.name));
        return newDefaults.length > 0 ? [...prev, ...newDefaults] : prev;
      });
    }
    setDefaultsInitialized(true);
  }, [appDetail, defaultBoundSkills, defaultBoundMcps, defaultBoundKnowledgeBases, defaultsInitialized]);

  const lightningBadgeCount = selectedSkills.length + selectedMcps.length;
  const plusBadgeCount = selectedDataSources.length + selectedKnowledgeBases.length;

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
          dataSources: selectedDataSources.length > 0 ? selectedDataSources : undefined,
          knowledgeBases: selectedKnowledgeBases.length > 0 ? selectedKnowledgeBases : undefined,
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
    setSelectedDataSources([]);
    setSelectedKnowledgeBases([]);
  };

  // 从 appList 中过滤出入驻首页的应用
  const homeSceneApps = useMemo(() => {
    return appList
      .filter(app => app.ext_config?.home_scene?.featured)
      .sort((a, b) => (a.ext_config?.home_scene?.position ?? 99) - (b.ext_config?.home_scene?.position ?? 99));
  }, [appList]);

  // Agent 场景切换
  const handleAgentSelect = useCallback((app: IApp) => {
    // 切回默认（toggle）
    if (selectedApp?.app_code === app.app_code) {
      const defaultApp = appList.find(a => a.app_code === 'chat_normal') || null;
      setSelectedApp(defaultApp);
      setPendingConvUid('');
      return;
    }
    setSelectedApp(app);
    setPendingConvUid('');
    setUploadedResources([]);
    setUploadingFiles([]);
  }, [appList, selectedApp]);

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
    isSelected = false,
    disabled = false,
    onClick
  }: {
    icon: React.ReactNode;
    text: string;
    bgColor?: string;
    iconColor?: string;
    isOutline?: boolean;
    isSelected?: boolean;
    disabled?: boolean;
    onClick?: () => void;
  }) => (
    <div
      className={cls(
        "flex flex-col items-center gap-2 cursor-pointer group transition-all duration-200",
        disabled && "opacity-50 pointer-events-none"
      )}
      onClick={onClick}
    >
      <div className={cls(
        "w-14 h-14 rounded-full flex items-center justify-center transition-all duration-200 group-hover:scale-110 group-hover:shadow-lg relative",
        isOutline
          ? "bg-white dark:bg-[#232734] border-2 border-dashed border-gray-300 dark:border-gray-600"
          : bgColor,
        isSelected && "ring-2 ring-offset-2 ring-blue-500 scale-110 shadow-lg shadow-blue-200/50 dark:shadow-blue-900/50 dark:ring-offset-gray-900"
      )}>
        <span className={cls("text-xl", iconColor)}>{icon}</span>
        {isSelected && (
          <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center border-2 border-white dark:border-gray-900 shadow-sm">
            <CheckOutlined className="text-white text-[10px]" />
          </div>
        )}
      </div>
      <span className={cls(
        "text-xs text-center max-w-[80px] leading-tight transition-colors",
        isSelected
          ? "text-blue-600 dark:text-blue-400 font-medium"
          : "text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-gray-200"
      )}>
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

  // "+" 按钮弹出菜单
  const plusMenuContent = useMemo(() => {
    const filteredDbList = dbSearch
      ? dbList.filter((ds: any) => ds.db_name?.toLowerCase().includes(dbSearch.toLowerCase()) || ds.comment?.toLowerCase().includes(dbSearch.toLowerCase()))
      : dbList;
    const filteredSpaces = kbSearch
      ? spaceListData.filter((kb: any) => kb.name?.toLowerCase().includes(kbSearch.toLowerCase()) || kb.desc?.toLowerCase().includes(kbSearch.toLowerCase()))
      : spaceListData;

    if (plusMenuView === 'datasource') {
      return (
        <div className="w-72 flex flex-col max-h-[400px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 dark:border-gray-700">
            <button onClick={() => { setPlusMenuView('main'); setDbSearch(''); }} className="w-6 h-6 rounded flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500">
              <LeftOutlined className="text-xs" />
            </button>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('select_datasource', '选择数据源')}</span>
          </div>
          <div className="px-3 py-2">
            <Input prefix={<SearchOutlined className="text-gray-400" />} placeholder={t('search_datasource', '搜索数据源...')} bordered={false} className="!bg-gray-50 dark:!bg-gray-800 rounded-lg" size="small" value={dbSearch} onChange={(e) => setDbSearch(e.target.value)} />
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {dbLoading ? (
              <div className="flex items-center justify-center py-8"><Spin size="small" /></div>
            ) : filteredDbList.length === 0 ? (
              <div className="text-center text-gray-400 text-xs py-8">{t('no_datasource', '暂无数据源')}</div>
            ) : filteredDbList.map((ds: any) => {
              const isSelected = selectedDataSources.some(s => s.id === ds.id);
              return (
                <div key={ds.id} className={cls('flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors mb-1', isSelected ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800' : 'hover:bg-gray-50 dark:hover:bg-gray-800')} onClick={() => handleDataSourceSelect(ds)}>
                  <div className="flex items-center gap-2 overflow-hidden">
                    <DatabaseOutlined className={cls('text-sm flex-shrink-0', isSelected ? 'text-green-500' : 'text-gray-400')} />
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
            })}
          </div>
        </div>
      );
    }

    if (plusMenuView === 'knowledge') {
      return (
        <div className="w-72 flex flex-col max-h-[400px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 dark:border-gray-700">
            <button onClick={() => { setPlusMenuView('main'); setKbSearch(''); }} className="w-6 h-6 rounded flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500">
              <LeftOutlined className="text-xs" />
            </button>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('select_knowledge_base', '选择知识库')}</span>
          </div>
          <div className="px-3 py-2">
            <Input prefix={<SearchOutlined className="text-gray-400" />} placeholder={t('search_knowledge_base', '搜索知识库...')} bordered={false} className="!bg-gray-50 dark:!bg-gray-800 rounded-lg" size="small" value={kbSearch} onChange={(e) => setKbSearch(e.target.value)} />
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {spaceLoading ? (
              <div className="flex items-center justify-center py-8"><Spin size="small" /></div>
            ) : filteredSpaces.length === 0 ? (
              <div className="text-center text-gray-400 text-xs py-8">{t('no_knowledge_base', '暂无知识库')}</div>
            ) : filteredSpaces.map((kb: any) => {
              const isSelected = selectedKnowledgeBases.some(s => (s.id || s.name) === (kb.id || kb.name));
              return (
                <div key={kb.id || kb.name} className={cls('flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors mb-1', isSelected ? 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800' : 'hover:bg-gray-50 dark:hover:bg-gray-800')} onClick={() => handleKnowledgeBaseSelect(kb)}>
                  <div className="flex items-center gap-2 overflow-hidden">
                    <BookOutlined className={cls('text-sm flex-shrink-0', isSelected ? 'text-amber-500' : 'text-gray-400')} />
                    <div className="overflow-hidden">
                      <div className="text-sm text-gray-700 dark:text-gray-200 truncate">{kb.name}</div>
                      {kb.desc && <div className="text-xs text-gray-400 truncate">{kb.desc}</div>}
                    </div>
                  </div>
                  {isSelected && <CheckOutlined className="text-amber-500 text-xs flex-shrink-0" />}
                </div>
              );
            })}
          </div>
        </div>
      );
    }

    return (
      <div className="w-56 p-1">
        <Upload showUploadList={false} beforeUpload={(file) => { handleFileUpload(file); setIsPlusMenuOpen(false); return false; }}>
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-gray-700 dark:text-gray-200 w-full">
            <UploadOutlined className="text-base text-gray-500" />
            <span className="text-sm">{t('upload_file', '上传文件')}</span>
          </div>
        </Upload>
        <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-gray-700 dark:text-gray-200" onClick={() => { setPlusMenuView('datasource'); fetchDbList(); }}>
          <DatabaseOutlined className="text-base text-gray-500" />
          <span className="text-sm">{t('select_datasource', '选择数据源')}</span>
        </div>
        <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-gray-700 dark:text-gray-200" onClick={() => { setPlusMenuView('knowledge'); fetchSpaceListData(); }}>
          <BookOutlined className="text-base text-gray-500" />
          <span className="text-sm">{t('select_knowledge_base', '选择知识库')}</span>
        </div>
      </div>
    );
  }, [plusMenuView, dbList, spaceListData, dbLoading, spaceLoading, selectedDataSources, selectedKnowledgeBases, dbSearch, kbSearch, t, handleFileUpload, handleDataSourceSelect, handleKnowledgeBaseSelect, fetchDbList, fetchSpaceListData]);

  // 闪电按钮弹出内容
  const lightningContent = useMemo(() => (
    <div className="w-80 flex flex-col max-h-[450px]">
      <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-700">
        <Input prefix={<SearchOutlined className="text-gray-400" />} placeholder={t('search_skills', '搜索技能...')} bordered={false} className="!bg-gray-50 dark:!bg-gray-800 rounded-lg" size="small" value={lightningSearch} onChange={(e) => setLightningSearch(e.target.value)} allowClear />
      </div>
      <div className="flex-1 overflow-y-auto py-1 px-2">
        {filteredLightningSkills.length > 0 && (
          <>
            <div className="px-2 py-1.5 text-xs text-gray-400 font-medium">{t('skills', '技能')}</div>
            {filteredLightningSkills.map((skill: any) => {
              const isSelected = selectedSkills.some((s: any) => s.skill_code === skill.skill_code);
              return (
                <div key={skill.skill_code} className={cls('flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors mb-0.5', isSelected ? 'bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800' : 'hover:bg-gray-50 dark:hover:bg-gray-800')} onClick={() => handleLightningSkillToggle(skill)}>
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
                    {skill.icon ? <img src={skill.icon} className="w-5 h-5 rounded" alt={skill.name} /> : <ThunderboltOutlined className="text-white text-sm" />}
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">{skill.name}</span>
                      {skill.type && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 flex-shrink-0">{t('official', '官方')}</span>}
                    </div>
                    {skill.description && <div className="text-xs text-gray-400 truncate mt-0.5">{skill.description}</div>}
                  </div>
                  {isSelected && <CheckOutlined className="text-purple-500 text-sm flex-shrink-0" />}
                </div>
              );
            })}
          </>
        )}
        {filteredLightningMcps.length > 0 && (
          <>
            <div className="px-2 py-1.5 text-xs text-gray-400 font-medium mt-1">{t('mcp_servers', 'MCP 服务')}</div>
            {filteredLightningMcps.map((mcp: any) => {
              const mcpId = mcp.id || mcp.uuid || mcp.name;
              const isSelected = selectedMcps.some((m: any) => (m.id || m.uuid || m.name) === mcpId);
              return (
                <div key={mcpId} className={cls('flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors mb-0.5', isSelected ? 'bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800' : 'hover:bg-gray-50 dark:hover:bg-gray-800')} onClick={() => handleLightningMcpToggle(mcp)}>
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center flex-shrink-0">
                    {mcp.icon ? <img src={mcp.icon} className="w-5 h-5 rounded" alt={mcp.name} /> : <ApiOutlined className="text-white text-sm" />}
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">{mcp.name}</span>
                      {mcp.available && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400 flex-shrink-0">Active</span>}
                    </div>
                    {mcp.description && <div className="text-xs text-gray-400 truncate mt-0.5">{mcp.description}</div>}
                  </div>
                  {isSelected && <CheckOutlined className="text-purple-500 text-sm flex-shrink-0" />}
                </div>
              );
            })}
          </>
        )}
        {filteredLightningSkills.length === 0 && filteredLightningMcps.length === 0 && (
          <div className="text-center text-gray-400 text-xs py-8">{t('no_skills_found', '未找到相关技能')}</div>
        )}
      </div>
      <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100 dark:border-gray-700">
        <span className="text-xs text-gray-400">{fullSkillList.length + fullMcpList.length} {t('skills_available', '个可用')}</span>
        <button className="text-xs text-indigo-500 hover:text-indigo-600 font-medium" onClick={() => { setIsLightningOpen(false); openConnectorsModal('skill'); }}>
          {t('manage_skills', '管理技能')} →
        </button>
      </div>
    </div>
  ), [lightningSearch, filteredLightningSkills, filteredLightningMcps, selectedSkills, selectedMcps, fullSkillList.length, fullMcpList.length, t, handleLightningSkillToggle, handleLightningMcpToggle]);

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

        {/* Active Agent Indicator */}
        {selectedApp && selectedApp.app_code !== 'chat_normal' && (
          <div className="flex items-center justify-center mb-3 transition-all duration-300">
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 shadow-sm">
              <div className="w-5 h-5 rounded-full bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center">
                {selectedApp.icon ? (
                  <img src={selectedApp.icon} className="w-4 h-4 rounded-full object-cover" alt="" />
                ) : (
                  <RobotOutlined className="text-white text-[10px]" />
                )}
              </div>
              <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                当前智能体：{selectedApp.app_name}
              </span>
              <button
                onClick={() => {
                  const defaultApp = appList.find(a => a.app_code === 'chat_normal') || null;
                  setSelectedApp(defaultApp);
                  setPendingConvUid('');
                }}
                className="ml-1 w-5 h-5 rounded-full flex items-center justify-center text-blue-400 hover:text-white hover:bg-blue-500 transition-all duration-200"
              >
                <CloseOutlined className="text-[10px]" />
              </button>
            </div>
          </div>
        )}

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

            {/* 底部工具栏 */}
            <div className="flex items-center justify-between px-2 pb-1">
              <div className="flex items-center gap-2">
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
                  <Badge count={plusBadgeCount} size="small" offset={[-4, 4]} color="#10b981">
                    <button className={cls(
                      "h-8 w-8 rounded-full flex items-center justify-center border transition-all",
                      plusBadgeCount > 0
                        ? "border-emerald-300 dark:border-emerald-700 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20"
                        : "border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:text-indigo-500 hover:border-indigo-300 dark:hover:border-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20"
                    )}>
                      <PlusOutlined className="text-sm" />
                    </button>
                  </Badge>
                </Popover>

                {/* 闪电按钮 - Skills/MCP */}
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
                    <button className="h-8 w-8 rounded-full flex items-center justify-center bg-purple-50 dark:bg-purple-900/30 border border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/50 hover:border-purple-400 transition-all">
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

              {/* 右侧：发送按钮 */}
              <div className="flex items-center gap-3">
                <button
                  className={cls(
                    'h-9 w-9 rounded-full flex items-center justify-center transition-all',
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
          </div>
        </div>

        {/* Quick Actions - 动态场景入口 */}
        <div className="flex flex-wrap justify-center gap-10 mt-10 max-w-4xl">
          {homeSceneApps.map((app) => {
            const homeScene = app.ext_config?.home_scene;
            const IconComp = HOME_SCENE_ICON_MAP[homeScene?.icon_type || ''] || RobotOutlined;
            const bgColor = homeScene?.bg_color
              ? `bg-gradient-to-br ${homeScene.bg_color}`
              : 'bg-gradient-to-br from-blue-400 to-blue-500';
            return (
              <QuickActionButton
                key={app.app_code}
                icon={<IconComp />}
                text={app.app_name}
                bgColor={bgColor}
                iconColor="text-white"
                isSelected={selectedApp?.app_code === app.app_code}
                onClick={() => handleAgentSelect(app)}
              />
            );
          })}
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
