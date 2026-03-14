/**
 * Monitoring Dashboard API Client
 * 监控仪表盘 API 客户端
 */

import { GET, POST, ins } from './index';

// =============================================================================
// Types
// =============================================================================

export interface MonitoringStats {
  tasks: {
    total_created: number;
    total_completed: number;
    total_failed: number;
    active: number;
  };
  subagents: {
    total: number;
    running: number;
  };
  workers: {
    total: number;
    active: number;
    idle: number;
    busy: number;
  };
  alerts: {
    total: number;
    unresolved: number;
    critical: number;
    error: number;
    warning: number;
  };
  events: {
    total: number;
    subscribers: number;
  };
}

export interface TaskProgress {
  task_id: string;
  goal: string;
  status: 'created' | 'running' | 'completed' | 'failed';
  total_steps: number;
  current_step: number;
  progress_percent: number;
  total_subtasks: number;
  completed_subtasks: number;
  failed_subtasks: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  tokens_used: number;
  llm_calls: number;
  errors: string[];
}

export interface WorkerProgress {
  worker_id: string;
  status: 'idle' | 'busy' | 'stopping' | 'stopped' | 'error';
  pid: number | null;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  current_tasks: number;
  cpu_percent: number;
  memory_mb: number;
  started_at: string | null;
  last_heartbeat: string | null;
}

export interface HealthAlert {
  alert_id: string;
  alert_type: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
  message: string;
  timestamp: string;
  resolved: boolean;
  resolved_at: string | null;
}

export interface DashboardEvent {
  event_type: string;
  timestamp: string;
  task_id: string | null;
  agent_id: string | null;
  subagent_name: string | null;
  data: Record<string, any>;
}

export interface DashboardData {
  tasks: TaskProgress[];
  active_tasks: TaskProgress[];
  workers: WorkerProgress[];
  alerts: HealthAlert[];
  stats: MonitoringStats;
  timestamp: string;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * 获取监控统计信息
 */
export const getMonitoringStats = async () => {
  return GET<null, MonitoringStats>('/api/v1/monitoring/stats');
};

/**
 * 获取仪表盘完整数据
 */
export const getDashboardData = async () => {
  return GET<null, DashboardData>('/api/v1/monitoring/dashboard');
};

/**
 * 获取任务列表
 */
export const getMonitoringTasks = async (activeOnly: boolean = false) => {
  return GET<{ active_only: boolean }, TaskProgress[]>('/api/v1/monitoring/tasks', {
    active_only: activeOnly,
  });
};

/**
 * 获取单个任务详情
 */
export const getMonitoringTask = async (taskId: string) => {
  return GET<null, TaskProgress>(`/api/v1/monitoring/tasks/${taskId}`);
};

/**
 * 获取任务的子Agent
 */
export const getTaskSubagents = async (taskId: string) => {
  return GET<null, any[]>(`/api/v1/monitoring/tasks/${taskId}/subagents`);
};

/**
 * 获取Worker列表
 */
export const getMonitoringWorkers = async () => {
  return GET<null, WorkerProgress[]>('/api/v1/monitoring/workers');
};

/**
 * 获取告警列表
 */
export const getMonitoringAlerts = async (unresolvedOnly: boolean = false, severity?: string) => {
  return GET<{ unresolved_only: boolean; severity?: string }, HealthAlert[]>(
    '/api/v1/monitoring/alerts',
    { unresolved_only: unresolvedOnly, severity }
  );
};

/**
 * 解决告警
 */
export const resolveAlert = async (alertId: string) => {
  return POST<null, { success: boolean }>(`/api/v1/monitoring/alerts/${alertId}/resolve`);
};

/**
 * 获取事件历史
 */
export const getMonitoringEvents = async (eventType?: string, taskId?: string, limit: number = 100) => {
  return GET<{ event_type?: string; task_id?: string; limit: number }, DashboardEvent[]>(
    '/api/v1/monitoring/events',
    { event_type: eventType, task_id: taskId, limit }
  );
};

/**
 * 创建WebSocket连接
 */
export const createMonitoringWebSocket = (onMessage: (event: DashboardEvent) => void, onError?: (error: Event) => void): WebSocket => {
  const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = typeof window !== 'undefined' ? window.location.host : 'localhost:8888';
  const wsUrl = `${protocol}//${host}/api/v1/monitoring/ws`;

  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as DashboardEvent;
      onMessage(data);
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    onError?.(error);
  };

  return ws;
};