/**
 * Tool Type Definitions - Unified Tool Authorization System
 *
 * TypeScript equivalents of the Python models in derisk/core/tools/metadata.py
 */

// ========== Enums ==========

/**
 * Tool categories for classification and filtering.
 */
export const ToolCategory = {
  FILE_SYSTEM: 'file_system',
  SHELL: 'shell',
  NETWORK: 'network',
  CODE: 'code',
  DATA: 'data',
  AGENT: 'agent',
  INTERACTION: 'interaction',
  EXTERNAL: 'external',
  CUSTOM: 'custom',
} as const;
export type ToolCategory = (typeof ToolCategory)[keyof typeof ToolCategory];

/**
 * Risk levels for authorization decisions.
 */
export const RiskLevel = {
  SAFE: 'safe',
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical',
} as const;
export type RiskLevel = (typeof RiskLevel)[keyof typeof RiskLevel];

/**
 * Risk categories for fine-grained risk assessment.
 */
export const RiskCategory = {
  READ_ONLY: 'read_only',
  FILE_WRITE: 'file_write',
  FILE_DELETE: 'file_delete',
  SHELL_EXECUTE: 'shell_execute',
  NETWORK_OUTBOUND: 'network_outbound',
  DATA_MODIFY: 'data_modify',
  SYSTEM_CONFIG: 'system_config',
  PRIVILEGED: 'privileged',
} as const;
export type RiskCategory = (typeof RiskCategory)[keyof typeof RiskCategory];

// ========== Interfaces ==========

/**
 * Authorization requirements for a tool.
 * Defines when and how authorization should be requested for tool execution.
 */
export interface AuthorizationRequirement {
  /** Whether authorization is required */
  requires_authorization: boolean;
  /** Base risk level */
  risk_level: RiskLevel;
  /** Risk categories for detailed assessment */
  risk_categories: RiskCategory[];
  /** Custom authorization prompt template */
  authorization_prompt?: string;
  /** Parameters that contain sensitive data */
  sensitive_parameters: string[];
  /** Function reference for parameter-level risk assessment */
  parameter_risk_assessor?: string;
  /** Whitelist rules - skip authorization when matched */
  whitelist_rules: Record<string, unknown>[];
  /** Support session-level authorization grant */
  support_session_grant: boolean;
  /** Grant TTL in seconds, undefined means permanent */
  grant_ttl?: number;
}

/**
 * Tool parameter definition.
 * Defines the schema and validation rules for a tool parameter.
 */
export interface ToolParameter {
  /** Parameter name */
  name: string;
  /** Parameter type: string, number, boolean, object, array */
  type: string;
  /** Parameter description */
  description: string;
  /** Whether parameter is required */
  required: boolean;
  /** Default value */
  default?: unknown;
  /** Enumeration values */
  enum?: unknown[];
  /** Regex pattern for string validation */
  pattern?: string;
  /** Minimum value for numbers */
  min_value?: number;
  /** Maximum value for numbers */
  max_value?: number;
  /** Minimum length for strings/arrays */
  min_length?: number;
  /** Maximum length for strings/arrays */
  max_length?: number;
  /** Whether parameter contains sensitive data */
  sensitive: boolean;
  /** Pattern to detect sensitive values */
  sensitive_pattern?: string;
}

/**
 * Tool Metadata - Unified Standard.
 * Complete metadata definition for a tool.
 */
export interface ToolMetadata {
  // ========== Basic Information ==========
  /** Unique tool identifier */
  id: string;
  /** Tool name */
  name: string;
  /** Version number */
  version: string;
  /** Description */
  description: string;
  /** Category */
  category: ToolCategory;

  // ========== Author and Source ==========
  /** Author name */
  author?: string;
  /** Source: builtin/plugin/custom/mcp */
  source: string;
  /** Package name */
  package?: string;
  /** Homepage URL */
  homepage?: string;
  /** Repository URL */
  repository?: string;

  // ========== Parameter Definitions ==========
  /** List of parameters */
  parameters: ToolParameter[];
  /** Return type */
  return_type: string;
  /** Return description */
  return_description?: string;

  // ========== Authorization and Security ==========
  /** Authorization requirements */
  authorization: AuthorizationRequirement;

  // ========== Execution Configuration ==========
  /** Default timeout in seconds */
  timeout: number;
  /** Maximum concurrent executions */
  max_concurrent: number;
  /** Retry count on failure */
  retry_count: number;
  /** Retry delay in seconds */
  retry_delay: number;

  // ========== Dependencies and Conflicts ==========
  /** Required tools */
  dependencies: string[];
  /** Conflicting tools */
  conflicts: string[];

  // ========== Tags and Examples ==========
  /** Tags for categorization */
  tags: string[];
  /** Usage examples */
  examples: Record<string, unknown>[];

  // ========== Meta Information ==========
  /** Creation timestamp (ISO date string) */
  created_at: string;
  /** Last update timestamp (ISO date string) */
  updated_at: string;
  /** Whether tool is deprecated */
  deprecated: boolean;
  /** Deprecation message */
  deprecation_message?: string;

  // ========== Extension Fields ==========
  /** Additional metadata */
  metadata: Record<string, unknown>;
}

/**
 * OpenAI Function Calling specification.
 */
export interface OpenAIFunctionSpec {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: {
      type: 'object';
      properties: Record<string, unknown>;
      required: string[];
    };
  };
}

/**
 * Default authorization requirement values.
 */
export const defaultAuthorizationRequirement: AuthorizationRequirement = {
  requires_authorization: true,
  risk_level: RiskLevel.MEDIUM,
  risk_categories: [],
  sensitive_parameters: [],
  whitelist_rules: [],
  support_session_grant: true,
};

/**
 * Default tool parameter values.
 */
export const defaultToolParameter: Partial<ToolParameter> = {
  required: true,
  sensitive: false,
};
