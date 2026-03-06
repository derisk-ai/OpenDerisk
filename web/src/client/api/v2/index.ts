/**
 * Core_v2 Agent API 客户端
 */
import { GET, POST, DELETE } from '../index';
import type {
  V2Session,
  V2RuntimeStatus,
  CreateSessionParams,
  ChatParams,
  V2AgentTemplate,
} from '@/types/v2';

const V2_BASE = '/api/v2';

// ========== Session API ==========

/** 创建会话 */
export const createV2Session = (data: CreateSessionParams) => {
  return POST<CreateSessionParams, V2Session>(`${V2_BASE}/session`, data);
};

/** 获取会话信息 */
export const getV2Session = (sessionId: string) => {
  return GET<null, V2Session>(`${V2_BASE}/session/${sessionId}`);
};

/** 关闭会话 */
export const closeV2Session = (sessionId: string) => {
  return DELETE<null, { status: string }>(`${V2_BASE}/session/${sessionId}`);
};

/** 获取运行时状态 */
export const getV2Status = () => {
  return GET<null, V2RuntimeStatus>(`${V2_BASE}/status`);
};

// ========== Agent API ==========

/** 获取可用 Agent 模板列表 */
export const getV2AgentTemplates = () => {
  return GET<null, V2AgentTemplate[]>(`${V2_BASE}/agents/templates`);
};

/** 获取 Agent 详情 */
export const getV2AgentInfo = (agentName: string) => {
  return GET<null, V2AgentTemplate>(`${V2_BASE}/agents/${agentName}`);
};

// ========== Chat Stream ==========

/** 创建聊天流式连接 */
export const createV2ChatStream = (
  params: ChatParams,
  callbacks: {
    onMessage: (chunk: any) => void;
    onError: (error: Error) => void;
    onDone: () => void;
  }
): { abort: () => void } => {
  const controller = new AbortController();
  
  fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}${V2_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        throw new Error('No reader available');
      }
      
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              callbacks.onMessage(data);
              if (data.is_final) {
                callbacks.onDone();
              }
            } catch (e) {
              console.error('Parse error:', e);
            }
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
  
  return {
    abort: () => controller.abort(),
  };
};

export type { V2Session, V2RuntimeStatus, CreateSessionParams, ChatParams, V2AgentTemplate };
