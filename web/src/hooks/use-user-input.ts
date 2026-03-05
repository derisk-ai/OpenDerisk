import { useState, useCallback, useRef, useEffect } from 'react';
import { message } from 'antd';

export interface UserInputItem {
  content: string;
  input_type: string;
  metadata?: Record<string, any>;
}

export interface UserInputQueueState {
  hasPendingInput: boolean;
  queueLength: number;
  executionNode?: string;
  isLocal?: boolean;
}

export interface ExecutionNodeInfo {
  session_id: string;
  execution_node: string | null;
  is_local: boolean;
  current_node: string;
}

export function useUserInput(sessionId: string | undefined) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [queueState, setQueueState] = useState<UserInputQueueState>({
    hasPendingInput: false,
    queueLength: 0,
  });
  const pendingInputsRef = useRef<UserInputItem[]>([]);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const getBaseUrl = useCallback(() => {
    return process.env.NEXT_PUBLIC_API_BASE_URL ?? '';
  }, []);

  const submitUserInput = useCallback(async (
    content: string,
    inputType: string = 'text',
    metadata?: Record<string, any>
  ): Promise<boolean> => {
    if (!content.trim()) {
      return false;
    }

    if (!sessionId) {
      message.warning('Session not ready');
      return false;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch(
        `${getBaseUrl()}/api/v2/input/submit`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            content,
            input_type: inputType,
            metadata,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`);
      }

      const result = await response.json();

      if (result.success) {
        setQueueState(prev => ({
          ...prev,
          hasPendingInput: true,
          queueLength: result.queue_length,
          executionNode: result.execution_node,
        }));
        
        pendingInputsRef.current.push({ content, input_type: inputType, metadata });
        
        return true;
      } else {
        message.warning(result.message || 'No active execution');
        return false;
      }
    } catch (error) {
      console.error('Failed to submit user input:', error);
      message.error('Failed to submit input');
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }, [sessionId, getBaseUrl]);

  const getQueueStatus = useCallback(async () => {
    if (!sessionId) return;

    try {
      const response = await fetch(
        `${getBaseUrl()}/api/v2/input/queue/${sessionId}`
      );

      if (response.ok) {
        const result = await response.json();
        setQueueState({
          hasPendingInput: result.has_pending_input,
          queueLength: result.pending_count || (result.has_pending_input ? 1 : 0),
          executionNode: result.execution_node,
          isLocal: result.is_local,
        });
      }
    } catch (error) {
      console.error('Failed to get queue status:', error);
    }
  }, [sessionId, getBaseUrl]);

  const getExecutionNode = useCallback(async (): Promise<ExecutionNodeInfo | null> => {
    if (!sessionId) return null;

    try {
      const response = await fetch(
        `${getBaseUrl()}/api/v2/execution/node/${sessionId}`
      );

      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to get execution node:', error);
    }
    return null;
  }, [sessionId, getBaseUrl]);

  const clearQueue = useCallback(async () => {
    if (!sessionId) return;

    try {
      await fetch(
        `${getBaseUrl()}/api/v2/input/queue/${sessionId}`,
        { method: 'DELETE' }
      );

      setQueueState({
        hasPendingInput: false,
        queueLength: 0,
      });
      
      pendingInputsRef.current = [];
    } catch (error) {
      console.error('Failed to clear queue:', error);
    }
  }, [sessionId, getBaseUrl]);

  const getPendingInputs = useCallback(() => {
    return [...pendingInputsRef.current];
  }, []);

  const consumePendingInputs = useCallback(() => {
    const inputs = [...pendingInputsRef.current];
    pendingInputsRef.current = [];
    setQueueState(prev => ({
      ...prev,
      hasPendingInput: false,
      queueLength: 0,
    }));
    return inputs;
  }, []);

  const startPolling = useCallback((interval: number = 2000) => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }
    
    getQueueStatus();
    pollIntervalRef.current = setInterval(getQueueStatus, interval);
  }, [getQueueStatus]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  return {
    submitUserInput,
    getQueueStatus,
    clearQueue,
    getPendingInputs,
    consumePendingInputs,
    getExecutionNode,
    startPolling,
    stopPolling,
    isSubmitting,
    queueState,
    hasPendingInput: queueState.hasPendingInput,
    queueLength: queueState.queueLength,
    executionNode: queueState.executionNode,
    isLocal: queueState.isLocal,
  };
}

export default useUserInput;