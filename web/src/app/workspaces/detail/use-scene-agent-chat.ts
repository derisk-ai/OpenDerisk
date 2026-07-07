"use client";

import { useCallback, useRef, useState } from 'react';
import useChat from '@/hooks/use-chat';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep } from './agent-types';
import { parseAgentSteps } from './parse-agent-steps';

interface UseSceneAgentChatOptions {
  convUid?: string;
  appCode?: string;
  workspaceId?: number | string;
  taskId?: number | string;
  onWorkspaceEvent?: (event: WorkspaceEvent) => void;
}

interface UseSceneAgentChatResult {
  steps: AgentStep[];
  loading: boolean;
  error: string | null;
  send: (text: string) => void;
  abort: () => void;
  clearSteps: () => void;
}

const MAX_RECENT_STEPS = 8;

export function useSceneAgentChat({
  convUid,
  appCode,
  workspaceId,
  taskId,
  onWorkspaceEvent,
}: UseSceneAgentChatOptions): UseSceneAgentChatResult {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { chat } = useChat({ app_code: appCode || '' });

  const appendStep = useCallback((step: AgentStep) => {
    setSteps((prev) => {
      const next = [...prev, step];
      if (next.length > MAX_RECENT_STEPS) next.shift();
      return next;
    });
  }, []);

  const clearSteps = useCallback(() => setSteps([]), []);

  const send = useCallback(
    (text: string) => {
      if (!convUid || !text.trim()) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setError(null);

      chat({
        ctrl,
        data: {
          conv_uid: convUid,
          user_input: text.trim(),
          workspace_id: workspaceId,
          task_id: taskId,
        },
        onMessage: (message: string) => {
          if (message && typeof message === 'object') {
            const step = parseAgentSteps(message);
            if (step) appendStep(step);
          }
        },
        onDone: () => setLoading(false),
        onClose: () => setLoading(false),
        onError: (content: string) => {
          setError(content || 'Agent error');
          setLoading(false);
        },
        onWorkspaceEvent,
      });
    },
    [convUid, workspaceId, taskId, chat, appendStep, onWorkspaceEvent],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, []);

  return { steps, loading, error, send, abort, clearSteps };
}
