'use client';

import React, { useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { AppContext } from '@/contexts';
import {
  Button, Tabs, Empty, Tooltip, Popconfirm, Badge, Tag, App, Modal,
  Input, Form, Select, Divider, Space, Typography, Avatar
} from 'antd';
import { 
  PlusOutlined, DeleteOutlined, SaveOutlined, 
  ReloadOutlined, FileTextOutlined, ThunderboltOutlined,
  EditOutlined, EyeOutlined, SettingOutlined, ToolOutlined,
  TagOutlined, NumberOutlined, FileAddOutlined, FileMarkdownOutlined,
  MoreOutlined, CheckCircleOutlined, WarningOutlined, InfoCircleOutlined,
  FolderOutlined, BranchesOutlined, ScheduleOutlined, RocketOutlined,
  CodeOutlined, SafetyOutlined, DatabaseOutlined, CloudOutlined,
  ExperimentOutlined, BulbOutlined, FileSearchOutlined
} from '@ant-design/icons';
import { sceneApi, SceneDefinition } from '@/client/api/scene';
import { useTranslation } from 'react-i18next';
import CodeMirror from '@uiw/react-codemirror';
import { markdown } from '@codemirror/lang-markdown';

const { TextArea } = Input;
const { Text, Title } = Typography;
const { Option } = Select;

/**
 * 文件类型图标映射
 */
const getFileIcon = (sceneId: string) => {
  const iconMap: Record<string, React.ReactNode> = {
    'code': <CodeOutlined className="text-blue-500" />,
    'coding': <CodeOutlined className="text-blue-500" />,
    'review': <FileSearchOutlined className="text-purple-500" />,
    'code-review': <FileSearchOutlined className="text-purple-500" />,
    'schedule': <ScheduleOutlined className="text-green-500" />,
    'plan': <ScheduleOutlined className="text-green-500" />,
    'deploy': <RocketOutlined className="text-orange-500" />,
    'deployment': <RocketOutlined className="text-orange-500" />,
    'data': <DatabaseOutlined className="text-cyan-500" />,
    'database': <DatabaseOutlined className="text-cyan-500" />,
    'cloud': <CloudOutlined className="text-sky-500" />,
    'security': <SafetyOutlined className="text-red-500" />,
    'test': <ExperimentOutlined className="text-pink-500" />,
    'testing': <ExperimentOutlined className="text-pink-500" />,
    'doc': <FileTextOutlined className="text-yellow-500" />,
    'document': <FileTextOutlined className="text-yellow-500" />,
    'git': <BranchesOutlined className="text-indigo-500" />,
    'version': <BranchesOutlined className="text-indigo-500" />,
  };
  
  for (const key of Object.keys(iconMap)) {
    if (sceneId.toLowerCase().includes(key)) {
      return iconMap[key];
    }
  }
  return <FileMarkdownOutlined className="text-gray-500" />;
};

/**
 * 获取文件背景色
 */
const getFileBgColor = (sceneId: string, isActive: boolean) => {
  if (isActive) {
    return 'bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200';
  }
  
  const colorMap: Record<string, string> = {
    'code': 'hover:bg-blue-50/50',
    'coding': 'hover:bg-blue-50/50',
    'review': 'hover:bg-purple-50/50',
    'schedule': 'hover:bg-green-50/50',
    'deploy': 'hover:bg-orange-50/50',
    'data': 'hover:bg-cyan-50/50',
    'test': 'hover:bg-pink-50/50',
    'doc': 'hover:bg-yellow-50/50',
  };
  
  for (const key of Object.keys(colorMap)) {
    if (sceneId.toLowerCase().includes(key)) {
      return colorMap[key];
    }
  }
  return 'hover:bg-gray-50/50';
};

/**
 * 解析 Markdown 内容的 YAML Front Matter
 */
function parseFrontMatter(content: string): { frontMatter: Record<string, any>; body: string } {
  const match = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
  if (!match) {
    return { frontMatter: {}, body: content };
  }
  
  const yamlContent = match[1];
  const body = match[2];
  const frontMatter: Record<string, any> = {};
  
  yamlContent.split('\n').forEach(line => {
    const colonIndex = line.indexOf(':');
    if (colonIndex > 0) {
      const key = line.slice(0, colonIndex).trim();
      let value: any = line.slice(colonIndex + 1).trim();
      
      if (value.startsWith('[') && value.endsWith(']')) {
        value = value.slice(1, -1).split(',').map(v => v.trim()).filter(Boolean);
      } else if (value.startsWith('"') && value.endsWith('"')) {
        value = value.slice(1, -1);
      } else if (value.startsWith("'") && value.endsWith("'")) {
        value = value.slice(1, -1);
      }
      
      frontMatter[key] = value;
    }
  });
  
  return { frontMatter, body };
}

/**
 * 生成带 YAML Front Matter 的 Markdown 内容
 */
function generateFrontMatterContent(frontMatter: Record<string, any>, body: string): string {
  const yamlLines = Object.entries(frontMatter).map(([key, value]) => {
    if (Array.isArray(value)) {
      return `${key}: [${value.join(', ')}]`;
    } else if (typeof value === 'string' && (value.includes(':') || value.includes('"') || value.includes("'"))) {
      return `${key}: "${value.replace(/"/g, '\\"')}"`;
    }
    return `${key}: ${value}`;
  });
  
  return `---\n${yamlLines.join('\n')}\n---\n\n${body.trim()}\n`;
}

/**
 * 生成默认场景内容
 */
function generateDefaultSceneContent(sceneId: string, sceneName: string, description: string = ''): string {
  const frontMatter = {
    id: sceneId,
    name: sceneName,
    description: description || `${sceneName}场景`,
    priority: 5,
    keywords: [sceneId, sceneName],
    allow_tools: ['read', 'write', 'edit', 'search']
  };
  
  const body = `## 角色设定

你是${sceneName}专家，专注于解决相关领域的问题。

## 工作流程

1. 分析问题背景和需求
2. 制定解决方案
3. 执行并验证结果
4. 提供详细的分析和建议

## 注意事项

- 保持专业性和准确性
- 提供可操作的建议
- 解释关键决策的原因
`;
  
  return generateFrontMatterContent(frontMatter, body);
}

/**
 * 场景配置 Tab - 文件编辑器版本 (重构版)
 * 按顶级设计师风格设计，展示原文件名，中文介绍作为副标题
 */
export default function TabScenes() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const { message, modal } = App.useApp();
  
  // 状态管理
  const [availableScenes, setAvailableScenes] = useState<SceneDefinition[]>([]);
  const [selectedScenes, setSelectedScenes] = useState<string[]>([]);
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingContent, setEditingContent] = useState<string>('');
  const [hasChanges, setHasChanges] = useState(false);
  const [editMode, setEditMode] = useState<'edit' | 'preview'>('edit');
  
  // 新建场景弹窗
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);
  
  // 快捷编辑弹窗
  const [quickEditVisible, setQuickEditVisible] = useState(false);
  const [quickEditType, setQuickEditType] = useState<'tools' | 'priority' | 'keywords'>('tools');
  const [quickEditForm] = Form.useForm();

  // 从 appInfo 中获取已选择的场景
  useEffect(() => {
    if (appInfo?.scenes && appInfo.scenes.length > 0) {
      const serverHasNewScenes = appInfo.scenes.some(id => !selectedScenes.includes(id));
      const localHasUnsyncedScenes = selectedScenes.some(id => !appInfo.scenes.includes(id));
      const isInitializing = selectedScenes.length === 0;
      
      if (serverHasNewScenes || (isInitializing && !localHasUnsyncedScenes)) {
        setSelectedScenes(appInfo.scenes);
      }
    }
  }, [appInfo?.scenes]);

  // 加载可用场景列表
  useEffect(() => {
    loadScenes();
  }, []);

  const loadScenes = async () => {
    setLoading(true);
    try {
      const scenes = await sceneApi.list();
      setAvailableScenes(scenes);
      // 如果有已选场景，默认激活第一个
      if (selectedScenes.length > 0 && !activeSceneId) {
        const firstScene = scenes.find(s => selectedScenes.includes(s.scene_id));
        if (firstScene) {
          setActiveSceneId(firstScene.scene_id);
          setEditingContent(firstScene.md_content || '');
        }
      }
    } catch (error) {
      message.error(t('scene_load_failed', '加载场景失败'));
    } finally {
      setLoading(false);
    }
  };

  // 获取当前激活的场景
  const activeScene = availableScenes.find(s => s.scene_id === activeSceneId);
  
  // 解析当前编辑内容的 front matter
  const parsedContent = useMemo(() => {
    return parseFrontMatter(editingContent);
  }, [editingContent]);

  // 处理场景切换
  const handleSceneChange = useCallback((sceneId: string) => {
    if (hasChanges) {
      modal.confirm({
        title: t('scene_unsaved_title', '未保存的更改'),
        content: t('scene_unsaved_content', '是否保存当前更改？'),
        okText: t('scene_save', '保存'),
        cancelText: t('scene_discard', '放弃'),
        onOk: () => handleSave(),
        onCancel: () => {
          setHasChanges(false);
          switchToScene(sceneId);
        }
      });
    } else {
      switchToScene(sceneId);
    }
  }, [hasChanges, activeSceneId]);

  const switchToScene = (sceneId: string) => {
    setActiveSceneId(sceneId);
    const scene = availableScenes.find(s => s.scene_id === sceneId);
    if (scene) {
      setEditingContent(scene.md_content || generateDefaultSceneContent(scene.scene_id, scene.scene_name, scene.description));
      setHasChanges(false);
    }
  };

  // 处理内容编辑
  const handleContentChange = (value: string) => {
    setEditingContent(value);
    setHasChanges(true);
  };

  // 保存场景内容
  const handleSave = async () => {
    if (!activeSceneId) return;
    
    setSaving(true);
    try {
      await sceneApi.update(activeSceneId, {
        md_content: editingContent
      });
      
      // 更新本地状态
      setAvailableScenes(prev => prev.map(scene => 
        scene.scene_id === activeSceneId 
          ? { ...scene, md_content: editingContent }
          : scene
      ));
      
      setHasChanges(false);
      message.success(t('scene_save_success', '场景保存成功'));
    } catch (error) {
      message.error(t('scene_save_failed', '场景保存失败'));
    } finally {
      setSaving(false);
    }
  };

  // 直接添加场景文件（不弹窗）
  const handleAddScene = () => {
    setCreateModalVisible(true);
    createForm.resetFields();
  };

  // 创建新场景
  const handleCreateScene = async () => {
    try {
      const values = await createForm.validateFields();
      setCreating(true);
      
      const sceneId = values.scene_id.trim();
      const sceneName = values.scene_name.trim();
      const description = values.description?.trim() || '';
      
      // 检查是否已存在
      if (availableScenes.some(s => s.scene_id === sceneId)) {
        message.error(t('scene_exists', '场景ID已存在'));
        setCreating(false);
        return;
      }

      const defaultContent = generateDefaultSceneContent(sceneId, sceneName, description);
      
      const newScene = await sceneApi.create({
        scene_id: sceneId,
        scene_name: sceneName,
        description: description,
        md_content: defaultContent,
        trigger_keywords: [sceneId, sceneName],
        trigger_priority: 5,
        scene_role_prompt: '',
        scene_tools: ['read', 'write', 'edit', 'search'],
      });

      setAvailableScenes(prev => [...prev, newScene]);

      const newScenes = [...selectedScenes, newScene.scene_id];
      setSelectedScenes(newScenes);

      await fetchUpdateApp({ ...appInfo, scenes: newScenes });

      message.success(t('scene_create_success', '场景创建成功'));
      setCreateModalVisible(false);
      
      setActiveSceneId(newScene.scene_id);
      setEditingContent(defaultContent);
      setHasChanges(false);
    } catch (error) {
      if (error instanceof Error) {
        message.error(t('scene_create_failed', '场景创建失败'));
      }
    } finally {
      setCreating(false);
    }
  };

  // 移除场景
  const handleRemoveScene = async (sceneId: string) => {
    const newScenes = selectedScenes.filter(id => id !== sceneId);
    const previousScenes = selectedScenes;
    setSelectedScenes(newScenes);

    try {
      await fetchUpdateApp({ ...appInfo, scenes: newScenes });
      message.success(t('scene_remove_success', '场景移除成功'));

      if (sceneId === activeSceneId) {
        const remainingScene = availableScenes.find(s => newScenes.includes(s.scene_id));
        if (remainingScene) {
          setActiveSceneId(remainingScene.scene_id);
          setEditingContent(remainingScene.md_content || '');
        } else {
          setActiveSceneId(null);
          setEditingContent('');
        }
      }
    } catch (error) {
      setSelectedScenes(previousScenes);
      message.error(t('scene_remove_failed', '场景移除失败'));
    }
  };

  // 打开快捷编辑
  const openQuickEdit = (type: 'tools' | 'priority' | 'keywords') => {
    setQuickEditType(type);
    const frontMatter = parsedContent.frontMatter;
    
    if (type === 'tools') {
      quickEditForm.setFieldsValue({
        tools: frontMatter.allow_tools || []
      });
    } else if (type === 'priority') {
      quickEditForm.setFieldsValue({
        priority: frontMatter.priority || 5
      });
    } else if (type === 'keywords') {
      quickEditForm.setFieldsValue({
        keywords: Array.isArray(frontMatter.keywords) ? frontMatter.keywords : []
      });
    }
    
    setQuickEditVisible(true);
  };

  // 保存快捷编辑
  const handleQuickEditSave = async () => {
    try {
      const values = await quickEditForm.validateFields();
      const frontMatter = { ...parsedContent.frontMatter };
      
      if (quickEditType === 'tools') {
        frontMatter.allow_tools = values.tools;
      } else if (quickEditType === 'priority') {
        frontMatter.priority = values.priority;
      } else if (quickEditType === 'keywords') {
        frontMatter.keywords = values.keywords;
      }
      
      const newContent = generateFrontMatterContent(frontMatter, parsedContent.body);
      setEditingContent(newContent);
      setHasChanges(true);
      setQuickEditVisible(false);
      message.success(t('scene_quick_edit_success', '已更新，记得保存'));
    } catch (error) {
      console.error('Quick edit error:', error);
    }
  };

  // 刷新场景列表
  const handleRefresh = () => {
    loadScenes();
    message.success(t('scene_refresh_success', '场景列表已刷新'));
  };

  // 获取已选场景的详细信息
  const selectedSceneDetails = selectedScenes
    .map(id => availableScenes.find(s => s.scene_id === id))
    .filter(Boolean) as SceneDefinition[];

  // 渲染快捷编辑内容
  const renderQuickEditContent = () => {
    if (quickEditType === 'tools') {
      return (
        <Form form={quickEditForm} layout="vertical">
          <Form.Item 
            name="tools" 
            label={t('scene_tools', '允许的工具')}
            rules={[{ required: true }]}
          >
            <Select
              mode="tags"
              placeholder={t('scene_tools_placeholder', '输入工具名称')}
              style={{ width: '100%' }}
              options={[
                { label: 'read', value: 'read' },
                { label: 'write', value: 'write' },
                { label: 'edit', value: 'edit' },
                { label: 'search', value: 'search' },
                { label: 'execute', value: 'execute' },
                { label: 'browser', value: 'browser' },
                { label: 'ask', value: 'ask' },
              ]}
            />
          </Form.Item>
        </Form>
      );
    }
    
    if (quickEditType === 'priority') {
      return (
        <Form form={quickEditForm} layout="vertical">
          <Form.Item 
            name="priority" 
            label={t('scene_priority', '优先级')}
            rules={[{ required: true }]}
          >
            <Select placeholder={t('scene_priority_placeholder', '选择优先级')}>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(p => (
                <Option key={p} value={p}>{p} {p === 10 ? '(最高)' : p === 1 ? '(最低)' : ''}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      );
    }
    
    if (quickEditType === 'keywords') {
      return (
        <Form form={quickEditForm} layout="vertical">
          <Form.Item 
            name="keywords" 
            label={t('scene_keywords', '触发关键词')}
            rules={[{ required: true }]}
          >
            <Select
              mode="tags"
              placeholder={t('scene_keywords_placeholder', '输入关键词')}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Form>
      );
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-gradient-to-br from-gray-50/50 to-blue-50/20">
      {/* 顶部导航栏 - 玻璃拟态效果 */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200/60 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg shadow-blue-500/20">
            <ThunderboltOutlined className="text-white text-lg" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900 tracking-tight">
              {t('scene_config_title', '场景配置')}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              管理应用的智能场景定义
            </p>
          </div>
          <Badge 
            count={selectedScenes.length} 
            className="ml-2" 
            style={{ 
              backgroundColor: selectedScenes.length > 0 ? '#3b82f6' : '#9ca3af',
              boxShadow: '0 2px 4px rgba(59, 130, 246, 0.3)'
            }} 
          />
        </div>
        <div className="flex items-center gap-3">
          <Tooltip title={t('scene_refresh', '刷新')}>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={handleRefresh}
              loading={loading}
              className="hover:bg-gray-100 transition-colors"
            />
          </Tooltip>
          <Button 
            type="primary" 
            icon={<FileAddOutlined />}
            onClick={handleAddScene}
            className="bg-gradient-to-r from-blue-500 to-indigo-600 border-0 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 transition-all"
          >
            {t('scene_add', '添加场景')}
          </Button>
        </div>
      </div>

      {/* 主要内容区 */}
      <div className="flex flex-1 overflow-hidden">
        {selectedSceneDetails.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-8">
            <Empty
              image={
                <div className="w-40 h-40 mx-auto mb-4 bg-gradient-to-br from-blue-100 to-indigo-100 rounded-3xl flex items-center justify-center">
                  <FolderOutlined className="text-6xl text-blue-400" />
                </div>
              }
              description={
                <div className="text-center">
                  <p className="text-gray-500 mb-2 text-base font-medium">
                    {t('scene_empty_desc', '暂无配置的场景')}
                  </p>
                  <p className="text-gray-400 text-sm mb-6">
                    添加场景以扩展应用能力
                  </p>
                  <Button 
                    type="primary" 
                    size="large"
                    icon={<FileAddOutlined />} 
                    onClick={handleAddScene}
                    className="bg-gradient-to-r from-blue-500 to-indigo-600 border-0 shadow-lg shadow-blue-500/25"
                  >
                    {t('scene_add_first', '添加第一个场景')}
                  </Button>
                </div>
              }
            />
          </div>
        ) : (
          <>
            {/* 左侧场景文件列表 - 文件浏览器风格 */}
            <div className="w-80 border-r border-gray-200/60 bg-white/60 backdrop-blur-sm flex flex-col">
              <div className="px-4 py-3 border-b border-gray-200/60 bg-white/40">
                <div className="flex items-center gap-2 text-xs text-gray-500 font-medium uppercase tracking-wider">
                  <FolderOutlined />
                  <span>{t('scene_file_list', '场景文件')}</span>
                  <span className="ml-auto bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full text-xs">
                    {selectedSceneDetails.length}
                  </span>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {selectedSceneDetails.map((scene, index) => {
                  const isActive = scene.scene_id === activeSceneId;
                  const fileName = `${scene.scene_id}.md`;
                  
                  return (
                    <div
                      key={scene.scene_id}
                      onClick={() => handleSceneChange(scene.scene_id)}
                      className={`
                        group relative flex items-center gap-3 p-3 rounded-xl cursor-pointer
                        transition-all duration-200 ease-out
                        ${isActive 
                          ? 'bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200/50 shadow-sm' 
                          : 'border border-transparent hover:bg-gray-50/80 hover:border-gray-200/50'
                        }
                      `}
                    >
                      {/* 文件图标 */}
                      <div className={`
                        flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center
                        transition-all duration-200
                        ${isActive 
                          ? 'bg-white shadow-sm' 
                          : 'bg-gray-100 group-hover:bg-white group-hover:shadow-sm'
                        }
                      `}>
                        {getFileIcon(scene.scene_id)}
                      </div>
                      
                      {/* 文件信息 */}
                      <div className="flex-1 min-w-0">
                        {/* 主标题：原文件名 */}
                        <div className="flex items-center gap-2">
                          <span className={`
                            font-mono text-sm font-medium truncate
                            ${isActive ? 'text-blue-700' : 'text-gray-900'}
                          `}>
                            {fileName}
                          </span>
                          {isActive && hasChanges && (
                            <span className="flex-shrink-0 w-2 h-2 rounded-full bg-orange-400 animate-pulse" />
                          )}
                        </div>
                        {/* 副标题：中文介绍 */}
                        <p className="text-xs text-gray-500 truncate mt-0.5">
                          {scene.scene_name}
                          {scene.description && (
                            <span className="text-gray-400"> · {scene.description}</span>
                          )}
                        </p>
                      </div>
                      
                      {/* 悬停操作 */}
                      <Popconfirm
                        title={t('scene_remove_confirm', '确认移除')}
                        description={t('scene_remove_desc', '从应用中移除此场景？')}
                        onConfirm={(e) => {
                          e?.stopPropagation();
                          handleRemoveScene(scene.scene_id);
                        }}
                        okText={t('confirm', '确认')}
                        cancelText={t('cancel', '取消')}
                      >
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined className="text-xs" />}
                          className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 右侧编辑器区域 */}
            <div className="flex-1 flex flex-col bg-white/40 backdrop-blur-sm">
              {activeScene ? (
                <>
                  {/* 编辑器头部工具栏 */}
                  <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200/60 bg-white/60">
                    <div className="flex items-center gap-4 flex-wrap">
                      {/* 当前文件名显示 */}
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100/80 rounded-lg">
                          <FileMarkdownOutlined className="text-gray-500" />
                          <span className="font-mono text-sm font-medium text-gray-700">
                            {activeScene.scene_id}.md
                          </span>
                        </div>
                        <div className="h-4 w-px bg-gray-300" />
                        <span className="text-sm text-gray-600">
                          {activeScene.scene_name}
                        </span>
                      </div>
                      
                      {/* 快捷编辑按钮组 */}
                      <div className="flex items-center gap-1">
                        <Tooltip title={t('scene_edit_tools', '编辑工具')}>
                          <Button 
                            type="text" 
                            size="small"
                            icon={<ToolOutlined className="text-gray-500" />}
                            onClick={() => openQuickEdit('tools')}
                            className="hover:bg-blue-50 hover:text-blue-600"
                          >
                            <span className="text-xs">
                              {parsedContent.frontMatter.allow_tools?.length || 0} 工具
                            </span>
                          </Button>
                        </Tooltip>
                        <Tooltip title={t('scene_edit_priority', '编辑优先级')}>
                          <Button 
                            type="text" 
                            size="small"
                            icon={<NumberOutlined className="text-gray-500" />}
                            onClick={() => openQuickEdit('priority')}
                            className="hover:bg-blue-50 hover:text-blue-600"
                          >
                            <span className="text-xs">
                              优先级 {parsedContent.frontMatter.priority || 5}
                            </span>
                          </Button>
                        </Tooltip>
                        <Tooltip title={t('scene_edit_keywords', '编辑关键词')}>
                          <Button 
                            type="text" 
                            size="small"
                            icon={<TagOutlined className="text-gray-500" />}
                            onClick={() => openQuickEdit('keywords')}
                            className="hover:bg-blue-50 hover:text-blue-600"
                          >
                            <span className="text-xs">
                              {parsedContent.frontMatter.keywords?.length || 0} 关键词
                            </span>
                          </Button>
                        </Tooltip>
                      </div>
                      
                      {hasChanges && (
                        <Tag size="small" className="bg-orange-50 text-orange-600 border-orange-200">
                          <WarningOutlined className="mr-1" />
                          {t('scene_unsaved', '未保存')}
                        </Tag>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button.Group className="shadow-sm">
                        <Button 
                          type={editMode === 'edit' ? 'primary' : 'default'}
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => setEditMode('edit')}
                          className={editMode === 'edit' ? 'bg-blue-500' : ''}
                        >
                          {t('edit', '编辑')}
                        </Button>
                        <Button 
                          type={editMode === 'preview' ? 'primary' : 'default'}
                          size="small"
                          icon={<EyeOutlined />}
                          onClick={() => setEditMode('preview')}
                          className={editMode === 'preview' ? 'bg-blue-500' : ''}
                        >
                          {t('preview', '预览')}
                        </Button>
                      </Button.Group>
                      <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        size="small"
                        loading={saving}
                        disabled={!hasChanges}
                        onClick={handleSave}
                        className="bg-gradient-to-r from-green-500 to-emerald-600 border-0 shadow-lg shadow-green-500/25 hover:shadow-green-500/40 transition-all"
                      >
                        {t('save', '保存')}
                      </Button>
                    </div>
                  </div>

                  {/* 编辑器内容 */}
                  <div className="flex-1 overflow-hidden">
                    {editMode === 'edit' ? (
                      <div className="h-full p-4">
                        <div className="h-full rounded-xl overflow-hidden border border-gray-200/60 shadow-sm">
                          <CodeMirror
                            value={editingContent}
                            height="100%"
                            theme="light"
                            extensions={[markdown()]}
                            onChange={handleContentChange}
                            className="h-full text-sm"
                            basicSetup={{
                              lineNumbers: true,
                              highlightActiveLine: true,
                              highlightSelectionMatches: true,
                            }}
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="h-full overflow-auto p-6">
                        <div className="max-w-4xl mx-auto space-y-6">
                          {/* Front Matter 预览 */}
                          <div className="p-5 bg-gradient-to-br from-gray-50 to-blue-50/30 rounded-xl border border-gray-200/60">
                            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                              <InfoCircleOutlined />
                              YAML Front Matter
                            </h3>
                            <pre className="text-xs text-gray-600 overflow-auto bg-white/60 p-3 rounded-lg border border-gray-200/50">
                              {JSON.stringify(parsedContent.frontMatter, null, 2)}
                            </pre>
                          </div>
                          {/* Markdown 内容预览 */}
                          <div className="prose prose-sm max-w-none bg-white p-6 rounded-xl border border-gray-200/60 shadow-sm">
                            <div 
                              dangerouslySetInnerHTML={{ 
                                __html: parsedContent.body
                                  .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold text-gray-900 mb-4">$1</h1>')
                                  .replace(/^## (.*$)/gim, '<h2 class="text-xl font-semibold text-gray-800 mt-6 mb-3">$1</h2>')
                                  .replace(/^### (.*$)/gim, '<h3 class="text-lg font-medium text-gray-700 mt-4 mb-2">$1</h3>')
                                  .replace(/\*\*(.*)\*\*/gim, '<strong class="font-semibold text-gray-900">$1</strong>')
                                  .replace(/\*(.*)\*/gim, '<em class="text-gray-700">$1</em>')
                                  .replace(/^- (.*$)/gim, '<li class="ml-4 text-gray-600">$1</li>')
                                  .replace(/\n/gim, '<br />')
                              }} 
                            />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 底部状态栏 */}
                  <div className="px-6 py-3 border-t border-gray-200/60 bg-white/40 flex items-center justify-between text-xs text-gray-500">
                    <div className="flex items-center gap-6">
                      <span className="flex items-center gap-1.5">
                        <FileTextOutlined className="text-gray-400" />
                        {editingContent.length.toLocaleString()} 字符
                      </span>
                      <span className="flex items-center gap-1.5">
                        <BranchesOutlined className="text-gray-400" />
                        {editingContent.split('\n').length} 行
                      </span>
                      {parsedContent.frontMatter.allow_tools && (
                        <span className="flex items-center gap-1.5">
                          <ToolOutlined className="text-gray-400" />
                          {parsedContent.frontMatter.allow_tools.length} 个工具
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <CheckCircleOutlined className="text-green-500" />
                      {t('scene_last_modified', '最后修改')}: {new Date().toLocaleString()}
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
                  <div className="w-24 h-24 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
                    <FileMarkdownOutlined className="text-4xl text-gray-300" />
                  </div>
                  <p className="text-gray-500 font-medium">
                    {t('scene_select_tip', '请从左侧选择一个场景文件')}
                  </p>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* 创建场景弹窗 */}
      <Modal
        title={
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <FileAddOutlined className="text-white text-sm" />
            </div>
            <span className="font-semibold">{t('scene_create_title', '添加新场景')}</span>
          </div>
        }
        open={createModalVisible}
        onOk={handleCreateScene}
        onCancel={() => {
          setCreateModalVisible(false);
          createForm.resetFields();
        }}
        confirmLoading={creating}
        okText={t('create', '创建')}
        cancelText={t('cancel', '取消')}
        width={520}
        className="scene-create-modal"
      >
        <Form form={createForm} layout="vertical" className="mt-4">
          <Form.Item
            name="scene_id"
            label={
              <span className="font-medium text-gray-700">
                {t('scene_id', '场景ID')}
                <span className="text-gray-400 font-normal ml-1">(将作为文件名)</span>
              </span>
            }
            rules={[
              { required: true, message: t('scene_id_required', '请输入场景ID') },
              { pattern: /^[a-z0-9_-]+$/, message: t('scene_id_pattern', '只能使用小写字母、数字、下划线和横线') }
            ]}
          >
            <Input 
              placeholder={t('scene_id_placeholder', '如: code-review, data-analysis')}
              prefix={<FileTextOutlined className="text-gray-400" />}
              suffix=".md"
              className="font-mono"
            />
          </Form.Item>
          <Form.Item
            name="scene_name"
            label={<span className="font-medium text-gray-700">{t('scene_name', '场景名称')}</span>}
            rules={[{ required: true, message: t('scene_name_required', '请输入场景名称') }]}
          >
            <Input 
              placeholder={t('scene_name_placeholder', '如: 代码评审、数据分析')}
            />
          </Form.Item>
          <Form.Item
            name="description"
            label={<span className="font-medium text-gray-700">{t('scene_description', '场景描述')}</span>}
          >
            <TextArea 
              placeholder={t('scene_description_placeholder', '简要描述这个场景的用途')}
              rows={3}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 快捷编辑弹窗 */}
      <Modal
        title={
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center">
              <SettingOutlined className="text-white text-sm" />
            </div>
            <span className="font-semibold">
              {quickEditType === 'tools' && t('scene_edit_tools_title', '编辑工具')}
              {quickEditType === 'priority' && t('scene_edit_priority_title', '编辑优先级')}
              {quickEditType === 'keywords' && t('scene_edit_keywords_title', '编辑关键词')}
            </span>
          </div>
        }
        open={quickEditVisible}
        onOk={handleQuickEditSave}
        onCancel={() => setQuickEditVisible(false)}
        okText={t('confirm', '确认')}
        cancelText={t('cancel', '取消')}
        width={480}
      >
        <div className="mt-4">
          {renderQuickEditContent()}
        </div>
      </Modal>
    </div>
  );
}
