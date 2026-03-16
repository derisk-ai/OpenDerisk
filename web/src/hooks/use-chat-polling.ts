import { useState, useEffect, useRef, useCallback } from 'react';
import { queryChatStatus, ChatQueryResponse } from '@/client/api/chat';

type ConversationState = 'RUNNING' | 'COMPLETE' | 'FAILED' | 'WAITING' | 'UNKNOWN';

interface UseChatPollingOptions {
  convId: string | null;
  enabled?: boolean;
  interval?: number;
  onComplete?: (response: ChatQueryResponse) => void;
  onError?: (error: Error) => void;
}

interface UseChatPollingReturn {
  state: ConversationState;
  isPolling: boolean;
  data: ChatQueryResponse | null;
  startPolling: () => void;
  stopPolling: () => void;
  checkStatus: () => Promise<ChatQueryResponse | null>;
}

export function useChatPolling({
  convId,
  enabled = true,
  interval = 2000,
  onComplete,
  onError,
}: UseChatPollingOptions): UseChatPollingReturn {
  const [state, setState] = useState<ConversationState>('UNKNOWN');
  const [isPolling, setIsPolling] = useState(false);
  const [data, setData] = useState<ChatQueryResponse | null>(null);
  
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);

  const checkStatus = useCallback(async (): Promise<ChatQueryResponse | null> => {
    if (!convId) return null;
    
    try {
      const response = await queryChatStatus(convId);
      const result = response.data;
      
      if (mountedRef.current) {
        setData(result);
        setState(result.state as ConversationState);
      }
      
      return result;
    } catch (error) {
      if (mountedRef.current) {
        setState('UNKNOWN');
      }
      onError?.(error as Error);
      return null;
    }
  }, [convId, onError]);

  const startPolling = useCallback(() => {
    if (!convId || !enabled) return;
    
    setIsPolling(true);
    
    // 立即检查一次
    checkStatus().then(result => {
      if (result && result.state !== 'RUNNING') {
        // 如果不是运行中，不开始轮询
        setIsPolling(false);
        return;
      }
      
      // 开始轮询
      intervalRef.current = setInterval(async () => {
        const status = await checkStatus();
        
        if (status && status.state !== 'RUNNING') {
          // 对话完成或失败，停止轮询
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          setIsPolling(false);
          onComplete?.(status);
        }
      }, interval);
    });
  }, [convId, enabled, checkStatus, interval, onComplete]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  // 组件卸载时清理
  useEffect(() => {
    mountedRef.current = true;
    
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  // convId 变化时，检查状态
  useEffect(() => {
    if (convId && enabled) {
      checkStatus().then(result => {
        if (result?.state === 'RUNNING') {
          startPolling();
        }
      });
    }
    
    return () => {
      stopPolling();
    };
  }, [convId, enabled, checkStatus, startPolling, stopPolling]);

  return {
    state,
    isPolling,
    data,
    startPolling,
    stopPolling,
    checkStatus,
  };
}

export default useChatPolling;