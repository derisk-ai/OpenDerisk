'use client';

import { useCallback, useRef, useState } from 'react';
import useChat from '@/hooks/use-chat';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep } from './agent-types';
import { parseAgentSteps } from './parse-agent-steps';
import { parseWorkspaceView } from './parse-workspace-view';
import {
  buildSceneAgentSendData,
  type SceneAgentSendPayload,
} from './scene-agent-send-data';
import type { WorkspaceView } from './agent-workspace-types';

interface UseSceneAgentChatOptions {
  convUid?: string;
  appCode?: string;
  workspaceId?: number | string;
  taskId?: number | string;
  onWorkspaceEvent?: (event: WorkspaceEvent) => void;
}

interface UseSceneAgentChatResult {
  steps: AgentStep[];
  workspaceView: WorkspaceView;
  loading: boolean;
  error: string | null;
  lastInput: SceneAgentSendPayload | null;
  send: (payload: SceneAgentSendPayload) => void;
  abort: () => void;
  clearSteps: () => void;
  clearWorkspaceView: () => void;
}

// Re-export so callers can import the payload/data types from the hook module.
export type { SceneAgentSendPayload } from './scene-agent-send-data';

const EMPTY_WORKSPACE_VIEW: WorkspaceView = { planning: null, execution: [], summary: null };

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
  const [lastInput, setLastInput] = useState<SceneAgentSendPayload | null>(null);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>(EMPTY_WORKSPACE_VIEW);
  const abortRef = useRef<AbortController | null>(null);
  const { chat } = useChat({ app_code: appCode || '' });

  const appendStep = useCallback((step: AgentStep) => {
    setSteps((prev) => {
      const next = [...prev, step];
      if (next.length > MAX_RECENT_STEPS) next.shift();
      return next;
    });
  }, []);

  const clearSteps = useCallback(() => {
    setSteps([]);
    setWorkspaceView(EMPTY_WORKSPACE_VIEW);
  }, []);

  const clearWorkspaceView = useCallback(() => setWorkspaceView(EMPTY_WORKSPACE_VIEW), []);

  const send = useCallback(
    (payload: SceneAgentSendPayload) => {
      const { text } = payload;
      if (!convUid || !text.trim()) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setLastInput(payload);
      setError(null);

      const data = buildSceneAgentSendData(payload, { workspaceId, taskId }, convUid);

      chat({
        ctrl,
        data: {
          conv_uid: data.conv_uid,
          user_input: data.user_input,
          workspace_id: data.workspace_id,
          task_id: data.task_id,
          ...(data.model_name ? { model_name: data.model_name } : {}),
          ...(data.chat_in_params ? { chat_in_params: data.chat_in_params } : {}),
          team_mode: data.team_mode,
          app_config_code: data.app_config_code,
          agent_version: data.agent_version,
          ext_info: data.ext_info,
        },
        onMessage: (message: unknown) => {
          if (message && typeof message === 'object') {
            const step = parseAgentSteps(message);
            if (step) {
              appendStep(step);
              return;
            }
            // scene_agent_workspace 结构化 vis
            const mv = message as Record<string, unknown>;
            if (mv.render_name === 'scene_agent_workspace' || Array.isArray(mv.execution)) {
              setWorkspaceView((prev) => parseWorkspaceView(message, prev));
            }
          }
        },
        onDone: () => {
          setLoading(false);
          setLastInput(null);
        },
        onClose: () => {
          setLoading(false);
          setLastInput(null);
        },
        onError: (content: string) => {
          setError(content || 'Agent error');
          appendStep({
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
            type: 'unknown',
            title: 'Agent error',
            status: 'failed',
            timestamp: Date.now(),
            payload: { error: content || 'Agent error' },
          });
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

  return { steps, workspaceView, loading, error, lastInput, send, abort, clearSteps, clearWorkspaceView };
}