'use client';

import { useContext, useMemo, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequest } from 'ahooks';
import { Input, Spin, Tag, Tooltip, Dropdown, Collapse, Badge, Empty, message } from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  PlusOutlined,
  CheckCircleFilled,
  ToolOutlined,
  FileTextOutlined,
  CodeOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ApiOutlined,
  SearchOutlined as SearchIcon,
  InteractionOutlined,
  BarChartOutlined,
  ThunderboltOutlined,
  AppstoreOutlined,
  SafetyOutlined,
  SettingOutlined,
  GlobalOutlined,
  DesktopOutlined,
  RightOutlined,
  FilterOutlined,
} from '@ant-design/icons';

import { AppContext } from '@/contexts';
import {
  getToolsByCategory,
  toResourceToolFormat,
  ToolResource,
  ToolCategoryGroup,
} from '@/client/api/tools/v2';

// 图标映射
const CATEGORY_ICONS: Record<string, any> = {
  builtin: AppstoreOutlined,
  file_system: FileTextOutlined,
  code: CodeOutlined,
  shell: DesktopOutlined,
  sandbox: SafetyOutlined,
  user_interaction: InteractionOutlined,
  visualization: BarChartOutlined,
  network: GlobalOutlined,
  database: DatabaseOutlined,
  api: ApiOutlined,
  mcp: CloudServerOutlined,
  search: SearchIcon,
  analysis: BarChartOutlined,
  reasoning: ThunderboltOutlined,
  utility: SettingOutlined,
  plugin: AppstoreOutlined,
  custom: ToolOutlined,
};

// 风险等级颜色
const RISK_COLORS: Record<string, string> = {
  safe: 'green',
  low: 'green',
  medium: 'orange',
  high: 'red',
  critical: 'red',
};

// 来源标签
const SOURCE_TAGS: Record<string, { label: string; color: string }> = {
  core: { label: 'CORE', color: 'blue' },
  system: { label: 'SYSTEM', color: 'blue' },
  extension: { label: 'EXT', color: 'purple' },
  user: { label: 'CUSTOM', color: 'orange' },
  mcp: { label: 'MCP', color: 'purple' },
  api: { label: 'API', color: 'cyan' },
  agent: { label: 'AGENT', color: 'geekblue' },
};

export default function TabTools() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');
  const [expandedCategories, setExpandedCategories] = useState<string[]>([]);
  const [togglingTools, setTogglingTools] = useState<Set<string>>(new Set());

  // 获取分类工具列表
  const { data: toolsData, loading, refresh } = useRequest(
    async () => await getToolsByCategory({ include_empty: false }),
    { refreshDeps: [] }
  );

  // 获取已关联的工具ID集合
  const associatedToolIds = useMemo(() => {
    const ids = new Set<string>();
    (appInfo?.resource_tool || []).forEach((item: any) => {
      try {
        const parsed = JSON.parse(item.value || '{}');
        if (parsed.tool_id || parsed.key) {
          ids.add(parsed.tool_id || parsed.key);
        }
      } catch {
        // ignore
      }
    });
    return ids;
  }, [appInfo?.resource_tool]);

  // 过滤工具
  const filteredCategories = useMemo(() => {
    if (!toolsData?.categories) return [];
    
    if (!searchValue) return toolsData.categories;
    
    const lower = searchValue.toLowerCase();
    
    return toolsData.categories
      .map(category => ({
        ...category,
        tools: category.tools.filter(
          tool =>
            tool.name.toLowerCase().includes(lower) ||
            tool.display_name.toLowerCase().includes(lower) ||
            tool.description.toLowerCase().includes(lower) ||
            tool.tags.some(tag => tag.toLowerCase().includes(lower))
        ),
      }))
      .filter(category => category.tools.length > 0);
  }, [toolsData, searchValue]);

  // 处理工具关联/取消关联
  const handleToggle = useCallback(
    async (tool: ToolResource) => {
      const toolId = tool.tool_id;
      const isAssociated = associatedToolIds.has(toolId);
      
      // 防止重复点击
      if (togglingTools.has(toolId)) return;
      setTogglingTools(prev => new Set(prev).add(toolId));
      
      try {
        let updatedTools: any[];
        
        if (isAssociated) {
          // 取消关联
          updatedTools = (appInfo.resource_tool || []).filter((item: any) => {
            try {
              const parsed = JSON.parse(item.value || '{}');
              return (parsed.tool_id || parsed.key) !== toolId;
            } catch {
              return true;
            }
          });
          message.success(t('builder_tool_disassociated') || '工具已取消关联');
        } else {
          // 添加关联
          const newTool = toResourceToolFormat(tool);
          updatedTools = [...(appInfo.resource_tool || []), newTool];
          message.success(t('builder_tool_associated') || '工具已关联');
        }
        
        await fetchUpdateApp({ ...appInfo, resource_tool: updatedTools });
      } catch (error) {
        message.error(t('builder_tool_toggle_error') || '操作失败');
      } finally {
        setTogglingTools(prev => {
          const next = new Set(prev);
          next.delete(toolId);
          return next;
        });
      }
    },
    [appInfo, associatedToolIds, togglingTools, fetchUpdateApp, t]
  );

  // 切换分类展开状态
  const toggleCategory = (category: string) => {
    setExpandedCategories(prev =>
      prev.includes(category)
        ? prev.filter(c => c !== category)
        : [...prev, category]
    );
  };

  // 展开所有分类
  const expandAll = () => {
    setExpandedCategories(filteredCategories.map(c => c.category));
  };

  // 折叠所有分类
  const collapseAll = () => {
    setExpandedCategories([]);
  };

  // 创建新工具菜单
  const createMenuItems = [
    {
      key: 'skill',
      icon: <ThunderboltOutlined className="text-blue-500" />,
      label: (
        <div className="flex flex-col py-0.5">
          <span className="text-[13px] font-medium text-gray-700">
            {t('builder_create_skill')}
          </span>
          <span className="text-[11px] text-gray-400">
            {t('builder_create_skill_desc')}
          </span>
        </div>
      ),
    },
    {
      key: 'mcp',
      icon: <ApiOutlined className="text-purple-500" />,
      label: (
        <div className="flex flex-col py-0.5">
          <span className="text-[13px] font-medium text-gray-700">
            {t('builder_create_mcp')}
          </span>
          <span className="text-[11px] text-gray-400">
            {t('builder_create_mcp_desc')}
          </span>
        </div>
      ),
    },
    {
      key: 'local',
      icon: <ToolOutlined className="text-green-500" />,
      label: (
        <div className="flex flex-col py-0.5">
          <span className="text-[13px] font-medium text-gray-700">
            {t('builder_create_local_tool') || '创建本地工具'}
          </span>
          <span className="text-[11px] text-gray-400">
            {t('builder_create_local_tool_desc') || '编写自定义工具函数'}
          </span>
        </div>
      ),
    },
  ];

  const handleCreateMenuClick = (e: any) => {
    switch (e.key) {
      case 'skill':
        window.open('/agent-skills', '_blank');
        break;
      case 'mcp':
        window.open('/mcp', '_blank');
        break;
      case 'local':
        window.open('/agent-skills?type=local', '_blank');
        break;
    }
  };

  // 统计信息
  const totalTools = toolsData?.total || 0;
  const associatedCount = associatedToolIds.size;

  return (
    <div className="flex-1 overflow-hidden flex flex-col h-full">
      {/* 搜索 + 操作栏 */}
      <div className="px-5 py-3 border-b border-gray-100/40 flex items-center gap-2">
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('builder_search_tools_placeholder') || '搜索工具...'}
          value={searchValue}
          onChange={e => setSearchValue(e.target.value)}
          allowClear
          className="rounded-lg h-9 flex-1"
        />
        <Tooltip title={t('builder_refresh')}>
          <button
            onClick={refresh}
            className="w-9 h-9 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all flex-shrink-0"
          >
            <ReloadOutlined className={`text-sm ${loading ? 'animate-spin' : ''}`} />
          </button>
        </Tooltip>
        <Dropdown
          menu={{ items: createMenuItems, onClick: handleCreateMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <button
            className="h-9 px-3 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-600 text-white text-[13px] font-medium shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/30 transition-all flex-shrink-0"
          >
            <PlusOutlined className="text-xs" />
            {t('builder_create_new')}
          </button>
        </Dropdown>
      </div>

      {/* 统计和操作栏 */}
      <div className="px-5 py-2 border-b border-gray-100/40 flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>
            {t('builder_tools_total') || '共'} <b className="text-gray-700">{totalTools}</b> {t('builder_tools_count') || '个工具'}
          </span>
          <span>
            {t('builder_tools_associated') || '已关联'} <b className="text-blue-600">{associatedCount}</b> {t('builder_tools_count') || '个'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={expandAll}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            {t('builder_expand_all') || '展开全部'}
          </button>
          <span className="text-gray-300">|</span>
          <button
            onClick={collapseAll}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            {t('builder_collapse_all') || '收起全部'}
          </button>
        </div>
      </div>

      {/* 分类工具列表 */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <Spin spinning={loading}>
          {filteredCategories.length > 0 ? (
            <div className="p-3">
              {filteredCategories.map(category => (
                <ToolCategorySection
                  key={category.category}
                  category={category}
                  expanded={expandedCategories.includes(category.category)}
                  associatedToolIds={associatedToolIds}
                  togglingTools={togglingTools}
                  onToggleCategory={() => toggleCategory(category.category)}
                  onToggleTool={handleToggle}
                  t={t}
                />
              ))}
            </div>
          ) : (
            !loading && (
              <Empty
                description={t('builder_no_tools') || '没有找到匹配的工具'}
                className="py-12"
              />
            )
          )}
        </Spin>
      </div>
    </div>
  );
}

// 工具分类区块组件
function ToolCategorySection({
  category,
  expanded,
  associatedToolIds,
  togglingTools,
  onToggleCategory,
  onToggleTool,
  t,
}: {
  category: ToolCategoryGroup;
  expanded: boolean;
  associatedToolIds: Set<string>;
  togglingTools: Set<string>;
  onToggleCategory: () => void;
  onToggleTool: (tool: ToolResource) => void;
  t: (key: string) => string;
}) {
  const Icon = CATEGORY_ICONS[category.category] || ToolOutlined;
  const associatedCount = category.tools.filter(t => associatedToolIds.has(t.tool_id)).length;

  return (
    <div className="mb-2 border border-gray-100/80 rounded-xl overflow-hidden">
      {/* 分类头部 */}
      <div
        className="flex items-center justify-between px-4 py-3 bg-gray-50/50 cursor-pointer hover:bg-gray-100/50 transition-colors"
        onClick={onToggleCategory}
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-white border border-gray-100 flex items-center justify-center">
            <Icon className="text-gray-500 text-base" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-medium text-gray-700">
                {category.display_name}
              </span>
              <Badge
                count={category.count}
                style={{ backgroundColor: '#6b7280' }}
                className="text-[10px]"
              />
            </div>
            {category.description && (
              <div className="text-[11px] text-gray-400 mt-0.5">
                {category.description}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {associatedCount > 0 && (
            <Tag color="blue" className="mr-0 text-[10px]">
              {associatedCount} {t('builder_selected') || '已选'}
            </Tag>
          )}
          <RightOutlined
            className={`text-gray-400 text-xs transition-transform ${
              expanded ? 'rotate-90' : ''
            }`}
          />
        </div>
      </div>

      {/* 工具列表 */}
      {expanded && (
        <div className="bg-white">
          {category.tools.map((tool, idx) => (
            <ToolItem
              key={tool.tool_id}
              tool={tool}
              isAssociated={associatedToolIds.has(tool.tool_id)}
              isToggling={togglingTools.has(tool.tool_id)}
              onToggle={() => onToggleTool(tool)}
              isLast={idx === category.tools.length - 1}
              t={t}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 单个工具项组件
function ToolItem({
  tool,
  isAssociated,
  isToggling,
  onToggle,
  isLast,
  t,
}: {
  tool: ToolResource;
  isAssociated: boolean;
  isToggling: boolean;
  onToggle: () => void;
  isLast: boolean;
  t: (key: string) => string;
}) {
  const sourceTag = SOURCE_TAGS[tool.source] || { label: tool.source.toUpperCase(), color: 'default' };
  const riskColor = RISK_COLORS[tool.risk_level] || 'default';

  return (
    <div
      className={`group flex items-center justify-between px-4 py-3 cursor-pointer transition-all ${
        isLast ? '' : 'border-b border-gray-50'
      } ${
        isAssociated
          ? 'bg-blue-50/30 hover:bg-blue-50/50'
          : 'hover:bg-gray-50/50'
      } ${isToggling ? 'opacity-50 pointer-events-none' : ''}`}
      onClick={onToggle}
    >
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <div
          className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
            isAssociated ? 'bg-blue-100' : 'bg-gray-100'
          }`}
        >
          <ToolOutlined
            className={`text-xs ${
              isAssociated ? 'text-blue-500' : 'text-gray-400'
            }`}
          />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-gray-700 truncate">
              {tool.display_name || tool.name}
            </span>
            <Tag
              className="mr-0 text-[10px] rounded border-0 px-1.5"
              color={sourceTag.color}
            >
              {sourceTag.label}
            </Tag>
            {tool.risk_level === 'high' || tool.risk_level === 'critical' ? (
              <Tooltip title={t('builder_tool_high_risk') || '高风险工具'}>
                <SafetyOutlined className="text-red-400 text-xs" />
              </Tooltip>
            ) : null}
          </div>
          <div className="text-[11px] text-gray-400 truncate mt-0.5">
            {tool.description}
          </div>
        </div>
      </div>
      {isAssociated && (
        <CheckCircleFilled className="text-blue-500 text-sm ml-2 flex-shrink-0" />
      )}
    </div>
  );
}