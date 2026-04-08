// app
export type AgentVersion = 'v1' | 'v2';

// =============================================================================
// 分布式执行配置类型
// =============================================================================

/**
 * 存储后端类型
 */
export type StorageBackend = 'memory' | 'file' | 'redis' | 'database';

/**
 * 存储配置
 */
export interface StorageConfig {
  backend: StorageBackend;
  redis_url?: string;
  database_url?: string;
  file_path?: string;
}

/**
 * 负载均衡策略
 */
export type LoadBalanceStrategy = 'round_robin' | 'least_loaded' | 'random' | 'weighted';

/**
 * Worker池配置
 */
export interface WorkerPoolConfig {
  enabled: boolean;
  min_workers: number;
  max_workers: number;
  max_tasks_per_worker: number;
  auto_scale: boolean;
  load_balance: LoadBalanceStrategy;
}

/**
 * 监控配置
 */
export interface MonitoringConfig {
  enabled: boolean;
  websocket_enabled: boolean;
  max_history_events: number;
}

/**
 * 子Agent分布式执行配置
 */
export interface SubagentDistributedConfig {
  max_instances?: number;
  timeout?: number;
  retry_count?: number;
  interactive?: boolean;
}

/**
 * 资源Agent (子Agent绑定)
 */
export interface ResourceAgent {
  type: string;
  name: string;
  value: string;
  distributed_config?: SubagentDistributedConfig;
}

/**
 * 子Agent配置
 */
export interface SubagentConfig {
  name: string;
  description: string;
  max_instances: number;
  timeout?: number;
  retry_count?: number;
  interactive?: boolean;
}

/**
 * 首页场景入驻配置
 */
export interface HomeSceneConfig {
  /** 是否入驻首页 */
  featured: boolean;
  /** 排序位置（越小越靠前） */
  position?: number;
  /** antd 图标名称，如 "HeartOutlined" */
  icon_type?: string;
  /** 渐变背景色，如 "from-blue-400 to-blue-500" */
  bg_color?: string;
}

/**
 * 扩展配置 - 分布式执行设置
 */
export interface ExtConfig {
  storage?: StorageConfig;
  worker_pool?: WorkerPoolConfig;
  monitoring?: MonitoringConfig;
  subagents?: SubagentConfig[];
  /** 首页场景入驻配置 */
  home_scene?: HomeSceneConfig;
}

// =============================================================================
// Agent 运行时配置类型
// =============================================================================

/**
 * Doom Loop 检测配置
 */
export interface DoomLoopConfig {
  /** 启用 Doom Loop 检测 */
  enabled: boolean;
  /** 触发检测的连续相同调用次数阈值 */
  threshold: number;
  /** 历史记录最大保留数量 */
  max_history_size: number;
  /** 调用记录过期时间（秒） */
  expiry_seconds: number;
}

/**
 * Agent Loop 执行配置
 */
export interface AgentLoopConfig {
  /** 最大迭代次数 */
  max_iterations: number;
  /** 启用重试 */
  enable_retry: boolean;
  /** 最大重试次数 */
  max_retries: number;
  /** 每轮超时时间（秒） */
  iteration_timeout: number;
}

/**
 * Layer 1 - 截断配置
 */
export interface TruncationConfig {
  /** 最大输出行数 */
  max_output_lines: number;
  /** 最大输出字节数 */
  max_output_bytes: number;
}

/**
 * Layer 2 - 剪枝配置
 */
export interface PruningConfig {
  /** 启用自适应剪枝 */
  enable_adaptive_pruning: boolean;
  /** 保护 Token 数 */
  prune_protect_tokens: number;
  /** 最少保留消息数 */
  min_messages_keep: number;
  /** 低使用率触发阈值 */
  prune_trigger_low_usage: number;
  /** 中使用率触发阈值 */
  prune_trigger_medium_usage: number;
  /** 高使用率触发阈值 */
  prune_trigger_high_usage: number;
  /** 低使用率剪枝间隔 */
  prune_interval_low_usage: number;
  /** 中使用率剪枝间隔 */
  prune_interval_medium_usage: number;
  /** 高使用率剪枝间隔 */
  prune_interval_high_usage: number;
  /** 自适应检查间隔 */
  adaptive_check_interval: number;
  /** 自适应增长阈值 */
  adaptive_growth_threshold: number;
}

/**
 * Layer 3 - 压缩配置
 */
export interface CompactionConfig {
  /** 上下文窗口大小 */
  context_window: number;
  /** 压缩触发阈值比例 */
  compaction_threshold_ratio: number;
  /** 保留最近消息数 */
  recent_messages_keep: number;
  /** 每章最大消息数 */
  chapter_max_messages: number;
  /** 章节摘要最大 Token 数 */
  chapter_summary_max_tokens: number;
  /** 内存中最大章节数 */
  max_chapters_in_memory: number;
}

/**
 * Layer 4 - 多轮对话历史压缩配置
 */
export interface Layer4Config {
  /** 启用第四层压缩 */
  enable_layer4_compression: boolean;
  /** 压缩前保留的最大轮数 */
  max_rounds_before_compression: number;
  /** 最大保留总轮数 */
  max_total_rounds: number;
  /** 触发压缩的 Token 阈值 */
  layer4_compression_token_threshold: number;
}

/**
 * 内容保护配置
 */
export interface ContentProtectionConfig {
  /** 代码块保护 */
  code_block_protection: boolean;
  /** 思维链保护 */
  thinking_chain_protection: boolean;
  /** 文件路径保护 */
  file_path_protection: boolean;
  /** 最大保护块数 */
  max_protected_blocks: number;
}

/**
 * Work Log 压缩配置 - 整合四层压缩
 */
export interface WorkLogCompressionConfig {
  /** 启用压缩 */
  enabled: boolean;
  /** Layer 1 - 截断配置 */
  truncation: TruncationConfig;
  /** Layer 2 - 剪枝配置 */
  pruning: PruningConfig;
  /** Layer 3 - 压缩配置 */
  compaction: CompactionConfig;
  /** Layer 4 - 多轮历史配置 */
  layer4: Layer4Config;
  /** 内容保护配置 */
  content_protection: ContentProtectionConfig;
}

/**
 * Agent 运行时配置 - 整合所有 Agent 运行相关配置
 */
export interface AgentRuntimeConfig {
  /** Doom Loop 检测配置 */
  doom_loop: DoomLoopConfig;
  /** Agent Loop 执行配置 */
  loop: AgentLoopConfig;
  /** Work Log 压缩配置 */
  work_log_compression: WorkLogCompressionConfig;
}

/**
 * 默认 Doom Loop 配置
 */
export const DEFAULT_DOOM_LOOP_CONFIG: DoomLoopConfig = {
  enabled: true,
  threshold: 3,
  max_history_size: 100,
  expiry_seconds: 300,
};

/**
 * 默认 Agent Loop 配置
 */
export const DEFAULT_AGENT_LOOP_CONFIG: AgentLoopConfig = {
  max_iterations: 300,
  enable_retry: true,
  max_retries: 3,
  iteration_timeout: 300,
};

/**
 * 默认 Work Log 压缩配置
 */
export const DEFAULT_WORK_LOG_COMPRESSION_CONFIG: WorkLogCompressionConfig = {
  enabled: true,
  truncation: {
    max_output_lines: 2000,
    max_output_bytes: 51200,
  },
  pruning: {
    enable_adaptive_pruning: true,
    prune_protect_tokens: 10000,
    min_messages_keep: 20,
    prune_trigger_low_usage: 0.3,
    prune_trigger_medium_usage: 0.6,
    prune_trigger_high_usage: 0.8,
    prune_interval_low_usage: 15,
    prune_interval_medium_usage: 8,
    prune_interval_high_usage: 3,
    adaptive_check_interval: 5,
    adaptive_growth_threshold: 0.15,
  },
  compaction: {
    context_window: 128000,
    compaction_threshold_ratio: 0.8,
    recent_messages_keep: 5,
    chapter_max_messages: 100,
    chapter_summary_max_tokens: 2000,
    max_chapters_in_memory: 3,
  },
  layer4: {
    enable_layer4_compression: true,
    max_rounds_before_compression: 3,
    max_total_rounds: 10,
    layer4_compression_token_threshold: 8000,
  },
  content_protection: {
    code_block_protection: true,
    thinking_chain_protection: true,
    file_path_protection: true,
    max_protected_blocks: 10,
  },
};

/**
 * 默认 Agent 运行时配置
 */
export const DEFAULT_AGENT_RUNTIME_CONFIG: AgentRuntimeConfig = {
  doom_loop: DEFAULT_DOOM_LOOP_CONFIG,
  loop: DEFAULT_AGENT_LOOP_CONFIG,
  work_log_compression: DEFAULT_WORK_LOG_COMPRESSION_CONFIG,
};

export type IApp = {
  app_code: string;
  /**
   * Agent 版本 (v1: 经典版, v2: Core_v2)
   */
  agent_version?: AgentVersion;
  /**
   * 应用名
   */
  app_name: string;
  /**
   * 应用描述信息/简介
   */
  app_describe: string;
  /**
   * 语言/prompt关联
   */
  language: 'en' | 'zh';
  /**
   * 组织模式（AutoPlan/LayOut）
   */
  team_mode: string;
  /**
   * 组织上下文/ None
   */
  team_context: Record<string, any>;
  /**
   * 应用节点信息
   */
  details?: IDetail[];
  /**
   * 是否已收藏
   */
  is_collected: string;
  /**
   * 是否已发布
   */
  updated_at: string;
  hot_value: number;
  owner_name?: string;
  owner_avatar_url?: string;
  published?: string;
  param_need: ParamNeed[];
  recommend_questions?: Record<string, any>[];
  conv_uid?: string;
  layout?: {
    chat_layout: {
      name: string;
      [key: string]: string;
    };
    chat_in_layout: Array<{
      param_type: string;
      param_description: string;
      param_default_value: string;
      [key: string]: any;
    }>;
  };
  config_code?: string;
  icon?: string; // 添加icon字段
  /**
   * LLM配置信息
   */
  llm_config?: {
    llm_strategy?: string;
    llm_strategy_value?: string[];
  };
  /**
   * 绑定的场景文件ID列表
   */
  scenes?: string[];
  /**
   * 扩展配置 - 分布式执行设置
   */
  ext_config?: ExtConfig;
  /**
   * 子Agent资源绑定
   */
  resource_agent?: ResourceAgent[];
  /**
   * Agent 运行时配置
   */
  runtime_config?: AgentRuntimeConfig;
};

export type IAppData = {
  app_list: IApp[];
  current_page: number;
  total_count: number;
  total_page: number;
};

// agent
export type AgentParams = {
  agent_name: string;
  node_id: string;
  /**
   * Agent绑定的资源
   */
  resources: string;
  /**
   * Agent的绑定模板
   */
  prompt_template: string;
  /**
   * llm的使用策略，默认是priority
   */
  llm_strategy: string;
  /**
   * 策略包含的参数
   */
  llm_strategy_value: string;
};

export type IAgent = {
  describe?: string;
  name: string;
  system_message?: string;
  label?: string;
  desc?: string;
};

export type ITeamModal = {
  auto_plan: string;
  awel_layout: string;
  singe_agent: string;
};

export type IResource = {
  is_dynamic?: boolean;
  name?: string;
  type?: string;
  value?: string;
};

export type IDetail = {
  agent_name?: string;
  app_code?: string;
  llm_strategy?: string;
  llm_strategy_value?: string;
  resources?: IResource[];
  key?: string;
  prompt_template?: string;
  recommend_questions?: string[];
};

export interface GetAppInfoParams {
  chat_scene?: string;
  config_code?: string;
  app_code: string;
  building_mode?: boolean;
}

export interface TeamMode {
  name: string;
  value: string;
  name_cn: string;
  name_en: string;
  description: string;
  description_en: string;
  remark: string;
}

export interface CreateAppParams {
  app_describe?: string;
  app_name?: string;
  team_mode?: string;
  app_code?: string;
  details?: IDetail[];
  language?: 'zh' | 'en';
  recommend_questions?: [];
  team_context?: Record<string, any>;
  param_need?: ParamNeed[];
  icon?: string;
  agent_version?: AgentVersion;
  ext_config?: ExtConfig;
  runtime_config?: AgentRuntimeConfig;
}

export interface AppListResponse {
  total_count: number;
  app_list: IApp[];
  current_page: number;
  total_page: number;
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export interface StrategyResponse extends Omit<TeamMode, 'remark'> {}

export interface ParamNeed {
  type: string;
  value: any;
  bind_value?: string;
}

export interface NativeAppScenesResponse {
  chat_scene: string;
  scene_name: string;
  param_need: ParamNeed[];
}
