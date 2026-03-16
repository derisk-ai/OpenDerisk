import axios from 'axios';

const API_BASE = '/api/v1';

export interface ModelConfig {
  provider: string;
  model_id: string;
  api_key?: string;
  base_url?: string;
  temperature: number;
  max_tokens: number;
}

export interface PermissionConfig {
  default_action: string;
  rules: Record<string, string>;
}

export interface AgentConfig {
  name: string;
  description: string;
  max_steps: number;
  color: string;
  permission: PermissionConfig;
}

export interface SandboxConfig {
  enabled: boolean;
  image: string;
  memory_limit: string;
  timeout: number;
  network_enabled: boolean;
}

export interface OAuth2ProviderConfig {
  id: string;
  type: 'github' | 'custom';
  client_id: string;
  client_secret: string;
  authorization_url?: string;
  token_url?: string;
  userinfo_url?: string;
  scope?: string;
}

export interface OAuth2Config {
  enabled: boolean;
  providers: OAuth2ProviderConfig[];
  admin_users?: string[];
}

export interface AppConfig {
  name: string;
  version: string;
  default_model: ModelConfig;
  agents: Record<string, AgentConfig>;
  sandbox: SandboxConfig;
  oauth2?: OAuth2Config;
  workspace: string;
  log_level: string;
  server: {
    host: string;
    port: number;
  };
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  risk: string;
  requires_permission: boolean;
  examples: string[];
}

class ConfigService {
  async getConfig(): Promise<AppConfig> {
    const response = await axios.get(`${API_BASE}/config/current`);
    return response.data.data;
  }

  async getConfigSchema(): Promise<Record<string, any>> {
    const response = await axios.get(`${API_BASE}/config/schema`);
    return response.data.data;
  }

  async updateModelConfig(config: Partial<ModelConfig>): Promise<ModelConfig> {
    const response = await axios.post(`${API_BASE}/config/model`, config);
    return response.data.data;
  }

  async getAgents(): Promise<AgentConfig[]> {
    const response = await axios.get(`${API_BASE}/config/agents`);
    return response.data.data;
  }

  async getAgent(name: string): Promise<AgentConfig> {
    const response = await axios.get(`${API_BASE}/config/agents/${name}`);
    return response.data.data;
  }

  async createAgent(agent: Partial<AgentConfig>): Promise<AgentConfig> {
    const response = await axios.post(`${API_BASE}/config/agents`, agent);
    return response.data.data;
  }

  async updateAgent(name: string, config: Partial<AgentConfig>): Promise<AgentConfig> {
    const response = await axios.put(`${API_BASE}/config/agents/${name}`, config);
    return response.data.data;
  }

  async deleteAgent(name: string): Promise<void> {
    await axios.delete(`${API_BASE}/config/agents/${name}`);
  }

  async getSandboxConfig(): Promise<SandboxConfig> {
    const response = await axios.get(`${API_BASE}/config/sandbox`);
    return response.data.data;
  }

  async updateSandboxConfig(config: Partial<SandboxConfig>): Promise<SandboxConfig> {
    const response = await axios.post(`${API_BASE}/config/sandbox`, config);
    return response.data.data;
  }

  async validateConfig(): Promise<{ valid: boolean; warnings: Array<{ level: string; message: string }> }> {
    const response = await axios.post(`${API_BASE}/config/validate`);
    return response.data.data;
  }

  async reloadConfig(): Promise<AppConfig> {
    const response = await axios.post(`${API_BASE}/config/reload`);
    return response.data.data;
  }

  async exportConfig(): Promise<AppConfig> {
    const response = await axios.get(`${API_BASE}/config/export`);
    return response.data.data;
  }

  async importConfig(config: AppConfig): Promise<AppConfig> {
    const response = await axios.post(`${API_BASE}/config/import`, config);
    return response.data.data;
  }

  async getOAuth2Config(): Promise<OAuth2Config> {
    const response = await axios.get(`${API_BASE}/config/oauth2`);
    return response.data.data;
  }

  async updateOAuth2Config(config: OAuth2Config): Promise<OAuth2Config> {
    const response = await axios.post(`${API_BASE}/config/oauth2`, config);
    return response.data.data;
  }
}

class ToolsService {
  async listTools(): Promise<ToolInfo[]> {
    const response = await axios.get(`${API_BASE}/tools/list`);
    return response.data.data;
  }

  async getToolSchemas(): Promise<Record<string, any>> {
    const response = await axios.get(`${API_BASE}/tools/schemas`);
    return response.data.data;
  }

  async executeTool(toolName: string, args: Record<string, any>): Promise<any> {
    const response = await axios.post(`${API_BASE}/tools/execute`, {
      tool_name: toolName,
      args,
    });
    return response.data.data;
  }

  async batchExecute(calls: Array<{ tool: string; args: Record<string, any> }>, failFast = false): Promise<any> {
    const response = await axios.post(`${API_BASE}/tools/batch`, {
      calls,
      fail_fast: failFast,
    });
    return response.data.data;
  }

  async checkPermission(toolName: string, args?: Record<string, any>): Promise<{ allowed: boolean; action: string; message?: string }> {
    const response = await axios.post(`${API_BASE}/tools/permission/check`, {
      tool_name: toolName,
      args,
    });
    return response.data.data;
  }

  async getPermissionPresets(): Promise<Record<string, any>> {
    const response = await axios.get(`${API_BASE}/tools/permission/presets`);
    return response.data.data;
  }

  async getSandboxStatus(): Promise<{ docker_available: boolean; recommended: string }> {
    const response = await axios.get(`${API_BASE}/tools/sandbox/status`);
    return response.data.data;
  }
}

export const configService = new ConfigService();
export const toolsService = new ToolsService();