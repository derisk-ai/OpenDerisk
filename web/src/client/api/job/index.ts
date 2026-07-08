import { DELETE, GET, POST } from '../index';

// ---- Types ----

export interface JobAttempt {
  worker?: string;
  status: string;
  started_at?: string;
  finished_at?: string;
  error?: string;
}

export interface Job {
  id: string;
  job_type: string;
  space_slug?: string;
  payload: Record<string, any>;
  status: 'pending' | 'running' | 'done' | 'failed';
  priority: number;
  attempts: number;
  max_attempts: number;
  claimed_by?: string;
  claimed_at?: string;
  lease_until?: string;
  last_error?: string;
  result?: Record<string, any>;
  not_before?: string;
  required_worker?: string[];
  executed_by?: string;
  executed_at?: string;
  attempts_history?: JobAttempt[];
  gmt_created?: string;
  gmt_modified?: string;
}

export interface JobCreate {
  job_type: string;
  space_slug?: string;
  payload?: Record<string, any>;
  priority?: number;
  max_attempts?: number;
  not_before?: string;
  run_after_seconds?: number;
  required_worker?: string[];
}

export interface JobListResponse {
  items: Job[];
  total: number;
}

export interface JobStats {
  total: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_type_status: Record<string, Record<string, number>>;
  by_executor: Record<string, number>;
}

export interface WorkerInfo {
  worker_id: string;
  tags: string[];
  subscribe_types: string[];
  concurrency: number;
  running: boolean;
  in_flight: number;
}

export interface JobTypeParam {
  type: string;
  description?: string;
  default?: any;
  enum?: any[];
}

export interface JobType {
  job_type: string;
  description?: string;
  /** JSON Schema (draft 7) describing the payload fields. */
  params_schema?: {
    type?: string;
    properties?: Record<string, JobTypeParam>;
    required?: string[];
    $defs?: Record<string, any>;
  };
}

// ---- API ----

const API_PREFIX = '/api/v1/serve/job';

export const listJobs = (
  params: { job_type?: string; space_slug?: string; status?: string; limit?: number; offset?: number } = {},
) => {
  return GET<Record<string, any>, JobListResponse>(`${API_PREFIX}/jobs`, params as any);
};

export const getJob = (jobId: string) => {
  return GET<{}, Job>(`${API_PREFIX}/jobs/${jobId}`);
};

export const createJob = (data: JobCreate) => {
  return POST<JobCreate, Job>(`${API_PREFIX}/jobs`, data);
};

export const retryJob = (jobId: string) => {
  return POST<{}, { id: string; status: string }>(`${API_PREFIX}/jobs/${jobId}/retry`);
};

export const cancelJob = (jobId: string) => {
  return POST<{}, { id: string; status: string }>(`${API_PREFIX}/jobs/${jobId}/cancel`);
};

export const deleteJob = (jobId: string) => {
  return DELETE<{}, { ok: boolean }>(`${API_PREFIX}/jobs/${jobId}`);
};

export const getJobStats = () => {
  return GET<{}, JobStats>(`${API_PREFIX}/jobs/stats`);
};

export const getWorkers = () => {
  return GET<{}, WorkerInfo>(`${API_PREFIX}/jobs/workers`);
};

export const getJobTypes = () => {
  return GET<{}, JobType[]>(`${API_PREFIX}/jobs/types`);
};