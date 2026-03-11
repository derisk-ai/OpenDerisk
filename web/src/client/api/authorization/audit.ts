/**
 * Authorization Audit API Client
 * 
 * Provides API functions for authorization audit log management
 */

import { GET, DELETE } from '../index';

const AUDIT_BASE = '/api/authorization';

// ========== Types ==========

export interface AuthorizationAuditLog {
  id: number;
  session_id: string;
  user_id?: string;
  agent_name?: string;
  tool_name: string;
  arguments?: Record<string, any>;
  decision: string;
  action: string;
  reason?: string;
  risk_level?: string;
  risk_score?: number;
  risk_factors?: string[];
  cached: boolean;
  duration_ms: number;
  created_at: string;
}

export interface AuthorizationAuditStats {
  total_count: number;
  granted_count: number;
  denied_count: number;
  cached_count: number;
  confirmation_count: number;
  avg_risk_score: number;
  avg_duration_ms: number;
  high_risk_count: number;
  critical_risk_count: number;
}

export interface ToolUsageStats {
  tool_name: string;
  total: number;
  granted: number;
  denied: number;
  avg_risk_score: number;
}

export interface AuditLogListResponse {
  items: AuthorizationAuditLog[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuditLogResponse<T = any> {
  success: boolean;
  message?: string;
  data?: T;
}

export interface AuditLogQueryParams {
  session_id?: string;
  user_id?: string;
  agent_name?: string;
  tool_name?: string;
  decision?: string;
  risk_level?: string;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

// ========== API Functions ==========

/**
 * List authorization audit logs with filters
 */
export const listAuditLogs = (params: AuditLogQueryParams) => {
  const query = new URLSearchParams();
  
  if (params.session_id) query.set('session_id', params.session_id);
  if (params.user_id) query.set('user_id', params.user_id);
  if (params.agent_name) query.set('agent_name', params.agent_name);
  if (params.tool_name) query.set('tool_name', params.tool_name);
  if (params.decision) query.set('decision', params.decision);
  if (params.risk_level) query.set('risk_level', params.risk_level);
  if (params.start_time) query.set('start_time', params.start_time);
  if (params.end_time) query.set('end_time', params.end_time);
  if (params.page) query.set('page', String(params.page));
  if (params.page_size) query.set('page_size', String(params.page_size));
  
  return GET<null, AuditLogResponse<AuditLogListResponse>>(
    `${AUDIT_BASE}/logs?${query.toString()}`
  );
};

/**
 * Get a specific audit log by ID
 */
export const getAuditLog = (logId: number) => {
  return GET<null, AuditLogResponse<AuthorizationAuditLog>>(
    `${AUDIT_BASE}/logs/${logId}`
  );
};

/**
 * Get authorization audit statistics
 */
export const getAuditStats = (params?: {
  start_time?: string;
  end_time?: string;
}) => {
  const query = new URLSearchParams();
  
  if (params?.start_time) query.set('start_time', params.start_time);
  if (params?.end_time) query.set('end_time', params.end_time);
  
  const queryString = query.toString();
  const url = queryString ? `${AUDIT_BASE}/stats?${queryString}` : `${AUDIT_BASE}/stats`;
  
  return GET<null, AuditLogResponse<AuthorizationAuditStats>>(url);
};

/**
 * Get tool usage statistics
 */
export const getToolUsageStats = (params?: {
  start_time?: string;
  end_time?: string;
}) => {
  const query = new URLSearchParams();
  
  if (params?.start_time) query.set('start_time', params.start_time);
  if (params?.end_time) query.set('end_time', params.end_time);
  
  const queryString = query.toString();
  const url = queryString ? `${AUDIT_BASE}/tools/usage?${queryString}` : `${AUDIT_BASE}/tools/usage`;
  
  return GET<null, AuditLogResponse<ToolUsageStats[]>>(url);
};

/**
 * Cleanup old audit logs
 */
export const cleanupOldLogs = (days: number = 30) => {
  return DELETE<{ days: number }, AuditLogResponse<{ deleted_count: number; message: string }>>(
    `${AUDIT_BASE}/logs/cleanup?days=${days}`
  );
};

export default {
  listAuditLogs,
  getAuditLog,
  getAuditStats,
  getToolUsageStats,
  cleanupOldLogs,
};