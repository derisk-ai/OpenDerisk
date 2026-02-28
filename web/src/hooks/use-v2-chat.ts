/**
 * useV2Chat - Core_v2 Agent 聊天 Hook
 */
import { useState, useCallback, useRef } from 'react';
import { createV2Session, createV2ChatStream, closeV2Session } from '@/client/api/v2';
import type { V2Session, V2StreamChunk, CreateSessionParams } from '@/types/v2';

interface UseV2ChatOptions {
  agentName: string;
  onSessionCreated?: (session: V2Session) => void;
  onChunk?: (chunk: V2StreamChunk) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
}

interface V2ChatState {
  session: V2Session | null;
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    chunks: V2StreamChunk[];
    timestamp: number;
  }>;
  isStreaming: boolean;
  error: Error | null;
}

export function useV2Chat(options: UseV2ChatOptions) {
  const { agentName, onSessionCreated, onChunk, onError, onDone } = options;
  
  const [state, setState] = useState<V2ChatState>({
    session: null,
    messages: [],
    isStreaming: false,
    error: null,
  });
  
  const abortRef = useRef<(() => void) | null>(null);

  // 创建会话
  const createSession = useCallback(async (userId?: string) => {
    try {
      const session = await createV2Session({
        user_id: userId,
        agent_name: agentName,
      });
      
      setState((prev) => ({ ...prev, session }));
      onSessionCreated?.(session);
      return session;
    } catch (error) {
      const err = error as Error;
      setState((prev) => ({ ...prev, error: err }));
      onError?.(err);
      throw err;
    }
  }, [agentName, onSessionCreated, onError]);

  // 发送消息
  const sendMessage = useCallback(async (message: string) => {
    // 添加用户消息
    const userMsg = {
      role: 'user' as const,
      content: message,
      chunks: [],
      timestamp: Date.now(),
    };
    
    setState((prev) => ({
      ...prev,
      messages: [...prev.messages, userMsg],
      isStreaming: true,
      error: null,
    }));
    
    // 准备 assistant 消息
    const assistantMsg = {
      role: 'assistant' as const,
      content: '',
      chunks: [] as V2StreamChunk[],
      timestamp: Date.now(),
    };
    
    setState((prev) => ({
      ...prev,
      messages: [...prev.messages, assistantMsg],
    }));

    // 发起流式请求
    abortRef.current = createV2ChatStream(
      {
        message,
        session_id: state.session?.session_id,
        agent_name: agentName,
      },
      {
        onMessage: (chunk: V2StreamChunk) => {
          onChunk?.(chunk);
          
          setState((prev) => {
            const messages = [...prev.messages];
            const lastIdx = messages.length - 1;
            if (lastIdx >= 0 && messages[lastIdx].role === 'assistant') {
              const lastMsg = messages[lastIdx];
              messages[lastIdx] = {
                ...lastMsg,
                content: lastMsg.content + (chunk.type === 'response' ? chunk.content : ''),
                chunks: [...lastMsg.chunks, chunk],
              };
            }
            return { ...prev, messages };
          });
        },
        onError: (error) => {
          setState((prev) => ({ ...prev, error, isStreaming: false }));
          onError?.(error);
        },
        onDone: () => {
          setState((prev) => ({ ...prev, isStreaming: false }));
          onDone?.();
        },
      }
    );
  }, [agentName, state.session, onChunk, onError, onDone]);

  // 停止流
  const stopStream = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setState((prev) => ({ ...prev, isStreaming: false }));
  }, []);

  // 关闭会话
  const closeSession = useCallback(async () => {
    if (state.session) {
      await closeV2Session(state.session.session_id);
      setState((prev) => ({ ...prev, session: null, messages: [] }));
    }
  }, [state.session]);

  // 清空消息
  const clearMessages = useCallback(() => {
    setState((prev) => ({ ...prev, messages: [] }));
  }, []);

  return {
    session: state.session,
    messages: state.messages,
    isStreaming: state.isStreaming,
    error: state.error,
    createSession,
    sendMessage,
    stopStream,
    closeSession,
    clearMessages,
  };
}

export default useV2Chat;
