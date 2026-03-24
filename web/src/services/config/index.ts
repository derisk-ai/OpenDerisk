import { ins as axios } from '@/client/api';

const API_BASE = '/api/v1';

export interface DistributedConfig {
  enabled: boolean;
  redis_url: string;
  execution_ttl: number;
  heartbeat_interval: number;
}

export interface SystemConfig {
  language: string;
  log_level: string;
  api_keys: string[];
  encrypt_key_ref: string;
  distributed: DistributedConfig;
}

export interface DatabaseConfig {
  type: string;
  path: string;
  host: string;
  port: number;
  user: string;
  password_ref: string;
  name: string;
}

export interface WebServiceConfig {
  host: string;
  port: number;
  model_storage: string;
  web_url: string;
  database: DatabaseConfig;
}

export interface ModelConfig {
  provider: string;
  model_id: string;
  api_key?: string;
  base_url?: string;
  temperature: number;
  max_tokens: number;
}

export interface LLMModelConfig {
  name: string;
  temperature: number;
  max_new_tokens: number;
}

export interface LLMProviderConfig {
  provider: string;
  api_base: string;
  api_key_ref: string;
  models: LLMModelConfig[];
}

export interface AgentLLMConfig {
  temperature: number;
  providers: LLMProviderConfig[];
}

export interface SSEConfig {
  input_check_interval: number;
  notify_step_complete: boolean;
  max_wait_input_time: number;
}

export interface PermissionConfig {
  default_action: string;
  rules: Record<string, string>;
}

export interface AgentConfig {
  name: string;
  description: string;
  model?: ModelConfig;
  permission: PermissionConfig;
  max_steps: number;
  color: string;
  tools: string[];
  system_prompt?: string;
}

export interface SandboxConfig {
  enabled: boolean;
  type: string;
  image: string;
  memory_limit: string;
  timeout: number;
  network_enabled: boolean;
  work_dir: string;
}

export interface FileBackendConfig {
  type: string;
  storage_path: string;
  endpoint?: string;
  region?: string;
  access_key_ref: string;
  access_secret_ref: string;
  bucket: string;
}

export interface FileServiceConfig {
  enabled: boolean;
  default_backend: string;
  backends: FileBackendConfig[];
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

export interface SecretConfig {
  name: string;
  value: string;
  description: string;
  created_at?: string;
  updated_at?: string;
}

export interface SecretsConfig {
  secrets: Record<string, SecretConfig>;
}

export interface FeaturePluginEntry {
  enabled: boolean;
  settings: Record<string, unknown>;
}

export interface FeaturePluginCatalogItem {
  id: string;
  title: string;
  description: string;
  category: string;
  requires_restart: boolean;
  settings_schema: Record<string, unknown> | null;
  suggest_oauth2_admin: boolean;
  enabled: boolean;
  settings: Record<string, unknown>;
}

export interface AppConfig {
  name: string;
  version: string;
  system: SystemConfig;
  web: WebServiceConfig;
  default_model: ModelConfig;
  agent_llm: AgentLLMConfig;
  sse: SSEConfig;
  agents: Record<string, AgentConfig>;
  sandbox: SandboxConfig;
  file_service: FileServiceConfig;
  oauth2: OAuth2Config;
  feature_plugins?: Record<string, FeaturePluginEntry>;
  secrets: SecretsConfig;
  workspace: string;
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

  async updateSystemConfig(config: Partial<SystemConfig>): Promise<SystemConfig> {
    const response = await axios.post(`${API_BASE}/config/system`, config);
    return response.data.data;
  }

  async updateWebConfig(config: Partial<WebServiceConfig>): Promise<WebServiceConfig> {
    const response = await axios.post(`${API_BASE}/config/web`, config);
    return response.data.data;
  }

  async updateSandboxConfig(config: Partial<SandboxConfig>): Promise<SandboxConfig> {
    const response = await axios.post(`${API_BASE}/config/sandbox`, config);
    return response.data.data;
  }

  async updateFileServiceConfig(config: Partial<FileServiceConfig>): Promise<FileServiceConfig> {
    const response = await axios.post(`${API_BASE}/config/file-service`, config);
    return response.data.data;
  }

  async updateModelConfig(config: Partial<ModelConfig>): Promise<ModelConfig> {
    const response = await axios.post(`${API_BASE}/config/model`, config);
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

  async getFeaturePluginsCatalog(): Promise<FeaturePluginCatalogItem[]> {
    const response = await axios.get(`${API_BASE}/config/feature-plugins/catalog`);
    return response.data.data.items;
  }

  async getFeaturePluginsState(): Promise<Record<string, FeaturePluginEntry>> {
    const response = await axios.get(`${API_BASE}/config/feature-plugins`);
    return response.data.data;
  }

  async updateFeaturePlugin(body: {
    plugin_id: string;
    enabled?: boolean;
    settings?: Record<string, unknown>;
  }): Promise<FeaturePluginEntry> {
    const response = await axios.post(`${API_BASE}/config/feature-plugins`, body);
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

  async listSecrets(): Promise<Array<{ name: string; description: string; has_value: boolean; created_at?: string; updated_at?: string }>> {
    const response = await axios.get(`${API_BASE}/config/secrets`);
    return response.data.data;
  }

  async setSecret(name: string, value: string, description?: string): Promise<void> {
    await axios.post(`${API_BASE}/config/secrets`, { name, value, description });
  }

  async deleteSecret(name: string): Promise<void> {
    await axios.delete(`${API_BASE}/config/secrets/${name}`);
  }

  // LLM Key management
  async listLLMKeys(): Promise<Array<{
    provider: string;
    description: string;
    is_configured: boolean;
  }>> {
    const response = await axios.get(`${API_BASE}/config/llm-keys`);
    return response.data.data;
  }

  async setLLMKey(provider: string, apiKey: string): Promise<{
    success: boolean;
    message: string;
    provider: string;
    secret_name: string;
  }> {
    const response = await axios.post(`${API_BASE}/config/llm-keys`, {
      provider,
      api_key: apiKey,
    });
    return response.data;
  }

  async deleteLLMKey(provider: string): Promise<{
    success: boolean;
    message: string;
  }> {
    const response = await axios.delete(`${API_BASE}/config/llm-keys/${provider}`);
    return response.data;
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