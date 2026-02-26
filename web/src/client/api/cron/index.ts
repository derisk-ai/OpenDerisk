import { DELETE, GET, PATCH, POST, PUT } from '../index';

// Types
export interface CronSchedule {
  kind: 'at' | 'every' | 'cron';
  at?: string;
  every_ms?: number;
  anchor_ms?: number;
  expr?: string;
  tz?: string;
}

export interface CronPayload {
  kind: 'agentTurn' | 'toolCall' | 'systemEvent';
  message?: string;
  agent_id?: string;
  tool_name?: string;
  tool_args?: Record<string, any>;
  text?: string;
  timeout_seconds?: number;
  session_mode?: 'isolated' | 'shared';
  conv_session_id?: string;
}

export interface CronJobState {
  next_run_at_ms?: number;
  running_at_ms?: number;
  last_run_at_ms?: number;
  last_status?: 'ok' | 'error' | 'skipped';
  last_error?: string;
  last_duration_ms?: number;
  consecutive_errors: number;
}

export interface CronJob {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  delete_after_run?: boolean;
  schedule: CronSchedule;
  payload: CronPayload;
  state: CronJobState;
  gmt_created?: string;
  gmt_modified?: string;
}

export interface CronJobCreate {
  id?: string;
  name: string;
  description?: string;
  enabled?: boolean;
  delete_after_run?: boolean;
  schedule: CronSchedule;
  payload: CronPayload;
}

export interface CronJobUpdate {
  name?: string;
  description?: string;
  enabled?: boolean;
  delete_after_run?: boolean;
  schedule?: CronSchedule;
  payload?: CronPayload;
}

export interface CronStatus {
  enabled: boolean;
  running: boolean;
  jobs: number;
  enabled_jobs: number;
  next_wake_at_ms?: number;
}

// API endpoints
const API_PREFIX = '/api/v1/serve/cron';

/**
 * Get scheduler status
 */
export const getCronStatus = () => {
  return GET<{}, CronStatus>(`${API_PREFIX}/status`);
};

/**
 * List all cron jobs
 */
export const getCronJobs = (includeDisabled = false) => {
  return GET<{ include_disabled: boolean }, CronJob[]>(`${API_PREFIX}/jobs`, {
    include_disabled: includeDisabled,
  });
};

/**
 * Get a specific cron job
 */
export const getCronJob = (jobId: string) => {
  return GET<{}, CronJob>(`${API_PREFIX}/jobs/${jobId}`);
};

/**
 * Create a new cron job
 */
export const createCronJob = (data: CronJobCreate) => {
  return POST<CronJobCreate, CronJob>(`${API_PREFIX}/jobs`, data);
};

/**
 * Update a cron job (partial)
 */
export const updateCronJob = (jobId: string, data: CronJobUpdate) => {
  return PATCH<CronJobUpdate, CronJob>(`${API_PREFIX}/jobs/${jobId}`, data);
};

/**
 * Replace a cron job completely
 */
export const replaceCronJob = (jobId: string, data: CronJobCreate) => {
  return PUT<CronJobCreate, CronJob>(`${API_PREFIX}/jobs/${jobId}`, data);
};

/**
 * Delete a cron job
 */
export const deleteCronJob = (jobId: string) => {
  return DELETE<{}, null>(`${API_PREFIX}/jobs/${jobId}`);
};

/**
 * Run a cron job immediately
 */
export const runCronJob = (jobId: string, force = false) => {
  return POST<{ force: boolean }, { triggered: boolean; job_id: string }>(
    `${API_PREFIX}/jobs/${jobId}/run?force=${force}`
  );
};

/**
 * Enable a cron job
 */
export const enableCronJob = (jobId: string) => {
  return POST<{}, { enabled: boolean; job_id: string }>(
    `${API_PREFIX}/jobs/${jobId}/enable`
  );
};

/**
 * Disable a cron job
 */
export const disableCronJob = (jobId: string) => {
  return POST<{}, { enabled: boolean; job_id: string }>(
    `${API_PREFIX}/jobs/${jobId}/disable`
  );
};