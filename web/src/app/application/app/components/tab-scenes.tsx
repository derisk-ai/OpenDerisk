'use client';

import React, { useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { AppContext } from '@/contexts';
import {
  Button, Empty, Tooltip, Popconfirm, Badge, Tag, App, Modal,
  Input, Form, Select, Divider, Space, Typography, Segmented
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
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeRaw from 'rehype-raw';
import rehypeHighlight from 'rehype-highlight';

const { TextArea } = Input;
const { Text, Title } = Typography;
const { Option } = Select;

// ─── Icon & Color Mapping ─────────────────────────────────────────────────────

const ICON_CONFIG: Record<string, { icon: React.ReactNode; color: string; bg: string; activeBg: string }> = {
  'code':       { icon: <CodeOutlined />,       color: 'text-blue-500',   bg: 'bg-blue-50',   activeBg: 'from-blue-500 to-blue-600' },
  'coding':     { icon: <CodeOutlined />,       color: 'text-blue-500',   bg: 'bg-blue-50',   activeBg: 'from-blue-500 to-blue-600' },
  'review':     { icon: <FileSearchOutlined />, color: 'text-violet-500', bg: 'bg-violet-50', activeBg: 'from-violet-500 to-purple-600' },
  'code-review':{ icon: <FileSearchOutlined />, color: 'text-violet-500', bg: 'bg-violet-50', activeBg: 'from-violet-500 to-purple-600' },
  'schedule':   { icon: <ScheduleOutlined />,   color: 'text-emerald-500',bg: 'bg-emerald-50',activeBg: 'from-emerald-500 to-green-600' },
  'plan':       { icon: <ScheduleOutlined />,   color: 'text-emerald-500',bg: 'bg-emerald-50',activeBg: 'from-emerald-500 to-green-600' },
  'deploy':     { icon: <RocketOutlined />,     color: 'text-orange-500', bg: 'bg-orange-50', activeBg: 'from-orange-500 to-amber-600' },
  'deployment': { icon: <RocketOutlined />,     color: 'text-orange-500', bg: 'bg-orange-50', activeBg: 'from-orange-500 to-amber-600' },
  'data':       { icon: <DatabaseOutlined />,   color: 'text-cyan-500',   bg: 'bg-cyan-50',   activeBg: 'from-cyan-500 to-teal-600' },
  'database':   { icon: <DatabaseOutlined />,   color: 'text-cyan-500',   bg: 'bg-cyan-50',   activeBg: 'from-cyan-500 to-teal-600' },
  'cloud':      { icon: <CloudOutlined />,      color: 'text-sky-500',    bg: 'bg-sky-50',    activeBg: 'from-sky-500 to-blue-600' },
  'security':   { icon: <SafetyOutlined />,     color: 'text-rose-500',   bg: 'bg-rose-50',   activeBg: 'from-rose-500 to-red-600' },
  'test':       { icon: <ExperimentOutlined />, color: 'text-pink-500',   bg: 'bg-pink-50',   activeBg: 'from-pink-500 to-rose-600' },
  'testing':    { icon: <ExperimentOutlined />, color: 'text-pink-500',   bg: 'bg-pink-50',   activeBg: 'from-pink-500 to-rose-600' },
  'doc':        { icon: <FileTextOutlined />,   color: 'text-amber-500',  bg: 'bg-amber-50',  activeBg: 'from-amber-500 to-yellow-600' },
  'document':   { icon: <FileTextOutlined />,   color: 'text-amber-500',  bg: 'bg-amber-50',  activeBg: 'from-amber-500 to-yellow-600' },
  'git':        { icon: <BranchesOutlined />,   color: 'text-indigo-500', bg: 'bg-indigo-50', activeBg: 'from-indigo-500 to-violet-600' },
  'version':    { icon: <BranchesOutlined />,   color: 'text-indigo-500', bg: 'bg-indigo-50', activeBg: 'from-indigo-500 to-violet-600' },
};

const DEFAULT_ICON_CONFIG = { icon: <FileMarkdownOutlined />, color: 'text-slate-400', bg: 'bg-slate-50', activeBg: 'from-slate-500 to-gray-600' };

function getIconConfig(sceneId: string) {
  for (const key of Object.keys(ICON_CONFIG)) {
    if (sceneId.toLowerCase().includes(key)) {
      return ICON_CONFIG[key];
    }
  }
  return DEFAULT_ICON_CONFIG;
}

// ─── YAML Front Matter Parsing ────────────────────────────────────────────────

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
        value = value.slice(1, -1).split(',').map((v: string) => v.trim()).filter(Boolean);
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

// ─── Markdown Preview Components ──────────────────────────────────────────────

const sceneMarkdownComponents: Partial<Components> = {
  h1: ({ children, ...props }) => (
    <h1 className="text-2xl font-bold text-gray-900 mb-4 pb-3 border-b border-gray-200" {...props}>{children}</h1>
  ),
  h2: ({ children, ...props }) => (
    <div className="mt-8 mb-4">
      <h2 className="text-lg font-semibold text-gray-800 pl-3 py-1 border-l-[3px] border-blue-500" {...props}>{children}</h2>
    </div>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="text-base font-semibold text-gray-700 mt-5 mb-2" {...props}>{children}</h3>
  ),
  p: ({ children, ...props }) => (
    <p className="text-sm text-gray-600 leading-relaxed mb-3" {...props}>{children}</p>
  ),
  strong: ({ children, ...props }) => (
    <strong className="font-semibold text-gray-800" {...props}>{children}</strong>
  ),
  ul: ({ children, ...props }) => (
    <ul className="space-y-1.5 my-3 ml-1" {...props}>{children}</ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="space-y-1.5 my-3 ml-1 counter-reset-item" {...props}>{children}</ol>
  ),
  li: ({ children, ...props }) => (
    <li className="flex items-start gap-2 text-sm text-gray-600" {...props}>
      <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-blue-400 mt-2" />
      <span className="flex-1">{children}</span>
    </li>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote className="my-4 pl-4 py-2 border-l-[3px] border-amber-400 bg-amber-50/50 rounded-r-lg text-sm text-gray-600 italic" {...props}>
      {children}
    </blockquote>
  ),
  code: ({ className, children, ...props }) => {
    const isInline = !className;
    if (isInline) {
      return (
        <code className="px-1.5 py-0.5 text-xs font-mono bg-blue-50 text-blue-700 rounded border border-blue-100" {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className={`${className || ''} text-xs`} {...props}>{children}</code>
    );
  },
  pre: ({ children, ...props }) => (
    <pre className="my-4 p-4 bg-[#1e293b] rounded-xl overflow-x-auto text-sm leading-relaxed shadow-sm" {...props}>
      {children}
    </pre>
  ),
  table: ({ children, ...props }) => (
    <div className="my-4 rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      <table className="w-full text-sm" {...props}>{children}</table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead className="bg-gray-50/80" {...props}>{children}</thead>
  ),
  th: ({ children, ...props }) => (
    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider" {...props}>{children}</th>
  ),
  td: ({ children, ...props }) => (
    <td className="px-4 py-2.5 text-sm text-gray-600 border-t border-gray-100" {...props}>{children}</td>
  ),
  hr: (props) => (
    <hr className="my-6 border-none h-px bg-gradient-to-r from-transparent via-gray-200 to-transparent" {...props} />
  ),
  a: ({ children, ...props }) => (
    <a className="text-blue-600 hover:text-blue-700 underline underline-offset-2 decoration-blue-300 hover:decoration-blue-500 transition-colors" {...props}>
      {children}
    </a>
  ),
};

// ─── Main Component ───────────────────────────────────────────────────────────

export default function TabScenes() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const { message, modal } = App.useApp();
  
  // State
  const [availableScenes, setAvailableScenes] = useState<SceneDefinition[]>([]);
  const [selectedScenes, setSelectedScenes] = useState<string[]>([]);
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingContent, setEditingContent] = useState<string>('');
  const [hasChanges, setHasChanges] = useState(false);
  const [editMode, setEditMode] = useState<'edit' | 'preview'>('edit');
  
  // Create modal
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);
  
  // Quick-edit modal
  const [quickEditVisible, setQuickEditVisible] = useState(false);
  const [quickEditType, setQuickEditType] = useState<'tools' | 'priority' | 'keywords'>('tools');
  const [quickEditForm] = Form.useForm();

  // Sync selected scenes from appInfo
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

  useEffect(() => {
    loadScenes();
  }, []);

  const loadScenes = async () => {
    setLoading(true);
    try {
      const scenes = await sceneApi.list();
      setAvailableScenes(scenes);
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

  const activeScene = availableScenes.find(s => s.scene_id === activeSceneId);
  
  const parsedContent = useMemo(() => {
    return parseFrontMatter(editingContent);
  }, [editingContent]);

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

  const handleContentChange = (value: string) => {
    setEditingContent(value);
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!activeSceneId) return;
    
    setSaving(true);
    try {
      await sceneApi.update(activeSceneId, {
        md_content: editingContent
      });
      
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

  const handleAddScene = () => {
    setCreateModalVisible(true);
    createForm.resetFields();
  };

  const handleCreateScene = async () => {
    try {
      const values = await createForm.validateFields();
      setCreating(true);
      
      const sceneId = values.scene_id.trim();
      const sceneName = values.scene_name.trim();
      const description = values.description?.trim() || '';
      
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

  const handleRefresh = () => {
    loadScenes();
    message.success(t('scene_refresh_success', '场景列表已刷新'));
  };

  const selectedSceneDetails = selectedScenes
    .map(id => availableScenes.find(s => s.scene_id === id))
    .filter(Boolean) as SceneDefinition[];

  // ─── Quick Edit Form Renderer ───────────────────────────────────────────────

  const renderQuickEditContent = () => {
    if (quickEditType === 'tools') {
      return (
        <Form form={quickEditForm} layout="vertical">
          <Form.Item 
            name="tools" 
            label={
              <span className="text-sm font-medium text-gray-700">
                {t('scene_tools', '允许的工具')}
              </span>
            }
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
            label={
              <span className="text-sm font-medium text-gray-700">
                {t('scene_priority', '优先级')}
              </span>
            }
            rules={[{ required: true }]}
          >
            <Select placeholder={t('scene_priority_placeholder', '选择优先级')}>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(p => (
                <Option key={p} value={p}>
                  <span className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${
                      p >= 8 ? 'bg-rose-500' : p >= 5 ? 'bg-amber-500' : 'bg-emerald-500'
                    }`} />
                    {p} {p === 10 ? '(最高)' : p === 1 ? '(最低)' : ''}
                  </span>
                </Option>
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
            label={
              <span className="text-sm font-medium text-gray-700">
                {t('scene_keywords', '触发关键词')}
              </span>
            }
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

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full w-full bg-[#f8f9fb]">
      {/* ─── Top Header Bar ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-6 py-3.5 border-b border-gray-200/70 bg-white sticky top-0 z-10">
        <div className="flex items-center gap-3.5">
          <div className="relative flex items-center justify-center w-9 h-9 rounded-[10px] bg-gradient-to-br from-blue-500 to-indigo-600 shadow-md shadow-blue-500/25">
            <ThunderboltOutlined className="text-white text-base" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <h2 className="text-[15px] font-semibold text-gray-900 leading-tight">
                {t('scene_config_title', '场景配置')}
              </h2>
              {selectedScenes.length > 0 && (
                <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[11px] font-semibold text-blue-600 bg-blue-50 rounded-md">
                  {selectedScenes.length}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 leading-tight mt-0.5">
              {t('scene_config_subtitle', '管理应用的智能场景定义')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Tooltip title={t('scene_refresh', '刷新')}>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={handleRefresh}
              loading={loading}
              size="small"
              className="!border-gray-200 hover:!border-gray-300 hover:!bg-gray-50 transition-all"
            />
          </Tooltip>
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={handleAddScene}
            size="small"
            className="!bg-gradient-to-r !from-blue-500 !to-indigo-600 !border-0 !shadow-md !shadow-blue-500/20 hover:!shadow-blue-500/30 !transition-all !h-8 !px-3.5 !text-[13px]"
          >
            {t('scene_add', '添加场景')}
          </Button>
        </div>
      </div>

      {/* ─── Main Content ──────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {selectedSceneDetails.length === 0 ? (
          /* ─── Empty State ──────────────────────────────────────────────── */
          <div className="flex-1 flex items-center justify-center p-8">
            <div className="text-center max-w-sm">
              {/* Decorative illustration */}
              <div className="relative w-32 h-32 mx-auto mb-6">
                <div className="absolute inset-0 bg-gradient-to-br from-blue-100 to-indigo-100 rounded-[28px] rotate-6 opacity-60" />
                <div className="relative w-full h-full bg-gradient-to-br from-blue-50 to-indigo-50 rounded-[28px] flex items-center justify-center border border-blue-100/50">
                  <div className="relative">
                    <FolderOutlined className="text-5xl text-blue-300" />
                    <div className="absolute -bottom-1 -right-2 w-6 h-6 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center shadow-sm">
                      <PlusOutlined className="text-white text-[10px]" />
                    </div>
                  </div>
                </div>
              </div>
              <p className="text-gray-600 text-base font-medium mb-1.5">
                {t('scene_empty_desc', '暂无配置的场景')}
              </p>
              <p className="text-gray-400 text-sm mb-6 leading-relaxed">
                {t('scene_empty_hint', '添加场景以扩展应用的智能处理能力')}
              </p>
              <Button 
                type="primary" 
                size="large"
                icon={<PlusOutlined />} 
                onClick={handleAddScene}
                className="!bg-gradient-to-r !from-blue-500 !to-indigo-600 !border-0 !shadow-lg !shadow-blue-500/25 hover:!shadow-blue-500/35 !transition-all !h-10 !px-6 !rounded-xl !text-sm !font-medium"
              >
                {t('scene_add_first', '添加第一个场景')}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {/* ─── Left Sidebar: File Browser ──────────────────────────────── */}
            <div className="w-72 border-r border-gray-200/70 bg-white flex flex-col">
              {/* Sidebar header */}
              <div className="px-4 py-2.5 border-b border-gray-100">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-gray-400 font-semibold uppercase tracking-widest">
                    {t('scene_file_list', '场景文件')}
                  </span>
                  <span className="text-[11px] text-gray-400 tabular-nums">
                    {selectedSceneDetails.length} {selectedSceneDetails.length === 1 ? 'file' : 'files'}
                  </span>
                </div>
              </div>
              
              {/* File list */}
              <div className="flex-1 overflow-y-auto py-1.5 px-2">
                {selectedSceneDetails.map((scene) => {
                  const isActive = scene.scene_id === activeSceneId;
                  const iconCfg = getIconConfig(scene.scene_id);
                  const fileName = `${scene.scene_id}.md`;
                  
                  return (
                    <div
                      key={scene.scene_id}
                      onClick={() => handleSceneChange(scene.scene_id)}
                      className={`
                        group relative flex items-center gap-2.5 px-2.5 py-2.5 rounded-lg cursor-pointer mb-0.5
                        transition-all duration-150 ease-out
                        ${isActive 
                          ? 'bg-blue-50/80 shadow-[inset_0_0_0_1px_rgba(59,130,246,0.15)]' 
                          : 'hover:bg-gray-50'
                        }
                      `}
                    >
                      {/* Active indicator bar */}
                      {isActive && (
                        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-blue-500" />
                      )}
                      
                      {/* Icon */}
                      <div className={`
                        flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-sm
                        transition-all duration-150
                        ${isActive 
                          ? `bg-gradient-to-br ${iconCfg.activeBg} text-white shadow-sm` 
                          : `${iconCfg.bg} ${iconCfg.color}`
                        }
                      `}>
                        {iconCfg.icon}
                      </div>
                      
                      {/* File info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className={`
                            font-mono text-[13px] leading-tight truncate
                            ${isActive ? 'text-blue-700 font-semibold' : 'text-gray-700 font-medium'}
                          `}>
                            {fileName}
                          </span>
                          {isActive && hasChanges && (
                            <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse" />
                          )}
                        </div>
                        <p className={`text-[11px] truncate mt-0.5 leading-tight ${isActive ? 'text-blue-500/70' : 'text-gray-400'}`}>
                          {scene.scene_name}
                          {scene.description && ` \u00B7 ${scene.description}`}
                        </p>
                      </div>
                      
                      {/* Delete button on hover */}
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
                        <button
                          className="flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-red-50 text-gray-300 hover:text-red-500 transition-all"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <DeleteOutlined className="text-xs" />
                        </button>
                      </Popconfirm>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ─── Right: Editor Area ──────────────────────────────────────── */}
            <div className="flex-1 flex flex-col bg-[#f8f9fb] min-w-0">
              {activeScene ? (
                <>
                  {/* ─── Editor Toolbar ─────────────────────────────────────── */}
                  <div className="flex items-center justify-between px-5 py-2.5 border-b border-gray-200/70 bg-white">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      {/* Current file identifier */}
                      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-50 rounded-md border border-gray-100 flex-shrink-0">
                        <FileMarkdownOutlined className="text-gray-400 text-xs" />
                        <span className="font-mono text-[12px] font-medium text-gray-600">
                          {activeScene.scene_id}.md
                        </span>
                      </div>
                      
                      <span className="text-gray-300">|</span>
                      
                      {/* Quick-edit chips */}
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button 
                          onClick={() => openQuickEdit('tools')}
                          className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-gray-500 hover:text-blue-600 bg-gray-50 hover:bg-blue-50 rounded-md border border-gray-100 hover:border-blue-200 transition-all"
                        >
                          <ToolOutlined className="text-[10px]" />
                          {parsedContent.frontMatter.allow_tools?.length || 0} tools
                        </button>
                        <button 
                          onClick={() => openQuickEdit('priority')}
                          className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-gray-500 hover:text-blue-600 bg-gray-50 hover:bg-blue-50 rounded-md border border-gray-100 hover:border-blue-200 transition-all"
                        >
                          <NumberOutlined className="text-[10px]" />
                          P{parsedContent.frontMatter.priority || 5}
                        </button>
                        <button 
                          onClick={() => openQuickEdit('keywords')}
                          className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-gray-500 hover:text-blue-600 bg-gray-50 hover:bg-blue-50 rounded-md border border-gray-100 hover:border-blue-200 transition-all"
                        >
                          <TagOutlined className="text-[10px]" />
                          {parsedContent.frontMatter.keywords?.length || 0} kw
                        </button>
                      </div>
                      
                      {hasChanges && (
                        <Tag 
                          className="!m-0 !bg-amber-50 !text-amber-600 !border-amber-200 !text-[11px] !px-2 !py-0 !rounded-md !leading-5 flex-shrink-0"
                        >
                          <WarningOutlined className="mr-1 text-[10px]" />
                          {t('scene_unsaved', '未保存')}
                        </Tag>
                      )}
                    </div>
                    
                    <div className="flex items-center gap-2.5 flex-shrink-0 ml-3">
                      <Segmented
                        size="small"
                        value={editMode}
                        onChange={(val) => setEditMode(val as 'edit' | 'preview')}
                        options={[
                          {
                            label: (
                              <span className="flex items-center gap-1 px-0.5">
                                <EditOutlined className="text-[11px]" />
                                <span className="text-[12px]">{t('edit', '编辑')}</span>
                              </span>
                            ),
                            value: 'edit',
                          },
                          {
                            label: (
                              <span className="flex items-center gap-1 px-0.5">
                                <EyeOutlined className="text-[11px]" />
                                <span className="text-[12px]">{t('preview', '预览')}</span>
                              </span>
                            ),
                            value: 'preview',
                          },
                        ]}
                      />
                      <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        size="small"
                        loading={saving}
                        disabled={!hasChanges}
                        onClick={handleSave}
                        className="!bg-gradient-to-r !from-emerald-500 !to-green-600 !border-0 !shadow-md !shadow-emerald-500/20 hover:!shadow-emerald-500/30 !transition-all !h-7 !text-[12px]"
                      >
                        {t('save', '保存')}
                      </Button>
                    </div>
                  </div>

                  {/* ─── Editor Content ─────────────────────────────────────── */}
                  <div className="flex-1 overflow-hidden">
                    {editMode === 'edit' ? (
                      <div className="h-full p-4">
                        <div className="h-full rounded-xl overflow-hidden border border-gray-200/70 bg-white shadow-sm">
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
                        <div className="max-w-3xl mx-auto space-y-5">
                          {/* Front Matter card */}
                          {Object.keys(parsedContent.frontMatter).length > 0 && (
                            <div className="rounded-xl border border-gray-200/70 bg-white shadow-sm overflow-hidden">
                              <div className="px-4 py-2.5 bg-gray-50/80 border-b border-gray-100 flex items-center gap-2">
                                <InfoCircleOutlined className="text-gray-400 text-xs" />
                                <span className="text-[12px] font-semibold text-gray-500 uppercase tracking-wider">Front Matter</span>
                              </div>
                              <div className="p-4">
                                <div className="grid grid-cols-2 gap-3">
                                  {Object.entries(parsedContent.frontMatter).map(([key, value]) => (
                                    <div key={key} className="flex flex-col gap-0.5">
                                      <span className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">{key}</span>
                                      <span className="text-sm text-gray-700 font-mono">
                                        {Array.isArray(value) ? (
                                          <span className="flex flex-wrap gap-1">
                                            {value.map((v: string, i: number) => (
                                              <span key={i} className="inline-flex px-1.5 py-0.5 text-[11px] bg-blue-50 text-blue-600 rounded border border-blue-100">
                                                {v}
                                              </span>
                                            ))}
                                          </span>
                                        ) : String(value)}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          )}
                          
                          {/* Markdown body */}
                          <div className="rounded-xl border border-gray-200/70 bg-white shadow-sm p-6 md:p-8">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm, remarkBreaks]}
                              rehypePlugins={[rehypeRaw, rehypeHighlight]}
                              components={sceneMarkdownComponents}
                            >
                              {parsedContent.body}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* ─── Status Bar ─────────────────────────────────────────── */}
                  <div className="px-5 py-2 border-t border-gray-200/70 bg-white flex items-center justify-between">
                    <div className="flex items-center gap-5 text-[11px] text-gray-400">
                      <span className="flex items-center gap-1.5 tabular-nums">
                        <FileTextOutlined className="text-[10px]" />
                        {editingContent.length.toLocaleString()} chars
                      </span>
                      <span className="flex items-center gap-1.5 tabular-nums">
                        <CodeOutlined className="text-[10px]" />
                        {editingContent.split('\n').length} lines
                      </span>
                      {parsedContent.frontMatter.allow_tools && (
                        <span className="flex items-center gap-1.5">
                          <ToolOutlined className="text-[10px]" />
                          {parsedContent.frontMatter.allow_tools.length} tools
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
                      {hasChanges ? (
                        <>
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                          <span className="text-amber-500">{t('scene_modified', '已修改')}</span>
                        </>
                      ) : (
                        <>
                          <CheckCircleOutlined className="text-emerald-500 text-[10px]" />
                          <span className="text-emerald-500">{t('scene_saved', '已保存')}</span>
                        </>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                /* No scene selected placeholder */
                <div className="flex-1 flex flex-col items-center justify-center">
                  <div className="w-20 h-20 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
                    <FileMarkdownOutlined className="text-3xl text-gray-300" />
                  </div>
                  <p className="text-gray-400 text-sm font-medium">
                    {t('scene_select_tip', '请从左侧选择一个场景文件')}
                  </p>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ─── Create Scene Modal ──────────────────────────────────────────────── */}
      <Modal
        title={
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-sm shadow-blue-500/20">
              <PlusOutlined className="text-white text-sm" />
            </div>
            <div>
              <span className="font-semibold text-[15px] text-gray-900">{t('scene_create_title', '添加新场景')}</span>
              <p className="text-xs text-gray-400 font-normal mt-0.5">{t('scene_create_subtitle', '创建新的智能场景定义文件')}</p>
            </div>
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
        okButtonProps={{
          className: '!bg-gradient-to-r !from-blue-500 !to-indigo-600 !border-0 !shadow-md !shadow-blue-500/20',
        }}
      >
        <div className="mt-5 mb-1">
          <Form form={createForm} layout="vertical" requiredMark={false}>
            <Form.Item
              name="scene_id"
              label={
                <span className="text-sm font-medium text-gray-700">
                  {t('scene_id', '场景ID')}
                  <span className="text-gray-400 font-normal text-xs ml-1.5">({t('scene_id_hint', '将作为文件名')})</span>
                </span>
              }
              rules={[
                { required: true, message: t('scene_id_required', '请输入场景ID') },
                { pattern: /^[a-z0-9_-]+$/, message: t('scene_id_pattern', '只能使用小写字母、数字、下划线和横线') }
              ]}
            >
              <Input 
                placeholder={t('scene_id_placeholder', '如: code-review, data-analysis')}
                prefix={<FileTextOutlined className="text-gray-300" />}
                suffix={<span className="text-gray-300 text-xs font-mono">.md</span>}
                className="!font-mono"
              />
            </Form.Item>
            <Form.Item
              name="scene_name"
              label={<span className="text-sm font-medium text-gray-700">{t('scene_name', '场景名称')}</span>}
              rules={[{ required: true, message: t('scene_name_required', '请输入场景名称') }]}
            >
              <Input 
                placeholder={t('scene_name_placeholder', '如: 代码评审、数据分析')}
              />
            </Form.Item>
            <Form.Item
              name="description"
              label={
                <span className="text-sm font-medium text-gray-700">
                  {t('scene_description', '场景描述')}
                  <span className="text-gray-400 font-normal text-xs ml-1.5">({t('optional', '选填')})</span>
                </span>
              }
            >
              <TextArea 
                placeholder={t('scene_description_placeholder', '简要描述这个场景的用途')}
                rows={3}
                className="!resize-none"
              />
            </Form.Item>
          </Form>
        </div>
      </Modal>

      {/* ─── Quick Edit Modal ───────────────────────────────────────────────── */}
      <Modal
        title={
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-[10px] flex items-center justify-center shadow-sm ${
              quickEditType === 'tools' 
                ? 'bg-gradient-to-br from-violet-500 to-purple-600 shadow-violet-500/20' 
                : quickEditType === 'priority'
                ? 'bg-gradient-to-br from-amber-500 to-orange-600 shadow-amber-500/20'
                : 'bg-gradient-to-br from-emerald-500 to-green-600 shadow-emerald-500/20'
            }`}>
              {quickEditType === 'tools' && <ToolOutlined className="text-white text-sm" />}
              {quickEditType === 'priority' && <NumberOutlined className="text-white text-sm" />}
              {quickEditType === 'keywords' && <TagOutlined className="text-white text-sm" />}
            </div>
            <span className="font-semibold text-[15px] text-gray-900">
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
        okButtonProps={{
          className: `!border-0 !shadow-md ${
            quickEditType === 'tools' 
              ? '!bg-gradient-to-r !from-violet-500 !to-purple-600 !shadow-violet-500/20' 
              : quickEditType === 'priority'
              ? '!bg-gradient-to-r !from-amber-500 !to-orange-600 !shadow-amber-500/20'
              : '!bg-gradient-to-r !from-emerald-500 !to-green-600 !shadow-emerald-500/20'
          }`,
        }}
      >
        <div className="mt-4">
          {renderQuickEditContent()}
        </div>
      </Modal>
    </div>
  );
}
