/**
 * Interaction Type Definitions - Unified Tool Authorization System
 *
 * TypeScript equivalents of the Python models in derisk/core/interaction/protocol.py
 */

// ========== Enums ==========

/**
 * Types of user interactions.
 */
export const InteractionType = {
  // User input types
  TEXT_INPUT: 'text_input',
  FILE_UPLOAD: 'file_upload',
  // Selection types
  SINGLE_SELECT: 'single_select',
  MULTI_SELECT: 'multi_select',
  // Confirmation types
  CONFIRMATION: 'confirmation',
  AUTHORIZATION: 'authorization',
  PLAN_SELECTION: 'plan_selection',
  // Notification types
  INFO: 'info',
  WARNING: 'warning',
  ERROR: 'error',
  SUCCESS: 'success',
  PROGRESS: 'progress',
  // Task management types
  TODO_CREATE: 'todo_create',
  TODO_UPDATE: 'todo_update',
} as const;
export type InteractionType =
  (typeof InteractionType)[keyof typeof InteractionType];

/**
 * Priority levels for interactions.
 */
export const InteractionPriority = {
  /** Can be deferred */
  LOW: 'low',
  /** Normal processing */
  NORMAL: 'normal',
  /** Should be handled promptly */
  HIGH: 'high',
  /** Must be handled immediately */
  CRITICAL: 'critical',
} as const;
export type InteractionPriority =
  (typeof InteractionPriority)[keyof typeof InteractionPriority];

/**
 * Status of an interaction request.
 */
export const InteractionStatus = {
  /** Waiting for response */
  PENDING: 'pending',
  /** User has responded */
  RESPONDED: 'responded',
  /** Request has expired */
  EXPIRED: 'expired',
  /** Request was cancelled */
  CANCELLED: 'cancelled',
  /** User skipped the interaction */
  SKIPPED: 'skipped',
  /** User deferred the interaction */
  DEFERRED: 'deferred',
} as const;
export type InteractionStatus =
  (typeof InteractionStatus)[keyof typeof InteractionStatus];

/**
 * Grant scope for authorization.
 */
export const GrantScope = {
  /** Allow this operation once */
  ONCE: 'once',
  /** Allow this tool for the entire session */
  SESSION: 'session',
  /** Always allow this tool */
  ALWAYS: 'always',
} as const;
export type GrantScope = (typeof GrantScope)[keyof typeof GrantScope];

// ========== Interfaces ==========

/**
 * Option for selection-type interactions.
 */
export interface InteractionOption {
  /** Display text */
  label: string;
  /** Value returned on selection */
  value: string;
  /** Extended description */
  description?: string;
  /** Icon identifier */
  icon?: string;
  /** Whether option is disabled */
  disabled: boolean;
  /** Whether this is the default option */
  default: boolean;
  /** Additional metadata */
  metadata: Record<string, unknown>;
}

/**
 * Authorization context for AUTHORIZATION type interactions.
 */
export interface AuthorizationContext {
  /** Tool name */
  tool_name: string;
  /** Tool arguments */
  arguments: Record<string, unknown>;
  /** Risk level */
  risk_level: string;
  /** Risk factors */
  risk_factors: string[];
}

/**
 * Interaction request sent to the user.
 */
export interface InteractionRequest {
  // Basic information
  /** Unique request identifier */
  request_id: string;
  /** Interaction type */
  type: InteractionType;
  /** Priority level */
  priority: InteractionPriority;

  // Content
  /** Dialog title */
  title?: string;
  /** Main message */
  message: string;
  /** Options for selection */
  options: InteractionOption[];

  // Default values
  /** Default single selection */
  default_value?: string;
  /** Default multiple selections */
  default_values: string[];

  // Control flags
  /** Timeout in seconds */
  timeout?: number;
  /** Allow cancellation */
  allow_cancel: boolean;
  /** Allow skipping */
  allow_skip: boolean;
  /** Allow deferring */
  allow_defer: boolean;

  // Session context
  /** Session ID */
  session_id?: string;
  /** Agent name */
  agent_name?: string;
  /** Step index */
  step_index?: number;
  /** Execution ID */
  execution_id?: string;

  // Authorization context (for AUTHORIZATION type)
  /** Authorization context */
  authorization_context?: AuthorizationContext;
  /** Allow "always allow" option */
  allow_session_grant: boolean;

  // File upload settings (for FILE_UPLOAD type)
  /** Accepted file types */
  accepted_file_types: string[];
  /** Max file size in bytes */
  max_file_size?: number;
  /** Allow multiple file uploads */
  allow_multiple_files: boolean;

  // Progress settings (for PROGRESS type)
  /** Progress value (0.0 to 1.0) */
  progress_value?: number;
  /** Progress message */
  progress_message?: string;

  // Metadata
  /** Additional metadata */
  metadata: Record<string, unknown>;
  /** Creation timestamp (ISO date string) */
  created_at: string;
}

/**
 * User response to an interaction request.
 */
export interface InteractionResponse {
  // Reference
  /** Request ID this response is for */
  request_id: string;
  /** Session ID */
  session_id?: string;

  // Response content
  /** Single selection choice */
  choice?: string;
  /** Multiple selection choices */
  choices: string[];
  /** Text input value */
  input_value?: string;
  /** Uploaded file IDs */
  file_ids: string[];

  // Status
  /** Response status */
  status: InteractionStatus;

  // User message
  /** Optional explanation from user */
  user_message?: string;
  /** Reason for cancellation */
  cancel_reason?: string;

  // Authorization grant scope
  /** Grant scope: once, session, or always */
  grant_scope?: GrantScope;
  /** Grant duration in seconds */
  grant_duration?: number;

  // Metadata
  /** Additional metadata */
  metadata: Record<string, unknown>;
  /** Response timestamp (ISO date string) */
  timestamp: string;
}

// ========== Helper Types ==========

/**
 * Notification types subset.
 */
export type NotificationType =
  | typeof InteractionType.INFO
  | typeof InteractionType.WARNING
  | typeof InteractionType.ERROR
  | typeof InteractionType.SUCCESS;

/**
 * Input types subset.
 */
export type InputInteractionType =
  | typeof InteractionType.TEXT_INPUT
  | typeof InteractionType.FILE_UPLOAD;

/**
 * Selection types subset.
 */
export type SelectionInteractionType =
  | typeof InteractionType.SINGLE_SELECT
  | typeof InteractionType.MULTI_SELECT;

/**
 * Confirmation types subset.
 */
export type ConfirmationInteractionType =
  | typeof InteractionType.CONFIRMATION
  | typeof InteractionType.AUTHORIZATION
  | typeof InteractionType.PLAN_SELECTION;

// ========== Factory Functions Types ==========

/**
 * Parameters for creating an authorization request.
 */
export interface CreateAuthorizationRequestParams {
  tool_name: string;
  tool_description: string;
  arguments: Record<string, unknown>;
  risk_level?: string;
  risk_factors?: string[];
  session_id?: string;
  agent_name?: string;
  allow_session_grant?: boolean;
  timeout?: number;
}

/**
 * Parameters for creating a text input request.
 */
export interface CreateTextInputRequestParams {
  message: string;
  title?: string;
  default_value?: string;
  placeholder?: string;
  session_id?: string;
  agent_name?: string;
  required?: boolean;
  timeout?: number;
}

/**
 * Parameters for creating a confirmation request.
 */
export interface CreateConfirmationRequestParams {
  message: string;
  title?: string;
  confirm_label?: string;
  cancel_label?: string;
  default_confirm?: boolean;
  session_id?: string;
  agent_name?: string;
  timeout?: number;
}

/**
 * Parameters for creating a selection request.
 */
export interface CreateSelectionRequestParams {
  message: string;
  options: Array<string | Partial<InteractionOption> | InteractionOption>;
  title?: string;
  multiple?: boolean;
  default_value?: string;
  default_values?: string[];
  session_id?: string;
  agent_name?: string;
  timeout?: number;
}

/**
 * Parameters for creating a notification.
 */
export interface CreateNotificationParams {
  message: string;
  type?: NotificationType;
  title?: string;
  session_id?: string;
  agent_name?: string;
}

/**
 * Parameters for creating a progress update.
 */
export interface CreateProgressUpdateParams {
  message: string;
  progress: number;
  title?: string;
  session_id?: string;
  agent_name?: string;
}
