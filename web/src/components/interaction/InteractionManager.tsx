/**
 * InteractionManager - React Context and Hook for Managing User Interactions
 *
 * Provides global state management for the Unified Tool Authorization System.
 * Handles interaction requests, responses, and connection state.
 */

'use client';

import React, {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useState,
  useMemo,
  useRef,
} from 'react';
import {
  InteractionService,
  getInteractionService,
  type ConnectionState,
  type InteractionServiceConfig,
} from '@/services/interactionService';
import type {
  InteractionRequest,
  InteractionResponse,
  GrantScope,
} from '@/types/interaction';
import { InteractionType } from '@/types/interaction';

// ========== Context Types ==========

/**
 * State for the interaction manager.
 */
export interface InteractionState {
  /** Current connection state */
  connectionState: ConnectionState;
  /** All pending interaction requests */
  pendingRequests: InteractionRequest[];
  /** Currently active request (being displayed) */
  activeRequest: InteractionRequest | null;
  /** Whether the interaction dialog is open */
  isDialogOpen: boolean;
  /** Error message if any */
  error: string | null;
}

/**
 * Actions for the interaction manager.
 */
export interface InteractionActions {
  /** Connect to the interaction gateway */
  connect: () => Promise<void>;
  /** Disconnect from the interaction gateway */
  disconnect: () => void;
  /** Set session ID and reconnect */
  setSessionId: (sessionId: string) => Promise<void>;
  /** Open the dialog for a specific request */
  showRequest: (requestId: string) => void;
  /** Close the current dialog */
  hideDialog: () => void;
  /** Submit a response to the active request */
  submitResponse: (response: Partial<InteractionResponse>) => Promise<boolean>;
  /** Quick confirm for confirmation-type requests */
  confirm: (confirmed: boolean, grantScope?: GrantScope) => Promise<boolean>;
  /** Quick authorize for authorization-type requests */
  authorize: (allow: boolean, grantScope?: GrantScope) => Promise<boolean>;
  /** Submit text input */
  submitTextInput: (value: string) => Promise<boolean>;
  /** Submit selection */
  submitSelection: (choices: string | string[]) => Promise<boolean>;
  /** Cancel the active request */
  cancelRequest: (reason?: string) => Promise<boolean>;
  /** Skip the active request */
  skipRequest: () => Promise<boolean>;
  /** Defer the active request */
  deferRequest: () => Promise<boolean>;
  /** Refresh pending requests from server */
  refreshRequests: () => Promise<void>;
  /** Clear error */
  clearError: () => void;
}

/**
 * Full interaction context value.
 */
export interface InteractionContextValue extends InteractionState, InteractionActions {}

// ========== Context ==========

const defaultState: InteractionState = {
  connectionState: 'disconnected',
  pendingRequests: [],
  activeRequest: null,
  isDialogOpen: false,
  error: null,
};

const defaultActions: InteractionActions = {
  connect: async () => {},
  disconnect: () => {},
  setSessionId: async () => {},
  showRequest: () => {},
  hideDialog: () => {},
  submitResponse: async () => false,
  confirm: async () => false,
  authorize: async () => false,
  submitTextInput: async () => false,
  submitSelection: async () => false,
  cancelRequest: async () => false,
  skipRequest: async () => false,
  deferRequest: async () => false,
  refreshRequests: async () => {},
  clearError: () => {},
};

export const InteractionContext = createContext<InteractionContextValue>({
  ...defaultState,
  ...defaultActions,
});

// ========== Provider Props ==========

export interface InteractionProviderProps {
  children: React.ReactNode;
  /** Initial session ID */
  sessionId?: string;
  /** Auto-connect on mount */
  autoConnect?: boolean;
  /** Custom service configuration */
  config?: InteractionServiceConfig;
}

// ========== Provider Component ==========

export function InteractionProvider({
  children,
  sessionId,
  autoConnect = true,
  config,
}: InteractionProviderProps) {
  // State
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [pendingRequests, setPendingRequests] = useState<InteractionRequest[]>([]);
  const [activeRequest, setActiveRequest] = useState<InteractionRequest | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Service ref
  const serviceRef = useRef<InteractionService | null>(null);

  // Initialize service
  useEffect(() => {
    const serviceConfig: InteractionServiceConfig = {
      ...config,
      sessionId,
    };

    const service = getInteractionService(serviceConfig, {
      onRequest: (request) => {
        setPendingRequests((prev) => {
          const exists = prev.find((r) => r.request_id === request.request_id);
          if (exists) {
            return prev.map((r) =>
              r.request_id === request.request_id ? request : r
            );
          }
          return [...prev, request];
        });

        // Auto-show high priority requests
        if (
          request.priority === 'critical' ||
          request.priority === 'high' ||
          request.type === InteractionType.AUTHORIZATION
        ) {
          setActiveRequest(request);
          setIsDialogOpen(true);
        }
      },
      onRequestUpdate: (requestId, update) => {
        setPendingRequests((prev) =>
          prev.map((r) =>
            r.request_id === requestId ? { ...r, ...update } : r
          )
        );
        // Update active request if it's the one being updated
        setActiveRequest((prev) =>
          prev?.request_id === requestId ? { ...prev, ...update } : prev
        );
      },
      onConnectionStateChange: setConnectionState,
      onError: (err) => setError(err.message),
    });

    serviceRef.current = service;

    // Auto-connect if enabled
    if (autoConnect) {
      service.connect().catch((err) => {
        setError(err.message);
      });
    }

    return () => {
      // Don't disconnect on unmount - service is singleton
    };
  }, [sessionId, autoConnect, config]);

  // ========== Actions ==========

  const connect = useCallback(async () => {
    const service = serviceRef.current;
    if (service) {
      try {
        await service.connect();
      } catch (err) {
        setError((err as Error).message);
      }
    }
  }, []);

  const disconnect = useCallback(() => {
    serviceRef.current?.disconnect();
  }, []);

  const setSessionIdAction = useCallback(async (newSessionId: string) => {
    const service = serviceRef.current;
    if (service) {
      try {
        await service.setSessionId(newSessionId);
        setPendingRequests(service.getPendingRequests());
      } catch (err) {
        setError((err as Error).message);
      }
    }
  }, []);

  const showRequest = useCallback((requestId: string) => {
    const request = pendingRequests.find((r) => r.request_id === requestId);
    if (request) {
      setActiveRequest(request);
      setIsDialogOpen(true);
    }
  }, [pendingRequests]);

  const hideDialog = useCallback(() => {
    setIsDialogOpen(false);
    // Don't clear activeRequest immediately for smooth animation
    setTimeout(() => {
      setActiveRequest(null);
    }, 300);
  }, []);

  const submitResponse = useCallback(async (response: Partial<InteractionResponse>): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const fullResponse: Partial<InteractionResponse> = {
      ...response,
      request_id: activeRequest.request_id,
      session_id: activeRequest.session_id,
    };

    const success = await service.submitResponse(fullResponse);
    if (success) {
      // Remove from pending
      setPendingRequests((prev) =>
        prev.filter((r) => r.request_id !== activeRequest.request_id)
      );
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const confirm = useCallback(async (confirmed: boolean, grantScope?: GrantScope): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const success = await service.confirm(activeRequest.request_id, confirmed, grantScope);
    if (success) {
      setPendingRequests((prev) =>
        prev.filter((r) => r.request_id !== activeRequest.request_id)
      );
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const authorize = useCallback(async (allow: boolean, grantScope?: GrantScope): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const success = await service.authorizeToolExecution(
      activeRequest.request_id,
      allow,
      grantScope
    );
    if (success) {
      setPendingRequests((prev) =>
        prev.filter((r) => r.request_id !== activeRequest.request_id)
      );
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const submitTextInput = useCallback(async (value: string): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const success = await service.submitTextInput(activeRequest.request_id, value);
    if (success) {
      setPendingRequests((prev) =>
        prev.filter((r) => r.request_id !== activeRequest.request_id)
      );
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const submitSelection = useCallback(async (choices: string | string[]): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const success = await service.submitSelection(activeRequest.request_id, choices);
    if (success) {
      setPendingRequests((prev) =>
        prev.filter((r) => r.request_id !== activeRequest.request_id)
      );
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const cancelRequest = useCallback(async (reason?: string): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const success = await service.cancelRequest(activeRequest.request_id, reason);
    if (success) {
      setPendingRequests((prev) =>
        prev.filter((r) => r.request_id !== activeRequest.request_id)
      );
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const skipRequest = useCallback(async (): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const success = await service.skipRequest(activeRequest.request_id);
    if (success) {
      setPendingRequests((prev) =>
        prev.filter((r) => r.request_id !== activeRequest.request_id)
      );
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const deferRequest = useCallback(async (): Promise<boolean> => {
    const service = serviceRef.current;
    if (!service || !activeRequest) return false;

    const success = await service.deferRequest(activeRequest.request_id);
    if (success) {
      hideDialog();
    }
    return success;
  }, [activeRequest, hideDialog]);

  const refreshRequests = useCallback(async () => {
    const service = serviceRef.current;
    if (service) {
      const requests = await service.fetchPendingRequests();
      setPendingRequests(requests);
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // ========== Context Value ==========

  const value = useMemo<InteractionContextValue>(() => ({
    // State
    connectionState,
    pendingRequests,
    activeRequest,
    isDialogOpen,
    error,
    // Actions
    connect,
    disconnect,
    setSessionId: setSessionIdAction,
    showRequest,
    hideDialog,
    submitResponse,
    confirm,
    authorize,
    submitTextInput,
    submitSelection,
    cancelRequest,
    skipRequest,
    deferRequest,
    refreshRequests,
    clearError,
  }), [
    connectionState,
    pendingRequests,
    activeRequest,
    isDialogOpen,
    error,
    connect,
    disconnect,
    setSessionIdAction,
    showRequest,
    hideDialog,
    submitResponse,
    confirm,
    authorize,
    submitTextInput,
    submitSelection,
    cancelRequest,
    skipRequest,
    deferRequest,
    refreshRequests,
    clearError,
  ]);

  return (
    <InteractionContext.Provider value={value}>
      {children}
    </InteractionContext.Provider>
  );
}

// ========== Hook ==========

/**
 * Hook to access interaction context.
 * Must be used within InteractionProvider.
 */
export function useInteraction(): InteractionContextValue {
  const context = useContext(InteractionContext);
  if (!context) {
    throw new Error('useInteraction must be used within an InteractionProvider');
  }
  return context;
}

/**
 * Hook for pending requests with filtering.
 */
export function usePendingRequests(filter?: {
  type?: string;
  priority?: string;
  sessionId?: string;
}): InteractionRequest[] {
  const { pendingRequests } = useInteraction();

  return useMemo(() => {
    if (!filter) return pendingRequests;

    return pendingRequests.filter((req) => {
      if (filter.type && req.type !== filter.type) return false;
      if (filter.priority && req.priority !== filter.priority) return false;
      if (filter.sessionId && req.session_id !== filter.sessionId) return false;
      return true;
    });
  }, [pendingRequests, filter]);
}

/**
 * Hook for authorization requests specifically.
 */
export function useAuthorizationRequests(): InteractionRequest[] {
  return usePendingRequests({ type: InteractionType.AUTHORIZATION });
}

/**
 * Hook for connection state.
 */
export function useInteractionConnection(): {
  state: ConnectionState;
  isConnected: boolean;
  connect: () => Promise<void>;
  disconnect: () => void;
} {
  const { connectionState, connect, disconnect } = useInteraction();

  return {
    state: connectionState,
    isConnected: connectionState === 'connected',
    connect,
    disconnect,
  };
}

export default InteractionProvider;
