/**
 * V2 API 客户端
 * 
 * 完整的前端API封装
 */

import type { 
  V2Session, 
  V2StreamChunk, 
  CreateSessionParams, 
  ChatRequest,
  ProgressReport,
  ExecutionSnapshot,
  Checkpoint,
  Goal,
  InteractionRequest,
  InteractionResponse,
} from '@/types/v2';

const API_PREFIX = '/api/v2';

// ========== 基础请求封装 ==========

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// ========== 会话管理 ==========

export async function createV2Session(params: CreateSessionParams): Promise<V2Session> {
  return request<V2Session>('/session', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getV2Session(sessionId: string): Promise<V2Session | null> {
  return request<V2Session | null>(`/session/${sessionId}`);
}

export async function closeV2Session(sessionId: string): Promise<boolean> {
  const result = await request<{ success: boolean }>(`/session/${sessionId}`, {
    method: 'DELETE',
  });
  return result.success;
}

// ========== 聊天 ==========

interface StreamCallbacks {
  onMessage: (chunk: V2StreamChunk) => void;
  onError: (error: Error) => void;
  onDone: () => void;
}

export function createV2ChatStream(
  params: ChatRequest,
  callbacks: StreamCallbacks
): () => void {
  const controller = new AbortController();
  
  fetch(`${API_PREFIX}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n').filter(Boolean);

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          
          const jsonStr = line.slice(6); // 去掉 'data: ' 前缀
          try {
            const data = JSON.parse(jsonStr);
            
            if (data.vis === '[DONE]') {
              callbacks.onDone();
              return;
            }
            
            const chunk: V2StreamChunk = {
              type: 'response',
              content: data.vis || '',
              metadata: {},
              is_final: false,
            };
            callbacks.onMessage(chunk);
          } catch (e) {
            console.error('SSE parse error:', e, 'line:', line);
          }
        }
      }

      callbacks.onDone();
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        callbacks.onError(error);
      }
    });

  return () => controller.abort();
}

// ========== 进度追踪 ==========

export async function getProgress(executionId: string): Promise<ProgressReport> {
  return request<ProgressReport>(`/execution/${executionId}/progress`);
}

export async function pauseExecution(executionId: string): Promise<boolean> {
  const result = await request<{ success: boolean }>(`/execution/${executionId}/pause`, {
    method: 'POST',
  });
  return result.success;
}

export async function resumeExecution(executionId: string): Promise<boolean> {
  const result = await request<{ success: boolean }>(`/execution/${executionId}/resume`, {
    method: 'POST',
  });
  return result.success;
}

export async function cancelExecution(executionId: string): Promise<boolean> {
  const result = await request<{ success: boolean }>(`/execution/${executionId}/cancel`, {
    method: 'POST',
  });
  return result.success;
}

// ========== 检查点管理 ==========

export async function listCheckpoints(executionId: string): Promise<Checkpoint[]> {
  return request<Checkpoint[]>(`/execution/${executionId}/checkpoints`);
}

export async function restoreCheckpoint(checkpointId: string): Promise<string> {
  const result = await request<{ execution_id: string }>(`/checkpoint/${checkpointId}/restore`, {
    method: 'POST',
  });
  return result.execution_id;
}

// ========== 目标管理 ==========

export async function createGoal(
  executionId: string,
  params: { name: string; description: string; criteria?: any[] }
): Promise<Goal> {
  return request<Goal>(`/execution/${executionId}/goal`, {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function listGoals(executionId: string): Promise<Goal[]> {
  return request<Goal[]>(`/execution/${executionId}/goals`);
}

export async function completeGoal(executionId: string, goalId: string): Promise<boolean> {
  const result = await request<{ success: boolean }>(`/execution/${executionId}/goal/${goalId}/complete`, {
    method: 'POST',
  });
  return result.success;
}

// ========== 执行历史 ==========

export async function listExecutions(): Promise<ExecutionSnapshot[]> {
  return request<ExecutionSnapshot[]>('/executions');
}

export async function getExecution(executionId: string): Promise<ExecutionSnapshot> {
  return request<ExecutionSnapshot>(`/execution/${executionId}`);
}

export async function getExecutionStats(): Promise<any> {
  return request<any>('/stats');
}

// ========== 交互管理 ==========

export async function submitInteraction(
  requestId: string,
  response: Partial<InteractionResponse>
): Promise<boolean> {
  const result = await request<{ success: boolean }>(`/interaction/${requestId}/response`, {
    method: 'POST',
    body: JSON.stringify(response),
  });
  return result.success;
}

// ========== 配置管理 ==========

export async function getConfig(key: string): Promise<any> {
  return request<any>(`/config/${key}`);
}

export async function setConfig(key: string, value: any): Promise<boolean> {
  const result = await request<{ success: boolean }>('/config', {
    method: 'POST',
    body: JSON.stringify({ key, value }),
  });
  return result.success;
}

// ========== WebSocket 连接 ==========

export class V2WebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  constructor(
    private sessionId: string,
    private handlers: {
      onMessage: (data: any) => void;
      onError?: (error: Error) => void;
      onOpen?: () => void;
      onClose?: () => void;
    }
  ) {}

  connect() {
    const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/${this.sessionId}`;
    
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.handlers.onOpen?.();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handlers.onMessage(data);
      } catch (e) {
        console.error('WebSocket message parse error:', e);
      }
    };

    this.ws.onerror = (error) => {
      this.handlers.onError?.(new Error('WebSocket error'));
    };

    this.ws.onclose = () => {
      this.handlers.onClose?.();
      this.attemptReconnect();
    };
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts);
    }
  }

  send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  close() {
    this.ws?.close();
    this.ws = null;
  }
}