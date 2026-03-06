/**
 * Tools API - 工具API客户端
 * 
 * 提供前端调用的工具API：
 * - 工具列表查询（分类展示）
 * - 工具详情获取
 * - 工具与应用关联
 * - 工具配置管理
 */

import { GET, POST, DELETE } from '../index';

const TOOLS_BASE = '/api/tools';

// ========== Types ==========

export type ToolVisibility = 'public' | 'private' | 'system';
export type ToolStatus = 'active' | 'disabled' | 'deprecated';

export interface ToolResource {
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
  visibility: ToolVisibility;
  status: ToolStatus;
  owner?: string;
  input_schema: Record<string, any>;
  output_schema: Record<string, any>;
  examples: Record<string, any>[];
  timeout: number;
  execution_mode: string;
  app_ids: string[];
  created_at: string;
  updated_at: string;
  call_count: number;
  success_count: number;
}

export interface ToolCategoryGroup {
  category: string;
  display_name: string;
  description: string;
  icon?: string;
  tools: ToolResource[];
  count: number;
}

export interface ToolListResponse {
  success: boolean;
  total: number;
  categories: ToolCategoryGroup[];
}

export interface ToolResponse<T = any> {
  success: boolean;
  message?: string;
  data?: T;
}

export interface ToolOverview {
  total: number;
  by_category: Record<string, number>;
  by_source: Record<string, number>;
  by_risk_level: Record<string, number>;
  categories: Array<{
    name: string;
    display_name: string;
    count: number;
  }>;
}

// ========== API Functions ==========

/**
 * 按分类获取工具列表
 */
export const getToolsByCategory = (params?: {
  include_empty?: boolean;
  visibility?: string;
  status?: string;
}) => {
  const query = new URLSearchParams();
  if (params?.include_empty) query.set('include_empty', 'true');
  if (params?.visibility) query.set('visibility', params.visibility);
  if (params?.status) query.set('status', params.status);
  
  return GET<null, ToolListResponse>(`${TOOLS_BASE}/categories?${query.toString()}`);
};

/**
 * 获取工具列表（扁平结构）
 */
export const listAllTools = (params?: {
  category?: string;
  source?: string;
  query?: string;
}) => {
  const query = new URLSearchParams();
  if (params?.category) query.set('category', params.category);
  if (params?.source) query.set('source', params.source);
  if (params?.query) query.set('query', params.query);
  
  return GET<null, ToolResponse<ToolResource[]>>(`${TOOLS_BASE}/list?${query.toString()}`);
};

/**
 * 搜索工具
 */
export const searchTools = (params: {
  q: string;
  category?: string;
  tags?: string;
}) => {
  const query = new URLSearchParams();
  query.set('q', params.q);
  if (params.category) query.set('category', params.category);
  if (params.tags) query.set('tags', params.tags);
  
  return GET<null, ToolResponse<ToolResource[]>>(`${TOOLS_BASE}/search?${query.toString()}`);
};

/**
 * 获取工具详情
 */
export const getToolDetail = (toolId: string) => {
  return GET<null, ToolResponse<ToolResource>>(`${TOOLS_BASE}/${toolId}`);
};

/**
 * 获取工具的输入输出Schema
 */
export const getToolSchema = (toolId: string) => {
  return GET<null, ToolResponse<{
    tool_id: string;
    name: string;
    input_schema: Record<string, any>;
    output_schema: Record<string, any>;
    examples: Record<string, any>[];
  }>>(`${TOOLS_BASE}/schema/${toolId}`);
};

/**
 * 关联工具到应用
 */
export const associateToolToApp = (data: {
  tool_id: string;
  app_id: string;
}) => {
  return POST<typeof data, ToolResponse>(`${TOOLS_BASE}/associate`, data);
};

/**
 * 解除工具与应用的关联
 */
export const dissociateToolFromApp = (data: {
  tool_id: string;
  app_id: string;
}) => {
  return DELETE<typeof data, ToolResponse>(`${TOOLS_BASE}/associate`, data);
};

/**
 * 获取应用关联的工具列表
 */
export const getAppTools = (appId: string) => {
  return GET<null, ToolResponse<ToolResource[]>>(`${TOOLS_BASE}/app/${appId}`);
};

/**
 * 更新工具配置
 */
export const updateTool = (data: {
  tool_id: string;
  status?: string;
  visibility?: string;
  owner?: string;
}) => {
  return POST<typeof data, ToolResponse>(`${TOOLS_BASE}/update`, data);
};

/**
 * 获取工具概览
 */
export const getToolOverview = () => {
  return GET<null, ToolResponse<ToolOverview>>(`${TOOLS_BASE}/overview`);
};

// ========== 兼容旧API ==========

/**
 * 列出本地工具（兼容旧API）
 */
export const listLocalTools = () => {
  return GET<null, ToolResponse<ToolResource[]>>(`${TOOLS_BASE}/list/local`);
};

/**
 * 列出内置工具（兼容旧API）
 */
export const listBuiltinTools = () => {
  return GET<null, ToolResponse<ToolResource[]>>(`${TOOLS_BASE}/list/builtin`);
};

// ========== Resource Tool 格式转换 ==========

/**
 * 将ToolResource转换为resource_tool格式
 */
export const toResourceToolFormat = (tool: ToolResource) => {
  return {
    type: `tool(${tool.source})`,
    name: tool.display_name || tool.name,
    value: JSON.stringify({
      key: tool.tool_id,
      name: tool.name,
      display_name: tool.display_name,
      description: tool.description,
      category: tool.category,
      source: tool.source,
      tool_id: tool.tool_id,
    }),
  };
};

/**
 * 从resource_tool格式解析ToolResource信息
 */
export const fromResourceToolFormat = (resourceTool: any): Partial<ToolResource> => {
  try {
    const parsed = JSON.parse(resourceTool.value || '{}');
    return {
      tool_id: parsed.tool_id || parsed.key,
      name: parsed.name,
      display_name: parsed.display_name || parsed.name,
      description: parsed.description || '',
      category: parsed.category,
      source: parsed.source,
    };
  } catch {
    return {
      tool_id: resourceTool.name,
      name: resourceTool.name,
    };
  }
};

/**
 * 批量检查工具是否已关联到应用
 */
export const checkToolsAssociated = (
  tools: ToolResource[],
  resourceTools: Array<{ type: string; name: string; value: string }>
): Record<string, boolean> => {
  const associatedIds = new Set<string>();
  
  resourceTools.forEach(rt => {
    const parsed = fromResourceToolFormat(rt);
    if (parsed.tool_id) {
      associatedIds.add(parsed.tool_id);
    }
  });
  
  const result: Record<string, boolean> = {};
  tools.forEach(tool => {
    result[tool.tool_id] = associatedIds.has(tool.tool_id);
  });
  
  return result;
};

export default {
  getToolsByCategory,
  listAllTools,
  searchTools,
  getToolDetail,
  getToolSchema,
  associateToolToApp,
  dissociateToolFromApp,
  getAppTools,
  updateTool,
  getToolOverview,
  listLocalTools,
  listBuiltinTools,
  toResourceToolFormat,
  fromResourceToolFormat,
  checkToolsAssociated,
};