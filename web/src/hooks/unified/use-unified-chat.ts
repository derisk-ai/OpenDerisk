/**
 * 统一聊天Hook
 * 
 * 提供统一的聊天接口，自动适配V1/V2 Agent
 */

import { useCallback, useState, useEffect } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { getUnifiedAppService, UnifiedAppConfig } from '@/services/unified/unified-app-service';
import { 
  getUnifiedSessionService, 
  UnifiedSession, 
  UnifiedMessage 
} from '@/services/unified/unified-session-service';

/**
 * 用户聊天内容
 */
export type UserChatContent = string | {
  content: Array<{
    type: 'text' | 'image_url' | 'video' | 'file_url';
    text?: string;
    image_url?: { url: string; fileName?: string };
    video?: string;
    file_url?: { url: string; fileName?: string };
  }>;
};

/**
 * 聊天选项
 */
export interface ChatOptions {
  model_name?: string;
  temperature?: number;
  max_new_tokens?: number;
  incremental?: boolean;
  vis_render?: string;
  [key: string]: any;
}

/**
 * 统一聊天配置
 */
export interface UnifiedChatConfig {
  appCode: string;
  agentVersion?: 'v1' | 'v2';
  onMessage?: (message: UnifiedMessage) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
}

/**
 * 统一聊天Hook
 */
export function useUnifiedChat(config: UnifiedChatConfig) {
  const { appCode, agentVersion = 'v2' } = config;
  
  const [session, setSession] = useState<UnifiedSession | null>(null);
  const [appConfig, setAppConfig] = useState<UnifiedAppConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [abortController, setAbortController] = useState<AbortController | null>(null);

  // 初始化应用配置和会话
  useEffect(() => {
    const initSession = async () => {
      try {
        const appService = getUnifiedAppService();
        const sessionService = getUnifiedSessionService();

        const app = await appService.loadAppConfig(appCode);
        setAppConfig(app);

        const sess = await sessionService.getOrCreateSession(
          appCode,
          app.agentVersion
        );
        setSession(sess);
      } catch (error) {
        console.error('[useUnifiedChat] 初始化失败:', error);
        config.onError?.(error as Error);
      }
    };

    if (appCode) {
      initSession();
    }
  }, [appCode]);

  /**
   * 发送消息
   */
  const sendMessage = useCallback(async (
    content: UserChatContent,
    options?: ChatOptions
  ) => {
    if (!session) {
      config.onError?.(new Error('会话未初始化'));
      return;
    }

    const ctrl = new AbortController();
    setAbortController(ctrl);
    setLoading(true);

    try {
      const endpoint = session.agentVersion === 'v2'
        ? '/api/unified/chat/stream'
        : '/api/chat/completions';

      const requestBody: any = {
        session_id: session.sessionId,
        conv_id: session.convId,
        app_code: appCode,
        user_input: content,
        agent_version: session.agentVersion,
        ...options
      };

      let accumulatedContent = '';

      await fetchEventSource(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: ctrl.signal,
        onmessage: (event) => {
          const message = _parseStreamMessage(event.data, session.agentVersion);
          
          if (session.agentVersion === 'v2') {
            if (message.metadata?.isFinal) {
              config.onMessage?.({
                id: `${Date.now()}`,
                role: 'assistant',
                content: accumulatedContent,
                timestamp: new Date(),
                metadata: message.metadata
              });
              accumulatedContent = '';
            } else {
              accumulatedContent += message.content;
              config.onMessage?.(message);
            }
          } else {
            if (options?.incremental) {
              accumulatedContent += message.content;
            } else {
              accumulatedContent = message.content;
            }
            
            config.onMessage?.({
              id: `${Date.now()}`,
              role: 'assistant',
              content: accumulatedContent,
              timestamp: new Date(),
              metadata: message.metadata
            });
          }
        },
        onerror: (error) => {
          console.error('[useUnifiedChat] 流式错误:', error);
          config.onError?.(error);
          throw error;
        },
        onclose: () => {
          setLoading(false);
          setAbortController(null);
          config.onClose?.();
        }
      });

      config.onDone?.();
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        console.error('[useUnifiedChat] 发送消息失败:', error);
        config.onError?.(error);
      }
    } finally {
      setLoading(false);
    }
  }, [session, appCode, config]);

  /**
   * 停止生成
   */
  const stopGeneration = useCallback(() => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
    }
  }, [abortController]);

  /**
   * 加载历史消息
   */
  const loadHistory = useCallback(async () => {
    if (!session) return [];
    return session.history;
  }, [session]);

  /**
   * 解析流式消息
   */
  const _parseStreamMessage = (data: string, version: 'v1' | 'v2'): UnifiedMessage => {
    try {
      if (version === 'v2') {
        const chunk = JSON.parse(data);
        return {
          id: `${Date.now()}_${Math.random()}`,
          role: 'assistant',
          content: chunk.content || '',
          timestamp: new Date(),
          metadata: {
            type: chunk.type,
            toolName: chunk.metadata?.tool_name,
            isFinal: chunk.is_final,
            agentVersion: 'v2'
          }
        };
      } else {
        return {
          id: `${Date.now()}_${Math.random()}`,
          role: 'assistant',
          content: data,
          timestamp: new Date(),
          metadata: {
            agentVersion: 'v1'
          }
        };
      }
    } catch (error) {
      return {
        id: `${Date.now()}_${Math.random()}`,
        role: 'assistant',
        content: data,
        timestamp: new Date(),
        metadata: {
          agentVersion: version
        }
      };
    }
  };

  return {
    session,
    appConfig,
    loading,
    sendMessage,
    stopGeneration,
    loadHistory
  };
}

export default useUnifiedChat;