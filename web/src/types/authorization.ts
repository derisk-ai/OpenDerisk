/**
 * Authorization Type Definitions - Unified Tool Authorization System
 *
 * TypeScript equivalents of the Python models in derisk/core/authorization/model.py
 */

import type { ToolMetadata } from './tool';

// ========== Enums ==========

/**
 * Permission action types.
 */
export const PermissionAction = {
  ALLOW: 'allow',
  DENY: 'deny',
  ASK: 'ask',
} as const;
export type PermissionAction =
  (typeof PermissionAction)[keyof typeof PermissionAction];

/**
 * Authorization modes for different security levels.
 */
export const AuthorizationMode = {
  /** Strict mode: follow tool definitions */
  STRICT: 'strict',
  /** Moderate mode: can override tool definitions */
  MODERATE: 'moderate',
  /** Permissive mode: default allow */
  PERMISSIVE: 'permissive',
  /** Unrestricted mode: skip all checks */
  UNRESTRICTED: 'unrestricted',
} as const;
export type AuthorizationMode =
  (typeof AuthorizationMode)[keyof typeof AuthorizationMode];

/**
 * LLM judgment policy for authorization decisions.
 */
export const LLMJudgmentPolicy = {
  /** Disable LLM judgment */
  DISABLED: 'disabled',
  /** Conservative: tend to ask */
  CONSERVATIVE: 'conservative',
  /** Balanced: neutral judgment */
  BALANCED: 'balanced',
  /** Aggressive: tend to allow */
  AGGRESSIVE: 'aggressive',
} as const;
export type LLMJudgmentPolicy =
  (typeof LLMJudgmentPolicy)[keyof typeof LLMJudgmentPolicy];

// ========== Interfaces ==========

/**
 * Permission rule for fine-grained access control.
 * Rules are evaluated in priority order (lower number = higher priority).
 */
export interface PermissionRule {
  /** Unique rule identifier */
  id: string;
  /** Rule name */
  name: string;
  /** Rule description */
  description?: string;
  /** Tool name pattern (supports wildcards) */
  tool_pattern: string;
  /** Category filter */
  category_filter?: string;
  /** Risk level filter */
  risk_level_filter?: string;
  /** Parameter conditions for matching */
  parameter_conditions: Record<string, unknown>;
  /** Action to take when matched */
  action: PermissionAction;
  /** Priority (lower = higher priority) */
  priority: number;
  /** Whether rule is enabled */
  enabled: boolean;
  /** Time range for rule activation */
  time_range?: {
    start: string;
    end: string;
  };
}

/**
 * Permission ruleset - a collection of rules.
 * Rules are evaluated in priority order. First matching rule wins.
 */
export interface PermissionRuleset {
  /** Ruleset identifier */
  id: string;
  /** Ruleset name */
  name: string;
  /** Ruleset description */
  description?: string;
  /** Rules list (sorted by priority) */
  rules: PermissionRule[];
  /** Default action when no rule matches */
  default_action: PermissionAction;
}

/**
 * Authorization configuration for an agent or session.
 */
export interface AuthorizationConfig {
  /** Authorization mode */
  mode: AuthorizationMode;
  /** Permission ruleset */
  ruleset?: PermissionRuleset;
  /** LLM judgment policy */
  llm_policy: LLMJudgmentPolicy;
  /** Custom LLM prompt */
  llm_prompt?: string;
  /** Tool-level overrides (highest priority after blacklist) */
  tool_overrides: Record<string, PermissionAction>;
  /** Whitelist tools (skip authorization) */
  whitelist_tools: string[];
  /** Blacklist tools (deny execution) */
  blacklist_tools: string[];
  /** Session-level authorization cache enabled */
  session_cache_enabled: boolean;
  /** Session cache TTL in seconds */
  session_cache_ttl: number;
  /** Authorization timeout in seconds */
  authorization_timeout: number;
  /** User confirmation callback function name */
  user_confirmation_callback?: string;
}

/**
 * Authorization decision result.
 */
export interface AuthorizationDecision {
  /** Whether authorization was granted */
  authorized: boolean;
  /** The action taken */
  action: PermissionAction;
  /** Reason for the decision */
  reason?: string;
  /** Which rule matched (if any) */
  matched_rule?: string;
  /** Whether this was from cache */
  from_cache: boolean;
  /** Cache expiration time (ISO date string) */
  cache_expires_at?: string;
}

/**
 * Authorization request for a tool execution.
 */
export interface AuthorizationRequest {
  /** Tool name */
  tool_name: string;
  /** Tool metadata */
  tool_metadata?: ToolMetadata;
  /** Tool arguments */
  arguments: Record<string, unknown>;
  /** Session ID */
  session_id?: string;
  /** Agent name */
  agent_name?: string;
  /** Execution ID */
  execution_id?: string;
}

// ========== Default Configurations ==========

/**
 * Strict authorization configuration.
 */
export const STRICT_CONFIG: AuthorizationConfig = {
  mode: AuthorizationMode.STRICT,
  llm_policy: LLMJudgmentPolicy.DISABLED,
  tool_overrides: {},
  whitelist_tools: [],
  blacklist_tools: [],
  session_cache_enabled: true,
  session_cache_ttl: 3600,
  authorization_timeout: 300,
};

/**
 * Permissive authorization configuration.
 */
export const PERMISSIVE_CONFIG: AuthorizationConfig = {
  mode: AuthorizationMode.PERMISSIVE,
  llm_policy: LLMJudgmentPolicy.DISABLED,
  tool_overrides: {},
  whitelist_tools: [],
  blacklist_tools: [],
  session_cache_enabled: true,
  session_cache_ttl: 3600,
  authorization_timeout: 300,
};

/**
 * Unrestricted authorization configuration.
 */
export const UNRESTRICTED_CONFIG: AuthorizationConfig = {
  mode: AuthorizationMode.UNRESTRICTED,
  llm_policy: LLMJudgmentPolicy.DISABLED,
  tool_overrides: {},
  whitelist_tools: [],
  blacklist_tools: [],
  session_cache_enabled: false,
  session_cache_ttl: 0,
  authorization_timeout: 300,
};

/**
 * Create a read-only ruleset that only allows read operations.
 */
export const READ_ONLY_RULESET: PermissionRuleset = {
  id: 'read_only',
  name: 'Read-Only Ruleset',
  rules: [
    {
      id: 'rule_read',
      name: 'Allow read operations',
      tool_pattern: 'read*',
      parameter_conditions: {},
      action: PermissionAction.ALLOW,
      priority: 10,
      enabled: true,
    },
    {
      id: 'rule_glob',
      name: 'Allow glob',
      tool_pattern: 'glob',
      parameter_conditions: {},
      action: PermissionAction.ALLOW,
      priority: 20,
      enabled: true,
    },
    {
      id: 'rule_grep',
      name: 'Allow grep',
      tool_pattern: 'grep',
      parameter_conditions: {},
      action: PermissionAction.ALLOW,
      priority: 30,
      enabled: true,
    },
    {
      id: 'rule_search',
      name: 'Allow search operations',
      tool_pattern: 'search*',
      parameter_conditions: {},
      action: PermissionAction.ALLOW,
      priority: 40,
      enabled: true,
    },
    {
      id: 'rule_list',
      name: 'Allow list operations',
      tool_pattern: 'list*',
      parameter_conditions: {},
      action: PermissionAction.ALLOW,
      priority: 50,
      enabled: true,
    },
    {
      id: 'rule_get',
      name: 'Allow get operations',
      tool_pattern: 'get*',
      parameter_conditions: {},
      action: PermissionAction.ALLOW,
      priority: 60,
      enabled: true,
    },
    {
      id: 'rule_deny_all',
      name: 'Deny all other operations',
      tool_pattern: '*',
      parameter_conditions: {},
      action: PermissionAction.DENY,
      priority: 1000,
      enabled: true,
    },
  ],
  default_action: PermissionAction.DENY,
};
