/**
 * 统一应用服务
 * 
 * 提供统一的应用配置加载和管理接口
 */

import { GET, POST } from '@/client/api';

/**
 * 统一资源配置
 */
export interface UnifiedResource {
  type: string;
  name: string;
  config: Record<string, any>;
  version: string;
  metadata?: Record<string, any>;
}

/**
 * 统一应用配置
 */
export interface UnifiedAppConfig {
  appCode: string;
  appName: string;
  agentVersion: 'v1' | 'v2';
  teamMode: 'single_agent' | 'multi_agent';
  resources: UnifiedResource[];
  config: Record<string, any>;
  metadata?: Record<string, any>;
}

/**
 * 应用详情响应
 */
interface AppDetailResponse {
  app_code: string;
  app_name: string;
  app_desc?: string;
  team_mode?: string;
  agent_version?: string;
  resources?: any[];
  layout?: any;
  llm_strategy?: any;
  team_context?: any;
  config_code?: string;
  language?: string;
}

/**
 * 统一应用服务类
 */
export class UnifiedAppService {
  private configCache: Map<string, UnifiedAppConfig> = new Map();

  /**
   * 加载应用配置
   * 
   * @param appCode 应用代码
   * @param forceRefresh 是否强制刷新
   */
  async loadAppConfig(appCode: string, forceRefresh = false): Promise<UnifiedAppConfig> {
    if (!forceRefresh && this.configCache.has(appCode)) {
      return this.configCache.get(appCode)!;
    }

    const response = await GET<any, AppDetailResponse>(`/api/application/${appCode}`);

    const config: UnifiedAppConfig = {
      appCode: response.app_code,
      appName: response.app_name,
      agentVersion: this._detectAgentVersion(response),
      teamMode: this._normalizeTeamMode(response.team_mode),
      resources: this._normalizeResources(response.resources || []),
      config: this._extractConfig(response),
      metadata: {
        appDesc: response.app_desc,
        language: response.language,
        configCode: response.config_code,
      }
    };

    this.configCache.set(appCode, config);
    return config;
  }

  /**
   * 检测Agent版本
   */
  private _detectAgentVersion(response: AppDetailResponse): 'v1' | 'v2' {
    if (response.agent_version) {
      return response.agent_version as 'v1' | 'v2';
    }

    if (response.team_context) {
      const ctx = response.team_context;
      if (ctx.agent_version) {
        return ctx.agent_version as 'v1' | 'v2';
      }
    }

    return 'v2';
  }

  /**
   * 标准化Team模式
   */
  private _normalizeTeamMode(mode?: string): 'single_agent' | 'multi_agent' {
    if (mode === 'multi_agent' || mode === 'auto_plan') {
      return 'multi_agent';
    }
    return 'single_agent';
  }

  /**
   * 标准化资源列表
   */
  private _normalizeResources(resources: any[]): UnifiedResource[] {
    return resources.map(res => this._normalizeResource(res)).filter(Boolean) as UnifiedResource[];
  }

  /**
   * 标准化单个资源
   */
  private _normalizeResource(res: any): UnifiedResource | null {
    if (!res) return null;

    if (res.type && res.name) {
      return {
        type: res.type,
        name: res.name,
        config: res.value || res.config || {},
        version: res.version || 'v2',
        metadata: {
          id: res.id,
          description: res.description,
        }
      };
    }

    if (res.type) {
      return {
        type: res.type,
        name: res.name || 'unnamed',
        config: res.value || res.config || {},
        version: res.version || 'v2',
      };
    }

    return null;
  }

  /**
   * 提取配置
   */
  private _extractConfig(response: AppDetailResponse): Record<string, any> {
    return {
      appCode: response.app_code,
      appName: response.app_name,
      appDesc: response.app_desc || '',
      teamMode: response.team_mode || 'single_agent',
      language: response.language || 'en',
      llmStrategy: response.llm_strategy,
      layout: response.layout,
    };
  }

  /**
   * 清理缓存
   */
  clearCache(appCode?: string) {
    if (appCode) {
      this.configCache.delete(appCode);
    } else {
      this.configCache.clear();
    }
  }

  /**
   * 获取资源
   */
  getResourceByType(config: UnifiedAppConfig, type: string): UnifiedResource[] {
    return config.resources.filter(r => r.type === type);
  }

  /**
   * 获取工具资源
   */
  getTools(config: UnifiedAppConfig): UnifiedResource[] {
    return this.getResourceByType(config, 'tool');
  }

  /**
   * 获取知识库资源
   */
  getKnowledge(config: UnifiedAppConfig): UnifiedResource[] {
    return this.getResourceByType(config, 'knowledge');
  }

  /**
   * 获取技能资源
   */
  getSkills(config: UnifiedAppConfig): UnifiedResource[] {
    return this.getResourceByType(config, 'skill');
  }
}

// 单例实例
let unifiedAppServiceInstance: UnifiedAppService | null = null;

/**
 * 获取统一应用服务实例
 */
export function getUnifiedAppService(): UnifiedAppService {
  if (!unifiedAppServiceInstance) {
    unifiedAppServiceInstance = new UnifiedAppService();
  }
  return unifiedAppServiceInstance;
}