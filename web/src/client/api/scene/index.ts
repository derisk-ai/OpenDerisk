/**
 * 场景管理 API 客户端
 * 提供场景的 CRUD 操作和管理功能
 * 
 * 场景定义支持 YAML Front Matter 格式：
 * ```markdown
 * ---
 * id: scene-id
 * name: 场景名称
 * description: 场景描述
 * priority: 5
 * keywords: ["keyword1", "keyword2"]
 * allow_tools: ["read", "write", "edit"]
 * ---
 * 
 * ## 角色设定
 * ...
 * ```
 */

import { ins as request } from '../index';

/**
 * 场景定义
 * 支持 YAML Front Matter 格式的 Markdown 内容
 */
export interface SceneDefinition {
  scene_id: string;
  scene_name: string;
  description: string;
  trigger_keywords: string[];
  trigger_priority: number;
  scene_role_prompt: string;
  scene_tools: string[];
  created_at: string;
  updated_at: string;
  md_content?: string;
}

/**
 * YAML Front Matter 解析结果
 */
export interface ParsedFrontMatter {
  id?: string;
  name?: string;
  description?: string;
  priority?: number;
  keywords?: string[];
  allow_tools?: string[];
  [key: string]: any;
}

/**
 * 解析后的 Markdown 内容
 */
export interface ParsedSceneContent {
  frontMatter: ParsedFrontMatter;
  body: string;
}

/**
 * 场景创建请求
 */
export interface SceneCreateRequest {
  scene_id: string;
  scene_name: string;
  description?: string;
  trigger_keywords?: string[];
  trigger_priority?: number;
  scene_role_prompt?: string;
  scene_tools?: string[];
  md_content?: string;
}

/**
 * 场景更新请求
 */
export interface SceneUpdateRequest {
  scene_name?: string;
  description?: string;
  trigger_keywords?: string[];
  trigger_priority?: number;
  scene_role_prompt?: string;
  scene_tools?: string[];
  md_content?: string;
}

/**
 * 场景激活请求
 */
export interface SceneActivateRequest {
  session_id: string;
  agent_id: string;
}

/**
 * 场景切换请求
 */
export interface SceneSwitchRequest {
  session_id: string;
  agent_id: string;
  from_scene?: string;
  to_scene: string;
  reason?: string;
}

/**
 * 场景 Prompt 注入请求
 */
export interface ScenePromptInjectionRequest {
  session_id: string;
  scene_ids: string[];
  inject_mode?: 'append' | 'prepend' | 'replace';
}

/**
 * 场景 Prompt 注入响应
 */
export interface ScenePromptInjectionResponse {
  success: boolean;
  session_id: string;
  injected_scenes: string[];
  system_prompt: string;
  message: string;
}

/**
 * 会话场景 Prompt 响应
 */
export interface SessionScenePromptResponse {
  has_prompt: boolean;
  system_prompt: string | null;
  injected_scenes: string[];
  injected_at?: string;
  inject_mode?: string;
}

export const sceneApi = {
  /**
   * 列出所有场景
   */
  list: async (skip = 0, limit = 100): Promise<SceneDefinition[]> => {
    const response = await request.get('/api/scenes', {
      params: { skip, limit },
    });
    return response.data;
  },

  /**
   * 获取场景详情
   */
  get: async (sceneId: string): Promise<SceneDefinition> => {
    const response = await request.get(`/api/scenes/${sceneId}`);
    return response.data;
  },

  /**
   * 创建场景
   */
  create: async (data: SceneCreateRequest): Promise<SceneDefinition> => {
    const response = await request.post('/api/scenes', data);
    return response.data;
  },

  /**
   * 更新场景
   */
  update: async (sceneId: string, data: SceneUpdateRequest): Promise<SceneDefinition> => {
    const response = await request.put(`/api/scenes/${sceneId}`, data);
    return response.data;
  },

  /**
   * 删除场景
   */
  delete: async (sceneId: string): Promise<{ success: boolean; message: string }> => {
    const response = await request.delete(`/api/scenes/${sceneId}`);
    return response.data;
  },

  /**
   * 激活场景
   */
  activate: async (data: SceneActivateRequest): Promise<any> => {
    const response = await request.post('/api/scenes/activate', data);
    return response.data;
  },

  /**
   * 切换场景
   */
  switch: async (data: SceneSwitchRequest): Promise<any> => {
    const response = await request.post('/api/scenes/switch', data);
    return response.data;
  },

  /**
   * 获取场景切换历史
   */
  getHistory: async (sessionId: string): Promise<any[]> => {
    const response = await request.get(`/api/scenes/history/${sessionId}`);
    return response.data.history;
  },

  /**
   * 将场景注入到 System Prompt
   * 自动将场景定义转换为 System Prompt 并注入到会话中
   */
  injectPrompt: async (data: ScenePromptInjectionRequest): Promise<ScenePromptInjectionResponse> => {
    const response = await request.post('/api/scenes/inject-prompt', data);
    return response.data;
  },

  /**
   * 获取会话的场景 System Prompt
   */
  getSessionPrompt: async (sessionId: string): Promise<SessionScenePromptResponse> => {
    const response = await request.get(`/api/scenes/prompt/${sessionId}`);
    return response.data;
  },
};

/**
 * 解析 Markdown 内容的 YAML Front Matter
 * @param content Markdown 内容
 * @returns 解析结果，包含 frontMatter 和 body
 */
export function parseFrontMatter(content: string): ParsedSceneContent {
  const result: ParsedSceneContent = {
    frontMatter: {},
    body: content
  };

  const match = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
  if (!match) {
    return result;
  }

  const yamlContent = match[1];
  const body = match[2];
  const frontMatter: ParsedFrontMatter = {};

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
      } else if (!isNaN(Number(value))) {
        value = Number(value);
      }

      frontMatter[key] = value;
    }
  });

  result.frontMatter = frontMatter;
  result.body = body;
  return result;
}

/**
 * 生成带 YAML Front Matter 的 Markdown 内容
 * @param frontMatter front matter 对象
 * @param body 正文内容
 * @returns 完整的 Markdown 内容
 */
export function generateFrontMatterContent(
  frontMatter: ParsedFrontMatter, 
  body: string
): string {
  const yamlLines = Object.entries(frontMatter).map(([key, value]) => {
    if (Array.isArray(value)) {
      return `${key}: [${value.join(', ')}]`;
    } else if (typeof value === 'string' && (value.includes(':') || value.includes('"'))) {
      return `${key}: "${value.replace(/"/g, '\\"')}"`;
    }
    return `${key}: ${value}`;
  });

  return `---\n${yamlLines.join('\n')}\n---\n\n${body.trim()}\n`;
}

export default sceneApi;