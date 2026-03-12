/**
 * Tools V2 API - 工具管理 API 客户端
 * 
 * 支持工具分组管理和 Agent 工具绑定配置
 */

import { GET, POST } from '../index';

const TOOLS_BASE = '/api/tools';

// ========== Types ==========

export type ToolBindingType = 'builtin_required' | 'builtin_optional' | 'custom' | 'external';

export interface ToolBinding {
  tool_id: string;
  binding_type: ToolBindingType;
  is_bound: boolean;
  is_default: boolean;
  can_unbind: boolean;
  disabled_at_runtime: boolean;
  bound_at?: string;
  unbound_at?: string;
  metadata?: Record<string, any>;
}

export interface ToolGroup {
  group_id: string;
  group_name: string;
  group_type: ToolBindingType;
  description: string;
  icon?: string;
  tools: ToolWithBinding[];
  count: number;
  is_collapsible: boolean;
  default_expanded: boolean;
  display_order: number;
}

export interface ToolWithBinding {
  tool_id: string;
  name: string;
  display_name: string;
  description: string;
  version: string;
  category: string;
  subcategory?: string;
  source: string;
  tags: string[];
  risk_level: string;
  requires_permission: boolean;
  input_schema: Record<string, any>;
  output_schema: Record<string, any>;
  examples: Record<string, any>[];
  timeout: number;
  author?: string;
  doc_url?: string;
  // 绑定状态
  binding?: ToolBinding;
  is_bound: boolean;
  is_default: boolean;
  can_unbind: boolean;
}

export interface AgentToolConfig {
  app_id: string;
  agent_name: string;
  bindings: Record<string, ToolBinding>;
  updated_at: string;
}

export interface RuntimeTool {
  tool_id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  source: string;
  risk_level: string;
}

export interface ToolBindingUpdateRequest {
  app_id: string;
  agent_name: string;
  tool_id: string;
  is_bound: boolean;
  disabled_at_runtime?: boolean;
}

export interface BatchToolBindingUpdateRequest {
  app_id: string;
  agent_name: string;
  bindings: Array<{
    tool_id: string;
    is_bound: boolean;
    disabled_at_runtime?: boolean;
  }>;
}

export interface RuntimeToolsRequest {
  app_id: string;
  agent_name: string;
  format_type?: 'openai' | 'anthropic';
}

// ========== API Functions ==========

/**
 * 获取工具分组列表
 */
export const getToolGroups = (params?: {
  app_id?: string;
  agent_name?: string;
  lang?: string;
  sandbox_enabled?: boolean;
}) => {
  const query = new URLSearchParams();
  if (params?.app_id) query.set('app_id', params.app_id);
  if (params?.agent_name) query.set('agent_name', params.agent_name);
  if (params?.lang) query.set('lang', params.lang);
  if (params?.sandbox_enabled !== undefined) query.set('sandbox_enabled', String(params.sandbox_enabled));
  
  return GET<null, { success: boolean; data: ToolGroup[] }>(
    `${TOOLS_BASE}/groups?${query.toString()}`
  );
};

/**
 * 获取 Agent 的工具配置
 */
export const getAgentToolConfig = (params: {
  app_id: string;
  agent_name: string;
}) => {
  const query = new URLSearchParams();
  query.set('app_id', params.app_id);
  query.set('agent_name', params.agent_name);
  
  return GET<null, { success: boolean; data: AgentToolConfig }>(
    `${TOOLS_BASE}/agent-config?${query.toString()}`
  );
};

/**
 * 更新单个工具绑定状态
 */
export const updateToolBinding = (data: ToolBindingUpdateRequest) => {
  return POST<ToolBindingUpdateRequest, { success: boolean; message?: string }>(
    `${TOOLS_BASE}/binding/update`,
    data
  );
};

/**
 * 批量更新工具绑定状态
 */
export const batchUpdateToolBindings = (data: BatchToolBindingUpdateRequest) => {
  return POST<BatchToolBindingUpdateRequest, { 
    success: boolean; 
    data?: {
      results: Array<{ tool_id: string; success: boolean }>;
      total: number;
      success_count: number;
    };
    message?: string;
  }>(`${TOOLS_BASE}/binding/batch-update`, data);
};

/**
 * 获取运行时工具列表
 */
export const getRuntimeTools = (data: RuntimeToolsRequest) => {
  return POST<RuntimeToolsRequest, { 
    success: boolean; 
    data?: {
      tools: RuntimeTool[];
      count: number;
    };
    message?: string;
  }>(`${TOOLS_BASE}/runtime-tools`, data);
};

/**
 * 获取运行时工具 Schema 列表
 */
export const getRuntimeToolSchemas = (data: RuntimeToolsRequest) => {
  return POST<RuntimeToolsRequest, { 
    success: boolean; 
    data?: {
      schemas: Record<string, any>[];
      count: number;
      format: string;
    };
    message?: string;
  }>(`${TOOLS_BASE}/runtime-schemas`, data);
};

/**
 * 清除工具配置缓存
 */
export const clearToolCache = (params?: {
  app_id?: string;
  agent_name?: string;
}) => {
  const query = new URLSearchParams();
  if (params?.app_id) query.set('app_id', params.app_id);
  if (params?.agent_name) query.set('agent_name', params.agent_name);
  
  return POST<null, { success: boolean; message?: string }>(
    `${TOOLS_BASE}/cache/clear?${query.toString()}`,
    null
  );
};

// ========== Helper Functions ==========

/**
 * 根据分组类型获取分组颜色
 */
export const getToolGroupColor = (groupType: ToolBindingType): string => {
  const colors: Record<ToolBindingType, string> = {
    builtin_required: 'blue',
    builtin_optional: 'cyan',
    custom: 'orange',
    external: 'purple',
  };
  return colors[groupType] || 'default';
};

/**
 * 根据分组类型获取分组图标
 */
export const getToolGroupIcon = (groupType: ToolBindingType): string => {
  const icons: Record<ToolBindingType, string> = {
    builtin_required: 'SafetyOutlined',
    builtin_optional: 'ToolOutlined',
    custom: 'AppstoreOutlined',
    external: 'CloudServerOutlined',
  };
  return icons[groupType] || 'ToolOutlined';
};

/**
 * 获取绑定状态文本
 */
export const getBindingStatusText = (
  binding: ToolBinding | undefined,
  t: (key: string) => string
): { text: string; color: string } => {
  if (!binding) {
    return { text: t('tool_status_unbound') || '未绑定', color: 'default' };
  }
  
  if (binding.is_default && binding.is_bound) {
    return { text: t('tool_status_default_bound') || '默认绑定', color: 'blue' };
  }
  
  if (binding.is_bound) {
    return { text: t('tool_status_bound') || '已绑定', color: 'green' };
  }
  
  if (binding.disabled_at_runtime) {
    return { text: t('tool_status_disabled') || '已禁用', color: 'red' };
  }
  
  return { text: t('tool_status_unbound') || '未绑定', color: 'default' };
};

export default {
  getToolGroups,
  getAgentToolConfig,
  updateToolBinding,
  batchUpdateToolBindings,
  getRuntimeTools,
  getRuntimeToolSchemas,
  clearToolCache,
  getToolGroupColor,
  getToolGroupIcon,
  getBindingStatusText,
};
